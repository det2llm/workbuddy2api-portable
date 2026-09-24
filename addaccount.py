#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy2API 账号登录（纯 Python，不需要 Go / Git Bash）。

实现 CodeBuddy 设备授权流程，与 cmd/login 逻辑等价：
  1) POST /v2/plugin/auth/state?platform=CLI  → 拿 state + 授权链接
  2) 用户在浏览器完成登录
  3) GET  /v2/plugin/auth/token?state=        → 换 access/refresh token
  4) GET  /v2/plugin/login/account?state=     → 拿 uid / nickname
  5) 落盘 auths/workbuddy-<uid>.json（+ 国内版每日签到）

用法：双击 addaccount.bat，或 python addaccount.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
AUTH_DIR = os.path.join(ROOT, "auths")

UA = "CLI/2.63.2 CodeBuddy/2.63.2"

REALMS = {
    "cn": {"base": "https://copilot.tencent.com", "origin": "https://www.codebuddy.cn"},
    "global": {"base": "https://www.workbuddy.ai", "origin": "https://www.workbuddy.ai"},
}


def line(ch="=", n=60):
    print(ch * n)


def http_json(url, method="GET", body=None, headers=None, timeout=30):
    data = None
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        env = json.loads(raw)
    except Exception:
        raise RuntimeError("响应不是合法 JSON: %s" % raw[:200])
    if env.get("code") != 0:
        raise RuntimeError("code=%s msg=%s" % (env.get("code"), env.get("msg")))
    return env.get("data") or {}


def base_headers(origin, token=None):
    h = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": origin,
        "Referer": origin + "/",
        "User-Agent": UA,
    }
    if token:
        h["Authorization"] = "Bearer " + token
    return h


def daily_checkin(token, uid, ent_id, domain):
    """国内版每日签到（幂等，失败不影响登录结果）。"""
    req = urllib.request.Request(
        "https://www.codebuddy.cn/v2/billing/meter/daily-checkin",
        data=b"{}", method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-User-Id": uid,
            **({"X-Enterprise-Id": ent_id, "X-Tenant-Id": ent_id} if ent_id else {}),
            **({"X-Domain": domain} if domain else {}),
        })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode() or "{}")
        return body.get("msg") or ("成功 %s" % json.dumps(body.get("data") or {}, ensure_ascii=False)[:100])
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode() or "{}")
            return body.get("msg", "http %d" % e.code)
        except Exception:
            return "http %d" % e.code
    except Exception as e:
        return str(e)


def main():
    line()
    print("  WorkBuddy2API 账号登录")
    line()

    print("\n选择版本: 1) 国内版 cn  2) 国际版 global")
    choice = input("  请输入 1 或 2 [默认 1] ").strip() or "1"
    realm = "global" if choice == "2" else "cn"
    conf = REALMS[realm]
    print("  已选择: %s (%s)" % (realm, conf["base"]))

    print("\n正在获取授权链接...")
    try:
        st = http_json(conf["base"] + "/v2/plugin/auth/state?platform=CLI",
                       method="POST", body={},
                       headers=base_headers(conf["origin"]))
    except Exception as e:
        print("  获取失败: %s" % e)
        return 1
    state, auth_url = st.get("state"), st.get("authUrl")
    if not state or not auth_url:
        print("  返回内容缺少 state / authUrl: %s" % st)
        return 1

    print()
    line("-")
    print("  请在浏览器中打开以下链接并完成登录：\n")
    print("  " + auth_url)
    print()
    line("-")
    print()
    print("  ⚠️ 请**先在浏览器里完整登录成功**，再回到这里按回车。")
    print("     （顺序反了会导致拿不到 token，这是最常见的失败原因）")
    input("\n  登录完成后按回车继续... ")

    print("\n正在获取 token...")
    try:
        tok = http_json(conf["base"] + "/v2/plugin/auth/token?state=" + state,
                        headers=base_headers(conf["origin"]))
    except Exception as e:
        print("  获取 token 失败: %s" % e)
        print("  通常是登录尚未完成，请重新运行本脚本。")
        return 1
    access = tok.get("accessToken") or ""
    if not access:
        print("  未拿到 accessToken，登录可能未完成。")
        return 1

    acct = {}
    try:
        acct = http_json(conf["base"] + "/v2/plugin/login/account?state=" + state,
                         headers=base_headers(conf["origin"], token=access))
    except Exception as e:
        print("  获取账号信息失败（不影响登录）: %s" % e)

    uid = acct.get("uid") or ""
    if not uid:
        print("  无法获取 uid，请检查 token 是否有效。")
        return 1

    os.makedirs(AUTH_DIR, exist_ok=True)
    auth_file = os.path.join(AUTH_DIR, "workbuddy-%s.json" % uid)
    payload = {
        "account": {
            "uid": uid,
            "enterpriseId": acct.get("enterpriseId", ""),
            "nickname": acct.get("nickname", ""),
        },
        "auth": {
            "accessToken": access,
            "refreshToken": tok.get("refreshToken", ""),
            "expiresAt": int(time.time()) + int(tok.get("expiresIn") or 0),
            "domain": tok.get("domain", ""),
            "realm": realm,
        },
    }
    with open(auth_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print("  已保存: %s" % auth_file)
    print("  昵称  : %s" % (acct.get("nickname") or "-"))
    print("  UID   : %s" % uid)

    if realm == "cn":
        print("  签到  : %s" % daily_checkin(access, uid, acct.get("enterpriseId", ""), tok.get("domain", "")))

    print()
    line()
    print("  登录完成！")
    print()
    print("  ⚠️ 网关只在启动时加载账号，请**重启网关**后才会生效：")
    print("     - 双击 4_run.bat（前台，带日志）")
    print("     - 或双击 4_run-hidden.vbs（后台无窗口）")
    print("     - 或重新运行 1_install.bat")
    print()
    try:
        cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
        port = str(cfg.get("listen", ":8080")).rsplit(":", 1)[-1]
        print("  重启后检查：http://127.0.0.1:%s/healthz （应为 healthy:1）" % port)
    except Exception:
        pass
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n已取消。")
        sys.exit(1)

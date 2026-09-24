#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy2API 一键安装器（Windows）。

双击 install.bat 启动本脚本。交互式配置端口 / API 密钥 / 对外 IP，
然后构建、写配置、生成启动脚本、可选开机自启并立即启动。

用法:
    install.py                 # 交互式安装
    install.py --dry-run       # 只预览将做的改动，不写任何文件
    install.py --uninstall     # 移除开机自启并停止服务
"""
import json
import os
import random
import re
import shutil
import socket
import string
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ROOT, "config.json")
AUTHS = os.path.join(ROOT, "auths")
DATA = os.path.join(ROOT, "data")
STARTUP_NAME = "WorkBuddy2API-Autostart.vbs"
# 启动脚本按执行顺序编号，方便用户一眼看出 1→2→3 的顺序
RUN_BAT = "4_run.bat"
RUN_VBS = "4_run-hidden.vbs"

DRY_RUN = "--dry-run" in sys.argv
UNINSTALL = "--uninstall" in sys.argv

# 与 config.example.json 一致的完整默认配置
DEFAULT_CONFIG = {
    "listen": ":8080",
    "api_key": "",
    "auth_dir": "./auths",
    "state_file": "./data/state.json",
    "server": {"max_body_mb": 8},
    "cooldown": {"soft_rate": "600s", "soft_rate_max": "2h"},
    "schedule": {
        "checkin_hours": [9, 21], "travel_hours": [9, 21], "activity_hours": [10],
        "keepalive_hours": [22], "school_hours": [12], "cat_hours": [1],
        "checkin_enabled": True, "travel_enabled": True, "activity_enabled": True,
        "keepalive_enabled": True, "school_enabled": True, "cat_enabled": True,
    },
    "global": {"enabled": True, "chat_base": "", "billing_base": ""},
    "upstream": {
        "timeout_seconds": 120, "header_timeout_seconds": 120, "idle_timeout_seconds": 300,
        "user_agent": "", "client_version": "", "cli_version": "",
        "device_token": "", "device_token_file": "", "client_name": "WorkBuddy",
        "passthrough_ip": False,
    },
    "features": {"sanitize_blacklist_fingerprints": True},
    "prompt": {"mode": "passthrough", "file": ""},
    "upstash": {"url": "", "token": ""},
    "pool": {
        "max_in_flight": 3, "breaker_threshold": 3, "breaker_cooldown": "30m",
        "breaker_cooldown_max": "6h", "idle_weight_per_hour": 0.5,
        "idle_weight_max": 5.0, "expiring_soon": "168h",
    },
    "session_sticky": {"enabled": True, "ttl": "30m", "gc_interval": "5m"},
}


# ────────────────────────── 基础工具 ──────────────────────────

def line(ch="=", n=62):
    print(ch * n)


def title(text):
    print()
    line()
    print("  " + text)
    line()


def ask(prompt, default=""):
    """读取一行输入，空输入返回默认值。"""
    suffix = "  [默认: %s] " % default if default else " "
    try:
        val = input("  " + prompt + suffix).strip()
    except EOFError:
        val = ""
    return val or default


def ask_yn(prompt, default=True):
    d = "Y/n" if default else "y/N"
    try:
        val = input("  %s [%s] " % (prompt, d)).strip().lower()
    except EOFError:
        val = ""
    if not val:
        return default
    return val in ("y", "yes")


def lan_ip():
    """探测本机在局域网中的 IP（用于生成客户端访问地址）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("223.5.5.5", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def have(cmd):
    return shutil.which(cmd) is not None


def startup_dir():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")


def pid_on_port(port):
    """返回占用该端口的监听进程 PID 列表。"""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    except Exception:
        return []
    pids = []
    for ln in out.splitlines():
        if ":%d" % port in ln and "LISTENING" in ln.upper():
            parts = ln.split()
            if parts and parts[-1].isdigit() and parts[-1] not in pids:
                pids.append(parts[-1])
    return pids


def kill_port(port):
    killed = []
    for pid in pid_on_port(port):
        r = subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, text=True)
        if r.returncode == 0:
            killed.append(pid)
    return killed


def random_key(n=24):
    alphabet = string.ascii_letters + string.digits
    return "sk-" + "".join(random.choice(alphabet) for _ in range(n))


# ────────────────────────── 卸载 ──────────────────────────

def do_uninstall():
    title("卸载 / 停止 WorkBuddy2API")
    sd = startup_dir()
    if sd:
        p = os.path.join(sd, STARTUP_NAME)
        if os.path.exists(p):
            if not DRY_RUN:
                os.remove(p)
            print("  已移除开机自启: %s" % p)
        else:
            print("  开机自启项不存在，跳过")
    try:
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        port = int(str(cfg.get("listen", ":8080")).rsplit(":", 1)[-1])
    except Exception:
        port = 8080
    killed = kill_port(port) if not DRY_RUN else []
    print("  已停止占用 %d 的进程: %s" % (port, killed or "无"))
    print("\n  卸载完成（账号凭证 auths/ 与配置已保留）。")


# ────────────────────────── 主流程 ──────────────────────────

def main():
    if UNINSTALL:
        do_uninstall()
        return

    title("WorkBuddy2API 一键安装")
    if DRY_RUN:
        print("  ** DRY RUN 预览模式：不会写入任何文件 **")

    # 1. 环境检查
    print("\n[1/6] 环境检查")
    print("  Python : %s" % sys.version.split()[0])
    go_ok = have("go")
    print("  Go     : %s" % ("已安装" if go_ok else "未安装（将跳过构建，使用已有二进制）"))

    # 2. 读取现有配置作为默认值
    cfg = dict(DEFAULT_CONFIG)
    old_port, old_key = 8080, ""
    if os.path.exists(CONFIG):
        try:
            cur = json.load(open(CONFIG, encoding="utf-8"))
            cfg.update(cur)
            old_port = int(str(cur.get("listen", ":8080")).rsplit(":", 1)[-1])
            old_key = cur.get("api_key", "")
            print("  检测到已有 config.json，将以其为默认值")
        except Exception as e:
            print("  警告：现有 config.json 解析失败(%s)，将使用默认配置" % e)

    # 3. 交互配置
    title("[2/6] 参数配置（直接回车 = 使用默认值）")

    print("\n  ── 监听端口 ──")
    print("  注意：7863 常被 Windows(Hyper-V/Docker) 预留而绑定失败，建议 8080")
    while True:
        port_s = ask("监听端口", str(old_port))
        if not port_s.isdigit() or not (1 < int(port_s) < 65536):
            print("  端口无效，请输入 1-65535 的数字")
            continue
        port = int(port_s)
        # 注意：Windows 上 socket.bind 带 SO_REUSEADDR 时**可以**绑到已占用的端口，
        # 所以 port_free() 在 Windows 不可靠 —— 必须以 netstat(pid_on_port) 为准。
        own = pid_on_port(port)
        if own or not port_free(port):
            who = (" (PID %s)" % ",".join(own)) if own else ""
            print("  警告：端口 %d 已被占用%s" % (port, who))
            print("  安装/启动时会尝试结束该占用进程。若那是别的程序，请换一个端口。")
            if not ask_yn("  仍要继续使用此端口？", True):
                continue
        break

    print("\n  ── API 密钥 ──")
    print("  1) 不鉴权（留空）        仅本机/可信内网使用")
    print("  2) 自定义密钥            自己填一个")
    print("  3) 随机生成强密钥        推荐（对外暴露时）")
    if old_key:
        print("  当前已设置: %s" % ("*" * min(len(old_key), 12)))
    while True:
        choice = ask("选择 [1/2/3]", "1" if not old_key else "2")
        if choice == "3":
            api_key = random_key()
            print("  已生成: %s" % api_key)
            break
        if choice == "2":
            api_key = ask("请输入 API 密钥", old_key)
            break
        if choice == "1":
            api_key = ""
            break
        print("  无效选择，请输入 1、2 或 3")

    print("\n  ── 对外访问 IP ──")
    print("  客户端（Trae / VS Code 等）访问网关用的地址。")
    print("  重要：部分客户端（如 Trae CN、跑在 WSL/远程的 VS Code）用 127.0.0.1 会")
    print("        连接失败，必须用本机局域网 IP。")
    detected = lan_ip()
    print("  自动探测到: %s" % detected)
    host = ask("对外 IP（直接回车用探测值）", detected)
    host = host.strip() or detected

    cfg["listen"] = ":%d" % port
    cfg["api_key"] = api_key
    cfg["auth_dir"] = "./auths"
    cfg["state_file"] = "./data/state.json"

    base_url = "http://%s:%d/v1" % (host, port)

    # 4. 构建
    title("[3/6] 构建")
    src_ok = os.path.isdir(os.path.join(ROOT, "cmd", "server"))
    exe = os.path.join(ROOT, "wb2api.exe")
    if not os.path.exists(exe) and not src_ok:
        # 便携版：不含 Go 源码，无法构建
        print("  便携版不含 Go 源码，直接使用自带 wb2api.exe")
        need_build = False
    elif os.path.exists(exe):
        need_build = ask_yn("已存在 wb2api.exe，是否重新构建？", False)
    else:
        need_build = True
    if need_build:
        if not go_ok or not src_ok:
            print("  缺少 Go 或源码，跳过构建（请确保 wb2api.exe 已存在）")
        else:
            print("  正在构建 go build -o wb2api.exe ./cmd/server ...")
            if not DRY_RUN:
                r = run(["go", "build", "-o", "wb2api.exe", "./cmd/server"])
                print(r.stdout.strip())
                if r.returncode != 0:
                    print("  构建失败:\n" + (r.stderr or "")[:800])
                    return
                print("  构建成功")
            else:
                print("  [dry-run] 跳过实际构建")
    else:
        print("  跳过构建，使用现有 wb2api.exe")

    # 5. 写配置 / 目录 / 启动脚本
    title("[4/6] 写入配置与启动脚本")
    if not DRY_RUN:
        os.makedirs(AUTHS, exist_ok=True)
        os.makedirs(DATA, exist_ok=True)
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print("  已写入 %s" % CONFIG)
        print("  目录就绪: auths/  data/")

        # 4_run.bat（纯 ASCII，避免 GBK 乱码）
        bat = "\r\n".join([
            "@echo off",
            "REM WorkBuddy2API launcher (generated by install.py - ASCII only)",
            "cd /d \"%~dp0\"",
            "echo Freeing port %d if occupied ..." % port,
            # 注意：只有带 % port 的行会做 % 折叠，故需 %%%%a → %%a；
            # 其余普通字面量直接写 %%a / %~dp0（不会被折叠）。
            "for /f \"tokens=5\" %%%%a in ('netstat -ano ^| findstr \":%d\" ^| findstr \"LISTENING\"') do (" % port,
            "    taskkill /f /pid %%a >nul 2>&1",
            ")",
            "timeout /t 1 >nul",
            "echo Starting WorkBuddy2API on :%d ..." % port,
            "title WorkBuddy2API",
            "wb2api.exe -config config.json",
            "",
        ])
        open(os.path.join(ROOT, RUN_BAT), "w", encoding="ascii").write(bat)
        print("  已生成 %s（端口 %d）" % (RUN_BAT, port))

        # 后台隐藏启动脚本
        # 注意：这里必须用「脚本自身所在目录」而不是绝对路径，
        # 否则便携版拷到别的电脑/别的目录后就会失效。
        vbs = (
            'Set ws = CreateObject("WScript.Shell")\r\n'
            'Set fso = CreateObject("Scripting.FileSystemObject")\r\n'
            'here = fso.GetParentFolderName(WScript.ScriptFullName)\r\n'
            'ws.CurrentDirectory = here\r\n'
            'ws.Run """" & here & "\\wb2api.exe"" -config """ & here & "\\config.json""", 0, False\r\n'
        )
        open(os.path.join(ROOT, RUN_VBS), "w", encoding="ascii").write(vbs)
        print("  已生成 %s（后台无窗口启动）" % RUN_VBS)
    else:
        print("  [dry-run] 将写入 config.json / %s / %s，创建 auths/ data/" % (RUN_BAT, RUN_VBS))

    # 6. 开机自启
    title("[5/6] 开机自启")
    sd = startup_dir()
    autostart = ask_yn("是否开机自动启动（写入当前用户的「启动」文件夹，无需管理员）？", True)
    if autostart:
        if not sd:
            print("  无法定位启动文件夹，跳过")
        else:
            dst = os.path.join(sd, STARTUP_NAME)
            if not DRY_RUN:
                vbs = (
                    'Set ws = CreateObject("WScript.Shell")\r\n'
                    'ws.CurrentDirectory = "%s"\r\n'
                    'ws.Run """%s"" -config ""%s""", 0, False\r\n'
                    % (ROOT, os.path.join(ROOT, "wb2api.exe"), CONFIG)
                )
                open(dst, "w", encoding="ascii").write(vbs)
                print("  已写入: %s" % dst)
            else:
                print("  [dry-run] 将写入 %s" % os.path.join(sd, STARTUP_NAME))
    else:
        print("  跳过开机自启（之后可用 %s 手动启动）" % RUN_BAT)

    # 7. 立即启动
    title("[6/6] 立即启动")
    start_now = ask_yn("立即启动网关？", True)
    if start_now:
        if not DRY_RUN:
            for pid in kill_port(port):
                print("  已结束旧进程 PID %s" % pid)
            subprocess.Popen(
                ["wscript.exe", os.path.join(ROOT, RUN_VBS)],
                cwd=ROOT,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print("  已后台启动（无窗口）。等待 3 秒后探活...")
            import time
            time.sleep(3)
            try:
                import urllib.request
                with urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=5) as r:
                    print("  探活成功: %s" % r.read().decode()[:120])
            except Exception as e:
                print("  探活失败: %s" % e)
                print("  可查看日志或双击 %s 前台运行排查" % RUN_BAT)
        else:
            print("  [dry-run] 将结束端口 %d 占用进程并后台启动" % port)

    # 7.5 刷新模型清单（复用 scripts/list_models.py）
    # 注意：网关在尚未加号时 /v1/models 返回空数组，此时绝不能覆盖已有清单，
    # 故由 list_models.generate() 内部做空列表保护。
    if not DRY_RUN:
        try:
            sys.path.insert(0, os.path.join(ROOT, "scripts"))
            sys.dont_write_bytecode = True  # 避免在 scripts/ 下留下 __pycache__
            import list_models as lm
            ok, msg = lm.generate("http://127.0.0.1:%d" % port, api_key)
            print("  模型清单: %s" % msg)
        except Exception as e:
            print("  模型清单: 刷新跳过（%s）" % e)
    else:
        print("  [dry-run] 将尝试刷新 models-trae.md（0 账号时自动跳过）")

    # 8. 生成客户端配置说明
    gen_client_guide(base_url, api_key, port)

    # 完成
    title("安装完成")
    print("  网关地址 : %s" % base_url)
    print("  鉴权     : %s" % ("开启（密钥已设置）" if api_key else "未开启（任何人可调用）"))
    if api_key:
        print("  API 密钥 : %s" % api_key)
    print("  探活     : http://127.0.0.1:%d/healthz （无需密钥）" % port)
    print()
    print("  下一步：")
    print("    1) 加号：Git Bash 里执行 ./login.sh（国际版 --realm=global）")
    print("       注意：先在浏览器完成登录，再回终端按 y")
    print("    2) 加号后必须重启网关才会生效 —— 双击 4_run.bat 即可")
    print("    3) 查看账号：curl -H \"Authorization: Bearer %s\" http://127.0.0.1:%d/status"
          % (api_key or "YOUR_KEY", port))
    print()
    print("  客户端配置已生成: 客户端配置.md")
    print()


def gen_client_guide(base_url, api_key, port):
    """生成客户端接入说明（含真实 IP / 端口 / 密钥）。"""
    key_show = api_key or "YOUR_KEY"
    auth_hdr = '-H "Authorization: Bearer %s"' % key_show if api_key else "# 未启用鉴权，无需 Authorization 头"
    md = """# 客户端接入配置

> 由 install.py 自动生成，重新运行安装器会覆盖本文件。

## 连接信息

| 项 | 值 |
|---|---|
| 网关地址 | `{base}` |
| 局域网地址 | `http://{ip}:{port}/v1` |
| API 密钥 | `{key}` |
| 探活地址 | `http://127.0.0.1:{port}/healthz`（无需密钥） |

## 快速验证

```bash
curl {auth} http://127.0.0.1:{port}/status
```

## Trae CN

- API 地址：`http://{ip}:{port}/v1`
- API 密钥：`{key}`
- 模型 ID：见 `models-trae.md`

> ⚠️ Trae CN 填 `127.0.0.1` 会 Connection refused，**必须用上面的局域网 IP**。

## VS Code 内置 Copilot Chat（BYOK Custom Endpoint）

用 UI 配置，不要手改 JSON：`Ctrl+Shift+P` → `Chat: Manage Language Models`
→ `Add Models` → `Custom Endpoint` → 填入密钥 `{key}` → API Type 选
`Chat Completions`。随后 VS Code 打开 `chatLanguageModels.json`，**保留
`apiKey` 的 `${{input:chat.lm.secret.xxx}}` 引用不动**，只填：

```json
{{
  "name": "workbuddy",
  "vendor": "customendpoint",
  "apiKey": "${{input:chat.lm.secret.xxxxxxxx}}",
  "apiType": "chat-completions",
  "models": [
    {{
      "id": "cn:hy4-preview-f",
      "name": "hy4-preview-f",
      "url": "http://{ip}:{port}/v1/chat/completions",
      "toolCalling": true,
      "vision": true,
      "maxInputTokens": 1000000,
      "maxOutputTokens": 64000
    }}
  ]
}}
```

> ⚠️ 两个坑：`apiKey` **不能手填明文**（否则 401）；`url` 建议写完整路径
> `.../v1/chat/completions`（单独 `/v1` 会 404）。
> 若你的 VS Code 报 404，把 url 改回 `http://{ip}:{port}/v1` 再试。

## Cline / Roo Code / Continue

- Base URL：`http://{ip}:{port}/v1`
- API Key：`{key}`
- Model ID：从 `models-trae.md` 中选

## 常用管理命令

```bash
# 账号状态
curl {auth} http://127.0.0.1:{port}/status

# 模型列表
curl {auth} http://127.0.0.1:{port}/v1/models

# 刷新模型清单文档
python3 scripts/list_models.py http://{ip}:{port} {key}
```
""".format(base=base_url, ip=base_url.split("//")[1].split(":")[0],
           port=port, key=key_show, auth=auth_hdr)

    if DRY_RUN:
        print("\n  [dry-run] 将生成 客户端配置.md")
        return
    p = os.path.join(ROOT, "客户端配置.md")
    open(p, "w", encoding="utf-8").write(md)
    print("  已生成 %s" % p)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消。")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy2API 图形化控制面板（后端，仅用 Python 标准库）。

把原本分散在 3 个 bat / 1 个 vbs 里的 4 个步骤整合到一个网页界面：
    1) 安装配置   1_3_install.bat
    2) 添加账号   2_addaccount.bat
    3) 前台启动   4_run.bat
    4) 后台启动   4_run-hidden.vbs

启动方式：
    双击 0_panel.bat      或     python control_panel.py [--port 8765] [--no-browser]

浏览器会自动打开 http://127.0.0.1:<port> ，服务只监听 127.0.0.1。
"""
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(ROOT, "ui")
LOG_DIR = os.path.join(ROOT, "logs")
GATEWAY_LOG = os.path.join(LOG_DIR, "gateway.log")
CONFIG_PATH = os.path.join(ROOT, "config.json")
AUTHS_DIR = os.path.join(ROOT, "auths")
DATA_DIR = os.path.join(ROOT, "data")
STATE_PATH = os.path.join(DATA_DIR, "panel_state.json")
CLIENT_MD = os.path.join(ROOT, "客户端配置.md")
EXE = os.path.join(ROOT, "wb2api.exe")
RUN_BAT = "4_run.bat"
RUN_VBS = "4_run-hidden.vbs"
AUTOSTART_NAME = "WorkBuddy2API-Autostart.vbs"

for _d in (LOG_DIR, DATA_DIR, AUTHS_DIR):
    os.makedirs(_d, exist_ok=True)

CREATE_NEW_CONSOLE = 0x00000010
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


# ───────────────────────── 复用已有脚本 ─────────────────────────

def load_module(name, path):
    """按文件路径加载模块（不依赖 sys.path，也不产生 __pycache__）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


INST = None
try:
    INST = load_module("wb2a_install", os.path.join(ROOT, "install.py"))
    INST.RUN_BAT = RUN_BAT
    INST.RUN_VBS = RUN_VBS
except Exception as _e:  # 安装器缺失不影响面板其他功能
    INST = None

ACCT = None
try:
    ACCT = load_module("wb2a_addaccount", os.path.join(ROOT, "addaccount.py"))
except Exception:
    ACCT = None

LM = None
try:
    LM = load_module("wb2a_list_models", os.path.join(ROOT, "scripts", "list_models.py"))
except Exception:
    LM = None


# ───────────────────────── 日志缓冲 ─────────────────────────

LOG_LOCK = threading.Lock()
LOGS = []
LOG_ID = 0


def log(text, level="info"):
    global LOG_ID
    line = str(text).rstrip()
    with LOG_LOCK:
        LOG_ID += 1
        LOGS.append({
            "id": LOG_ID,
            "t": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "text": line,
        })
        if len(LOGS) > 3000:
            del LOGS[:800]
    try:
        print("[%s] %s" % (level, line))
    except Exception:
        pass


def logs_since(since):
    with LOG_LOCK:
        return [x for x in LOGS if x["id"] > since]


# ───────────────────────── 基础工具 ─────────────────────────

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def cfg_port(cfg=None):
    cfg = cfg if cfg is not None else read_config()
    try:
        return int(str(cfg.get("listen", ":8080")).rsplit(":", 1)[-1])
    except Exception:
        return 8080


def lan_ip():
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


def pids_on_port(port):
    """占用该端口并处于 LISTENING 的 PID 列表。"""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=20).stdout
    except Exception:
        return []
    pids = []
    for ln in out.splitlines():
        if "LISTENING" not in ln.upper():
            continue
        parts = ln.split()
        if len(parts) < 4:
            continue
        local = parts[1]
        if local.rsplit(":", 1)[-1] != str(port):
            continue
        pid = parts[-1]
        if pid.isdigit() and pid not in pids:
            pids.append(pid)
    return pids


def pid_alive(pid):
    try:
        pid = int(pid)
    except Exception:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=20).stdout
        return str(pid) in out
    except Exception:
        return False


def kill_pid(pid):
    try:
        r = subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def kill_port(port):
    killed = []
    for pid in pids_on_port(port):
        if kill_pid(pid):
            killed.append(pid)
    return killed


def read_panel_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_panel_state(d):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def startup_dir():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")


def autostart_path():
    sd = startup_dir()
    return os.path.join(sd, AUTOSTART_NAME) if sd else None


def autostart_enabled():
    p = autostart_path()
    return bool(p and os.path.exists(p))


def probe_health(port, timeout=3):
    """返回 (ok, text)。"""
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/healthz" % port)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, r.read().decode("utf-8", "replace").strip()[:200]
    except urllib.error.HTTPError as e:
        return False, "HTTP %d" % e.code
    except Exception as e:
        return False, str(e)


def gateway_status():
    port = cfg_port()
    pids = pids_on_port(port)
    st = read_panel_state()
    saved_pid = st.get("pid")
    running = bool(pids)
    pid = pids[0] if pids else (saved_pid if pid_alive(saved_pid) else None)
    ok, text = probe_health(port)
    return {
        "running": running,
        "pid": pid,
        "port": port,
        "mode": st.get("mode", ""),
        "started_at": st.get("started_at", ""),
        "health": ok,
        "health_text": text if ok else (text if running else ""),
        "tracked": bool(pid),
    }


def list_accounts():
    out = []
    try:
        names = sorted(os.listdir(AUTHS_DIR))
    except Exception:
        return out
    for fn in names:
        if not fn.lower().endswith(".json"):
            continue
        p = os.path.join(AUTHS_DIR, fn)
        try:
            with open(p, encoding="utf-8") as f:
                j = json.load(f)
            a = j.get("account", {}) or {}
            au = j.get("auth", {}) or {}
            exp = au.get("expiresAt")
            remain_h = None
            expire_at = ""
            if isinstance(exp, (int, float)) and exp > 0:
                remain_h = round((exp - time.time()) / 3600.0, 1)
                try:
                    expire_at = datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    expire_at = ""
            out.append({
                "file": fn,
                "uid": a.get("uid", ""),
                "nickname": a.get("nickname", "") or "-",
                "realm": au.get("realm", "cn"),
                "expire_at": expire_at,
                "remain_h": remain_h,
                "expired": bool(remain_h is not None and remain_h < 0),
                "mtime": datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M"),
            })
        except Exception as e:
            out.append({"file": fn, "uid": "", "nickname": "读取失败: %s" % e,
                        "realm": "", "expire_at": "", "remain_h": None,
                        "expired": False, "mtime": ""})
    return out


def bundled_python():
    """当前解释器是否来自项目自带的 runtime/python（绿色免安装）。"""
    base = os.path.join(ROOT, "runtime") + os.sep
    return os.path.normcase(os.path.abspath(sys.executable)).startswith(os.path.normcase(base))


def count_models():
    """优先问网关，失败则读 models-trae.md 里的统计。"""
    cfg = read_config()
    port = cfg_port(cfg)
    key = cfg.get("api_key", "")
    if LM is not None:
        try:
            models = LM.fetch_models("http://127.0.0.1:%d" % port, key, timeout=3)
            if models:
                return len(models), "在线"
        except Exception:
            pass
    try:
        with open(os.path.join(ROOT, "models-trae.md"), encoding="utf-8") as f:
            txt = f.read()
        import re
        m = re.search(r"共 \*\*(\d+)\*\* 个模型", txt)
        if m:
            return int(m.group(1)), "文档"
    except Exception:
        pass
    return 0, "-"


def exe_info():
    if not os.path.exists(EXE):
        return {"exists": False}
    try:
        st = os.stat(EXE)
        return {
            "exists": True,
            "size_mb": round(st.st_size / 1048576.0, 1),
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
        }
    except Exception:
        return {"exists": True}


def state_payload():
    cfg = read_config()
    port = cfg_port(cfg)
    lan = lan_ip()
    svc = gateway_status()
    n_model, model_src = count_models()
    accounts = list_accounts()
    try:
        with open(CLIENT_MD, encoding="utf-8") as f:
            guide = f.read()
    except Exception:
        guide = ""
    return {
        "root": ROOT,
        "now": now_str(),
        "env": {
            "python": sys.version.split()[0],
            "python_exe": sys.executable,
            "python_bundled": bundled_python(),
            "go": shutil.which("go") is not None,
            "exe": exe_info(),
            "src": os.path.isdir(os.path.join(ROOT, "cmd", "server")),
        },
        "config": {
            "port": port,
            "listen": cfg.get("listen", ""),
            "api_key": cfg.get("api_key", ""),
            "auth_dir": cfg.get("auth_dir", ""),
            "state_file": cfg.get("state_file", ""),
            "exists": os.path.exists(CONFIG_PATH),
        },
        "service": svc,
        "accounts": accounts,
        "lan_ip": lan,
        "base_url": "http://%s:%d/v1" % (lan, port),
        "local_url": "http://127.0.0.1:%d/v1" % port,
        "healthz": "http://127.0.0.1:%d/healthz" % port,
        "autostart": {"enabled": autostart_enabled(), "path": autostart_path() or ""},
        "models": {"count": n_model, "source": model_src},
        "client_guide": guide,
        "log_file": GATEWAY_LOG,
    }


# ───────────────────────── 步骤 1：安装 / 配置 ─────────────────────────

def write_launchers(port):
    bat = "\r\n".join([
        "@echo off",
        "REM WorkBuddy2API launcher (generated by control_panel.py - ASCII only)",
        'cd /d "%~dp0"',
        "echo Freeing port %d if occupied ..." % port,
        'for /f "tokens=5" %%a in (\'netstat -ano ^| findstr ":' + str(port) + '" ^| findstr "LISTENING"\') do (',
        "    taskkill /f /pid %%a >nul 2>&1",
        ")",
        "timeout /t 1 >nul",
        "echo Starting WorkBuddy2API on :%d ..." % port,
        "title WorkBuddy2API",
        "wb2api.exe -config config.json",
        "",
    ])
    with open(os.path.join(ROOT, RUN_BAT), "w", encoding="ascii") as f:
        f.write(bat)

    vbs = "\r\n".join([
        'Set ws = CreateObject("WScript.Shell")',
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        'here = fso.GetParentFolderName(WScript.ScriptFullName)',
        'ws.CurrentDirectory = here',
        r'ws.Run """" & here & "\wb2api.exe"" -config """ & here & "\config.json""", 0, False',
        "",
    ])
    with open(os.path.join(ROOT, RUN_VBS), "w", encoding="ascii") as f:
        f.write(vbs)
    return True


def set_autostart(enabled):
    dst = autostart_path()
    if not dst:
        return False, "无法定位启动文件夹（APPDATA 缺失）"
    if enabled:
        vbs = "\r\n".join([
            'Set ws = CreateObject("WScript.Shell")',
            'ws.CurrentDirectory = "%s"' % ROOT,
            'ws.Run """%s"" -config ""%s""", 0, False' % (EXE, CONFIG_PATH),
            "",
        ])
        try:
            with open(dst, "w", encoding="ascii") as f:
                f.write(vbs)
            return True, "已写入 %s" % dst
        except Exception as e:
            return False, "写入失败: %s" % e
    try:
        if os.path.exists(dst):
            os.remove(dst)
            return True, "已移除 %s" % dst
        return True, "开机自启本来就是关闭状态"
    except Exception as e:
        return False, "移除失败: %s" % e


def do_install(opts):
    """执行「安装 / 应用配置」，等价于 1_3_install.bat 的全部交互内容。"""
    try:
        port = int(str(opts.get("port", "8080")).strip())
    except Exception:
        return {"ok": False, "error": "端口不是合法数字"}
    if not (1 < port < 65536):
        return {"ok": False, "error": "端口需在 1-65535 之间"}

    api_key = str(opts.get("api_key", "") or "")
    host = (str(opts.get("host", "") or "").strip()) or lan_ip()
    autostart = bool(opts.get("autostart", False))
    start_now = bool(opts.get("start_now", False))
    refresh_models = bool(opts.get("refresh_models", True))

    log("=" * 56, "step")
    log("[1/6] 环境检查")
    log("Python : %s" % sys.version.split()[0])
    log("Go     : %s" % ("已安装" if shutil.which("go") else "未安装（便携版直接用自带 exe）"))
    log("wb2api.exe : %s" % ("存在" if os.path.exists(EXE) else "缺失"))

    cfg = dict(INST.DEFAULT_CONFIG) if INST is not None else {}
    old = read_config()
    if old:
        cfg.update(old)
        log("[2/6] 检测到已有 config.json，以其为默认值合并")
    else:
        log("[2/6] 未发现 config.json，使用内置默认配置")

    occupied = pids_on_port(port)
    if occupied:
        log("警告：端口 %d 已被占用 (PID %s)" % (port, ",".join(occupied)), "warn")

    cfg["listen"] = ":%d" % port
    cfg["api_key"] = api_key
    cfg["auth_dir"] = "./auths"
    cfg["state_file"] = "./data/state.json"

    log("[3/6] 构建：便携版使用自带 wb2api.exe，跳过 go build")

    log("[4/6] 写入 config.json / %s / %s" % (RUN_BAT, RUN_VBS))
    os.makedirs(AUTHS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        write_config(cfg)
        write_launchers(port)
    except Exception as e:
        log("写入失败: %s" % e, "error")
        return {"ok": False, "error": "写入文件失败: %s" % e}
    log("config.json 已更新（端口 %d，鉴权 %s）" % (port, "开启" if api_key else "未开启"))
    log("已生成 %s / %s" % (RUN_BAT, RUN_VBS))

    log("[5/6] 开机自启：%s" % ("开启" if autostart else "关闭"))
    ok, msg = set_autostart(autostart)
    log(msg, "info" if ok else "warn")

    base_url = "http://%s:%d/v1" % (host, port)
    if INST is not None:
        try:
            INST.gen_client_guide(base_url, api_key, port)
            log("已生成 客户端配置.md")
        except Exception as e:
            log("客户端配置.md 生成失败: %s" % e, "warn")

    result = {"ok": True, "port": port, "base_url": base_url}

    log("[6/6] 立即启动：%s" % ("是" if start_now else "否"))
    if start_now:
        r = start_gateway("hidden")
        result["started"] = r.get("ok")
        if refresh_models:
            time.sleep(1.5)
            result["models"] = refresh_model_list()
    elif refresh_models:
        result["models"] = refresh_model_list()

    log("安装/配置完成 → %s" % base_url, "ok")
    log("提示：加号后必须重启网关才会生效", "info")
    return result


def parse_models_md():
    """兜底：从 models-trae.md 的表格里解析模型清单。"""
    out = []
    path = os.path.join(ROOT, "models-trae.md")
    if not os.path.exists(path):
        return out
    try:
        import re
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        row = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*(.*?)\|\s*$")
        for ln in txt.splitlines():
            m = row.match(ln.strip())
            if not m:
                continue
            mid = m.group(1).strip()
            if mid in ("模型 ID", "---"):
                continue
            out.append({
                "id": mid,
                "name": m.group(2).strip(),
                "credits": m.group(3).strip(),
                "description": m.group(4).strip(),
            })
    except Exception:
        pass
    return out


def fetch_model_list():
    """返回 (models, source)。优先问网关 /v1/models，失败退回 models-trae.md。"""
    cfg = read_config()
    port = cfg_port(cfg)
    key = cfg.get("api_key", "")
    if LM is not None:
        try:
            models = LM.fetch_models("http://127.0.0.1:%d" % port, key, timeout=6)
            if models:
                return [{
                    "id": m.get("id", ""),
                    "name": m.get("name", ""),
                    "credits": str(m.get("credits") if m.get("credits") is not None else "-"),
                    "description": m.get("description", ""),
                } for m in models], "在线"
        except Exception:
            pass
    return parse_models_md(), "文档"


def refresh_model_list():
    cfg = read_config()
    port = cfg_port(cfg)
    key = cfg.get("api_key", "")
    if LM is None:
        log("模型清单：scripts/list_models.py 不可用，跳过", "warn")
        return {"ok": False, "msg": "list_models.py 不可用"}
    ok, msg = LM.generate("http://127.0.0.1:%d" % port, key)
    log("模型清单: %s" % msg, "ok" if ok else "warn")
    return {"ok": ok, "msg": msg}


def after_account_flow(auto=True):
    """加号后的自动流程：按需（重）启动网关 → 刷新 models-trae.md → 取模型列表。

    网关只在启动时加载 auths/，所以想让新账号立刻生效、并拉到它的模型，
    必须先重启网关，再请求 /v1/models。
    """
    res = {"gateway": {}, "models": {"list": [], "source": "-", "count": 0, "msg": ""}}
    svc = gateway_status()
    if auto:
        if svc["running"]:
            log("网关正在运行，自动重启以加载新账号 ...", "info")
            res["gateway"] = restart_gateway("hidden")
        else:
            log("网关未运行，自动后台启动 ...", "info")
            res["gateway"] = start_gateway("hidden")
    else:
        log("跳过自动重启（未勾选），直接尝试拉取模型列表", "info")
        res["gateway"] = {"ok": svc["running"], "health": svc["health"], "skipped": True}

    md = refresh_model_list()
    models, src = fetch_model_list()
    res["models"] = {"list": models, "source": src, "count": len(models),
                     "msg": md.get("msg", "")}
    if models:
        log("模型列表已更新：%d 个（来源：%s）" % (len(models), src), "ok")
    else:
        log("未能取到模型列表：网关可能未运行或账号尚未加载", "warn")
    return res


# ───────────────────────── 步骤 2：添加账号 ─────────────────────────

def account_begin(realm):
    if ACCT is None:
        return {"ok": False, "error": "addaccount.py 不可用"}
    conf = ACCT.REALMS.get(realm)
    if not conf:
        return {"ok": False, "error": "未知版本: %s" % realm}
    log("正在向 %s 申请设备授权码..." % conf["base"])
    try:
        st = ACCT.http_json(conf["base"] + "/v2/plugin/auth/state?platform=CLI",
                            method="POST", body={},
                            headers=ACCT.base_headers(conf["origin"]))
    except Exception as e:
        log("获取授权链接失败: %s" % e, "error")
        return {"ok": False, "error": str(e)}
    state, auth_url = st.get("state"), st.get("authUrl")
    if not state or not auth_url:
        log("返回内容缺少 state/authUrl: %s" % st, "error")
        return {"ok": False, "error": "返回内容缺少 state / authUrl"}
    log("拿到授权链接（state=%s）" % state[:12] + "...")
    return {"ok": True, "state": state, "auth_url": auth_url, "realm": realm}


def account_complete(realm, state, auto=True):
    if ACCT is None:
        return {"ok": False, "error": "addaccount.py 不可用"}
    conf = ACCT.REALMS.get(realm)
    if not conf:
        return {"ok": False, "error": "未知版本: %s" % realm}
    log("正在用 state 换取 token ...")
    try:
        tok = ACCT.http_json(conf["base"] + "/v2/plugin/auth/token?state=" + state,
                             headers=ACCT.base_headers(conf["origin"]))
    except Exception as e:
        log("换取 token 失败（多半是浏览器里还没登录完）: %s" % e, "error")
        return {"ok": False, "error": "换取 token 失败：%s（请先在浏览器完成登录再点完成）" % e}
    access = tok.get("accessToken") or ""
    if not access:
        log("未拿到 accessToken，登录可能未完成", "error")
        return {"ok": False, "error": "未拿到 accessToken，登录可能未完成"}

    acct_info = {}
    try:
        acct_info = ACCT.http_json(conf["base"] + "/v2/plugin/login/account?state=" + state,
                                   headers=ACCT.base_headers(conf["origin"], token=access))
        log("账号信息获取成功")
    except Exception as e:
        log("账号信息获取失败（不影响登录）: %s" % e, "warn")

    uid = acct_info.get("uid") or ""
    if not uid:
        log("无法获取 uid", "error")
        return {"ok": False, "error": "无法获取 uid，请检查 token 是否有效"}

    os.makedirs(AUTHS_DIR, exist_ok=True)
    auth_file = os.path.join(AUTHS_DIR, "workbuddy-%s.json" % uid)
    payload = {
        "account": {
            "uid": uid,
            "enterpriseId": acct_info.get("enterpriseId", ""),
            "nickname": acct_info.get("nickname", ""),
        },
        "auth": {
            "accessToken": access,
            "refreshToken": tok.get("refreshToken", ""),
            "expiresAt": int(time.time()) + int(tok.get("expiresIn") or 0),
            "domain": tok.get("domain", ""),
            "realm": realm,
        },
    }
    try:
        with open(auth_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
    except Exception as e:
        log("写入凭证失败: %s" % e, "error")
        return {"ok": False, "error": "写入凭证失败: %s" % e}

    log("已保存: %s" % os.path.basename(auth_file), "ok")
    log("昵称: %s    UID: %s" % (acct_info.get("nickname") or "-", uid))

    checkin = ""
    if realm == "cn":
        try:
            checkin = ACCT.daily_checkin(access, uid, acct_info.get("enterpriseId", ""),
                                         tok.get("domain", ""))
            log("每日签到: %s" % checkin)
        except Exception as e:
            checkin = str(e)

    log("登录完成！正在自动重载网关并拉取模型列表 ...", "ok")
    flow = after_account_flow(auto)
    result = {
        "ok": True,
        "file": os.path.basename(auth_file),
        "uid": uid,
        "nickname": acct_info.get("nickname") or "-",
        "checkin": checkin,
        "gateway": flow["gateway"],
        "models": flow["models"],
    }
    if not auto:
        log("提示：未自动重启网关，请到步骤 ③ 手动重启后账号才会生效", "warn")
    return result


def account_delete(fn):
    if not fn or "/" in fn or "\\" in fn or not fn.lower().endswith(".json"):
        return {"ok": False, "error": "文件名不合法"}
    p = os.path.join(AUTHS_DIR, os.path.basename(fn))
    if not os.path.exists(p):
        return {"ok": False, "error": "文件不存在"}
    try:
        os.remove(p)
        log("已删除账号文件: %s" % fn, "warn")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ───────────────────────── 步骤 3 / 4：启动与停止 ─────────────────────────

def start_gateway(mode="console"):
    mode = "console" if mode == "console" else "hidden"
    if not os.path.exists(EXE):
        log("找不到 wb2api.exe，无法启动", "error")
        return {"ok": False, "error": "找不到 wb2api.exe"}
    cfg = read_config()
    port = cfg_port(cfg)

    old = read_panel_state()
    if old.get("pid") and pid_alive(old.get("pid")) and not pids_on_port(port):
        log("结束上一次由面板启动的进程 PID %s" % old["pid"])
        kill_pid(old["pid"])

    occupied = pids_on_port(port)
    if occupied:
        log("端口 %d 被占用 (PID %s)，先结束它们" % (port, ",".join(occupied)), "warn")
        for pid in occupied:
            kill_pid(pid)
        time.sleep(1)

    os.makedirs(AUTHS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    flags = CREATE_NEW_CONSOLE if mode == "console" else (CREATE_NO_WINDOW | DETACHED_PROCESS)
    try:
        f = open(GATEWAY_LOG, "ab")
        try:
            proc = subprocess.Popen([EXE, "-config", "config.json"], cwd=ROOT,
                                    stdout=f, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, creationflags=flags)
        finally:
            f.close()
    except Exception as e:
        log("启动失败: %s" % e, "error")
        return {"ok": False, "error": "启动失败: %s" % e}

    write_panel_state({"pid": proc.pid, "mode": mode, "started_at": now_str(), "port": port})
    log("已启动 wb2api.exe（PID %d，模式：%s，端口 %d）" % (proc.pid, mode, port),
        "ok" if mode == "hidden" else "info")
    if mode == "console":
        log("已打开独立控制台窗口，输出同时回显到下方日志区")
    else:
        log("后台无窗口运行中，输出写入 %s" % GATEWAY_LOG)

    ok, text = False, ""
    for _ in range(16):
        time.sleep(0.5)
        ok, text = probe_health(port, timeout=2)
        if ok:
            break
    if ok:
        log("探活成功: %s" % text, "ok")
    else:
        log("8 秒内未探活成功（%s）。可点「刷新状态」再看，或查看日志" % (text or "无响应"), "warn")
    return {"ok": True, "pid": proc.pid, "port": port, "health": ok, "health_text": text}


def stop_gateway():
    cfg = read_config()
    port = cfg_port(cfg)
    killed = kill_port(port)
    st = read_panel_state()
    if st.get("pid") and str(st["pid"]) not in killed:
        if kill_pid(st["pid"]):
            killed.append(str(st["pid"]))
    write_panel_state({})
    if killed:
        log("已停止网关进程 PID %s" % ",".join(killed), "ok")
    else:
        log("没有发现运行中的网关进程（端口 %d 空闲）" % port)
    return {"ok": True, "killed": killed}


def restart_gateway(mode="hidden"):
    stop_gateway()
    time.sleep(1)
    return start_gateway(mode)


# ───────────────────────── HTTP 服务 ─────────────────────────

class ApiHandler(SimpleHTTPRequestHandler):
    server_version = "WorkBuddy2API-Panel/1.0"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=UI_DIR, **kw)

    # 静音默认访问日志，避免控制台刷屏
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except Exception:
            pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            return {}

    def do_GET(self):
        u = urlsplit(self.path)
        p = u.path
        try:
            if p == "/api/state":
                return self._send(200, {"ok": True, "data": state_payload()})
            if p == "/api/logs":
                q = parse_qs(u.query)
                since = int((q.get("since") or ["0"])[0] or 0)
                return self._send(200, {"ok": True, "lines": logs_since(since),
                                        "next": LOG_ID})
            if p.startswith("/api/"):
                return self._send(404, {"ok": False, "error": "未知接口 " + p})
        except Exception:
            return self._send(500, {"ok": False, "error": traceback.format_exc(limit=6)})
        return super().do_GET()

    def do_POST(self):
        u = urlsplit(self.path)
        p = u.path
        body = self._body()
        try:
            if p == "/api/install":
                return self._send(200, do_install(body))
            if p == "/api/port/check":
                try:
                    port = int(body.get("port", 0))
                except Exception:
                    return self._send(200, {"ok": False, "error": "端口不合法"})
                pids = pids_on_port(port)
                return self._send(200, {"ok": True, "port": port, "pids": pids,
                                        "free": (not pids) and port_free(port)})
            if p == "/api/port/kill":
                port = int(body.get("port", cfg_port()))
                killed = kill_port(port)
                log("端口 %d：结束进程 %s" % (port, killed or "无"), "ok" if killed else "info")
                return self._send(200, {"ok": True, "killed": killed})
            if p == "/api/account/begin":
                return self._send(200, account_begin(body.get("realm", "cn")))
            if p == "/api/account/complete":
                return self._send(200, account_complete(body.get("realm", "cn"),
                                                        body.get("state", ""),
                                                        body.get("auto", True)))
            if p == "/api/account/delete":
                return self._send(200, account_delete(body.get("file", "")))
            if p == "/api/service/start":
                return self._send(200, start_gateway(body.get("mode", "console")))
            if p == "/api/service/stop":
                return self._send(200, stop_gateway())
            if p == "/api/service/restart":
                return self._send(200, restart_gateway(body.get("mode", "hidden")))
            if p == "/api/autostart":
                ok, msg = set_autostart(bool(body.get("enabled", False)))
                log("开机自启: %s" % msg, "ok" if ok else "warn")
                return self._send(200, {"ok": ok, "msg": msg})
            if p == "/api/models/refresh":
                return self._send(200, refresh_model_list())
            if p == "/api/models/list":
                models, src = fetch_model_list()
                return self._send(200, {"ok": True, "models": models,
                                        "source": src, "count": len(models)})
            if p == "/api/logs/clear":
                with LOG_LOCK:
                    LOGS.clear()
                return self._send(200, {"ok": True})
            if p == "/api/open":
                target = body.get("target", "root")
                path = {"root": ROOT, "auths": AUTHS_DIR, "logs": LOG_DIR,
                        "data": DATA_DIR}.get(target, ROOT)
                try:
                    subprocess.Popen(["explorer", path])
                    return self._send(200, {"ok": True})
                except Exception as e:
                    return self._send(200, {"ok": False, "error": str(e)})
            return self._send(404, {"ok": False, "error": "未知接口 " + p})
        except Exception:
            log("接口异常: %s" % traceback.format_exc(limit=6), "error")
            return self._send(500, {"ok": False, "error": traceback.format_exc(limit=6)})


def pick_port(start=8765, tries=20):
    for i in range(tries):
        port = start + i
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            s.close()
    return start


def main():
    port = 8765
    no_browser = False
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a in ("--port", "-p") and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except Exception:
                pass
        if a == "--no-browser":
            no_browser = True

    if not os.path.isdir(UI_DIR):
        print("缺少 ui/ 目录，界面文件不存在：%s" % UI_DIR)
        return 1

    port = pick_port(port)
    log("WorkBuddy2API 控制面板已启动")
    log("Python  : %s（%s）" % (sys.version.split()[0],
                              "项目自带 runtime/python" if bundled_python() else "系统 Python"))
    log("项目目录: %s" % ROOT)
    log("网关端口: %d（来自 config.json）" % cfg_port())
    svc = gateway_status()
    log("网关状态: %s" % ("运行中 PID %s" % svc["pid"] if svc["running"] else "未运行"))

    def tailer():
        try:
            pos = max(0, os.path.getsize(GATEWAY_LOG) - 6000)
        except Exception:
            pos = 0
        while True:
            try:
                size = os.path.getsize(GATEWAY_LOG)
                if size < pos:
                    pos = 0
                if size > pos:
                    with open(GATEWAY_LOG, "rb") as f:
                        f.seek(pos)
                        chunk = f.read(size - pos)
                        pos = size
                    for ln in chunk.decode("utf-8", "replace").splitlines():
                        if ln.strip():
                            log(ln, "out")
            except Exception:
                pass
            time.sleep(0.5)

    threading.Thread(target=tailer, daemon=True).start()

    url = "http://127.0.0.1:%d/" % port
    httpd = ThreadingHTTPServer(("127.0.0.1", port), ApiHandler)
    print("\n  控制面板地址: %s" % url)
    print("  按 Ctrl+C 退出（网关进程不受影响）\n")

    if not no_browser:
        threading.Thread(target=lambda: (time.sleep(0.8), webbrowser.open(url)),
                         daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出控制面板。")
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

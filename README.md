# WorkBuddy2API · Windows 控制面板（便携免安装版）

<p align="center">  
  <b>给 WorkBuddy2API 网关套一个图形界面 + 绿色运行环境，解压双击即用</b>  
  
  不用 Docker · 不用装 Go · 不用装 Python · 不用敲命令行  
</p>

<p align="center">  
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows%2010%2F11%20x64-0078D6?logo=windows\&logoColor=white\&style=flat-square">  
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12.10%20(内置)-3776AB?logo=python\&logoColor=white\&style=flat-square">  
  <img alt="Deps" src="https://img.shields.io/badge/Dependencies-零第三方依赖-16A34A?style=flat-square">  
  <img alt="License" src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square">  
  <img alt="UI" src="https://img.shields.io/badge/Web%20UI-127.0.0.1%3A8765-0DBD8B?style=flat-square">  
</p>

---

## 这个项目解决了什么

网关原本要在 Linux 上跑 Docker，或在 Windows 上手动装 Go、装 Python、敲一堆命令；加号之后还得记得手动重启网关才生效。

本仓库把这件事压缩成**三步点按钮**：

- 🟢 **免安装** — 内置 Python 运行环境，整目录拷贝 / 解压即用，不污染系统环境
- 🖥 **全图形界面** — 安装配置、加号登录、启动停止、账号与模型查看，全在同一个网页里，输出实时回显
- 🔁 **加号即生效** — 添加账号后自动重启网关并拉取该账号可用的模型列表，省掉「忘了重启」这个最常见的坑
- 📋 **接入信息直接给** — Trae / VS Code / Cline 等客户端要填的地址和密钥，界面里一键复制，并自动生成 `客户端配置.md`
- 🔧 **零依赖** — 控制面板只用 Python 标准库写成，不需要 pip 装任何东西

> 一句话：网关照常跑它的 Go 二进制，这个壳只负责把你从命令行里解放出来。

---

## 快速开始

### 环境要求

- Windows 10 / 11 x64
- 约 60 MB 磁盘空间（网关二进制 ~12 MB + 内置 Python ~22 MB）
- 一个或多个**本人授权使用**的 CodeBuddy / WorkBuddy 账号
- **不需要**管理员权限、**不需要** Docker / Go / Python

### 三步跑起来

```bat
1. 双击 0_panel.bat          :: 浏览器自动打开 http://127.0.0.1:8765
2. 界面① 点「一键安装 / 应用配置」
3. 界面② 点「获取登录链接」→ 浏览器登录 → 点「我已完成登录」
```

完成后网关已在后台运行，界面①底部可直接复制填入客户端的地址和密钥。

<details>

<summary>也保留原来的命令行入口</summary>

```bat
0_panel.bat          :: 控制面板（推荐）
1_3_install.bat      :: 命令行安装向导
2_addaccount.bat     :: 命令行加号
4_run.bat            :: 前台启动网关（带控制台窗口）
4_run-hidden.vbs     :: 后台启动网关（无窗口）
```

所有 bat / vbs 都会**优先使用项目自带的 `runtime\python\python.exe`**，找不到才回退系统 Python。

</details>

---

## 三个界面

### ① 安装 / 配置

- **环境检查** — Python 版本与来源（项目自带 / 系统）、Go 工具链、`wb2api.exe` 是否存在及体积时间
- **参数配置** — 监听端口（带占用检测，可一键结束占用进程）、API 密钥（不鉴权 / 自定义 / 随机生成）、对外 IP（自动探测局域网地址）
- **附加选项** — 开机自启（写当前用户「启动」文件夹，无需管理员）、完成后立即启动、刷新模型清单
- **产出** — 写 `config.json` → 生成 `4_run.bat` / `4_run-hidden.vbs` → 生成 `客户端配置.md`
- **客户端接入信息** — 网关地址、本机地址、API 密钥（可显隐）、探活地址、日志文件路径，均可一键复制

> ⚠️ 端口小贴士：`7863` 在 Windows 上常被 Hyper-V / Docker 预留导致绑定失败，**建议用 8080**。

### ② 添加账号 / 模型列表

按「🔗 获取登录链接 → 浏览器完成登录 → ✅ 我已完成登录」的顺序走，剩下的面板自动完成：

1. 用 OAuth 设备授权凭证换取 token，落盘 `auths/workbuddy-<uid>.json`
2. 国内版自动执行一次每日签到
3. **自动重启网关**（网关只在启动时加载 `auths/`，不重启新账号不会生效）
4. **自动拉取 `/v1/models`**，把该账号可用模型以表格展示：模型 ID、展示名、积分倍率、说明，支持搜索与复制 ID
5. 同时把清单写入 `models-trae.md` 供 Trae 参考

不想要自动重启？取消勾选「添加后自动重启网关并拉取模型列表」即可。下方还有已保存账号列表（昵称、UID、版本、token 剩余时长、删除）。

### ③ 启动网关

前台 / 后台合并成一个界面，卡片二选一：

| 模式             | 行为                              | 等价脚本               |
| -------------- | ------------------------------- | ------------------ |
| **后台隐藏启动**（默认） | 无窗口静默运行，输出写入 `logs/gateway.log` | `4_run-hidden.vbs` |
| **前台启动**       | 弹出独立控制台窗口                       | `4_run.bat`        |

两种模式的输出都会实时回显到界面底部统一的**执行日志**控制台（黑底终端样式，带自动滚动和清空）。

同页还有：运行状态（PID / 端口 / 启动方式 / 启动时间 / 探活 / 鉴权）、停止、重启、探活、`/status` 快捷打开、日志目录，以及开机自启开关。

---

## 目录结构

```
workbuddy2api-portable/
├─ 0_panel.bat              控制面板入口（推荐双击这个）
├─ 1_3_install.bat          命令行安装向导
├─ 2_addaccount.bat         命令行加号
├─ 4_run.bat                前台启动网关（安装时按端口自动生成）
├─ 4_run-hidden.vbs         后台启动网关（安装时自动生成）
│
├─ control_panel.py         控制面板后端（纯标准库，本地 HTTP 服务）
├─ install.py               安装逻辑
├─ addaccount.py            加号登录逻辑
├─ scripts/
│  └─ list_models.py        拉取并生成 models-trae.md
│
├─ ui/                      控制面板前端（HTML + CSS + JS，无框架、无 CDN）
├─ runtime/python/          内置 Python 3.12.10 Embeddable（含 LICENSE.txt）
├─ wb2api.exe               网关二进制
│
├─ config.json              网关配置（含密钥，已 gitignore）
├─ auths/                   账号凭证（隐私，已 gitignore）
├─ data/                    网关运行时状态
├─ logs/                    网关运行日志
├─ models-trae.md           可用模型清单（自动生成）
└─ 客户端配置.md             客户端接入说明（自动生成）
```

---

## 进阶说明

### 控制面板

```bat
0_panel.bat                      :: 默认端口 8765，自动打开浏览器
python control_panel.py --port 9000 --no-browser
```

- 只监听 `127.0.0.1`，外部机器无法访问控制面板本身；端口被占用时自动 +1
- 网关的对外地址由界面①的「对外访问 IP」决定，与面板端口无关
- 关掉面板**不会**停掉网关，两者是独立进程

### 客户端接入

| 客户端                         | API 地址                    | 备注                                               |
| --------------------------- | ------------------------- | ------------------------------------------------ |
| Trae CN                     | `http://<局域网IP>:<端口>/v1`  | 填 `127.0.0.1` 会 Connection refused，**必须用局域网 IP** |
| VS Code Copilot Chat (BYOK) | `.../v1/chat/completions` | 走 UI 配置，勿手改 JSON；`apiKey` 不要填明文                  |
| Cline / Roo Code / Continue | `http://<局域网IP>:<端口>/v1`  | 模型 ID 从 `models-trae.md` 选                       |

<https://mp.weixin.qq.com/s/cnr2qaDrLV7NfqRo0zJwbA>

账号池权重、熔断阈值、定时任务开关、双域适配等更细的配置字段，请查阅文末项目地址处的上游文档，本项目不重复搬运。

---

## 常见问题

**Q：双击没反应 / 一闪而过？**  
先确认 `runtime\python\python.exe` 存在；若被杀软拦截，把整个目录加白名单即可（Python Embeddable 是官方原版，非打包程序）。

**Q：加号成功了，为什么调用还是没额度 / 404？**  
网关只在**启动时**加载 `auths/`。界面②默认会自动重启；若你取消了自动重启，请到界面③手动点一次「重启网关」。

**Q：端口被占用怎么办？**  
界面①输入端口后点「检测占用」，会列出占用 PID，再点「结束占用进程」。注意确认那个 PID 不是别的程序。

**Q：Trae 里连不上？**  
用「对外访问 IP」探测到的**局域网 IP**，不要用 `127.0.0.1`；另外本机防火墙需放行该端口。

**Q：开机自启没生效？**  
自启脚本写在 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\WorkBuddy2API-Autostart.vbs`，只对当前用户生效，不需要管理员权限，可在界面③随时开关。

**Q：能不能给多人 / 公网用？**  
可以设密钥后局域网共用，但**不建议暴露到公网**。

---

## 安全须知

- 本项目是**非官方**网关封装，使用 CodeBuddy / WorkBuddy 账号作为上游，涉及目标平台服务条款与账号风险，**仅限本人授权账号、本机 / 私有环境使用**
- 不得用于账号共享、转售、违规分发，或违反目标平台条款的任何用途
- 妥善保管 `auths/`（明文凭证）与网关端口，**不要提交到 Git**——本仓库 `.gitignore` 已排除 `auths/`、`data/`、`config.json`、`logs/`
- 若需要自行编译网关二进制，请前往下方项目地址获取源码

---

## 开源许可 / 归属

本项目是网关的 Windows 封装与可视化面板，网关核心为预编译二进制，来自上游项目：

**<https://github.com/HanawaBanana/workbuddy2api>**

本仓库采用 **MIT License**，根目录 `LICENSE` 中保留了上游版权与许可声明，第三方组件清单见 [NOTICE.md](NOTICE.md)。本项目不授予任何上游（CodeBuddy / WorkBuddy）接口或服务的权利，使用者仍需自行遵守上游平台的服务条款。

🙏 如果本项目对你有帮助，请把 star 也给到上游仓库。

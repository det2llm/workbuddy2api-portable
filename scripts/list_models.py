#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从运行中的 workbuddy2api 拉取模型清单，生成 models-trae.md。

既可作为命令行工具，也可被 install.py 导入调用。

命令行:
    python scripts/list_models.py [base_url] [api_key]
    例: python scripts/list_models.py http://192.168.50.54:8080 1

作为库:
    from list_models import generate
    ok, msg = generate("http://127.0.0.1:8080", "1", "models-trae.md")
"""
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_OUT_NAME = "models-trae.md"


def fetch_models(base, key="", timeout=20):
    """GET /v1/models，返回模型列表（dict）。失败抛异常。"""
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/models",
        headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace")).get("data") or []


def _family(mid):
    if mid in ("cn:auto", "cn:fast-model", "cn:balanced-model", "cn:deep-model"):
        return "A. 自动 / 档位（推荐首选）"
    if "deepseek" in mid:
        return "B. DeepSeek 系"
    if "glm" in mid:
        return "C. GLM / 智谱"
    if "kimi" in mid:
        return "D. Kimi / 月之暗面"
    if "minimax" in mid:
        return "E. MiniMax"
    if "hunyuan" in mid or mid.startswith("cn:hy"):
        return "F. 混元 / 腾讯"
    if mid.startswith("cn:default"):
        return "G. Claude 系列"
    return "H. 其他"


def render_markdown(models, base, key):
    """把模型列表渲染成 markdown 文本。"""
    groups = {}
    for m in models:
        groups.setdefault(_family(m.get("id", "")), []).append(m)

    L = [
        "# WorkBuddy2API 可用模型清单（供 Trae CN 添加）",
        "",
        "- 网关地址：`%s/v1`" % base.rstrip("/"),
        "- API 密钥：`%s`" % (key or "（未启用鉴权）"),
        "- 共 **%d** 个模型" % len(models),
        "",
        "**说明**：「模型 ID」就是填到 Trae「模型 ID」输入框里的内容；"
        "带不带 `cn:` 前缀实测都能调用，推荐填写下面这份完整 ID。",
        "「倍率」= 积分消耗倍率，数字越小越省；`x0.00` 为当前免费档（可能有额度或排队限制）。",
        "",
    ]
    for g in sorted(groups):
        L += ["", "## " + g, "",
              "| 模型 ID | 展示名 | 倍率 | 说明 |", "|---|---|---|---|"]
        for m in groups[g]:
            desc = (m.get("description") or "").replace("|", "/")
            L.append("| `%s` | %s | %s | %s |" % (
                m.get("id", ""), m.get("name", ""), m.get("credits") or "-", desc))

    L += [
        "", "---", "", "## 面向 Trae 编程的推荐", "",
        "1. `cn:auto` — 自动匹配最优模型，最省心，日常首选",
        "2. `cn:glm-5.3` — 旗舰型，官方定位「复杂软件工程与长程 Agent 任务」，适合重活（x0.79）",
        "3. `cn:deepseek-v4-pro` — DeepSeek 旗舰，1M 上下文，适合大仓库 / 长上下文（x0.51）",
        "4. `cn:deepseek-v4.1-flash` — 极便宜（x0.03），1M 上下文且原生多模态，适合高频日常补全",
        "5. `cn:kimi-k3-1` — 前端开发能力突出、擅长长程自主任务，但最贵（x1.62）",
        "",
        "**免费档（x0.00）**：`cn:hy3`、`cn:hy4-preview-f`",
        "",
        "**Trae 里用不上的**：`cn:hunyuan-image-alpha-edit` 是图像编辑模型，写代码无需添加。",
        "",
    ]
    return "\n".join(L)


def generate(base, key="", out=None, timeout=20):
    """拉取并写入 models-trae.md。

    返回 (ok, msg)。**空列表时不覆盖已有文件** —— 网关在未加账号时
    /v1/models 会返回空数组，若此时覆盖会把有效清单刷没。
    """
    if out is None:
        out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           DEFAULT_OUT_NAME)
    try:
        models = fetch_models(base, key, timeout=timeout)
    except urllib.error.HTTPError as e:
        return False, "获取失败 HTTP %d（保留已有清单）" % e.code
    except Exception as e:
        return False, "获取失败：%s（保留已有清单）" % e

    if not models:
        return False, "网关返回 0 个模型（多半是尚未加号），保留已有清单"

    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write(render_markdown(models, base, key))
    except Exception as e:
        return False, "写入失败：%s" % e
    return True, "已更新 %d 个模型 -> %s" % (len(models), os.path.basename(out))


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
    key = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("WB2A_API_KEY", "")
    ok, msg = generate(base, key)
    print(("OK  " if ok else "SKIP") + "  " + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(1)

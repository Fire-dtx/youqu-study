#!/usr/bin/env python3
"""扫描本机 omp 会话记录，汇总电脑管家自动化测试相关会话到 .omp-sessions/。

数据源：
  ~/.omp/agent/sessions/**/*.jsonl   会话原始记录（含子代理会话）
  ~/.omp/agent/history.db            session_recaps / session_titles

用法：
  python3 .omp-sessions/scripts/scan_omp_sessions.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
SESSIONS_ROOT = HOME / ".omp" / "agent" / "sessions"
HISTORY_DB = HOME / ".omp" / "agent" / "history.db"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / ".omp-sessions"
SESS_DIR = OUT_DIR / "sessions"
TZ = timezone(timedelta(hours=8))

# 直接相关的工作目录：这些目录下的会话全部纳入（含子代理会话）
RELEVANT_ROOTS = [
    str(PROJECT_ROOT),
    str(HOME / "Documents/test/log/电脑管家自动化测试"),
    str(HOME / "Documents/TestCode/youqu-study"),
    str(HOME / "Documents/TestCode/youqu-ai"),
    str(HOME / "Documents/test/testyouqu-ai"),
    str(HOME / "Documents/TestCode/deepin-pc-manager"),
]

# 跨目录会话：用户提示词命中关键词才纳入（部署/执行/排障）
KEYWORD_RE = re.compile(r"电脑管家|pc[\s_-]?manager|youqu|manage\.py|allure", re.IGNORECASE)
# 本汇总会话自身：标题命中即排除，避免把运行时的不完整记录算进统计
SELF_TITLE_RE = re.compile(r"汇总电脑管家测试会话")

# 旧版 README 中的人工主题，保留原有中文口径；新会话用标题/任务自动生成
TOPIC_OVERRIDES = {
    "01a0851c-34e8": "youqu_ai wheel 安装失败",
    "01a08542-450e": "youqu-ai 与 multica 配合",
    "01a11a82-e92f": "manage.py run 报错排查",
    "01a152c1-b147": "UOS25 loong64 虚拟机与 youqu 部署",
    "01a15338-ad2b": "SSH 运行全套用例",
    "01a15718-eae7": "部署、CSV 去重与逐条执行",
    "01a1573a-55b4": "远程逐条执行 youqu 用例",
    "01a1614d-803b": "排查 manage.py run 失败",
    "01a16676-89c6": "Allure 套件列表乱码",
    "01a166bc-6d0a": "提交当前修改（10-23）",
    "01a177c5-936d": "部署到测试环境",
    "01a17c76-913f": "测试机部署与用例修复主线（最长会话）",
    "01a19a4e-ec7a": "梳理用例总数与 P1–P4 优先级",
    "01a1a9a1-e4b4": "V25 全量运行并生成报告",
    "01a1b071-2ba3": "提交当前修改（V20/V25 适配）",
    "01a1c315-8333": "系统垃圾日志类别核对（产品侧）",
    "01a1c8ba-180a": "逐条过检 PC 管家用例",
    "01a1cedc-0ea4": "核查/修复用例并统一收尾（152、055、316 等）",
    "01a1cf32-3809": "删除已废弃测试用例",
    "01a1cf61-e946": "控件查找日志与 setObjectName 排查",
    "01a1d50d-b6b6": "重写提交信息描述完整改动",
    "01a1d510-0685": "V25 批量运行并修复失败用例（工作树）",
    "01a1d539-e220": "克隆 youqu-study 仓库",
    "01a1e22c-2676": "youqu-ai conftest 乱码修复提交",
    "01a1e235-ae40": "分析 youqu-ai 项目架构",
    "01a1e30c-7fe9": "汇总电脑管家会话并做分享（生成本目录）",
    "01a1e3f7-55fa": "youqu-study 提交并推送",
    "01a1e742-b71b": "更新 621f0302 提交信息",
    "01a1e81b-a3b0": "汇总电脑管家 harness 会话（.deepseek-harness-sessions）",
    "01a1e867-8778": "分析 Product defects 并修复用例与软件源",
    "01a1e906-cbc0": "youqu-study 分片压缩 report tar 并清理",
    "01a1e8a0-d9e8": "统计 report_2026_11_17 的 1、2 级不通过用例",
    "01a1e90f-e0c4": "分片压缩 youqu-study.tar 并删除原文件",
}

# 上一版人工汇总（2026-11-16，README/ manifest 已被本次覆盖前的快照）的基线，
# 用于 README「与 2026-11-16 汇总的差异」；prompt_counts 取自上版索引表。
BASELINE_20261116 = {
    "generated_at": "2026-11-16 14:37",
    "sessions": 25,
    "user_prompts": 398,
    "assistant_messages": 4899,
    "requests": 13923,
    "prompt_counts": {
        "01a0851c-34e8": 2,
        "01a08542-450e": 1,
        "01a11a82-e92f": 2,
        "01a152c1-b147": 17,
        "01a15338-ad2b": 5,
        "01a15718-eae7": 59,
        "01a1573a-55b4": 20,
        "01a1614d-803b": 3,
        "01a16676-89c6": 4,
        "01a166bc-6d0a": 1,
        "01a177c5-936d": 6,
        "01a17c76-913f": 143,
        "01a19a4e-ec7a": 5,
        "01a1a9a1-e4b4": 14,
        "01a1b071-2ba3": 3,
        "01a1c315-8333": 7,
        "01a1c8ba-180a": 33,
        "01a1cedc-0ea4": 51,
        "01a1cf32-3809": 1,
        "01a1cf61-e946": 12,
        "01a1d50d-b6b6": 1,
        "01a1d510-0685": 4,
        "01a1d539-e220": 1,
        "01a1e22c-2676": 1,
        "01a1e235-ae40": 2,
    },
}

EXCLUDED_NOTES = [
    ("`-Documents/test/WingFuzz/…`（01a12e18 及其 4 个子会话）",
     "安装器模糊测试扫描；`youqu`/`用例` 仅出现在助手输出，不是电脑管家用例工作。"),
    ("`-Documents-TestCode/deepin-repair/…/UosRecoverySurvey.jsonl`",
     "磐石快照/急救箱调研子代理，只把 pc_manager 用例作为旁证引用。"),
    ("`-Documents/test/log/兼容问题确认/…`（01a176f2）",
     "控制中心 / uos-recovery 兼容问题确认，关键词误命中。"),
    ("`-Documents-TestCode/2026-10-19…01a151dd`",
     "GitHub 克隆超时排查，与电脑管家无关。"),
    ("`-Documents-TestCode/deepin-installer_gerrit`、`uos-recovery`、`deepin-repair` 等",
     "安装器 / 恢复类项目会话，非电脑管家自动化测试。"),
    ("`-Documents-TestCode-youqu_deepin_pc_manager/2026-11-18…01a1ec77`",
     "本次汇总会话本身，运行时记录不完整，不纳入统计。"),
]

TOOL_TOP_N = 8
PROMPT_CHAR_CAP = 4000
ASSISTANT_CHAR_CAP = 1500
ASSISTANT_BLOCK_CAP = 150


def load_recaps() -> dict[str, list[str]]:
    recaps: dict[str, list[str]] = {}
    if not HISTORY_DB.exists():
        return recaps
    try:
        conn = sqlite3.connect(f"file:{HISTORY_DB}?mode=ro", uri=True)
        rows = conn.execute(
            "select session_id, recap from session_recaps order by created_at"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return recaps
    for sid, recap in rows:
        recaps.setdefault(sid, []).append(recap)
    return recaps


def to_local(ts: str | None) -> str | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def in_relevant_root(cwd: str) -> bool:
    for root in RELEVANT_ROOTS:
        if cwd == root or cwd.startswith(root + os.sep):
            return True
    return False


PREFIX_RE = re.compile(r"^[^\w\u4e00-\u9fff]+")
KIND_PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9/ ]{1,12}:\s*")


def clean_title(title: str) -> str:
    title = (title or "").strip()
    title = PREFIX_RE.sub("", title)
    title = KIND_PREFIX_RE.sub("", title)
    return title.strip()


def text_of(message: dict) -> str:
    pieces = []
    for item in message.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            text = (item.get("text") or "").strip()
            if text:
                pieces.append(text)
    return "\n\n".join(pieces).strip()


def first_line(text: str, limit: int = 80) -> str:
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    line = re.sub(r"^[#>*\-\s]+", "", line)
    return line[:limit]


TASK_TARGET_RE = re.compile(r"#\s*(?:Target|目标)\s*\n+(.+)")


def shorten(line: str, limit: int = 40) -> str:
    if len(line) <= limit:
        return line
    window = line[: limit + 1]
    for sep in ("。", "；", "，", "、", "：", ":", ";", ",", " "):
        index = window.rfind(sep)
        if index >= limit // 2:
            return window[:index].rstrip()
    return window[:limit].rstrip()


def task_head(prompt: str, limit: int = 40) -> str:
    """从子代理任务书里取 `# Target` / `# 目标` 的首句，作为片段主题。"""
    match = TASK_TARGET_RE.search(prompt)
    if match:
        line = match.group(1)
    elif prompt.lstrip().startswith("Complete assignment"):
        return ""
    else:
        line = first_line(prompt, 200)
    line = re.sub(r"\s+", " ", line).strip().strip(":：").strip()
    return shorten(line.rstrip(" ，,、:："), limit)


def parse_session(path: Path) -> dict | None:
    sid = cwd = created = parent = None
    title = ""
    last_ts = None
    prompts: list[str] = []
    assistant_texts: list[str] = []
    models: dict[str, dict[str, int]] = {}
    tools: Counter[str] = Counter()
    try:
        fh = path.open(encoding="utf-8")
    except OSError:
        return None
    with fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            rtype = rec.get("type")
            ts = rec.get("timestamp")
            if isinstance(ts, str):
                last_ts = ts
            elif isinstance(ts, (int, float)):
                last_ts = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
            if rtype == "session":
                sid = rec.get("id")
                cwd = rec.get("cwd") or ""
                created = rec.get("timestamp")
                parent = rec.get("parentSession")
            elif rtype == "title" and rec.get("title"):
                title = rec["title"]
            elif rtype == "message":
                message = rec.get("message") or {}
                role = message.get("role")
                if role == "user":
                    text = text_of(message)
                    if text:
                        prompts.append(text)
                elif role == "assistant":
                    model = message.get("model") or "unknown"
                    stat = models.setdefault(
                        model,
                        {
                            "requests": 0,
                            "input": 0,
                            "output": 0,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                            "totalTokens": 0,
                        },
                    )
                    stat["requests"] += 1
                    usage = message.get("usage") or {}
                    for key in ("input", "output", "cacheRead", "cacheWrite", "totalTokens"):
                        value = usage.get(key)
                        if isinstance(value, (int, float)):
                            stat[key] += int(value)
                    text = text_of(message)
                    if text:
                        assistant_texts.append(text)
            elif rtype == "custom" and rec.get("customType") == "tool_execution_start":
                tool_name = (rec.get("data") or {}).get("toolName")
                if tool_name:
                    tools[tool_name] += 1
    if not sid or not cwd:
        return None
    parent_id = None
    if parent:
        stem = Path(parent).stem
        parent_id = stem.split("_", 1)[1] if "_" in stem else stem
    return {
        "id": sid,
        "parent_id": parent_id,
        "cwd": cwd,
        "created": created,
        "last_activity": last_ts,
        "title": title,
        "prompts": prompts,
        "assistant_texts": assistant_texts,
        "models": models,
        "tools": dict(tools),
        "raw": str(path),
        "kind": "subagent" if parent_id else "top",
    }


def main_model(models: dict) -> str:
    if not models:
        return "-"
    return max(models.items(), key=lambda kv: kv[1]["requests"])[0]


def fmt_int(value: int) -> str:
    return f"{value:,}"


def slugify(label: str, fallback: str) -> str:
    slug = re.sub(r'[\\/:*?"<>|：\s]+', "-", label).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug[:48].strip("-")
    return slug or fallback


HEADING_RE = re.compile(r"(?m)^(\s{0,3})(#{1,6})(?=\s)")


def escape_headings(text: str) -> str:
    """嵌入会话原文时转义行首标题，避免破坏汇总文档的大纲结构。"""
    return HEADING_RE.sub(r"\1\\\2", text)


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n\n…（截断，原文 {len(text)} 字符）"


def relative_project(cwd: str) -> str:
    home = str(HOME)
    if cwd == home:
        return "~"
    if cwd.startswith(home + os.sep):
        return "~/" + cwd[len(home) + 1:]
    return cwd


def render_markdown(session: dict, label: str, recaps: list[str]) -> str:
    usage = {
        key: sum(m[key] for m in session["models"].values())
        for key in ("input", "output", "cacheRead", "cacheWrite", "totalTokens")
    }
    kind = "子代理/分片会话" if session["kind"] == "subagent" else "顶层会话"
    if session["parent_id"]:
        kind += f"（父会话 `{session['parent_id'][:13]}`，片段 `{session['title'] or Path(session['raw']).stem}`）"
    tool_top = ", ".join(
        f"{name}×{count}"
        for name, count in sorted(session["tools"].items(), key=lambda kv: -kv[1])[:TOOL_TOP_N]
    ) or "-"
    model_line = ", ".join(
        f"{name} × {stat['requests']}"
        for name, stat in sorted(session["models"].items(), key=lambda kv: -kv[1]["requests"])
    ) or "-"
    lines = [
        f"# {label}",
        "",
        f"- 会话 ID: `{session['id'][:13]}`",
        f"- 类型: {kind}",
        f"- 项目目录: `{session['cwd']}`",
        f"- 创建时间: {to_local(session['created']) or '-'}",
        f"- 最后活动: {to_local(session['last_activity']) or '-'}",
        f"- 消息: 用户提示词 {len(session['prompts'])} / 助手文本 {len(session['assistant_texts'])}"
        f" / 模型请求 {sum(m['requests'] for m in session['models'].values())}",
        f"- 模型: {model_line}",
        f"- Token: input={fmt_int(usage['input'])}, output={fmt_int(usage['output'])}, "
        f"cacheRead={fmt_int(usage['cacheRead'])}, total={fmt_int(usage['totalTokens'])}",
        f"- 工具调用 Top: {tool_top}",
        f"- 原始记录: `{session['raw']}`",
        "",
        "## 用户提示词",
        "",
    ]
    if session["prompts"]:
        for index, prompt in enumerate(session["prompts"], 1):
            lines += [f"### U{index}", "", clip(escape_headings(prompt), PROMPT_CHAR_CAP), ""]
    else:
        lines += ["（无用户文本提示词）", ""]
    lines += ["## 助手输出（按时间顺序，已省略 thinking 与工具参数）", ""]
    texts = session["assistant_texts"]
    for index, text in enumerate(texts[:ASSISTANT_BLOCK_CAP], 1):
        lines += [f"### A{index}", "", clip(escape_headings(text), ASSISTANT_CHAR_CAP), ""]
    if len(texts) > ASSISTANT_BLOCK_CAP:
        lines += [f"（其余 {len(texts) - ASSISTANT_BLOCK_CAP} 条助手文本略）", ""]
    if recaps:
        lines += ["## omp 空闲摘要（recap，最新在前）", ""]
        for recap in reversed(recaps):
            lines += [f"- {recap}", ""]
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    recaps = load_recaps()
    manifest_path = OUT_DIR / "manifest.json"

    parsed: list[dict] = []
    for path in sorted(SESSIONS_ROOT.rglob("*.jsonl")):
        session = parse_session(path)
        if session:
            parsed.append(session)
    parsed_by_id = {item["id"]: item for item in parsed}

    def included(session: dict) -> bool:
        if SELF_TITLE_RE.search(session["title"]):
            return False
        if session["kind"] == "subagent":
            parent = parsed_by_id.get(session["parent_id"] or "")
            if parent and not SELF_TITLE_RE.search(parent["title"]):
                if in_relevant_root(parent["cwd"]) or any(
                    KEYWORD_RE.search(p) for p in parent["prompts"]
                ):
                    return True
            if in_relevant_root(session["cwd"]):
                return True
            return any(KEYWORD_RE.search(p) for p in session["prompts"])
        if in_relevant_root(session["cwd"]):
            return True
        return any(KEYWORD_RE.search(p) for p in session["prompts"])

    selected = [item for item in parsed if included(item)]
    selected.sort(key=lambda item: item["created"] or "", reverse=True)

    # 生成每会话 markdown
    if SESS_DIR.exists():
        shutil.rmtree(SESS_DIR)
    SESS_DIR.mkdir(parents=True)

    manifest_sessions = []
    for session in selected:
        fallback = Path(session["raw"]).stem.split("_")[-1]
        override = TOPIC_OVERRIDES.get(session["id"][:13])
        if session["kind"] == "subagent":
            stem = Path(session["raw"]).stem
            head = task_head(session["prompts"][0]) if session["prompts"] else ""
            label = override or (f"{stem}：{head}" if head else stem)
        else:
            label = override or clean_title(session["title"]) or (
                first_line(session["prompts"][0]) if session["prompts"] else fallback
            )
        date = (to_local(session["created"]) or "0000-00-00")[:10]
        filename = f"{date}-{session['id'][:13]}-{slugify(clean_title(label), 'session')}.md"
        md_path = SESS_DIR / filename
        md_path.write_text(
            render_markdown(session, label, recaps.get(session["id"], [])), encoding="utf-8"
        )
        total_usage = {
            key: sum(m[key] for m in session["models"].values())
            for key in ("input", "output", "cacheRead", "cacheWrite", "totalTokens")
        }
        manifest_sessions.append(
            {
                "id": session["id"][:13],
                "label": label,
                "kind": session["kind"],
                "parent": session["parent_id"][:13] if session["parent_id"] else None,
                "project": session["cwd"],
                "created": to_local(session["created"]),
                "last_activity": to_local(session["last_activity"]),
                "file": str(md_path),
                "user_prompts": len(session["prompts"]),
                "assistant_messages": len(session["assistant_texts"]),
                "requests": sum(m["requests"] for m in session["models"].values()),
                "models": session["models"],
                "usage": total_usage,
                "tools": session["tools"],
                "recaps": recaps.get(session["id"], []),
                "raw": session["raw"],
            }
        )

    # 汇总统计
    totals = {
        key: sum(row["usage"][key] for row in manifest_sessions)
        for key in ("input", "output", "cacheRead", "cacheWrite", "totalTokens")
    }
    models_total: dict[str, dict[str, int]] = {}
    tools_total: Counter[str] = Counter()
    for row in manifest_sessions:
        for model, stat in row["models"].items():
            acc = models_total.setdefault(
                model,
                {
                    "requests": 0,
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                    "totalTokens": 0,
                },
            )
            for key in acc:
                acc[key] += stat[key]
        tools_total.update(row["tools"])
    top_level = [row for row in manifest_sessions if row["kind"] == "top"]
    subagent = [row for row in manifest_sessions if row["kind"] == "subagent"]
    created_dates = [row["created"][:10] for row in manifest_sessions if row["created"]]

    base_counts = BASELINE_20261116["prompt_counts"]
    new_top = [row for row in top_level if row["id"] not in base_counts]
    grown_rows = [
        (row, row["user_prompts"] - base_counts[row["id"]])
        for row in top_level
        if base_counts.get(row["id"]) is not None
        and row["user_prompts"] > base_counts[row["id"]]
    ]
    top_totals = {
        "user_prompts": sum(row["user_prompts"] for row in top_level),
        "assistant_messages": sum(row["assistant_messages"] for row in top_level),
        "requests": sum(row["requests"] for row in top_level),
    }
    subagent_by_parent = Counter(row["parent"] for row in subagent)
    label_by_id = {row["id"]: row["label"] for row in manifest_sessions}

    # README
    readme = []
    readme += [
        "# omp 会话汇总：电脑管家自动化测试用例（本机存档）",
        "",
        f"> 采集时间：{datetime.now(TZ).strftime('%Y-%m-%d %H:%M')} ｜ "
        "数据源：`~/.omp/agent/sessions/**/*.jsonl`、`~/.omp/agent/history.db`",
        "> 范围：本机所有 omp 会话中，实际处理 **youqu_deepin_pc_manager（电脑管家自动化测试）** "
        "的部署、执行、用例修复、报告分析与框架支撑会话；子代理/分片会话单独收录。",
        "> **注意：原始内容含内网 IP、测试机账号与密码、产品源码路径，仅限内部使用，"
        "不要提交到公开仓库或外发。**",
        "",
        "---",
        "",
        "## 1. 采集口径",
        "",
        "纳入条件（满足其一）：",
        "",
        "1. 工作目录属于 `youqu_deepin_pc_manager`、`Documents/test/log/电脑管家自动化测试`、"
        "`youqu-study`、`youqu-ai`、`deepin-pc-manager`（产品侧）等直接相关目录；",
        "2. 跨目录会话（`tmp`、`Documents/test`、`TestCode`）的用户提示词命中 "
        "`电脑管家`、`pc_manager`、`youqu`、`manage.py`、`allure`，且内容确为部署、执行或修复电脑管家用例；",
        "3. 直接父会话被纳入的子代理/分片会话（`parentSession` 指向已纳入会话）。",
        "",
        "排除：与电脑管家无关的安装器/恢复/备份/专利/日志类会话；关键词误命中的其他项目会话；"
        "纯问候/空会话；本次汇总会话自身。",
        "",
        f"最终纳入 **{len(manifest_sessions)} 个会话**"
        f"（顶层 {len(top_level)} + 子代理/分片 {len(subagent)}）。",
        "",
        "## 2. 统计总览",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 会话数 | {len(manifest_sessions)} |",
        f"| 顶层 / 子代理 | {len(top_level)} / {len(subagent)} |",
        f"| 时间跨度 | {min(created_dates)} → {max(created_dates)} |",
        f"| 用户提示词 | {sum(row['user_prompts'] for row in manifest_sessions)} |",
        f"| 助手文本消息 | {sum(row['assistant_messages'] for row in manifest_sessions)} |",
        f"| 模型请求 | {sum(row['requests'] for row in manifest_sessions)} |",
        f"| 输入 tokens | {fmt_int(totals['input'])} |",
        f"| 输出 tokens | {fmt_int(totals['output'])} |",
        f"| 缓存读 tokens | {fmt_int(totals['cacheRead'])} |",
        f"| 总 tokens | {fmt_int(totals['totalTokens'])} |",
        "",
        "> 统计口径：上表包含子代理/分片会话的全部请求与 token；"
        "父会话与子代理是各自独立的会话文件，不做去重合并。",
        "",
        "### 模型参与（按实际请求统计）",
        "",
        "| 模型 | 请求数 | 输入 | 输出 | 缓存读 | 总 tokens |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model, stat in sorted(models_total.items(), key=lambda kv: -kv[1]["requests"]):
        readme.append(
            f"| `{model}` | {fmt_int(stat['requests'])} | {fmt_int(stat['input'])} | "
            f"{fmt_int(stat['output'])} | {fmt_int(stat['cacheRead'])} | {fmt_int(stat['totalTokens'])} |"
        )
    readme += [
        "",
        "### 工作目录分布",
        "",
        "| 目录 | 会话数 |",
        "|---|---:|",
    ]
    cwd_count = Counter(relative_project(row["project"]) for row in manifest_sessions)
    for cwd, count in cwd_count.most_common():
        readme.append(f"| `{cwd}` | {count} |")

    readme += [
        "",
        "## 3. 顶层会话索引",
        "",
        "| 日期 | 会话 ID | 工作目录 | 主题 | 用户轮次 | 最后活动 | 主要模型 |",
        "|---|---|---|---|---:|---|---|",
    ]
    for row in top_level:
        readme.append(
            f"| {row['created'][:10]} | `{row['id']}` | {relative_project(row['project'])} | "
            f"{row['label']} | {row['user_prompts']} | {row['last_activity'][:16]} | "
            f"`{main_model(row['models'])}` |"
        )

    readme += [
        "",
        "## 4. 子代理 / 分片会话",
        "",
        "这些会话由父会话的 `task` 子代理产生，文件位于父会话同名目录下；"
        "父会话 ID 见「父会话」列。",
        "",
        "| 日期 | 会话 ID | 父会话 | 片段 | 用户提示词 | 模型请求 |",
        "|---|---|---|---|---:|---:|",
    ]
    for row in subagent:
        stem = Path(row["raw"]).stem
        readme.append(
            f"| {row['created'][:10]} | `{row['id']}` | `{row['parent']}` | {stem} | "
            f"{row['user_prompts']} | {row['requests']} |"
        )

    readme += [
        "",
        "## 5. 与 2026-11-16 汇总的差异",
        "",
        f"上一版汇总（{BASELINE_20261116['generated_at']}）：25 个顶层会话、"
        f"{BASELINE_20261116['user_prompts']} 条用户提示词、"
        f"{BASELINE_20261116['assistant_messages']} 条助手文本、"
        f"{fmt_int(BASELINE_20261116['requests'])} 次模型请求；未收录子代理会话。",
        "",
        "| 指标 | 2026-11-16（仅顶层） | 本次（仅顶层） | 本次（含子代理） |",
        "|---|---:|---:|---:|",
        f"| 会话数 | {BASELINE_20261116['sessions']} | {len(top_level)} | {len(manifest_sessions)} |",
        f"| 用户提示词 | {BASELINE_20261116['user_prompts']} | {top_totals['user_prompts']} | "
        f"{sum(row['user_prompts'] for row in manifest_sessions)} |",
        f"| 助手文本消息 | {BASELINE_20261116['assistant_messages']} | "
        f"{top_totals['assistant_messages']} | {sum(row['assistant_messages'] for row in manifest_sessions)} |",
        f"| 模型请求 | {fmt_int(BASELINE_20261116['requests'])} | {fmt_int(top_totals['requests'])} | "
        f"{fmt_int(sum(row['requests'] for row in manifest_sessions))} |",
        "",
        f"### 新增顶层会话（{len(new_top)} 个，相对 2026-11-16）",
        "",
    ]
    if new_top:
        readme += ["| 日期 | 会话 ID | 工作目录 | 主题 |", "|---|---|---|---|"]
        for row in new_top:
            readme.append(
                f"| {row['created'][:10]} | `{row['id']}` | {relative_project(row['project'])} | "
                f"{row['label']} |"
            )
    else:
        readme.append("（无新增顶层会话）")

    readme += ["", f"### 已收录会话的续跑增量（{len(grown_rows)} 个，按提示词数）", ""]
    if grown_rows:
        readme += ["| 会话 ID | 主题 | 11-16 提示词 | 本次提示词 | 增量 |", "|---|---|---:|---:|---:|"]
        for row, delta in grown_rows:
            readme.append(
                f"| `{row['id']}` | {row['label']} | {base_counts[row['id']]} | "
                f"{row['user_prompts']} | {delta:+d} |"
            )
    else:
        readme.append("（无续跑增量）")

    readme += [
        "",
        f"### 新增子代理/分片会话（{len(subagent)} 个）",
        "",
        "上一版汇总未收录子代理会话；本次按 `parentSession` 归入父会话。",
        "",
        "| 父会话 | 父会话主题 | 子会话数 |",
        "|---|---|---:|",
    ]
    for parent_id, count in subagent_by_parent.most_common():
        readme.append(f"| `{parent_id}` | {label_by_id.get(parent_id, '-')} | {count} |")

    readme += [
        "",
        "## 6. 目录结构",
        "",
        "```",
        ".omp-sessions/",
        "├── README.md              # 本文件：口径、统计、索引",
        "├── manifest.json          # 结构化清单：会话元数据、模型/请求/token、recaps",
        "├── scripts/",
        "│   └── scan_omp_sessions.py  # 重新扫描脚本",
        "└── sessions/",
        "    └── <日期>-<会话ID>-<主题>.md",
        "        ├── 元数据（项目目录、时间、消息数、模型、token、工具调用 Top、原始 JSONL 路径）",
        "        ├── 用户提示词全文（U1..Un，超长截断）",
        "        └── 助手输出文本（A1..An，已省略 thinking 与工具参数）",
        "```",
        "",
        "## 7. 未纳入的相近会话",
        "",
        "| 会话/目录 | 原因 |",
        "|---|---|",
    ]
    for where, reason in EXCLUDED_NOTES:
        readme.append(f"| {where} | {reason} |")
    readme += [
        "",
        "> 本目录只覆盖 omp 会话；deepseek-harness 与 Multica 的会话分别在 "
        "`.deepseek-harness-sessions/`、`.multica-sessions/` 中，口径与字段不同，未合并统计。",
        "",
        "## 8. 使用说明",
        "",
        "1. 做分享/复盘时先读 `.share/分享-基于有趣测试框架用AI构建电脑管家自动化测试.md`"
        "（已脱敏，可对外分享），本目录用于定位原始证据；再按主题进入具体会话。",
        "2. 会话中的 `recap` 是 omp 在会话空闲时写的摘要，适合快速定位；"
        "**结论以原始消息和仓库当前代码为准**，摘要可能滞后。",
        "3. 重新汇总：`python3 .omp-sessions/scripts/scan_omp_sessions.py`"
        "（覆盖 `sessions/` 与 `manifest.json`，并在 README 中记录相对上次的差异）。",
        "4. 会话里出现的测试机地址、账号、密码、Gerrit 凭据仅为历史记录；"
        "不要复制到代码、文档模板或公开材料中。",
        "",
    ]
    (OUT_DIR / "README.md").write_text("\n".join(readme), encoding="utf-8")

    manifest = {
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "source": "omp session archive (~/.omp/agent/sessions)",
        "scope": "youqu_deepin_pc_manager / 电脑管家自动化测试 / youqu 框架与测试机部署执行相关会话",
        "criteria": [
            "工作目录属于相关项目目录",
            "跨目录会话的用户提示词命中电脑管家/youqu/manage.py/allure 等关键词",
            "已纳入父会话的子代理/分片会话",
        ],
        "summary": {
            "sessions": len(manifest_sessions),
            "top_level": len(top_level),
            "subagent": len(subagent),
            "user_prompts": sum(row["user_prompts"] for row in manifest_sessions),
            "assistant_messages": sum(row["assistant_messages"] for row in manifest_sessions),
            "requests": sum(row["requests"] for row in manifest_sessions),
            "time_span": {"first": min(created_dates), "last": max(created_dates)},
            "usage": totals,
            "models": models_total,
            "tools": dict(tools_total.most_common(20)),
        },
        "sessions": manifest_sessions,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"扫描完成：{len(manifest_sessions)} 个会话"
        f"（顶层 {len(top_level)} / 子代理 {len(subagent)}），"
        f"新增顶层 {len(new_top)}，`{OUT_DIR}`"
    )


if __name__ == "__main__":
    main()

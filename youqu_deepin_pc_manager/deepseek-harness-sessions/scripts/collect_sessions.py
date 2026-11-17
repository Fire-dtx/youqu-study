#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采集本机 DeepSeek Harness(dsh) 中与「电脑管家自动化测试用例」相关的会话。

用法:
    python3 .deepseek-harness-sessions/scripts/collect_sessions.py [--root ~/.dsh/sessions] [--out .deepseek-harness-sessions]

产物:
    index.json / sessions.csv / cases.json / cases.md / sessions.md / README.md
    digests/<日期>/<HHMM>_<session>.md
    raw/<project>/<session>/<session file>   原始压缩会话副本
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections import Counter, OrderedDict

PROJECT_KEYWORD = "youqu_deepin_pc_manager"
PROJECT_PATH_HINT = "/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager"
CASE_RE = re.compile(r"\b(20\d{5})\b")
TZ = dt.timezone(dt.timedelta(hours=8))


def human_time(ms):
    if not ms:
        return ""
    return dt.datetime.fromtimestamp(ms / 1000, TZ).strftime("%Y-%m-%d %H:%M:%S")


def md_escape(text, limit=None):
    if text is None:
        text = ""
    text = str(text).replace("\r", " ").replace("\n", " ").replace("|", "\\|")
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def unescape_layer(text):
    """解开一层 JSON 字符串转义（用于解析嵌套在 tool 结果里的 JSON）。"""
    out = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == "n":
                out.append("\n"); i += 2; continue
            if nxt == "t":
                out.append("\t"); i += 2; continue
            if nxt in '\\"':
                out.append(nxt); i += 2; continue
        out.append(text[i]); i += 1
    return "".join(out)


def content_text(content):
    if isinstance(content, str):
        return content
    out = []
    for item in content or []:
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
            out.append(item["text"])
    return "\n".join(out)


def balanced_object(text, start):
    """从 text[start] 的 '{' 起提取一个括号平衡的 JSON 对象。"""
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def parse_json_prefix(text):
    """解析前缀为 'EXIT: n\\n' 等噪声后跟 JSON 对象的文本。"""
    idx = text.find("{")
    if idx < 0:
        return None
    return balanced_object(text, idx)


def parse_records(code_text):
    records = []
    for m in re.finditer(r"harness\.py\s+record\b", code_text):
        tail = code_text[m.end() : m.end() + 6000]
        case_id = re.search(r"--id\s+(\d{5,8})", tail)
        result = re.search(r"--result\s+(pass|fail|blocked|skip|error)\b", tail)
        runs = re.search(r"--runs\s+(\d+)", tail)
        if not (case_id and result):
            continue
        note = ""
        nm = re.search(r"--note\s+(['\"])", tail)
        if nm:
            quote = nm.group(1)
            start = nm.end()
            i = start
            esc = False
            while i < len(tail):
                ch = tail[i]
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == quote:
                    break
                i += 1
            note = tail[start:i]
            note = note.replace("\\n", " ").replace("\\t", " ").replace('\\"', '"').replace("\\'", "'")
        records.append(
            {
                "id": case_id.group(1),
                "result": result.group(1),
                "runs": int(runs.group(1)) if runs else None,
                "note": re.sub(r"\s+", " ", note).strip(),
            }
        )
    # 去重并保持顺序
    uniq, seen = [], set()
    for r in records:
        key = (r["id"], r["result"], r["runs"], r["note"])
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq


def parse_session_file(path):
    raw = subprocess.run(["zstd", "-dc", path], capture_output=True, check=False)
    if raw.returncode != 0:
        raise RuntimeError(f"zstd 解压失败: {path}: {raw.stderr.decode('utf-8', 'replace')[:200]}")
    text = raw.stdout.decode("utf-8", "replace")

    sess = {
        "sessionId": "",
        "cwd": None,
        "title": None,
        "createdAt": None,
        "lastTime": None,
        "preset": None,
        "turns": 0,
        "prompt": "",
        "finalText": "",
        "toolErrors": 0,
        "busy": False,
        "done": False,
        "records": [],
        "nextCase": None,
        "referencedCaseIds": [],
        "runCommands": [],
        "recordResults": [],
        "historyEvents": [],
    }
    finals, tool_texts, code_chunks = [], [], []
    usage = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0, "cacheReadTokens": 0}
    models = Counter()
    end_reason = None
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = obj.get("type")
        data = obj.get("data") or {}
        if etype == "session":
            sess["cwd"] = obj.get("cwd") or data.get("cwd")
            sess["createdAt"] = obj.get("createdAt") or sess["createdAt"]
            sess["preset"] = data.get("agentPreset") or obj.get("agentPreset")
            sess["sessionId"] = obj.get("id") or sess["sessionId"]
        elif etype == "session/title":
            sess["title"] = data.get("title")
        elif etype == "turn/start":
            sess["turns"] += 1
        elif etype == "user/message":
            if (data.get("source") or {}).get("kind") == "schedule" and not sess["prompt"]:
                sess["prompt"] = content_text(data.get("content"))
        elif etype == "assistant/message":
            msg = data.get("message") or {}
            src = msg.get("source") or {}
            if src.get("model"):
                models[src.get("model")] += 1
            u = data.get("usage") or {}
            for key in usage:
                try:
                    usage[key] += int(u.get(key) or 0)
                except (TypeError, ValueError):
                    pass
            txt = content_text(msg.get("content"))
            if txt:
                finals.append(txt)
            for item in msg.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "tool-call":
                    args = item.get("arguments")
                    if isinstance(args, str):
                        code_chunks.append(args)
                    elif isinstance(args, dict):
                        code_chunks.append(json.dumps(args, ensure_ascii=False))
        elif etype == "tool/call":
            args = data.get("arguments")
            if isinstance(args, str):
                code_chunks.append(args)
            elif isinstance(args, dict):
                code_chunks.append(json.dumps(args, ensure_ascii=False))
        elif etype == "tool/result":
            msg = data.get("message") or {}
            txt = content_text(msg.get("content")) if isinstance(msg, dict) else content_text(data.get("content"))
            if txt:
                tool_texts.append(txt)
            if data.get("isError") or (isinstance(msg, dict) and msg.get("isError")):
                sess["toolErrors"] += 1
        elif etype == "turn/end":
            reason = data.get("reason") or {}
            if reason.get("kind") == "error":
                err = reason.get("error") or {}
                end_reason = f"{err.get('code') or 'ERROR'}: {err.get('message') or ''}".strip()
            elif reason.get("kind"):
                end_reason = reason.get("kind")
        elif etype == "job/registered":
            label = data.get("label")
            if isinstance(label, str):
                code_chunks.append(label)
        if obj.get("time"):
            sess["lastTime"] = obj.get("time")

    for chunk in code_chunks:
        try:
            parsed = json.loads(chunk)
            code = parsed.get("code") or parsed.get("command") or ""
            if isinstance(code, str):
                chunk = code
        except (json.JSONDecodeError, AttributeError):
            pass
        sess["records"].extend(parse_records(chunk))
        for m in re.finditer(r"run_case\.sh\s+\d{5,8}\s+\w+[^\n\"']{0,120}", chunk):
            if len(sess["runCommands"]) < 5:
                sess["runCommands"].append(re.sub(r"\s+", " ", m.group(0)).strip())

    # 同一用例同结果同 runs 只保留备注最完整的一条
    merged = OrderedDict()
    for r in sess["records"]:
        key = (r["id"], r["result"], r["runs"])
        old = merged.get(key)
        if old is None or len(r["note"]) > len(old["note"]):
            merged[key] = r
    sess["records"] = list(merged.values())
    sess["finalText"] = finals[-1] if finals else ""
    sess["usage"] = usage
    sess["models"] = dict(models)
    sess["endReason"] = end_reason

    blob = "\n".join(finals + tool_texts + code_chunks)
    # 从工具输出里提取 record 的真实返回值与 history 事件
    hist_pat = re.compile(
        r"(\d{4}-\d\d-\d\dT[0-9:+\-]+)\s+(claim|reclaim|record|release)\s+(\d{5,8})\s*(.*)"
    )
    for txt in tool_texts:
        probe = txt
        for depth in range(2):
            for m in re.finditer(r'\{\s*"ok"\s*:\s*true', probe):
                obj = balanced_object(probe, m.start())
                if not isinstance(obj, dict) or not obj.get("caseId"):
                    continue
                item = {
                    "id": str(obj.get("caseId")),
                    "status": obj.get("status"),
                    "counts": obj.get("counts") or {},
                    "total": obj.get("total"),
                }
                if item not in sess["recordResults"]:
                    sess["recordResults"].append(item)
            for m in hist_pat.finditer(probe):
                ev = {"ts": m.group(1), "event": m.group(2), "id": m.group(3), "note": m.group(4).strip()}
                if ev not in sess["historyEvents"]:
                    sess["historyEvents"].append(ev)
            if depth == 0:
                probe = unescape_layer(probe)
    known_ids = {r["id"] for r in sess["records"]}
    for rr in sess["recordResults"]:
        if rr["id"] in known_ids:
            continue
        note = ""
        for ev in reversed(sess["historyEvents"]):
            if ev["id"] == rr["id"] and ev["event"] == "record" and ev["note"]:
                note = ev["note"]
                break
        sess["records"].append(
            {
                "id": rr["id"],
                "result": "pass" if rr.get("status") == "passed" else "fail",
                "runs": None,
                "note": note,
                "source": "record-output",
            }
        )
        known_ids.add(rr["id"])
    # next 返回的用例对象（外层对象里含 done/case 字段）
    for txt in tool_texts:
        probe = txt
        for depth in range(2):
            dpos = probe.find('"done"')
            if dpos >= 0:
                brace = probe.rfind("{", 0, dpos)
                obj = balanced_object(probe, brace) if brace >= 0 else None
                if isinstance(obj, dict) and isinstance(obj.get("case"), dict):
                    sess["nextCase"] = obj["case"]
                    break
            if depth == 0:
                probe = unescape_layer(probe)
        if sess["nextCase"]:
            break
    # 引用到的用例编号（仅作上下文，不等同于处理）
    ids, seen_ids = [], set()
    for cid in CASE_RE.findall(blob):
        if cid not in seen_ids:
            seen_ids.add(cid)
            ids.append(cid)
    sess["referencedCaseIds"] = ids
    blob_unescaped = unescape_layer(blob)
    sess["busy"] = bool(
        re.search(r'"busy"\s*:\s*true', blob_unescaped)
        and re.search(r'"heartbeatAgeSec"\s*:', blob_unescaped)
    )
    sess["done"] = bool(re.search(r'"done"\s*:\s*true', blob_unescaped))
    sess["executed"] = {
        "record": bool(re.search(r"harness\.py\s+record\b", "\n".join(code_chunks))),
        "release": bool(re.search(r"harness\.py\s+release\b", "\n".join(code_chunks))),
        "requeue": bool(re.search(r"harness\.py\s+requeue-failed\b", "\n".join(code_chunks))),
        "next": bool(re.search(r"harness\.py\s+next\b", "\n".join(code_chunks))),
    }
    return sess, text


def classify(sess):
    title = sess.get("title") or ""
    final = sess.get("finalText") or ""
    executed = sess.get("executed") or {}
    if "监控恢复" in title:
        if sess["records"] or sess.get("recordResults") or executed.get("release") or executed.get("requeue") or executed.get("record"):
            return "监控恢复-介入", "recover"
        return "监控恢复-巡检", "normal"
    if "用例过检自动化任务" in title:
        return "编排任务", "task"
    if sess["records"]:
        results = {r["result"] for r in sess["records"]}
        return "单条处理-recorded", "+".join(sorted(results))
    if sess.get("endReason", "").startswith("AUTH"):
        return "未执行-鉴权失败", "auth-error"
    if sess.get("endReason", "").startswith("ERROR"):
        return "未执行-运行错误", "error"
    if re.search(r"测试机不可达|测试机失联|No route|环境阻断|无法执行|未执行|失联|SYNC_FAILED", final):
        return "单条处理-环境阻断", "blocked"
    if sess["busy"]:
        return "单条处理-忙等待", "busy"
    if sess["done"]:
        return "单条处理-队列完成", "done"
    return "单条处理-其他", "unknown"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_case_meta(project_root):
    manifest, ledger = {}, {}
    mpath = os.path.join(project_root, ".automation", "manifest.json")
    lpath = os.path.join(project_root, ".automation", "ledger.json")
    if os.path.exists(mpath):
        try:
            data = json.load(open(mpath, encoding="utf-8"))
            for c in data.get("cases", []):
                manifest[c.get("id")] = c
        except (json.JSONDecodeError, OSError):
            pass
    if os.path.exists(lpath):
        try:
            data = json.load(open(lpath, encoding="utf-8"))
            ledger = data.get("cases", {}) or {}
        except (json.JSONDecodeError, OSError):
            pass
    return manifest, ledger


def write_digest(path, rec):
    lines = [f"# {rec['title'] or '（无标题）'}", ""]
    lines.append(f"- 会话 ID：`{rec['sessionId']}`")
    lines.append(f"- 类型：{rec['type']}（{rec['status']}）")
    lines.append(f"- 开始时间：{rec['createdAtText']}  最后事件：{rec['lastTimeText']}")
    lines.append(f"- 工作目录：`{rec['cwd']}`")
    lines.append(f"- agentPreset：{rec['preset'] or '-'}；轮次：{rec['turns']}；工具错误：{rec['toolErrors']}")
    lines.append(f"- 原始文件：`{rec['sourcePath']}`")
    lines.append(f"- 副本：`{rec['copyPath']}`（{rec['bytes']} 字节，sha256 `{rec['sha256']}`）")
    if rec.get("prompt"):
        lines += ["", "## 调度提示", "", "```text", rec["prompt"].strip()[:4000], "```"]
    case = rec.get("nextCase") or {}
    if case:
        lines += [
            "",
            "## 领取用例",
            "",
            f"- 编号：{case.get('id')}",
            f"- 方法：{case.get('method')}",
            f"- 标题：{case.get('title')}",
            f"- 文件：{case.get('file')}",
            f"- 优先级：{case.get('priority')}；模块：{case.get('module')}",
        ]
    if rec["records"]:
        lines += ["", "## 结果记录", ""]
        for r in rec["records"]:
            lines.append(f"- `{r['id']}` → **{r['result']}**（runs={r['runs']}）")
            if r.get("note"):
                lines.append(f"  - 备注：{r['note']}")
    lines += ["", "## 最终结语", "", rec["finalText"].strip() or "（无最终文本）", ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def write_readme(out_dir, sessions, cases, stats, ledger):
    def brief(r, n=8):
        return r["sessionId"].replace("session-", "")[:n]

    tc = stats["typeCounter"]
    rc = stats["recordCounter"]
    total = stats["matchedSessions"]
    env_records = [c for c in cases if c.get("envBlocked")]
    fail_cases = [c for c in cases if c["finalResult"] in ("fail", "mixed")]
    auth = [r for r in sessions if r["status"] == "auth-error"]
    recover = [r for r in sessions if r["type"] == "监控恢复-介入"]
    busy = [r for r in sessions if "忙等待" in r["type"]]
    first, last = (stats["timeRange"] + ["-", "-"])[:2]

    def tspan(rs):
        if not rs:
            return "-"
        return f"{rs[0]['createdAtText']} ~ {rs[-1]['createdAtText']}"

    lines = [
        "# 电脑管家自动化测试用例 · DeepSeek Harness 会话汇总",
        "",
        f"> 生成时间：{stats['generatedAt']}　来源：`{stats['sourceRoot']}`",
        "",
        "## 1. 采集口径",
        "",
        "- 扫描本机 `~/.dsh/sessions` 下全部项目目录，仅保留会话 `cwd` 位于 `youqu_deepin_pc_manager` 的会话。",
        "- 每个会话解压 `session.v4.jsonl.zstd`，提取标题、调度提示、领取用例、`record` 结果、执行命令、最终结语、token/模型用量。",
        "- 原始副本保留在 `raw/`（可直接用 `zstd -dc` 复读）；`digests/` 为逐会话摘要；`index.json` 为全量结构化数据。",
        "- 结果以会话内 `harness.py record`（含监控通过脚本记录）为准；项目 `.automation/ledger.json` 当前状态单独标注。",
        "",
        "## 2. 总览",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 命中会话 | **{total}** |",
        f"| 时间范围 | {first} ~ {last} |",
        f"| 解压后文本量 / 压缩包体积 | {stats['textBytes'] / 1024 / 1024:.1f} MiB / {stats['compressedBytes'] / 1024 / 1024:.1f} MiB |",
        f"| 轮次 / 工具错误 | {stats['turns']} / {stats['toolErrors']} |",
        f"| 用例记录（pass/fail） | {rc.get('pass', 0)} / {rc.get('fail', 0)}（{stats['recordedSessions']} 个会话，覆盖 {stats['recordedCaseCount']} 条用例，含重试） |",
        f"| 环境阻断会话 | {stats['envBlockedSessions']} |",
        f"| ledger 当前状态 | "
        + "，".join(f"{k} {v}" for k, v in sorted(stats['ledgerStatusCounter'].items()))
        + f"（更新于 {stats['ledgerUpdatedAt']}） |",
        "",
        "## 3. 会话分类",
        "",
        "| 类型 | 会话数 | 说明 |",
        "|---|---|---|",
        f"| 单条处理-recorded | {tc.get('单条处理-recorded', 0)} | 领取并处理 1 条用例，最终执行 `record` |",
        f"| 单条处理-忙等待 | {tc.get('单条处理-忙等待', 0)} | `next` 返回 busy（他人在处理），按规程立即结束 |",
        f"| 单条处理-环境阻断 | {tc.get('单条处理-环境阻断', 0)} | 领到用例但测试机不可达，未真正执行 |",
        f"| 单条处理-队列完成 | {tc.get('单条处理-队列完成', 0)} | `next` 返回 done，仅汇报统计 |",
        f"| 单条处理-其他 | {tc.get('单条处理-其他', 0)} | 有领取动作但无明确结论 |",
        f"| 监控恢复-巡检 | {tc.get('监控恢复-巡检', 0)} | 心跳/测试机巡检，未改代码 |",
        f"| 监控恢复-介入 | {tc.get('监控恢复-介入', 0)} | 接管超时用例、改代码或记录结果 |",
        f"| 编排任务 | {tc.get('编排任务', 0)} | 主控/汇总会话 |",
        f"| 未执行-鉴权失败 | {tc.get('未执行-鉴权失败', 0)} | 模型/凭据鉴权错误，未开始 |",
        f"| 未执行-运行错误 | {tc.get('未执行-运行错误', 0)} | 会话因错误中断 |",
        "",
        f"> 上表按会话主类型归类；另有编排会话与监控接管会话也调用了 record，因此含记录的会话共 {stats['recordedSessions']} 个。",
        "",
        "## 4. 时间线（按小时）",
        "",
        "| 小时 | 会话数 | 忙等待 | 已记录 | 监控 |",
        "|---|---|---|---|---|",
    ]
    buckets = OrderedDict()
    for r in sessions:
        h = r["createdAtText"][:13]
        b = buckets.setdefault(h, {"n": 0, "busy": 0, "rec": 0, "mon": 0})
        b["n"] += 1
        b["busy"] += "忙等待" in r["type"]
        b["rec"] += bool(r["records"])
        b["mon"] += "监控" in r["type"]
    for h, b in buckets.items():
        lines.append(f"| {h}:00 | {b['n']} | {b['busy']} | {b['rec']} | {b['mon']} |")

    lines += [
        "",
        "## 5. 关键发现",
        "",
        f"1. **高频空转**：{len(busy)} 个 worker 会话（{tspan(busy)}）在 `next` 阶段遇到 busy，未处理用例；这是 5 分钟/10 分钟定时唤醒叠加单条串行处理的直接结果。",
        f"2. **测试机失联**：{stats['envBlockedSessions']} 个会话的结语显示 `10.20.33.103` 不可达；{len(env_records)} 条用例的 record 备注明确标注“环境阻断未执行”。worker 仍在离线状态重写用例代码，机器恢复后需 `requeue-failed` 重跑。",
        f"3. **监控接管**：{len(recover)} 个监控会话实际介入"
        + (f"（{', '.join(brief(r) for r in recover)}）" if recover else "")
        + "；其中心跳超时后 reclaim 并重写了同一用例代码，存在两个会话同时修改同一文件的情况。",
        f"4. **鉴权失败**：{len(auth)} 个会话"
        + (f"（{', '.join(brief(r) for r in auth)}）" if auth else "")
        + " 因 provider/凭据错误未执行。",
        f"5. **ledger 后续变化**：会话期记录为 pass {rc.get('pass', 0)} / fail {rc.get('fail', 0)}，而 ledger 当前为 "
        + "，".join(f"{k} {v}" for k, v in sorted(stats['ledgerStatusCounter'].items()))
        + f"（{stats['ledgerUpdatedAt']}），说明 11-11 之后还有会话外操作（如 requeue-failed、手工修复）。",
        "",
        f"## 6. 失败/混合用例清单（{len(fail_cases)} 条）",
        "",
        "| 用例 | 方法 | 会话结果 | ledger 当前 | 环境阻断 | 备注摘要 |",
        "|---|---|---|---|---|---|",
    ]
    for c in sorted(fail_cases, key=lambda x: x["id"]):
        note = (c.get("notes") or [c.get("ledgerNote") or ""])[-1]
        lines.append(
            f"| {c['id']} | {c.get('method') or '-'} | {c['finalResult']} | {c.get('ledgerStatus') or '-'} | "
            f"{'是' if c.get('envBlocked') else '否'} | {md_escape(note, 80)} |"
        )

    lines += [
        "",
        "## 7. 目录结构",
        "",
        "```text",
        ".deepseek-harness-sessions/",
        "├── README.md                 # 本文件",
        "├── index.json                # 全量会话（含摘要、记录、命令、token）",
        "├── sessions.csv / .md        # 会话级清单",
        "├── cases.json / .md          # 用例级聚合与备注",
        "├── digests/<日期>/<时分>_<sessionId>.md  # 单会话摘要",
        "├── raw/<projectKey>/<sessionId>/session.v4.jsonl.zstd  # 原始压缩副本",
        "└── scripts/collect_sessions.py           # 可重复执行的采集脚本",
        "```",
        "",
        "## 8. 复现",
        "",
        "```bash",
        "python3 .deepseek-harness-sessions/scripts/collect_sessions.py",
        "# 只读查看原始会话：",
        "zstd -dc .deepseek-harness-sessions/raw/<projectKey>/<sessionId>/session.v4.jsonl.zstd | less",
        "```",
        "",
        "## 9. 模型与 token（仅会话内统计）",
        "",
        "| 模型 | assistant 消息数 |",
        "|---|---|",
    ]
    for m, n in sorted(stats["modelCounter"].items(), key=lambda x: -x[1]):
        lines.append(f"| {m} | {n} |")
    u = stats["tokenUsage"]
    lines += [
        "",
        f"输入 {u['inputTokens']:,}，输出 {u['outputTokens']:,}，缓存读 {u['cacheReadTokens']:,}，合计 {u['totalTokens']:,}。",
        "",
        "> 说明：busy 会话与监控巡检轮次数量大、单轮 token 低；token 为 assistant/message 事件 `usage` 字段累加，缺失字段按 0 计。",
        "",
    ]
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.expanduser("~/.dsh/sessions"))
    ap.add_argument("--project-root", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out_dir = args.out or os.path.join(args.project_root, ".deepseek-harness-sessions")
    digests_dir = os.path.join(out_dir, "digests")
    raw_dir = os.path.join(out_dir, "raw")
    os.makedirs(digests_dir, exist_ok=True)
    os.makedirs(raw_dir, exist_ok=True)

    manifest, ledger = load_case_meta(args.project_root)
    sessions = []
    total_scanned = 0
    for project in sorted(os.listdir(args.root)):
        proj_dir = os.path.join(args.root, project)
        if not os.path.isdir(proj_dir):
            continue
        for sid in sorted(os.listdir(proj_dir)):
            sdir = os.path.join(proj_dir, sid)
            if not os.path.isdir(sdir):
                continue
            candidates = [
                os.path.join(sdir, "session.v4.jsonl.zstd"),
                os.path.join(sdir, "session.jsonl.zstd"),
            ]
            src = next((p for p in candidates if os.path.isfile(p)), None)
            if not src:
                continue
            total_scanned += 1
            with open(src, "rb") as fh:
                head = fh.read(64)
            sess, text = parse_session_file(src)
            if not sess["sessionId"]:
                sess["sessionId"] = sid
            cwd = sess["cwd"] or ""
            title = sess["title"] or ""
            relevant = PROJECT_KEYWORD in cwd
            if not relevant:
                continue
            created = sess["createdAt"] or 0
            rec = {
                "sessionId": sess["sessionId"],
                "projectKey": project,
                "title": title,
                "cwd": cwd,
                "preset": sess["preset"],
                "createdAt": created,
                "createdAtText": human_time(created),
                "lastTime": sess["lastTime"],
                "lastTimeText": human_time(sess["lastTime"]),
                "turns": sess["turns"],
                "prompt": re.sub(r"\s+", " ", sess["prompt"]).strip(),
                "toolErrors": sess["toolErrors"],
                "endReason": sess.get("endReason"),
                "usage": sess.get("usage"),
                "models": sess.get("models") or {},
                "records": sess["records"],
                "nextCase": sess["nextCase"],
                "referencedCaseIds": sess["referencedCaseIds"],
                "runCommands": sess["runCommands"],
                "finalText": sess["finalText"],
                "sourcePath": src,
                "bytes": os.path.getsize(src),
                "sha256": sha256_file(src),
                "textBytes": len(text.encode("utf-8")),
            }
            rec["type"], rec["status"] = classify(sess)
            for rr in rec["records"]:
                if rr["note"].startswith("$("):
                    rr["note"] = (ledger.get(rr["id"]) or {}).get("note") or ""
            copy_path = os.path.join(raw_dir, project, sid, os.path.basename(src))
            os.makedirs(os.path.dirname(copy_path), exist_ok=True)
            shutil.copy2(src, copy_path)
            rec["copyPath"] = os.path.relpath(copy_path, out_dir)
            # digest
            day = dt.datetime.fromtimestamp(created / 1000, TZ).strftime("%Y-%m-%d") if created else "unknown-date"
            hhmm = dt.datetime.fromtimestamp(created / 1000, TZ).strftime("%H%M") if created else "0000"
            digest_rel = os.path.join("digests", day, f"{hhmm}_{rec['sessionId']}.md")
            digest_abs = os.path.join(out_dir, digest_rel)
            os.makedirs(os.path.dirname(digest_abs), exist_ok=True)
            rec["digestPath"] = digest_rel
            write_digest(digest_abs, rec)
            sessions.append(rec)

    sessions.sort(key=lambda r: (r["createdAt"], r["sessionId"]))

    # 用例聚合（只统计真正 record 过的）
    case_map = OrderedDict()
    for rec in sessions:
        for r in rec["records"]:
            entry = case_map.setdefault(
                r["id"],
                {"id": r["id"], "sessions": [], "results": [], "notes": []},
            )
            entry["sessions"].append(
                {
                    "sessionId": rec["sessionId"],
                    "time": rec["createdAtText"],
                    "type": rec["type"],
                    "result": r["result"],
                    "runs": r["runs"],
                    "note": r["note"],
                    "digest": rec["digestPath"],
                }
            )
            entry["results"].append(r["result"])
            if r["note"]:
                entry["notes"].append(r["note"])
            if re.search(r"环境阻断|测试机不可达|测试机失联|No route|SYNC_FAILED|未执行任何用例", r["note"]):
                entry["envBlocked"] = True
    cases = []
    for cid, entry in case_map.items():
        meta = manifest.get(cid, {})
        led = ledger.get(cid, {})
        cleaned = []
        for n in entry["notes"]:
            if n.startswith("$(") and led.get("note"):
                n = led["note"]
            cleaned.append(n)
        entry["notes"] = cleaned
        entry.update(
            {
                "method": meta.get("method") or led.get("method"),
                "title": meta.get("title"),
                "module": meta.get("module"),
                "priority": meta.get("priority"),
                "file": meta.get("file"),
                "ledgerStatus": led.get("status"),
                "ledgerAttempts": led.get("attempts"),
                "ledgerNote": led.get("note"),
                "ledgerUpdatedAt": led.get("updatedAt"),
                "finalResult": "mixed" if len(set(entry["results"])) > 1 else entry["results"][-1],
            }
        )
        cases.append(entry)
    cases.sort(key=lambda c: c["id"])

    # 统计
    type_counter = Counter(r["type"] for r in sessions)
    status_counter = Counter(r["status"] for r in sessions)
    record_counter = Counter(r["result"] for r in sessions for r in r["records"])
    stats = {
        "generatedAt": dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S%z"),
        "sourceRoot": args.root,
        "scannedSessions": total_scanned,
        "matchedSessions": len(sessions),
        "timeRange": [sessions[0]["createdAtText"], sessions[-1]["createdAtText"]] if sessions else [],
        "compressedBytes": sum(r["bytes"] for r in sessions),
        "textBytes": sum(r["textBytes"] for r in sessions),
        "turns": sum(r["turns"] for r in sessions),
        "toolErrors": sum(r["toolErrors"] for r in sessions),
        "typeCounter": dict(type_counter),
        "statusCounter": dict(status_counter),
        "recordCounter": dict(record_counter),
        "recordedCaseCount": len(cases),
        "recordedSessions": sum(1 for r in sessions if r["records"]),
        "busySessions": sum(1 for r in sessions if "忙等待" in r["type"]),
        "blockedSessions": sum(1 for r in sessions if "环境阻断" in r["type"]),
        "monitorSessions": sum(1 for r in sessions if "监控" in r["type"]),
        "orchestratorSessions": sum(1 for r in sessions if r["type"] == "编排任务"),
        "ledgerStatusCounter": Counter(v.get("status") for v in ledger.values()),
        "ledgerUpdatedAt": max((v.get("updatedAt") or "") for v in ledger.values()) if ledger else "",
        "envBlockedSessions": sum(
            1
            for r in sessions
            if re.search(r"环境阻断|测试机不可达|测试机失联|No route|SYNC_FAILED", r["finalText"])
        ),
        "modelCounter": dict(Counter(k for r in sessions for k, v in r["models"].items() for _ in range(v))),
        "tokenUsage": {
            k: sum((r.get("usage") or {}).get(k, 0) for r in sessions)
            for k in ("inputTokens", "outputTokens", "totalTokens", "cacheReadTokens")
        },
    }

    index = {
        "generatedAt": stats["generatedAt"],
        "sourceRoot": args.root,
        "criteria": {
            "projectKeyword": PROJECT_KEYWORD,
            "match": "会话 cwd/title/内容包含 youqu_deepin_pc_manager 或 电脑管家",
            "recordCommand": "harness.py record --id <用例> --result <pass|fail> --runs <n> --note <备注>",
        },
        "stats": stats,
        "sessions": sessions,
    }
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "cases.json"), "w", encoding="utf-8") as fh:
        json.dump({"generatedAt": stats["generatedAt"], "cases": cases}, fh, ensure_ascii=False, indent=2)

    # sessions.csv
    with open(os.path.join(out_dir, "sessions.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["开始时间", "类型", "结果状态", "会话ID", "用例编号", "用例方法", "用例标题", "结果", "轮次", "工具错误", "摘要文件"])
        for r in sessions:
            case = r.get("nextCase") or {}
            rec_ids = ",".join(x["id"] for x in r["records"])
            w.writerow(
                [
                    r["createdAtText"],
                    r["type"],
                    r["status"],
                    r["sessionId"],
                    rec_ids or case.get("id", ""),
                    case.get("method", ""),
                    case.get("title", ""),
                    ",".join(x["result"] for x in r["records"]),
                    r["turns"],
                    r["toolErrors"],
                    r["digestPath"],
                ]
            )

    # sessions.md
    lines = [
        "# 会话清单（电脑管家自动化测试用例）",
        "",
        f"共 {len(sessions)} 个会话，按开始时间排序。",
        "",
        "| 开始时间 | 类型 | 会话 | 用例 | 结果 | 轮次 | 摘要 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in sessions:
        case = r.get("nextCase") or {}
        rec_ids = ", ".join(x["id"] for x in r["records"])
        cid = rec_ids or case.get("id") or "-"
        res = ", ".join(f"{x['id']}:{x['result']}" for x in r["records"]) or r["status"]
        short = r["sessionId"].replace("session-", "")[:8]
        lines.append(
            f"| {r['createdAtText']} | {r['type']} | `{short}` | {cid} | {res} | {r['turns']} | "
            f"[{md_escape(r['title'], 40)}]({r['digestPath']}) |"
        )
    with open(os.path.join(out_dir, "sessions.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    # cases.md
    lines = [
        "# 用例处理汇总（会话内 record 记录）",
        "",
        f"共 {len(cases)} 条用例在被采集的会话中被记录过；结果以 `harness.py record` 为准，"
        "`ledger` 列为项目 `.automation/ledger.json` 的当前状态（可能晚于会话时间）。",
        "",
        "| 用例 | 方法 | 标题 | 会话数 | 会话结果 | 最终结果 | ledger 当前状态 |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in cases:
        seq = " → ".join(f"{s['result']}({s['runs']})" for s in c["sessions"])
        lines.append(
            f"| {c['id']} | {c.get('method') or '-'} | {md_escape(c.get('title') or c.get('notes', [''])[-1], 48)} | "
            f"{len(c['sessions'])} | {seq} | {c['finalResult']} | {c.get('ledgerStatus') or '-'} |"
        )
    lines += ["", "## 备注（按会话时间）", ""]
    for c in cases:
        lines.append(f"### {c['id']} {c.get('method') or ''} {c.get('title') or ''}".strip())
        lines.append("")
        for s in c["sessions"]:
            note = md_escape(s["note"], 500) if s["note"] else "（无备注）"
            lines.append(f"- {s['time']} `{s['sessionId']}` → **{s['result']}**（runs={s['runs']}）：{note}")
        lines.append("")
    with open(os.path.join(out_dir, "cases.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    write_readme(out_dir, sessions, cases, stats, ledger)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

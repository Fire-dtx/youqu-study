# 电脑管家用例过检-监控恢复 · 2026-11-11 10:40

- 会话 ID：`session-ee82d70c-b8ee-42ad-bc3c-5d8a43ee2c19`
- 类型：监控恢复-巡检（normal）
- 开始时间：2026-11-11 10:40:00  最后事件：2026-11-11 10:42:11
- 工作目录：`/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager`
- agentPreset：ptc；轮次：1；工具错误：0
- 原始文件：`/home/ut000635@uos/.dsh/sessions/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-ee82d70c-b8ee-42ad-bc3c-5d8a43ee2c19/session.v4.jsonl.zstd`
- 副本：`raw/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-ee82d70c-b8ee-42ad-bc3c-5d8a43ee2c19/session.v4.jsonl.zstd`（37950 字节，sha256 `30dc1896095a88517ee62d80a9f63ac2d18f8515f18ab375cf669067efa14046`）

## 调度提示

```text
[SCHEDULE REMINDER] This is a scheduled message from the user schedule_id_json: "schedule-8556d470-3d63-4506-99b1-928d524ad804" occurrence_at: 2026-11-11T02:40:00.000Z reminder_prompt_json: "【电脑管家用例过检 · 监控恢复】你是该任务的监控者。第一步：cd /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager && /usr/bin/python3 .automation/harness.py status ，并完整读取 /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager/.automation/MONITOR.md 严格照做：判断是否全部完成、worker 是否心跳正常、心跳超时则查测试机是否真在跑，若已中断则 release 该条并由你接手按 PROCEDURE.md 处理 1 条。顺带巡检测试机残留与磁盘。不要并行跑用例，禁止 git commit，禁止向用户提问。"
```

## 最终结语

巡检完成，各项均正常，无需恢复操作。

**状态判断（MONITOR.md §3 正常在跑）**
- 总用例 229 条：passed 36 / failed 26 / in_progress 1 / pending 166
- 当前 owner：用例 `2005789`（`test_mycase_164`），`heartbeatAgeSec = 19s`，远小于 3600s 阈值 → worker 心跳正常，未超时
- 按规程：不改代码、不 release、不接手；未并行跑用例

**顺带巡检（§6）**
- 测试机磁盘 `/`：25G 总量，已用 11G，可用 13G（45%）→ 远高于 300MB 告警线，无需清理
- 测试机残留（`remote_check.sh`）：processes / loops(autotest) / mounts(autotest) / media / home / tmp / systemd bak 全部为空 → 无孤儿 loop、挂载或进程，无需 `remote_clean.sh`

下一条待处理用例为 `2005791`（`test_mycase_165` 应用修复-修复WPS-修复后双击文档可正常打开 WPS），留给 worker 正常领取。

# 电脑管家用例过检-监控恢复 · 2026-11-11 11:20

- 会话 ID：`session-a67cb846-fbaf-4160-980c-2ac06fbc66da`
- 类型：监控恢复-巡检（normal）
- 开始时间：2026-11-11 11:20:00  最后事件：2026-11-11 11:21:48
- 工作目录：`/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager`
- agentPreset：ptc；轮次：1；工具错误：0
- 原始文件：`/home/ut000635@uos/.dsh/sessions/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-a67cb846-fbaf-4160-980c-2ac06fbc66da/session.v4.jsonl.zstd`
- 副本：`raw/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-a67cb846-fbaf-4160-980c-2ac06fbc66da/session.v4.jsonl.zstd`（81764 字节，sha256 `d4e4135bb281164234116357a2828dd903382b136e6e87f4094d7ae0de744953`）

## 调度提示

```text
[SCHEDULE REMINDER] This is a scheduled message from the user schedule_id_json: "schedule-8556d470-3d63-4506-99b1-928d524ad804" occurrence_at: 2026-11-11T03:20:00.000Z reminder_prompt_json: "【电脑管家用例过检 · 监控恢复】你是该任务的监控者。第一步：cd /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager && /usr/bin/python3 .automation/harness.py status ，并完整读取 /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager/.automation/MONITOR.md 严格照做：判断是否全部完成、worker 是否心跳正常、心跳超时则查测试机是否真在跑，若已中断则 release 该条并由你接手按 PROCEDURE.md 处理 1 条。顺带巡检测试机残留与磁盘。不要并行跑用例，禁止 git commit，禁止向用户提问。"
```

## 最终结语

巡检完成，本轮无需接手用例。

**状态（11:21:22）**
- 总数 229：passed 38 / failed 26 / pending 165 / in_progress 0 — 未全部完成
- **owner 为空**：我刚唤醒时 owner 是 `2005791`（test_mycase_165，心跳 123s，正常在跑），巡检过程中该条已于 **11:20:48 PASS**（1 次通过，WPS 双击打开修复闭环）并自行释放，因此不属于心跳超时场景（`heartbeatAgeSec` 远小于 3600，未执行 release，也未改任何用例代码）
- 下一条待处理：`2005793` / test_mycase_166（应用修复-输入法修复-正常关闭运行中的输入法进程）
- 静默判断：history 最后记录 11:20:48，距今不到 1 分钟，远未到 90 分钟阈值，worker 调度正常。两个定时任务均 active，worker 下次触发 11:25:00，监控下次 11:40:00

**巡检发现并处理的问题**
- 测试机存在 2 个**孤儿 pytest 进程**（PID 318542/318631，`test_mycase_69` / `test_mycase_069`），10:23:26/33 启动、状态 `T`（已挂起 57 分钟）、同属一个已消失的父进程（PPID 6457），与本轮用例无关，属早期中断残留。已 TERM→KILL 清除，复核 `ps` 无 manage.py 进程
- 清理后 `remote_check.sh` 全空：无 autotest loop / 挂载 / 家目录与 /tmp 残留 / systemd bak 残留
- 磁盘：`/dev/sda5` 25G，已用 11G，**可用 13G（46%）**，远高于 300MB 阈值，无需清理 report 旧数据
- 锁状态 `LOCK_FREE`，无并发用例风险（全程未并行跑用例，未执行 git commit）

**下一步**：交给 11:25 的 worker 触发按 PROCEDURE 接管 `2005793`；若届时仍无进展或心跳超时，下一轮监控（11:40）再按 PROCure 第 4 步接手。

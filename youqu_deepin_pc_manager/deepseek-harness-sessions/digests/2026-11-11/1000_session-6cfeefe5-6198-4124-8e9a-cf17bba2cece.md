# 电脑管家用例过检-单条处理 · 2026-11-11 10:00

- 会话 ID：`session-6cfeefe5-6198-4124-8e9a-cf17bba2cece`
- 类型：单条处理-recorded（pass）
- 开始时间：2026-11-11 10:00:00  最后事件：2026-11-11 10:09:20
- 工作目录：`/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager`
- agentPreset：ptc；轮次：1；工具错误：1
- 原始文件：`/home/ut000635@uos/.dsh/sessions/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-6cfeefe5-6198-4124-8e9a-cf17bba2cece/session.v4.jsonl.zstd`
- 副本：`raw/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-6cfeefe5-6198-4124-8e9a-cf17bba2cece/session.v4.jsonl.zstd`（298232 字节，sha256 `ffb1280eeccdc7089503f8cc942ce5aaffb4266d8635c9e55bfb79bd1f4bd343`）

## 调度提示

```text
[SCHEDULE REMINDER] This is a scheduled message from the user schedule_id_json: "schedule-9cbdd9c0-1767-4248-bf5d-3601123db38a" occurrence_at: 2026-11-11T02:00:00.000Z reminder_prompt_json: "【电脑管家用例过检 · 单条处理】你是该任务的 worker，本次只处理 1 条用例，处理完立即结束、等待 5 分钟后的下次唤醒。第一步：cd /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager && /usr/bin/python3 .automation/harness.py next ，并完整读取 /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager/.automation/PROCEDURE.md 严格照做：读用例描述→改代码→bash .automation/scripts/run_case.sh <编号> <方法> 1800→最多修 2 次→清理残留→harness.py record 记录结果→写结束语后停止，不要再次 next。若 next 返回 busy 立即结束；若 done=true 报告全部完成。禁止 git commit，禁止向用户提问，禁止并行跑用例。"
```

## 领取用例

- 编号：2005779
- 方法：test_mycase_160
- 标题：应用修复-修复QQ-正常关闭运行中的QQ进程
- 文件：apps/autotest_my_app/case/2005779_应用修复-修复QQ-正常关闭运行中的QQ进程.py
- 优先级：1；模块：/修复工具(#134475)

## 结果记录

- `2005779` → **pass**（runs=1）
  - 备注：按产品 plugin-qq-fix/entry.sh 重写(原版只打开修复页、无任何断言): 用 sleep 复制品 /tmp/qq 等价构造'QQ 正在运行', ~/.config/QQ/Cache 写入 8MB 缓存; 断言修复对话框出现、输出日志出现'清理完成'、缓存目录彻底消失(文件数0/占用0)、qq 进程被 pkill -x qq 终止; 用例描述中的 '~/.config/QQ/Cache-QQ' 与产品脚本实际目标 '~/.config/QQ/Cache' 不一致, 以产品脚本为准; finally 结束模拟进程/删 /tmp/qq 与缓存并还原 ~/.config/QQ、Deepin-QQ 备份, 现场无残留

## 最终结语

用例 2005779 应用修复-修复QQ-正常关闭运行中的QQ进程：**PASS，运行 1 次**，备注：按产品 `plugin-qq-fix/entry.sh` 重写，原版只打开修复页且无任何断言；用与 QQ 同名的模拟进程 `/tmp/qq` 等价构造“QQ 正在运行”，在 `~/.config/QQ/Cache` 写入 8MB 缓存，断言修复对话框出现、输出日志包含“清理完成”、缓存目录彻底消失（文件数 0、占用 0）、QQ 进程被 `pkill -x qq` 终止；用例描述里的 `Cache-QQ` 与产品脚本实际目标 `Cache` 不一致，以产品脚本为准；finally 清理模拟进程、临时二进制和缓存，并还原 QQ 现场备份。

本次执行要点：
- 修复卡片列表已获取，确认存在 `QQ修复` 卡片；点击后进入详情并执行修复。
- 实测证据：模拟 QQ 进程 pid 317061、缓存构造 8220KB → 修复后 `pgrep -x qq` 为空、`Cache` 目录不存在、文件数与占用均为 0。
- 残留检查：测试机上无 `/tmp/qq`、无 `~/.config/QQ`、无 `~/.autotest_qq_backup`、无 QQ 进程，`/home` 分区占用未变（7.1G/119G 可用），无需 `remote_clean.sh`。

改动文件：
- [2005779_应用修复-修复QQ-正常关闭运行中的QQ进程.py](apps/autotest_my_app/case/2005779_应用修复-修复QQ-正常关闭运行中的QQ进程.py)
- [my_app_widget.py](apps/autotest_my_app/widget/my_app_widget.py)（新增 QQ 现场备份/还原、缓存计量、模拟 qq 进程启动/存活/终止等辅助方法，保留原有 `create_mock_qq_cache` 等接口供 2005781 复用）

进度计数（`record` 输出）：passed **32** / failed 26 / pending 171，总计 229。

按要求本次只处理这 1 条，已记录结果并结束，不继续领取下一条；下一条用例由 5 分钟后的定时唤醒接手。

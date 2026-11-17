# 电脑管家用例过检-单条处理 · 2026-11-11 10:10

- 会话 ID：`session-afb14e10-a202-4e57-a3d9-7aef9c2fcf9d`
- 类型：单条处理-recorded（pass）
- 开始时间：2026-11-11 10:10:00  最后事件：2026-11-11 10:13:11
- 工作目录：`/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager`
- agentPreset：ptc；轮次：1；工具错误：0
- 原始文件：`/home/ut000635@uos/.dsh/sessions/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-afb14e10-a202-4e57-a3d9-7aef9c2fcf9d/session.v4.jsonl.zstd`
- 副本：`raw/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-afb14e10-a202-4e57-a3d9-7aef9c2fcf9d/session.v4.jsonl.zstd`（123144 字节，sha256 `855a7329059e9c512e93647676fba375fec3bcc7b1dd28c028d083aace057972`）

## 调度提示

```text
[SCHEDULE REMINDER] This is a scheduled message from the user schedule_id_json: "schedule-9cbdd9c0-1767-4248-bf5d-3601123db38a" occurrence_at: 2026-11-11T02:10:00.000Z reminder_prompt_json: "【电脑管家用例过检 · 单条处理】你是该任务的 worker，本次只处理 1 条用例，处理完立即结束、等待 5 分钟后的下次唤醒。第一步：cd /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager && /usr/bin/python3 .automation/harness.py next ，并完整读取 /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager/.automation/PROCEDURE.md 严格照做：读用例描述→改代码→bash .automation/scripts/run_case.sh <编号> <方法> 1800→最多修 2 次→清理残留→harness.py record 记录结果→写结束语后停止，不要再次 next。若 next 返回 busy 立即结束；若 done=true 报告全部完成。禁止 git commit，禁止向用户提问，禁止并行跑用例。"
```

## 领取用例

- 编号：2005781
- 方法：test_mycase_161
- 标题：应用修复-修复QQ-清理 Linux 原生 QQ 缓存目录
- 文件：apps/autotest_my_app/case/2005781_应用修复-修复QQ-清理 Linux 原生 QQ 缓存目录.py
- 优先级：2；模块：/修复工具(#134475)

## 结果记录

- `2005781` → **pass**（runs=1）
  - 备注：原版用例只打开修复页且无任何断言, 按产品 plugin-qq-fix/entry.sh 重写: 用 backup_qq_state 保护真实现场后, 在 ~/.config/QQ/Cache 构造 avatar/filecache/temp 共 8MB 缓存(8220KB, >=4 文件)作为前置; 断言修复页面/QQ修复卡片/详情页可达、修复对话框弹出、输出日志出现'清理完成'(脚本执行到末尾)、缓存目录整体消失且文件数/占用均为 0; finally 关闭提示框/修复对话框、删构造缓存并 restore_qq_state 还原真实现场(本机原本无 QQ 数据), 残留检查无 autotest 对象

## 最终结语

用例 2005781 应用修复-修复QQ-清理 Linux 原生 QQ 缓存目录：PASS，运行 1 次，备注：原版用例只打开修复页、无任何断言；现按产品脚本 `plugin-qq-fix/entry.sh` 重写为真实闭环。先备份真实 QQ 现场，再在 `~/.config/QQ/Cache` 构造 avatar/filecache/temp 共 8MB 缓存（8220KB、≥4 个文件）作为前置；随后断言修复页/QQ 修复卡片/详情页可达、修复对话框弹出、输出日志含“清理完成”、缓存目录消失且文件数与占用均为 0；最后关闭提示框、删构造缓存并还原真实现场，残留检查无 autotest 对象。

record 输出为 `{"ok":true,"caseId":"2005781","status":"passed"}`，进度计数 **passed 33 / failed 26 / pending 170（total 229）**。本条处理完毕，本次会话结束，等待 5 分钟后的下次唤醒。

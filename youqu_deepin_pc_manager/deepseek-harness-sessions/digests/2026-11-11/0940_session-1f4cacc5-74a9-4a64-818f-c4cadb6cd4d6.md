# 电脑管家用例过检-单条处理 · 2026-11-11 09:40

- 会话 ID：`session-1f4cacc5-74a9-4a64-818f-c4cadb6cd4d6`
- 类型：单条处理-recorded（pass）
- 开始时间：2026-11-11 09:40:00  最后事件：2026-11-11 09:45:26
- 工作目录：`/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager`
- agentPreset：ptc；轮次：1；工具错误：0
- 原始文件：`/home/ut000635@uos/.dsh/sessions/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-1f4cacc5-74a9-4a64-818f-c4cadb6cd4d6/session.v4.jsonl.zstd`
- 副本：`raw/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-1f4cacc5-74a9-4a64-818f-c4cadb6cd4d6/session.v4.jsonl.zstd`（245795 字节，sha256 `7ca09d54ed7576ebf5a88d225ac18957c2e4704d1db0f8fb2bbe769b34ff1462`）

## 调度提示

```text
[SCHEDULE REMINDER] This is a scheduled message from the user schedule_id_json: "schedule-9cbdd9c0-1767-4248-bf5d-3601123db38a" occurrence_at: 2026-11-11T01:40:00.000Z reminder_prompt_json: "【电脑管家用例过检 · 单条处理】你是该任务的 worker，本次只处理 1 条用例，处理完立即结束、等待 5 分钟后的下次唤醒。第一步：cd /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager && /usr/bin/python3 .automation/harness.py next ，并完整读取 /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager/.automation/PROCEDURE.md 严格照做：读用例描述→改代码→bash .automation/scripts/run_case.sh <编号> <方法> 1800→最多修 2 次→清理残留→harness.py record 记录结果→写结束语后停止，不要再次 next。若 next 返回 busy 立即结束；若 done=true 报告全部完成。禁止 git commit，禁止向用户提问，禁止并行跑用例。"
```

## 领取用例

- 编号：2005775
- 方法：test_mycase_158
- 标题：应用修复-修复企业微信-磁盘空间不足执行脚本
- 文件：apps/autotest_my_app/case/2005775_应用修复-修复企业微信-磁盘空间不足执行脚本.py
- 优先级：3；模块：/修复工具(#134475)

## 结果记录

- `2005775` → **pass**（runs=1）
  - 备注：按产品 plugin-wecom-fix/entry.sh(kill.sh bottle + rm -rf ~/.deepinwine/Deepin-WXWork + openinfobox)闭环重写: 原版只建空缓存目录并忽略磁盘空间, 无低空间构造/无 try-finally/弱断言; 现新增 widget 低空间现场 setup_low_space_wecom_bottle/cleanup_low_space_wecom_bottle/is_mount_present/unmount_path, 并给 setup_mock_wecom_wine 增加 protect_bottle 开关: 挂 100MB tmpfs 并 bind 到 ~/.deepinwine(真实 bottle 先改名备份), 盘内写 30MB 占位(可用降到30MB<100MB), 再放置含40MB缓存/ user.reg /桩wineserver/模拟WeChat.exe 的桩bottle; 修复工具->企业微信修复卡片->详情页->开始修复后断言 shellRepair 对话框弹出(脚本真实执行)、bottle 目录被 rm -rf 删净(目录不存在+du=0)、低空间盘可用空间 30MB->70MB(释放40MB)、输出无 ENOSPC/No space left/Traceback 崩溃特征; finally 先卸 bind 再清桩并还原真实 bottle, 最后卸 tmpfs 并删挂载点; 1 次运行 PASS(30s), 复核远端无残留挂载/无 /tmp/autotest*/无桩进程/无备份目录

## 最终结语

用例 2005775 应用修复-修复企业微信-磁盘空间不足执行脚本：**PASS**，运行 1 次。

**改了什么**
- 原用例的问题：只建一个空缓存目录、`get_disk_free_space_mb()` 结果丢弃不用、无 try/finally，与"磁盘空间不足"前置无关。
- 新增 widget 能力（`my_app_widget.py`）：`setup_low_space_wecom_bottle` / `cleanup_low_space_wecom_bottle` / `is_mount_present` / `unmount_path`，并给 `setup_mock_wecom_wine` 加 `protect_bottle` 开关（避免备份被 mv 进 tmpfs）。
- 等价构造前置："可用空间不足 100MB"→ 挂 100MB tmpfs 并 bind 到 `~/.deepinwine`（真实 bottle 先改名备份），盘内写 30MB 占位，再放含 40MB 缓存 + `user.reg` + 桩 wineserver + 模拟 WeChat.exe 的桩 bottle，使产品 `rm -rf ~/.deepinwine/Deepin-WXWork/` 真实作用在低空间文件系统上。
- 断言：shellRepair 对话框弹出（entry.sh 真实执行）→ bottle 目录被删净（目录不存在 + `du`=0）→ 低空间盘可用空间 **30MB → 70MB**（释放 40MB）→ 输出无 `ENOSPC`/`No space left`/`Traceback` 崩溃特征。
- finally：先卸 bind（让真实 `~/.deepinwine` 复现）→ 清桩进程并还原备份 bottle → 卸 tmpfs 并删挂载点。

**残留复核**：远端无 `autotest` 挂载、无 `/tmp/autotest*`、无桩 `WeChat.exe`/wineserver 进程、无备份目录；`~/.deepinwine` 原有内容完好，根分区 45% 无异常。

进度：passed 30 / failed 26 / pending 173（共 229）。

# 电脑管家用例过检-单条处理 · 2026-11-11 06:45

- 会话 ID：`session-1d6e39c8-2cbc-4117-bcae-cfb8b0287fe1`
- 类型：单条处理-recorded（fail）
- 开始时间：2026-11-11 06:45:00  最后事件：2026-11-11 06:52:47
- 工作目录：`/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager`
- agentPreset：ptc；轮次：1；工具错误：1
- 原始文件：`/home/ut000635@uos/.dsh/sessions/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-1d6e39c8-2cbc-4117-bcae-cfb8b0287fe1/session.v4.jsonl.zstd`
- 副本：`raw/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-1d6e39c8-2cbc-4117-bcae-cfb8b0287fe1/session.v4.jsonl.zstd`（428680 字节，sha256 `7c15d72475dc9e434c8d05b3b35ec279541097670f125aa4a0d0afee8a39157e`）

## 调度提示

```text
[SCHEDULE REMINDER] This is a scheduled message from the user schedule_id_json: "schedule-9cbdd9c0-1767-4248-bf5d-3601123db38a" occurrence_at: 2026-11-10T22:45:00.000Z reminder_prompt_json: "【电脑管家用例过检 · 单条处理】你是该任务的 worker，本次只处理 1 条用例，处理完立即结束、等待 5 分钟后的下次唤醒。第一步：cd /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager && /usr/bin/python3 .automation/harness.py next ，并完整读取 /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager/.automation/PROCEDURE.md 严格照做：读用例描述→改代码→bash .automation/scripts/run_case.sh <编号> <方法> 1800→最多修 2 次→清理残留→harness.py record 记录结果→写结束语后停止，不要再次 next。若 next 返回 busy 立即结束；若 done=true 报告全部完成。禁止 git commit，禁止向用户提问，禁止并行跑用例。"
```

## 领取用例

- 编号：2005747
- 方法：test_mycase_245
- 标题：外设修复-U盘修复-- FAT32 U 盘损坏严重
- 文件：apps/autotest_my_app/case/2005747_外设修复-U盘修复-- FAT32 U 盘损坏严重.py
- 优先级：3；模块：/废弃(#135391)

## 结果记录

- `2005747` → **fail**（runs=1）
  - 备注：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 06:47 ssh rc=255 'No route to host', ip neigh=INCOMPLETE(无 L2 响应), 本机 eno1 10.20.33.186/24 正常(排除本机网络); run_case.sh 启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005747_test_mycase_245_20261111_065203.log), 未同步代码、未执行任何用例步骤、无远端副作用。根因同 2005719~2005745: 04:12 起该机失联, 需现场 console 或带外重启。本轮离线改造: 原实现只造 loop 设备 FAT32+轻微损坏, 既没进入 usb-fix 修复流程(仅停在修复工具首页), 也没有"无法自动修复"的断言, 与描述不符; 重写为真实 severe 分支验证 —— scsi_debug 合成 U 盘(udev 规则把 ID_BUS 覆写为 usb, 与 2005745 同一等价实现) -> FAT32 格式化并挂载 -> fsck 健康 -> 卸载后 dd 随机覆写前 4MB(引导扇区/BPB/FAT1/FAT2/根目录)构造"文件系统无法识别"的严重损坏(blkid 探测为空、fsck.vfat -n rc=1) -> 启动管家/修复工具/USB 设备修复/开始修复 -> 应答 设备选择 + 诊断结果 交互框 -> 断言输出含 已选择设备/文件系统无法识别/自动修复不可用/建议格式化/USB 修复流程结束, 且不含"修复成功"(等价于描述的"命令无法自动修复、报错退出") -> 物理校验分区仍无法识别(产品未擅自格式化) -> finally 关交互框/关修复框/卸载分区/取消 1500s 兜底定时器/删 udev 规则并 rmmod scsi_debug/恢复 udisks2。新增 widget 方法 4 个(create_fat32_severe_corruption/get_fat32_filesystem_unrecognized/get_fat32_filesystem_check_rc/close_usb_fix_prompt_dialog), 并加固 handle_usb_fix_confirm_dialog(列表项按 list item/table cell/cell/check box 多角色选中 + 坐标点击 + selected 状态校验 + 方向键兜底; 按钮兼容 确认/确定; 流程终止条件兼容 用户取消选择/交互通道不可用)。离线验证: 两文件 py_compile 通过; AST 校验用例引用的 29 个 widget 方法全部存在(含继承的 run_cmd/sudo_run_cmd); FakeWidget 跑通 9 条控制流(正常/udisks 未运行/产品谎报修复成功/取消设备选择/损坏不够严重/修复对话框未出现/中途异常/无合成盘改走实体盘/无任何设备), finally 在断言失败与异常路径均执行; 本机实测 severe 构造判据(64M FAT32 镜像覆写 4MB 后 blkid -p 输出为空、fsck.vfat -n rc=1), 7 条新增 shell 命令 bash -n 全部通过。待机器恢复: requeue-failed 或置回 pending 后直接重跑, 无需再改代码。

## 最终结语

用例 2005747 外设修复-U盘修复-- FAT32 U 盘损坏严重：FAIL，运行 1 次，备注 环境阻断未执行（测试机 10.20.33.103 自 04:12 起失联，06:47 仍 `No route to host`、ARP INCOMPLETE，`run_case.sh` 启动即 `SYNC_FAILED rc=255`，未同步代码、未执行任何步骤、无远端副作用）；本轮已完成该用例的离线实现：原版只造 loop 设备 FAT32 轻微损坏、停在修复工具首页、无"无法自动修复"断言，现重写为真实 severe 分支验证——scsi_debug 合成 U 盘（udev 把 `ID_BUS` 覆写为 `usb`，与 2005745 同一等价实现）→ FAT32 格式化挂载 → fsck 健康 → 卸载后覆写前 4MB 构造"文件系统无法识别"的严重损坏 → 修复工具/USB 设备修复/开始修复 → 应答设备选择与诊断结果交互框 → 断言输出含 `已选择设备`/`文件系统无法识别`/`自动修复不可用`/`建议格式化`/`USB 修复流程结束` 且不含 `修复成功`（等价"命令无法自动修复、报错退出"）→ 物理校验分区仍无法识别，finally 完整回退（交互框、修复框、分区、1500s 兜底定时器、udev 规则与 scsi_debug、udisks2）。新增 widget 方法 4 个并加固 `handle_usb_fix_confirm_dialog`。离线验证：两文件 `py_compile` 通过、用例引用的 29 个方法全在、FakeWidget 跑通 9 条控制流（finally 全部执行）、本机实测 severe 判据（blkid 为空、fsck.vfat rc=1）与 7 条新命令 `bash -n`；机器恢复后 requeue 直接重跑即可。

进度计数（`record` 输出）：passed 26 / failed 17 / pending 186 / total 229。

改动文件：[用例 2005747](apps/autotest_my_app/case/2005747_外设修复-U盘修复-- FAT32 U 盘损坏严重.py)、[my_app_widget.py](apps/autotest_my_app/widget/my_app_widget.py)。

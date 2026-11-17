# 电脑管家用例过检-单条处理 · 2026-11-11 05:40

- 会话 ID：`session-a5bc7e4e-95b7-459a-a9ac-148abf1474ae`
- 类型：单条处理-recorded（fail）
- 开始时间：2026-11-11 05:40:00  最后事件：2026-11-11 05:46:44
- 工作目录：`/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager`
- agentPreset：ptc；轮次：1；工具错误：1
- 原始文件：`/home/ut000635@uos/.dsh/sessions/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-a5bc7e4e-95b7-459a-a9ac-148abf1474ae/session.v4.jsonl.zstd`
- 副本：`raw/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-a5bc7e4e-95b7-459a-a9ac-148abf1474ae/session.v4.jsonl.zstd`（402939 字节，sha256 `2cae84c43a715679ffa22ca3c761d3f14bfa2b025fd13acc7386e24b1c592169`）

## 调度提示

```text
[SCHEDULE REMINDER] This is a scheduled message from the user schedule_id_json: "schedule-9cbdd9c0-1767-4248-bf5d-3601123db38a" occurrence_at: 2026-11-10T21:40:00.000Z reminder_prompt_json: "【电脑管家用例过检 · 单条处理】你是该任务的 worker，本次只处理 1 条用例，处理完立即结束、等待 5 分钟后的下次唤醒。第一步：cd /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager && /usr/bin/python3 .automation/harness.py next ，并完整读取 /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager/.automation/PROCEDURE.md 严格照做：读用例描述→改代码→bash .automation/scripts/run_case.sh <编号> <方法> 1800→最多修 2 次→清理残留→harness.py record 记录结果→写结束语后停止，不要再次 next。若 next 返回 busy 立即结束；若 done=true 报告全部完成。禁止 git commit，禁止向用户提问，禁止并行跑用例。"
```

## 领取用例

- 编号：2005735
- 方法：test_mycase_149
- 标题：系统修复-修复依赖关系不满足-apt-dpkg 命令不存在（待确认？？）
- 文件：apps/autotest_my_app/case/2005735_系统修复-修复依赖关系不满足-apt-dpkg 命令不存在（待确认？？）.py
- 优先级：3；模块：/修复工具(#134475)

## 结果记录

- `2005735` → **fail**（runs=1）
  - 备注：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 05:45/05:49 两次 ssh 均 rc=255 'No route to host', ip neigh=INCOMPLETE(无 L2 响应), tcp/22 直连报'没有到主机的路由'; 本机 eno1 10.20.33.186/24 正常(排除本机网络), run_case.sh 一启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005735_test_mycase_149_20261111_054558.log), 未同步代码、未执行任何用例步骤、无远端副作用。根因同 2005719~2005733: 04:12 起该机失联(疑 2005719 移走 NetworkManager 后网卡未取回地址或断电), 需现场 console 或带外重启。本轮已完成本用例离线实现: 原空壳(仅开应用点修复导航)重写为真实闭环 —— 前置核对网络正常/apt、apt-get、dpkg 可用/root 执行 apt update 成功(排除仓库不可达分支) → 先注册 systemd-run 900s 兜底恢复定时器 → 把 /usr/bin/apt、/usr/bin/apt-get、/usr/bin/dpkg 临时改名为 *.autotest_bak(即描述里的'路径被修改', 等价于'精简系统无 apt/dpkg 命令'), 断言 command -v 找不到三命令 → 直接执行 apt update -y 返回非 0 且输出含 command not found(预期1 直接复现), dpkg --configure -a 同样非 0 → 走产品 修复工具/依赖关系修复/开始修复, 断言出现'系统仓库更新失败'提示(输出日志或结果提示框任一命中), 且不出现'系统仓库更新成功'/'依赖关系修复成功'/'依赖关系未修复'(即产品在 apt update 失败分支停住, 未继续后续步骤), 产品进程未崩溃 → finally 先移回三个命令(失败重试一次, 仍未恢复则保留兜底定时器), 再取消定时器、关弹窗、杀进程、清 sudo 指纹, 并二次确认命令可用。新增 widget 方法 9 个(get_apt_dpkg_missing_commands/get_apt_dpkg_commands_available/get_apt_dpkg_binaries_state/schedule_apt_dpkg_binary_recovery/cancel_apt_dpkg_binary_recovery/restore_stale_apt_dpkg_binaries/break_apt_dpkg_binaries/restore_apt_dpkg_binaries/apt_update_command_missing/dpkg_configure_command_missing)。离线验证: 用例与 widget 两文件 py_compile 通过, 用例引用的 29 个 widget 方法全部存在, 用伪造目录实测'移走命令后 command -v 为空、apt update/dpkg 均 rc=127 输出 command not found、兜底脚本与 finally 反向 mv 均可完整恢复且不残留 .bak', 兜底脚本 bash -n 通过。机器恢复后需 requeue-failed 或手工置回 pending 直接重跑本条, 无需再改代码。

## 最终结语

用例 2005735 系统修复-修复依赖关系不满足-apt/dpkg 命令不存在（待确认？？）：**FAIL（环境阻断）**，运行 1 次（`run_case.sh` 在 SYNC 阶段即 `SYNC_FAILED rc=255`，用例未真正执行），备注：测试机 10.20.33.103 自 04:12 起失联（ssh `No route to host`、`ip neigh=INCOMPLETE`、tcp/22 无路由，本机 eno1 正常），根因同 2005719~2005733，需现场 console 或带外重启；本轮已完成该用例离线闭环实现（临时移走 `/usr/bin/apt`、`apt-get`、`dpkg` 等价"精简系统无命令"，直接复现 `apt update -y` rc≠0 且 command not found，再走产品"依赖关系修复"断言 `系统仓库更新失败` 且不出现成功/人工修复文案，`finally` 移回命令并保留 systemd 兜底定时器），py_compile 与伪造目录实测均通过，机器恢复后 requeue 即可直接重跑。

进度计数（`record` 输出）：`passed 26 / failed 12 / pending 191`，total 229，`owner: null`，下一条待处理 2005737。

- 用例文件：[2005735_系统修复-修复依赖关系不满足-apt-dpkg 命令不存在（待确认？？）.py](apps/autotest_my_app/case/2005735_系统修复-修复依赖关系不满足-apt-dpkg%20命令不存在（待确认？？）.py)
- 页面方法层：[my_app_widget.py](apps/autotest_my_app/widget/my_app_widget.py#L5423-L5645)

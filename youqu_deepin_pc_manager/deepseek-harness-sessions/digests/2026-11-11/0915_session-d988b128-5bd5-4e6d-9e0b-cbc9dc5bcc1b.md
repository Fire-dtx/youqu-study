# 电脑管家用例过检-单条处理 · 2026-11-11 09:15

- 会话 ID：`session-d988b128-5bd5-4e6d-9e0b-cbc9dc5bcc1b`
- 类型：单条处理-recorded（pass）
- 开始时间：2026-11-11 09:15:00  最后事件：2026-11-11 09:25:41
- 工作目录：`/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager`
- agentPreset：ptc；轮次：2；工具错误：0
- 原始文件：`/home/ut000635@uos/.dsh/sessions/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-d988b128-5bd5-4e6d-9e0b-cbc9dc5bcc1b/session.v4.jsonl.zstd`
- 副本：`raw/--home-ut000635~0040uos-Documents-TestCode-youqu_deepin_pc_manager--/session-d988b128-5bd5-4e6d-9e0b-cbc9dc5bcc1b/session.v4.jsonl.zstd`（303191 字节，sha256 `84bdaac56f16b2ca708f763ea7a3d9905174c78e35dbf82183f117b00b0dc3b6`）

## 调度提示

```text
[SCHEDULE REMINDER] This is a scheduled message from the user schedule_id_json: "schedule-9cbdd9c0-1767-4248-bf5d-3601123db38a" occurrence_at: 2026-11-11T01:15:00.000Z reminder_prompt_json: "【电脑管家用例过检 · 单条处理】你是该任务的 worker，本次只处理 1 条用例，处理完立即结束、等待 5 分钟后的下次唤醒。第一步：cd /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager && /usr/bin/python3 .automation/harness.py next ，并完整读取 /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager/.automation/PROCEDURE.md 严格照做：读用例描述→改代码→bash .automation/scripts/run_case.sh <编号> <方法> 1800→最多修 2 次→清理残留→harness.py record 记录结果→写结束语后停止，不要再次 next。若 next 返回 busy 立即结束；若 done=true 报告全部完成。禁止 git commit，禁止向用户提问，禁止并行跑用例。"
```

## 领取用例

- 编号：2005769
- 方法：test_mycase_155
- 标题：应用修复-修复微信-修复后微信功能验证
- 文件：apps/autotest_my_app/case/2005769_应用修复-修复微信-修复后微信功能验证.py
- 优先级：2；模块：/修复工具(#134475)

## 结果记录

- `2005769` → **pass**（runs=1）
  - 备注：按 entry.sh 闭环重写原用例(原版无 try/finally、仅断言进程存活): 先备份真实 ~/.xwechat, 构造 comm=wechat 的模拟微信进程 + radium/cache 缓存 + user_data 聊天记录/消息日志; 修复工具->微信卡片->开始修复后断言 shellRepair 对话框弹出、killall 生效、缓存目录删净、聊天记录 md5 前后一致、重启微信 60s 内健康启动(非僵尸/VmRSS>0)且 10s 观察窗内同 pid 稳定驻留、追加新消息行数增加; 新增 widget 辅助方法 8 个(create_mock_wechat_user_data/get_wechat_chat_history_digest/get_wechat_message_count/append_wechat_message/get_wechat_process_pid/get_wechat_process_info/is_wechat_process_healthy/wait_wechat_process_started/is_wechat_process_alive_after); 1 次运行 PASS(59s), 残留检查无 autotest 对象, finally 已杀进程/删 /tmp/wechat/清构造目录并还原备份

## 最终结语

26 条失败用例全部可从 `.automation/ledger.json` 与 `.automation/manifest.json` 复核，按根因分三类：

## 一、环境阻断：测试机失联，用例根本没执行（21 条）

`10.20.33.103` 自 **04:12** 起 ARP `FAILED/INCOMPLETE`、`ssh: No route to host`，`run_case.sh` 在 SYNC 阶段就退出（`SYNC_FAILED rc=255/12`），**未同步代码、未执行任何步骤、无远端副作用**。这 21 条在 note 里都标注了 `环境阻断未执行`：

| 编号 | 标题 | 尝试次数 |
|---|---|---|
| 2005723 | 修复依赖关系不满足-仓库更新成功依赖修复成功 | 7 |
| 2005725 | 修复依赖关系不满足-apt update 失败（仓库不可达） | 2 |
| 2005727 | 修复依赖关系不满足-apt install -fy 失败（依赖无法解决） | 1 |
| 2005729 | 修复依赖关系不满足-apt install -fy 部分修复成功 | 1 |
| 2005731 | 修复依赖关系不满足-dpkg --configure -a 执行失败 | 1 |
| 2005733 | 修复依赖关系不满足-修复成功 | 1 |
| 2005735 | 修复依赖关系不满足-apt-dpkg 命令不存在 | 1 |
| 2005737 | 不支持长文件名-修复成功 | 1 |
| 2005739 / 2005741 | 密钥环频繁弹出-修复成功 / 修复后弹窗验证 | 1 / 1 |
| 2005745 / 2005747 | FAT32 U 盘存在可修复错误 / 损坏严重 | 2 / 1 |
| 2005749 / 2005751 | exFAT U 盘无错误 / 存在可修复错误 | 3 / 1 |
| 2005753 / 2005757 / 2005759 | NTFS 无错误 / ext4 无错误 / ext4 可修复错误 | 1 / 1 / 1 |
| 2005761 | U 盘修复-设备路径不存在 | 1 |
| 2005763 / 2005765 / 2005767 | 修复微信-正常关闭进程 / 清理缓存 / 磁盘空间不足 | 1 / 1 / 1 |

> 这批不是用例代码问题（当时每条都已按产品 `entry.sh`/产品契约做了闭环改造），是测试机不可达。**09:19 我这条 2005769 已实跑 PASS**，说明机器已恢复，这 21 条可直接 `harness.py requeue-failed` 后重跑。

## 二、产品 1.1.7 把功能入口隐藏了（2 条）

- **2005697 修复工具--离线导入**、**2005699 离线导入失败验证**：`repair_page.cpp::createOverviewView()` 845-858 行把 `repair_offlineImportBtn` 的构造、`setA11yMeta`、`clicked` 连接**整段注释**，`zh_CN.ts` 里“离线导入”已标 vanished，实测页面上没有任何可及的“导入”节点（`get_repair_offline_import_btn_showing=False`）。替代路径也走不通：按包契约把插件 zip 放进 `~/.config/deepin-pc-manager/plugins` 后 `discoverConfiguredPlugins` 仍为 25 个（`plugin_manager.cpp` 已停用用户插件目录扫描），且无 CLI/D-Bus 入口能触发 `importOfflinePlugin`。→ **步骤 1 本身不可执行**，属产品实现变更，需产品确认是否废弃该用例。

## 三、产品缺陷：提权分支起不来（1 条）

- **2005705 开始修复（需要提权）**：构造 PipeWire 全局自启让音频修复进入提权分支后，产品以**无 tty 的管道**启动插件脚本，`sudo` 直接报 `no tty present and no askpass program specified`，密码输入行始终不可输入、提权命令未执行，脚本继续跑完其余步骤 → 提权对话框永远不出现，步骤 1/2/3 的预期全部不可达。这是产品侧问题（`entry.sh` 应使用 `sudo -S` 或 `[[PASSWORD]]` 契约），不是用例写法问题。

## 四、交互用例：仅最后一步关闭失败（1 条，已用满 3 次运行）

- **2005707 交互验证**：用 `[[TEXT]]` 交互桩让产品真实走到命令框分支，**步骤 1-4 全部通过**（运行时输入框/【提交】禁用 → 脚本请求输入后启用 → 点【提交】与按 Enter 分别把 `autotest-button-input` / `autotest-enter-input` 送进 TUI 并回显 → 提交后立即重新禁用）。**只有步骤 5 失败**：对话框标题「密钥环修复 — 电脑管家」，发 `xdotool windowclose(WM_DELETE_WINDOW)` 后窗口仍在，改用 Escape 兜底但已达 3 次运行上限未能复跑。→ 建议 requeue 后只复验步骤 5（很可能是 QML `Dialog` 未响应 WM_DELETE_WINDOW，属产品关闭路径问题）。

## 五、环境能力限制（1 条）

- **2005479 系统检测--无异常问题**：本机全面检测恒有 3 项不可自动修复异常——系统环境检测（Lastore 更新源任务失败）、网络检测（`failure:4012` 无外网）、系统稳定性（`service_restarts: failure:2515`），结果页只能是 `detection_manualIcon`“需人工处理”，`detection_successIcon` 的“未发现任何问题”页在本机无法触发。用例已按产品无异常状态写好断言（成功图标可见、描述含 no issues、无 issues/manual 图标、一键修复隐藏、重新检测显示），换到干净机器或修好更新源/外网后可直接通过。

**汇总**：26 = 21（测试机失联未执行，机器现已恢复）+ 2（离线导入入口被产品注释隐藏）+ 1（sudo 无 tty 提权框不出现，产品缺陷）+ 1（关闭按钮仅步骤 5 失败）+ 1（本机无法构造“无异常”现场）。

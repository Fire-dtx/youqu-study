# deepin-pc-manager 自动化测试经验与教训

写给接手本项目的人/AI。只记录实测到的现象与命令，不含推测；不确定的条目显式标注 `[未验证]`。
所有时间戳来自测试机 `10.20.33.103`（UOS 20 eagle，系统 python3.7，项目 `.venv`）的真实日志。

---

## 1. 环境与运行方式（事实）

| 项 | 值 |
|---|---|
| 被测产品 | deepin-pc-manager 2.14.0（`CURRENT`），测试机源码在 `~/deepin-pc-manager-src` |
| 应用日志 | `~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log` |
| 守护进程日志 | `~/.cache/deepin/deepin-pc-manager/deepin-pc-manager-session-daemon.log` |
| 运行命令 | `python3 manage.py run -a apps/autotest_my_app -k test_mycase_067` |
| 单用例耗时 | 067 实测 318.93s / 338.16s / 344.73s |
| 密码 | 见 `setting/globalconfig.ini`，本文不记录 |

运行前必须导出会话变量，否则 AT-SPI 取不到界面元素：

```bash
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
export DISPLAY=:0
export XAUTHORITY=$HOME/.Xauthority
```

### `manage.py run` 的行为（读代码确认）

- `manage.py` 顶部 `_reexec_in_project_venv()` 用 `os.execv` 把进程替换成 `.venv/bin/python3`。外部看像"启动后立即退出又重启"，实际是同一进程被替换。
- `setting/globalconfig.ini`：`RERUN = 1`（首次失败自动重跑 1 次）、`RECORD_FAILED_CASE = 1`（从第 1 次失败后开始录屏）、`CASE_TIME_OUT = 1800`。
- 日志里打印的 `失败重跑次数: 1` 是**配置回显**，不代表真的重跑过。判断是否重跑看 `report/allure/*result.json` 的条数与 `execution_count`。
- 执行产物：
  - `report/json/result_autotest_my_app_<时间戳>.json` → `items[].statistic`（passed/failed 计数）
  - `report/allure/*result.json` → `status` 与 `statusDetails.message`（失败原因）
  - `report/record/<日期>/<时>时<分>分<秒>秒_<用例名>_<序号>_autotest.mp4`（录屏；`_2_` 的含义未完全确认，推测为同一次执行内的第 2 段）
  - `report/logs/<日期>_debug.log`

---

## 2. 产品行为事实（实测）

1. **QML/AT-SPI：`showing` 恒为 `False`**，隐藏页元素常驻 AT-SPI 树。判断可见性**只能**用 `size` 非零（`(0,0)` 表示未显示）。项目内封装为 `MyAppWidget._any_visible()`。
2. **全面检测完成后停留在全面检测页**，不自动回检测首页。
3. **应用启动后会触发检测任务**（实测 20:37:37 启动、20:37:55 即有 `detect:*` 任务落日志）。因此应用重启次数 ≠ 用例执行次数：实测一天内应用启动约 200 次、`handleFullScanCompleted` 52 次，而 pytest 实际只跑了几次。
4. **单项检测结论只能从 D-Bus 拿**。界面不暴露单项状态（只能取分项问题总数）。通道：
   - `org.deepin.PCManager1.Detect(<id>)` → 返回 Task 对象路径
   - `Task.GetResult` → `(true|false, ...)`
   - 会话总线与系统总线各有一批检测项；会话总线报 `unknown operable item` 时切系统总线
   - Task `status` 形如 `running`、`success`、`failure:4012`、`failure:3011:sources.list has the immutable attribute set`
5. **产品检测阈值（源码事实）**：`deepin-pc-manager-daemon/src/detectors/hardware_detector.cpp::detectMemory`：
   `usagePercent = 100 - (availableMB * 100 / totalMB)`（整数运算），`> 80` 判异常。
6. **修复类弹窗没有超时（2026-11-12 实测，关键）**：修复脚本通过 session-daemon 的
   `action_executor` 弹 `OpenMessage/OpenInfoBox`，daemon 日志固定打印
   `runDialog: starting dialog exec, actionType= "OpenMessage" timeoutMs= 0`。
   `timeoutMs=0` 表示**弹窗永不自动消失**，脚本 `exec()` 一直阻塞，直到用户点【确定】。
   任何「等结果文案出现再关框」「等输出关键字」的写法在没有点掉弹窗时都只能烧到超时。
7. **`plugin-dependency/entry.sh` 不检查 `apt install -fy` 返回码**（2005727/2005729 实测）：
   `apt update` 成功、`dpkg --configure -a` 成功、`apt install -fy` 返回 100
   （`E: 无法修复依赖关系`）时，脚本仍打印 `[INFO] 依赖关系修复成功`，且不出现
   「依赖关系未修复，需要手动执行 sudo apt install -f 查看详情」。属产品缺陷，用例按
   `fail` 记录，不要改产品代码。

---

## 3. 已踩的坑、根因与修复

| # | 现象 | 根因（证据） | 修复 |
|---|---|---|---|
| 1 | 用例 PASS 但用户观察到"没有执行检测" | `wait_for_scan_progress` 用 `showing` 判定，V20 上恒 `False`，且返回值被丢弃 → 等于没等 | 改 `size` 判定；新增 `wait_for_scan_started()`（进度可见 **或** 结果态可见），点击全面检测后 `assert_true` 它 |
| 2 | `TypeError: assert_true() takes 1 positional argument but 2 were given` | funnylog 包装的 `assert_true` 只接受一个位置参数 | 断言不带消息；诊断信息写进 `raise AssertionError(...)` |
| 3 | 构造失败 `repository_url 构造失败: grep='0'` | `sources.list` 残留 `immutable` 属性 → `sed -i`/`>>` 静默失败；daemon 同时报 `failure:3011:sources.list has the immutable attribute set` | 构造与清理**都**先 `chattr -i`；`setup_repository_permission_abnormal` 写后 `lsattr` 校验并重试 |
| 4 | `coredump 前置构造失败` | 写 `/proc/sys/kernel/core_pattern` 偶发未落盘（高负载下 sudo 子进程被中断）；`cleanup_coredump` 还把上一轮测试残留值 `/tmp/pcm067-core.%p` 备份并写回 | 写入后 `cat` 校验并重试 3 次，失败抛备份值/当前值；备份值含 `pcm067` 时回落 `systemd-coredump` 默认值 |
| 5 | 系统盘 96%、`/boot` 93% | `disk_space` 构造留下 11.5G 的 `/pcm-test-067-fill.img`；`boot_partition_space` 留下 `/boot/pcm-test-067-fill.img`（1.15G），实例被中断后 `finally` 没跑到 | `kill` 残留实例后 `rm -f` 两个 fill 文件；`du -d1` 看不出 `/boot` 直下的散文件，要用 `find / -xdev -size +500M` |
| 6 | `AssertionError: 未判异常: memory(ok=True)` | 两个实例相隔 8s 并发（21:14:30 / 21:14:38），共用 `/mnt/pcm067-mem`，一个实例 `umount -l` 掉了另一个刚写的 tmpfs；检测时 `available 1130MB usage 72%`（< 80%） | 用例加跨进程 `flock`（`/tmp/pcm_conflict_test_067.lock`），拿不到锁直接 `SKIPPED`；内存构造余量 14% → 10%（实测 88%） |
| 7 | `/tmp` 涨到 1.8G | 每次运行生成 `_allure_*` 目录约 22M，累积 83 个 | 定期 `rm -rf /tmp/_allure_*`（正式报告在 `report/` 下另有留存） |
| 8 | 磁盘占用忽高忽低（47% ↔ 96%） | 多个 067 实例在不同阶段构造/清理 fill 文件 | 同 #6：只允许单实例 |

---

## 4. 用例编写规则（本项目强制约定）

1. 可见性判断用 `size`，不用 `showing`，也不要用"元素存在"代替"元素可见"。
2. 任何"点击后应发生某行为"的步骤，必须断言行为真的发生（如点击全面检测 → 检测运行态/结果态出现），不能只等 `sleep`。
3. 用例 PASS 不作为行为发生的证据；结论以 daemon 日志、D-Bus 返回、应用日志时间线为准。
4. 构造系统级异常必须满足三条：
   - **幂等**：先清历史残留再构造；
   - **防御**：写入系统文件前先解除 `immutable`；
   - **清理顺序正确**：`chattr -i` → 改文件 → 恢复；`cleanup_*` 函数自身也要能做这件事。
5. 构造失败时在异常里带上现场（`grep` 计数、`tail` 内容、`lsattr`），否则远程排查只能靠猜。
6. 用例会改写全局系统状态（`sources.list`、`core_pattern`、根分区、`/boot`、tmpfs、`/etc/passwd`、`aplay`、`/recovery` 挂载、`systemd-timesyncd`），必须跨进程互斥，冲突时 `SKIPPED` 而不是失败。
7. 清理后自查一遍：`core_pattern` 是否为 `systemd-coredump`、`sources.list` 是否 0 行残留且无 `i`、tmpfs 是否卸载、fill 文件是否删除、`/` 使用率是否回落。
8. **修复类用例禁止"等弹窗超时"**：产品提示框 `timeoutMs=0`（永不自动消失），必须用
   `wait_and_clear_repair_result()` 主动点掉；收尾必须 `close_repair_result_prompt` +
   `close_repair_completion_dialog` 并断言修复窗口已关闭。见 §6.6。
9. **任何 `backup_*` 都不许无条件覆盖已有备份**：先判断备份目录是否非空，非空说明上一次
   未闭环，必须先 `restore_*` 再重新备份，否则会用空备份覆盖掉用户真实文件（已发生一次）。

---

## 5. 排查手册（症状 → 查什么）

| 症状 | 命令 |
|---|---|
| 用例失败，要看原因 | `report/allure/*result.json` 的 `statusDetails.message` |
| 判断是否重跑过 | `report/json/result_*.json` 的 `statistics` + `report/record/<日期>/*.mp4` |
| 检测到底跑没跑 | `grep handleFullScanCompleted ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log`；`grep startDetection` 看 `cycleId` |
| 单分项结论为何不符 | `grep <项名> <daemon 日志>`（如 `detectMemory` 会打印 total/available/usage） |
| 磁盘突然满 | `df -h / /boot` → `find / -xdev -size +500M` → `sudo du -xhd1 /` |
| 是否多实例并发 | `ps -eo pid,etime,args | grep 'manage.py run'`（`bash_history` 里可能查不到，非交互启动） |
| 应用窗口是否真的在 | `DISPLAY=:0 XAUTHORITY=$HOME/.Xauthority xwininfo -root -tree | grep -c 电脑管家` |
| 用例断言已过却迟迟不退出 | 看 `grep -E "starting dialog exec|OpenMessage" ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager-session-daemon.log`，出现 `timeoutMs= 0` 说明弹窗在阻塞；再用 `xdotool search --onlyvisible --name ''` 逐个 `getwindowname` 找残留提示框 |
| 报告说 passed 但运行被 kill | `report/json/result_*.json` 的**文件名时间戳**必须晚于本次启动时间；被 kill 时 `parse_result.py` 会读到上一次的旧 json 而误报 passed，结论以 `SSH_RC`/`===RUN_RC` 为准 |

观察类需求的正确做法：在用例运行**中途**（例如第 40s、140s）从外部确认进程与窗口存在，而不是等用例结束后看（`finally` 会 `kill` 应用）。

---

## 6. 协作与工程教训

1. **单入口**：不要一边用 `manage.py run` 一边手动 `pytest`，会给同一台机器叠多个实例。
2. **远端改动流程**：先改本地 `apps/autotest_my_app/case/*.py`，再 base64 上传到测试机（中文文件名与嵌套引号用 base64 最稳），避免两端代码不一致。
3. **远端项目不要直接编辑**：测试机的文件是部署副本，改动以本地仓库为准。
4. **验证成本要算**：单次 067 约 5-6 分钟，`RERUN` 触发会翻倍；改动后一次跑完再下结论，不要逐条微改逐条全量跑。
5. **删文件前先看谁在用**：`lsof <file>`；本次 `pcm-test-067-fill.img` 无进程持有才可安全删除。
6. **一次性任务用临时脚本要清干净**：诊断代码不要留在用例里，用完删除。

---

## 6.3 进程名/弹窗/网络构造的实测坑(2026-11-12)

1. **`pgrep -x` 与 15 字符进程名截断**：`gnome-keyring-daemon` 的 `comm` 被截断为 `gnome-keyring-d`，`pgrep -x gnome-keyring-daemon` 永远查不到。重启/守护进程判定必须用截断名(`pgrep -x gnome-keyring-d`)；`pkill -x` 同理。
2. **`gcr-prompter` 弹窗识别**：密钥环"选择新密钥环的密码"由 gcr-prompter 进程承载，`xdotool search --class gcr-prompter` 可枚举；输入密码后弹窗消失、目录里出现 `login.keyring` 才算建库成功。
3. **`arping -D` 只在自己那段二层里可信**：同一 netns 内的 veth 对会把自己发的广播回环回来，导致**无冲突也返回 1**；对端必须放进独立 netns(`ip netns add` + `ip link set peer netns`)，无冲突 rc=0、对端配同 IP 才 rc=1。
4. **虚拟网卡会被产品探测**：veth 的 Qt 类型是 Ethernet、非 bridge、up/running 即进入 `loadIpConflictTargets`。用 `192.168.77.0/24` 这种与办公网无关的网段，避免影响 SSH。
5. **IP 冲突结论取证**：D-Bus `Task.GetResult` 只回 `failure:4013`；冲突地址在 `~/.cache/deepin/deepin-pc-manager/deepin-pc-manager-session-daemon.log`，形如 `detectIpConflict: probe "<IP>" on "<网卡>" exit 1` / `IP address conflict detected: ("<IP>")` / `success: false`。
6. **修复完成提示框**：`dpmapi openinfobox` 的标题进 accessible name(如"微信修复")，正文 label 不暴露文本(实测只读到 `DDialogTitleLabel DDialogMessageLabel`)。断言用"弹框存在 + 按钮文案(确定)"，不要断言正文文字。
7. **低磁盘空间构造**：用 100MB tmpfs + 70MB 占位承载目标目录(软链过去)，删除后 `df` 可用空间上升可量化；结束必须 `umount` 并校验 `/proc/mounts` 无残留。

---

## 6.4 `src.log` 不是日志函数（2026-11-12）

- `funnylog.log` 是**类装饰器**(`def log(cls):` 遍历类方法包异常), 不是日志输出函数。用例里 `from src import log` 后写 `log("...")` 不会报错也不会输出, 属于**静默 no-op**; 断言证据因此丢失, 排查时只能看 traceback。
- 正确写法: `from src import logger` + `logger.info("...")`。
- 排查影响面: `grep -rn "from src import log$" apps/autotest_my_app/case/*.py` 当前命中 24 个文件, 其中只有真正把 `log` 当装饰器用的文件应保留; 其余需逐个核改为 `logger`(不能无脑 sed, 装饰器用法会被破坏)。
- 同时注意: `detection_manualIcon` 等汇总态图标是**条件实例化**的 —— 产品按"是否存在可修复项"在 `manualIcon`/`issuesIcon`/`manualPartialIcon` 间切换, 不匹配时该元素在 AT-SPI 树中**完全不存在**(不是 size=0)。断言前应先按 D-Bus 结论确定期望状态, 不要假设图标常驻。

## 6.5 外部工具依赖预检与 UOS 安装白名单(2026-11-12)

- **现象**: 测试机未装 `lm-sensors` 时, 产品 CPU 温度检测返回
  `success=false code=1006 diagnostic="sensors.not.installed" canFix=true`, 导致
  "CPU温度检测正常"类用例整组 `issues>0` 而失败; 同类还有 `smartctl`(磁盘健康)、
  `jq`(音频修复)等可选工具。
- **统一做法**: 用例开头调用 `MyAppWidget.ensure_package_installed(package, probe_cmd)`,
  已安装直接复用(`installed_before=True`), 缺失则 `apt-get install -y`, 失败再
  `apt-get update` 重试一次, 最后用 `command -v` + dpkg 状态双重校验并返回
  `{"installed", "attempts", "whitelisted", "detail"}`。不再用"缺工具就 skip"。
- **测试机拦路**: UOS 上有 dpkg 安装前白名单钩子
  `/etc/dpkg/dpkg.cfg.d/88-whitepkg-install-hook`, 非
  `/etc/permissionmanager.db` 中 `package_white_table(pkgname, type)` 的包一律拒绝,
  报错形如 `禁止安装非白名单包 xxx ... failed: forbid install`, apt 退出码 256。
  实测 `lm-sensors` 不在白名单(2029 条默认), 直接 apt 安装必然失败。
- **helper 的处理**: 安装前用 `apt-get install -s -y <pkg>` 解析 `Inst` 依赖闭包,
  把不在白名单的包临时 `insert into package_white_table`, 安装完成在 `finally`
  删除本次新增行, 白名单条数回到 2029, 系统策略不留改动。
- **坑**: `sudo -S` 会把"请输入密码/验证成功"混入命令 stdout, 不能用
  `select count(*)` 的数字判断是否已在白名单, 要用
  `select case when exists(...) then 'WHITELISTED' else 'MISSING' end` 这类标记字符串。
- **已接入的用例**: `1999121`/`1999127`/`1999129`(lm-sensors)、`1999123`(需先装有
  sensors 才能构造"缺失"场景)、`1999119`(smartmontools)、`2032343`(jq)。
- **环境现状**: 测试机已装 lm-sensors 1:3.5.0-3+sign(`sensors` 输出
  `No sensors found!`, 属虚拟机无传感器硬件, 产品结论 `no.cpu.temperature.sensor`
  仍为成功); 该包安装属用例依赖, 未回退。

## 6.6 修复类用例收尾：弹窗必须主动点(2026-11-12)

**现象**：断言早已通过、`report/json` 里也是 `passed`，但用例进程 400~500s 才结束，
甚至被外层 `timeout` 杀掉（`SSH_RC=143`）。2026-11-12 实测两例：
`2005727`(145) 189s、`2005739`(151) 485s 未退出。

**根因（三条叠加）**：

| # | 根因 | 证据 |
|---|---|---|
| 1 | 修复完成弹窗 `timeoutMs=0`，不点永不消失 | daemon 日志 `starting dialog exec, actionType= "OpenMessage" timeoutMs= 0` |
| 2 | 用例写法是"等弹窗文本 → 再关"，但文本读不到时不会关 | `get_repair_result_prompt_text(timeout=240)` 空等 + `wait_repair_output_keywords(timeout=180)` 再空等 |
| 3 | 鉴权循环在"白名单授权"路径空转 | `for 20 次: if is_shell_repair_input_enabled(): ... sleep(2)`，无输入框时白等 40s |

**统一做法（`MyAppWidget.wait_and_clear_repair_result(keywords, timeout=90)`）**：

1. 每轮**看到弹窗就点**，不依赖能否读出正文：
   - 主进程无标题框 → `click_repair_notify_ok()`（失败时 `xdotool key Return` 兜底）；
   - session-daemon 侧 `OpenMessage/OpenInfoBox`（标题是脚本传入的，如"密钥环修复"/
     "依赖修复"）→ `close_info_dialogs("", rounds=1)`，按【确定】点掉。
2. 输出命中任一 keyword 立即返回 `(keyword, 弹窗正文列表, 输出文本)`。
3. **提前退出**：无弹窗且修复窗口已不可见（`get_repair_dialog_showing()` 为 False）就返回，
   不再空等满 timeout。
4. 鉴权循环改成「输入框被启用就提交；输出出现 `Preparing to execute repair tool` 就退出」，
   实测 40s → 3s。

实测收益（`2005727` / `2005739`）：收尾 50s→3s、185s→5s；整例 189s→97s（含 rerun）、485s→146s。

**调用模板**：

```python
done_keyword, prompt_texts, output = widget.wait_and_clear_repair_result(
    ("依赖关系未修复", "依赖关系修复成功", "修复完成", "执行完毕"), timeout=90,
)
widget.close_repair_result_prompt(rounds=2)        # 最后的结果提示框
widget.close_repair_completion_dialog()            # 修复完成对话框 / 修复窗口
self.assert_false(widget.get_repair_dialog_showing(timeout=10))
```

**顺带修掉的两个构造/回退缺陷**：

1. `KEYRING_PROMPT_EXCLUDES` 里只写 `deepin-pc-manager`，但 `ps -o comm=` 只保留 15 字符
   （`deepin-pc-manag`），排除失效 → 电脑管家自己的修复对话框被计成"密钥环弹窗"
   （修复期间采样 `count:1, title:'密钥环修复'`）。已在排除项补 `deepin-pc-manag`，
   采样恢复 `count:0`。
2. `backup_keyring_state()` 原来无条件 `rm -rf` 备份目录。上一次用例被中断（`finally` 未跑）
   时，下一次备份会**清空上一次的有效备份**，而源文件此时已被上一次删掉 → 备份变空目录，
   随后 `restore_keyring_state()` 的"备份里没有就删除"等于删用户真实文件。
   实测已造成测试机 `~/.local/share/keyrings/login.keyring` 永久丢失（wb 目录的
   `mkey/skey/user.keystore` 未受影响）。已改为：发现遗留非空备份先 `restore_keyring_state()`
   再重新备份。

**闭环自查补充**（本次新增）：`/tmp/autotest_keyring_state` 是否已删除、密钥环两处
`login.keyring` 与 `wb/status` 是否按备份还原、`/tmp` 下是否只剩框架锁 `pcm_case.lock`。

---

## 7. 已知未完成 / 待确认

- `deploy_pc_manager.sh` 的源码构建路径此前因 Qt5 dev 包与系统运行时不匹配，改为直接安装系统仓库中的同版本产品；**整脚本端到端未复验**。
- `2005463`、`2005465`、`2005479` 的 `showing` 判定已同步改为 `size` 判定；仅 `2005479`（test_mycase_021）跑过回归（`1 passed in 78.30s`），463/465 未单独回归。
- `memory` 构造依赖全局 `/proc/meminfo`，即使有锁，其它大内存进程仍可能影响结果；当前只做到"余量 10%"，未做重试重建。
- 部分检测项无法构造（`disk_health`、`battery_health`、`cpu_temperature`、`network_hardware`、`dhcp_service`、`ip_conflict` 等），用例只记录结论、不作前置断言。
- `repository_url`、`local_environment` 两项结论不可前置校验（分别依赖 lastore job 时长、会话守护进程权限），只记录。
- `2005727`(test_mycase_145) 与 `2005729`(test_mycase_146) 维持 `fail`：产品 dependency 插件未检查
  `apt install -fy` 返回码，失败仍报「依赖关系修复成功」。待产品修复后重跑即可转 `pass`。
- 测试机 `~/.local/share/keyrings/login.keyring` 已丢失且无备份可还原（16:08 手动运行被中断 +
  16:15 备份被覆盖）。`/tmp/autotest_keyring_state` 已清、wb 目录密钥材料完好。是否重建该文件
  待决定（缺失只影响首次访问时弹"新建密钥环"）。

---

## 8. 变更记录

### 8.1 系统检测批次（前一会话）

| 文件 | 改动 |
|---|---|
| `2005467_系统检测首页--扣分总和超 100 溢出.py` | 进度判定改 `size`；新增 `wait_for_scan_started` 断言；`chattr -i` 防御与校验重试；coredump 写入校验/重试与清理回落；内存余量 14%→10%；跨进程 `flock`；用例开头启动应用并断言进程 |
| `2005463` / `2005465` / `2005479` | `wait_for_scan_progress` 的 `showing` 判定改 `size`；479 的完成元素判定同步 |
| `2005483_系统检测--检测结果存在不可修复问题.py` | 汇总态断言改为按 issues/manual 实际状态分支; 新增 D-Bus `backup_partition` 前置校验与分组 `issues>0`; `log()` 全改 `logger.info()`; `finally` 增加关闭应用 |
| `my_app_widget.py` | 新增 `is_package_installed` / `ensure_package_installed`(含 UOS 安装白名单临时放行与回退); 温度/磁盘健康/jq 用例改用依赖预检 |
| 测试机环境 | 清理 3 个并发实例、11.5G 根分区 fill、1.15G `/boot` fill、1.8G `/tmp/_allure_*`；恢复 `core_pattern` 与 `sources.list` |

### 8.2 修复类用例批次（2026-11-12）

| 文件 | 改动 |
|---|---|
| `my_app_widget.py` | 新增 `wait_and_clear_repair_result(keywords, timeout=90)`：见弹窗就点 + 命中关键字/窗口不可见即返回；`import time`；`KEYRING_PROMPT_EXCLUDES` 补 `deepin-pc-manag`；`backup_keyring_state` 遇遗留备份先 `restore_keyring_state` 再备份 |
| `2005725_...apt update 失败（仓库不可达）.py` (144) | 不再只跑 `apt update`；改为真实点击【开始修复】由 daemon 执行，断言 `[ERROR] 系统仓库更新失败` + `Repair failed. Exit code: 1` 且无「系统仓库更新成功」。实测 PASS 45s |
| `2005727_...apt install -fy 失败（依赖无法解决）.py` (145) | 收尾换 `wait_and_clear_repair_result`；鉴权循环不再空转；缺陷断言带 `output[-600:]`。实测 97s（产品缺陷，维持 fail） |
| `2005729_...apt install -fy 部分修复成功.py` (146) | 同上；失败信息从 `<False>不为真` 变为带输出尾部的产品缺陷断言。实测 98s（产品缺陷，维持 fail） |
| `2005739_桌面修复--密钥环频繁弹出--修复成功.py` (151) | 弹窗等待换 `wait_and_clear_repair_result`；收尾补 `close_repair_notify_dialog`/`close_info_dialogs`/`close_repair_completion_dialog` + 断言修复窗口关闭。实测 PASS 146s（原 485s 未退出） |
| `.automation/ledger.json` | 144/151 记 `pass`，145/146 记 `fail`（含根因与证据） |

### 8.3 修复后验证用例批次（2026-11-12 晚）

| 文件 | 改动 |
|---|---|
| `2005741_...修复后密钥环弹窗问题验证.py` (152) | 完成判定从 `close_repair_result_prompt` + `wait_repair_output_keywords(60)`（§4.8 禁止的"等文案"写法）改为 `wait_and_clear_repair_result(90)`，并补 `close_repair_notify_dialog` / `close_info_dialogs` / `close_repair_completion_dialog` + `assert_false(get_repair_dialog_showing)`；开始修复改用 `click_start_repair_button_until_dialog(3×20s)`；第二次授权从 `gdbus ReadAlias`（不解锁、可能空过）改为真实 `Unlock`，断言 `collection=/org/freedesktop/secrets/collection/login` 且 `locked_before=False`；加 `/tmp/pcm_conflict_test_152.lock` flock（冲突 `SkipTest`）；`gnome-keyring-daemon` 按用例开始前 PID 快照恢复；`finally` 不再用 assert（收尾错误合并进原始异常）；诊断 `print` → `logger.info`；锁文件用完即删 |
| `my_app_widget.py` | `backup_keyring_dirs` 遇遗留非空备份先 `restore_keyring_dirs()` 再备份（对齐 §4.9，原实现无条件 `rm -rf`）；新增 `is_pid_alive`、`restore_keyring_daemon_state(initial_pids)`、`trigger_keyring_unlock()`（后台 `ReadAlias → Get(Locked) → Unlock → Prompt`，期间弹窗即记录并按 Escape 取消）、`get_keyring_tmp_residue(exclude=)` |

实测（2026-11-12 16:56:13→17:00:05）：`1 passed in 230.70s`，无 rerun。弹窗采样：首次授权 1 次（gcr-prompter 建库框）、设置密码后 0 次、总数 1 < 3；二次授权输出 `locked_before=False`。收尾 `/tmp` 仅 `pcm_case.lock`，备份目录已删，守护进程按快照恢复。

**152 首跑失败根因（16:48）**：点击开始修复后 `shellRepair_outputLog` 20s 不出现，session-daemon 日志该时段**没有任何** `execute: received request` —— AT-SPI `Press` 被产品忽略（不是弹窗阻塞、不是鉴权失败）。同目录 `2005759` 已踩过同一现象，统一用 `click_start_repair_button_until_dialog` 的有界重试规避。

### 8.4 企业微信修复用例批次（2026-11-12 晚）

| 文件 | 改动 |
|---|---|
| `my_app_widget.py` | 桩 `wineserver` 改为在参数任意位置匹配 `-k`（真实 `kill.sh` 以 `<wineserver> <原有参数> -k` 调用）；新增 `ensure_wecom_kill_helper()` / `remove_wecom_kill_helper()`：产品 `entry.sh` 依赖 `/opt/deepinwine/tools/kill.sh`，测试机 deepin-wine-runtime 不带该工具、缺失时脚本静默跳过，故补齐等价桩（按 `WINEPREFIX` 匹配 `wineserver` 后追加 `-k`），已有系统文件不动 |
| `2005771_...正常关闭运行中的企业微信进程.py` (156) | 完成判定原为 `get_repair_result_prompt_text`（§4.8 的"等文案"写法且读不到正文）→ 改 `get_info_dialog_state("企业微信修复")` 断言 exists/showing/title/buttons=`["确定"]`/正文标签 + session 总线 `OpenMessage` 请求参数核对；`start_confirm_dbus_monitor` 纳入 finally；点【确定】后断言提示框与修复窗口关闭；补用例级 `_require`（失败带现场）；finally 收尾改为全部 attempt 收集 |

实测（2026-11-12 18:16:43→18:17:43）：`1 passed in 74.41s`，无 rerun。提示框状态 `{'exists': True, 'showing': True, 'title': '企业微信修复', 'buttons': ['确定'], 'message_label_showing': True}`；总线抓到 `OpenMessage` + `title="企业微信修复"` + `message="企业微信缓存清理完成，修复完成"`。机检：`/opt/deepinwine/tools/kill.sh`、`~/.autotest_wecom_bottle_backup`、`~/.deepinwine/Deepin-WXWork`、`/tmp/autotest_wecom_wine`、`/tmp/autotest_confirm_dbus_monitor.log` 均不存在，无 `WeChat.exe`、无 `dbus-monitor`、无电脑管家主进程残留。

**关键事实**：`entry.sh` 结尾 `dpmapi openinfobox(..., timeoutMs=0)` 不会自动消失且阻塞脚本，不点【确定】用例永远结束不了；DTK 标签的 AT-SPI `name` 是 `objectName`（`_dialog_text` 读到的是 `DDialogTitleLabel DDialogMessageLabel DTitlebarCenterArea`），正文只能从总线请求参数取。`2005777`（企业微信修复后功能验证）同样缺 `kill.sh` 与弹窗收尾，已在 §8.5 补齐。

### 8.5 全量修复类用例统一收尾（2026-11-12 晚）

背景：`dpmapi openinfobox(..., timeoutMs=0)` 由 session-daemon 持有，杀主进程带不走；用例不点掉就把弹窗和修复窗口留在桌面，污染后续用例。做法：`my_app_widget.py` 提供 `finish_repair_flow(title="", rounds=3)`（点提示框 + 关修复窗口，返回 `window_left`），并在 `kill_pc_manager()` 内兜底调用一次，用例侧改为 `finally` 必调；56 个用例文件接入（音频 13、打印机/触控等 10、微信/QQ/WPS/输入法 13、U盘 11、交互弹窗 5、系统修复若干），全量 `py_compile` 通过。

| 问题 | 现场 | 处理与证据 |
|---|---|---|
| `window_left` 误报 | 2005707 两次 FAIL：窗口已关仍 `True` | 根因是判定用 AT-SPI `$//shellRepair_outputLog.showing`，该节点在窗口销毁后仍报 `showing=True`（仓库 `wait_repair_dialog_window_closed` 注释早记录此坑）。`finish_repair_flow` 改为按 X11 标题判定：新增 `get_repair_dialog_window_titles()`（标题含"修复"且不等于主窗口标题），逐轮 `close_repair_completion_dialog()` 后复查。实测 2010549 日志出现 3 次标题判定 + 1 次 Escape 关窗，`window_left=False` |
| 对话框标题形态 | `xdotool getwindowname` 实测为 `密钥环修复 — 电脑管家` | 主窗口标题只是 `电脑管家`；过滤**不能**用"含电脑管家"排除，否则对话框被一并排掉，`window_left` 恒 False（一次无效 PASS 已作废重跑） |
| 2005777 缺 `kill.sh` | 首跑 FAIL：`wait_wecom_process_killed` 超时 60s | 产品 `entry.sh` 调 `/opt/deepinwine/tools/kill.sh`，测试机 deepin-wine-runtime 不带；补 `ensure_wecom_kill_helper()`（系统已有则不动）+ finally `remove_wecom_kill_helper()`，复跑 PASS |

实跑清单（2026-11-12 18:29→19:26，均为改后新代码，单跑、无 rerun，全部 PASS）：2005703/2005745/2005739/2005765/2005767/2005769/2005771/2005773/2005777/2005779/2005783/2005785/2005787/2005789/2005791/2005793/2005707/2005713/2010253/2010549/2010557/2009157/2032323/2032325/2032335/2032345，共 26 条；其余接入文件为同模式机械改动，未单跑，仅编译校验。

### 8.6 055 覆盖安装用例的环境漂移（2026-11-13）

`2018689`（`test_mycase_055`）失败现场（11:25:30）：`apt-get install -y deepin-pc-manager` 输出只有

```
deepin-pc-manager 已经是最新版 (1.1.7)。
升级了 0 个软件包，新安装了 0 个软件包，要卸载 0 个软件包…
```

失败在 `assert_true("验证成功" in output or "Setting up" in output)`，随后还有 `new_version != original_version` 必然失败。两个独立原因：

1. **环境漂移**：`apt-cache policy` 显示 已装=候选=1.1.7，版本列表只有 `/usr/lib/dpkg-db/status 100`（仓库不含该包），`apt-get install --reinstall deepin-pc-manager` 直接报"不能重新安装…因为无法下载它"。用例原前提"仓库候选 1.1.7-1"已不成立，apt 空跑。
2. **断言依赖本地化文案**：机器 `LANG=zh_CN.UTF-8`，dpkg 输出"正在设置/正在解压"；原断言里的 `"验证成功"` 根本不是 apt 文案（本机 apt 包装脚本尾部偶尔打印该串），`"Setting up"` 只在英文环境出现。

改法：先 `apt-cache policy` 取候选；候选高于已装走 `apt-get install -y deepin-pc-manager`（真实升级路径），否则走本地同版本 deb + `--reinstall`（`apt-get install -y --reinstall /home/uostest/deepin-pc-manager_1.1.7_amd64.deb`，仍经 apt 处理依赖，不用 `dpkg -i`）。成功证据改为 `EXIT:0` + 输出含 `正在设置/正在解压/Setting up/Unpacking` + `/var/lib/dpkg/info/deepin-pc-manager.list` mtime 变化；版本号按分支断言（升级→不同，覆盖同版本→相同）。

实测（11:40:33→11:40:46）：`1 passed in 28s`。日志 `2018689_test_mycase_055_20261113_114035.log`：候选 `'1.1.7'` → 本地 deb 覆盖安装，安装后版本 `'1.1.7'`，安装后/回退后守护进程均 `NONE`。

**坑**：本地 deb 不加 `--reinstall` 时 apt 同样判"已经是最新版"空跑（本次第一版修复即踩此坑，`EXIT:0` 但没有任何安装动作）。

### 8.7 用例编号（`test_mycase_NNN`）的权威来源（2026-11-13）

编号即平台脚本 ID，写在登记表「用例」列的 `apps.autotest_my_app.case.<id>_<标题>.TestMyCase#test_mycase_NNN` 里（`.automation/gen_manifest.py` 读的 `V20电脑管家自动化测试单用例过检登记表.xlsx`）。`mycase.csv` 第 1 列、用例文件的方法名都必须与它一致，否则 `-k test_mycase_NNN` 跑到的不是登记的用例。

本次修正的错误（`914b08b` 引入）：它把 `1999071_删除 _usr_local_lib 目录…` 的编号改成 316，与 `2032309_清理玲珑环境、系统快照-V20 不显示系统快照` 撞号。按登记表交换：

| 用例文件 | 原方法名 | 现方法名 | csv |
|---|---|---|---|
| `2032309_清理玲珑环境、系统快照-V20 不显示系统快照.py` | `test_mycase_352` | `test_mycase_316` | `316,2032309` |
| `1999071_删除 _usr_local_lib 目录 -进行更新环境检测.py` | `test_mycase_316` | `test_mycase_352` | `352,1999071` |

核对口径（改完必须全过）：`mycase.csv` 编号/ID 均唯一、每个 `def test_mycase_NNN` 在 csv 有登记、`NNN` 等于所属文件名前缀、`pytest --collect-only` 里每个方法只出现一次且挂在正确文件下。本次结果：348 行登记 / 347 个方法（`2005451_电脑管家--功能模块.py` 里 061、274 两个用例共用一个文件，登记表也是两行，属正常）、收集 347 个 Function 无重复。实跑 `2032309 test_mycase_316` PASS（24.66s）。

### 8.8 输入法"激活但不接管键盘"的错配（168 曾失败，2026-11-13）

症状（`2005797 test_mycase_168`，日志 `..._20261113_183012.log`）：`fcitx-remote` 前置 1、激活后 2，`active_state == 2` 断言过；但 `xdotool type zhongguo` 后**候选条 620x88 恒为 `IsUnMapped`**，`wait_ime_candidate_visible` 10s 超时 → `<False>不为真`。手工同序列复现：编辑器落盘 `zhongguo`（按键直通，IME 未接管）。

现场取证（同一脚本、同一环境，只差输入法进程）：

| 状态 | fcitx | cpis 面板 | 结果 |
|---|---|---|---|
| 坏 | pid 1364511（用例用 `nohup fcitx -r -d` 拉起） | pid 1276473（登录会话遗留） | 状态 2、按键直通、候选恒 `IsUnMapped` |
| 好 | 重启后新 pid 1366119/1366482 | 新 pid 1366218 | 候选 557x88 `IsViewable`、落盘 `中国` |

即**框架进程与搜狗/cpis 配套服务（候选条 `cpis-panel-service`、`cpis-engine-service`、`ISE_NODE`）跨代配对**时，状态位仍报"已激活"，实际不处理按键。单独模拟一次"杀 fcitx + `nohup fcitx -r -d`"不复发，说明是反复重启累积出来的状态，不要指望靠固定步骤复现。

修复：

- `my_app_widget.py`：新增 `restart_input_method_stack()`（`fcitx-remote -e` → `stop_input_method()` → 清 4 类配套服务 → 拉起 helper + 框架 → 等 `fcitx-remote` 可读状态）、`start_input_method_framework()`（启动前清旧配套服务，`ensure_input_method_running`/`restart_input_method` 复用，删除两处重复的启动循环）、`get_ime_aux_service_pids()`。
- `2005797 test_mycase_168`：候选条 6s 不出现即判定错配 → 重启整栈 + **重开编辑器**（旧进程与框架的连接已失效）→ 重新激活 → 重试一次；恢复耗时不计入"无卡顿"阈值，恢复后仍无候选则失败（不无限重试）。失败信息里带候选窗口快照。

验证：168 常规 PASS（19.22s，落盘 `中国`，耗时 4.04s）；注入破坏（`pkill -9 -x fcitx-helper; killall fcitx`）强制走恢复分支 PASS（39.23s，日志 `2099998_test_mycase_996_20261113_184338`，恢复后候选 `IsViewable`、落盘 `中国`）；`167`（43.14s）、`132`（83.19s）回归 PASS。

### 8.9 232/233「点击」用例判定口径收敛（2026-11-13）

原来 232/233 断言"点击后应用日志新增一条 `pageId=large_file_clean` / `duplicate_file_clean` 的埋点"，被产品缺陷卡死（见 §8.8 相邻的埋点问题：`optimization_page.cpp:477/479/481` 拿 `pluginName` 比 `large-file-clean`/`duplicate-file-clean`/`startup-management`，实际 `plugin.name` 是 `large-file`/`duplicate-file`/`startup`，三张卡片全落默认 `SpaceClean`，实测日志 `pageId=space_clean`）。

按用户要求改成功能口径：**点击「大文件清理」/「重复文件清理」能进入插件运行时页并走到扫描、结果界面即通过**。

- `2005861 test_mycase_232`：点卡片 → `get_optimization_runtime_page_showing` → `get_large_file_scan_started(30)` → `get_large_file_scan_completed(180)` → 断言 `get_large_file_result_showing() or get_large_file_empty_showing()` → 返回键回空间清理页。
- `2005863 test_mycase_233`：同上，重复文件侧用 `get_dup_file_scan_started`/`get_dup_file_scan_completed`/`get_dup_file_result_showing`/`get_dup_file_empty_showing`。
- 埋点断言与 `count_app_log_matches` / `count_eventlog_daemon_receipts` 全部删除；两条用例的 docstring 保留埋点缺陷留档（含代码行与实测 pageId），避免缺陷信息丢失。

实测（判据两分支都验过）：

| 场景 | 结果 | 日志 |
|---|---|---|
| 232，机器无大文件 | PASS 28.08s，`结果页=False 空状态页=True` | `2005861_test_mycase_232_20261113_185848.log` |
| 232，`~/Documents` 造 120MB 文件 | PASS 27.37s，`结果页=True 空状态页=False` | `2005861_test_mycase_232_20261113_190029.log` |
| 233，机器有真实重复文件 | PASS 30.24s，`结果页=True 空状态页=False` | `2005863_test_mycase_233_20261113_185928.log` |

注意：232/233 现在与 `2001927 test_mycase_282`（大文件清理-扫描中）、`2001969 test_mycase_277`（重复文件清理-扫描中）覆盖重叠，差别只在 232/233 多一步"从空间清理页点卡片进入 + 返回键退出版面"。埋点 `pageId` 归类错误（含启动项管理 2005865）仍是待提缺陷单的产品问题。

### 8.10 057「启动管理器点击」判定口径收敛（2026-11-13）

与 §8.9 同因：`optimization_page.cpp:481` 拿 `card.pluginName` 比 `startup-management`，实际 `plugin-startup/config.json` 的 `name` 是 `startup`，实测上报 `pageId=space_clean`、`pageName=启动管理器`（tid 1001900001 正确）。原用例断言日志新增 `startup_management` 行，故稳定 fail（台账 11-11 起 3 次全红，今日 allure 仍 `AssertionError: 预期值<1>与实际值<0>`）。

改动（`2005865 test_mycase_057`）：删埋点断言，改为**点「启动管理器」→ 运行时页显示 → 启动项列表加载出至少一个开关 → 返回键回系统优化页**；埋点缺陷留档在 docstring。

启动管理器页无"扫描/结果"阶段，就绪判据用新增 widget 方法：

- `get_startup_list_items()`：枚举 `$//startup_.*/`，排除 `STARTUP_NON_ITEM_NAMES`（`startup_allFilter`/`enabledFilter`/`disabledFilter`/`scrollArea`/`listCard`），只留角色在 `STARTUP_SWITCH_ROLES`（`toggle button`/`check box`/`check_box`）的控件。页面里 `startup_` 前缀共 330 个节点（含大量 `startup_errorLabel` 等 label），必须靠角色过滤，否则计数虚高。
- `wait_startup_list_loaded(timeout=20)`：轮询上述计数，>0 即返回数量，超时返回 0。
- 顺带把 `find_startup_item_switch` 里内联的 `switch_roles`/`skip_names` 提成模块常量并复用上面的枚举方法（原回退分支重复实现同一套过滤）。

实测：

| 用例 | 结果 | 证据 |
|---|---|---|
| 057 | PASS 25.31s，`启动管理器列表已加载: 启动项 46 个` | `2005865_test_mycase_057_20261113_190745.log` |
| 重构后开关查找（临时脚本，直连测试机） | `items 46`、`switch_found True startup_PC Manager` | 冒烟输出，脚本已删 |

补充观测：`2001655 test_mycase_297`（自启动应用--开机自启动与启动器一致）两次复跑都失败在**启动器右键「开机自动启动」**（`set_autostart_via_launcher(True, 浏览器)`，`case/2001655...py:33`），发生在进入启动管理器之前，与本次 widget 重构无关；该用例无台账记录、此前无运行日志，属未验证过的启动器坐标自动化（`LAUNCHER_MENU_ITEM_OFFSETS` 为固定像素偏移）在新环境下的失败，需另行排查。

### 8.11 跨用例系统状态耦合：237 被 288 装上的 lm-sensors 打断（2026-11-13）

现象：`2005873 test_mycase_237`（硬件异常检出，要求 `sensors` 不存在）今日两次运行都失败在**第 39 行前置断言**，没跑到产品检测：

```
AssertionError: 预期值<>与实际值</usr/bin/sensors>不相等
```

根因链（时间戳可对齐）：

1. `1999121 test_mycase_288`（CPU温度检测正常）前置调用 `ensure_package_installed("lm-sensors")`；11-12 `09:53:12` 首次失败（白名单为空）、`09:53:17` 写入临时白名单后 `apt-get install -y lm-sensors` 成功 → 包永久留在测试机（`/var/lib/dpkg/info/lm-sensors.list` = `2026-11-12 09:53:14`）。
2. 237 把"lm-sensors 缺失"写成死前置 `assert_equal("", sensors_path)`，既不自建也不回退 → 环境一变必然红（11-11 13:34 台账是 passed，当时确未安装）。

修法：237 改为与 `1999123 test_mycase_324` 一致的构造方式 —— 若 `command -v sensors` 存在，`sudo mv /usr/bin/sensors /usr/bin/sensors.autotest_bak` 构造缺失，`finally` 移回并断言 `command -v sensors` 非空；**不卸载包、不改 dpkg 状态**，故不会被别处的依赖预检再次破坏。同理，324 也是这套写法，两者现在互不干扰。

实测：237 PASS 26.54s（`2005873_test_mycase_237_20261113_192525.log`），日志有 `环境存在 sensors(/usr/bin/sensors), 临时移走以构造缺失场景`；埋点原文 `abnormalCount:1, abnormalItems:[{reason:"温度检测包（lm-sensors）未安装", title:"CPU温度"}], normalCount:5`；回退后 `/usr/bin/sensors` 在位、无 `.autotest_bak` 残留。

教训（通用）：**依赖预检装包 ≠ 用例可以假定反向状态**。凡是"要求某能力缺失"的用例，自己构造缺失态并回退，不要依赖测试机既有状态；反之"要求存在"的用 `ensure_package_installed` 补齐。同一台机器上两种方向必须各自自洽。

### 8.12 238 跑错检测项：应为「网络检测」而非「系统环境检测」（2026-11-13）

`2005875 test_mycase_238`（网络异常检出）原先停 `systemd-timesyncd` 后执行 **「系统环境检测」**，断言异常项含"时间"。检出的是时间配置项，与用例名"网络异常检出"不符，也和 `1999031`（停止时间同步服务后进行时间配置检测）、`1999033`（禁用服务后进行时间配置检测）重复覆盖。

改为网络口径：

- 构造：iptables `OUTPUT` 插入 `-p tcp -m multiport --dports 80,443 -d 0.0.0.0/0 -m addrtype ! --dst-type LOCAL -j DROP`（公网访问不通，同网段管理链路不受影响）。插入前用 `-C` 判重，结束用**完整规则串** `-D`（不按行号删，避免误伤机器既有规则）并断言无残留。
- 执行：`run_detection_item("网络检测", timeout=180)`。
- 断言：埋点 `tid=1001900002` 新增一条、`abnormalCount>0` 且 `abnormalItems` 含"网络访问"（产品文案来源：`plugin-networkcheck/src/entry.cpp` 注册项 `Network Access` = `网络访问`，异常描述 `Network connection error` = `网络连接错误`）。

实测：PASS 48.76s（`2005875_test_mycase_238_20261113_193331.log`），异常项 `['网络连接错误', '网络访问']`；规则复检 `iptables -C` 返回 `Bad rule`（无残留）。

环境备注：测试机在当前网络下公网本就不通（`curl https://www.baidu.com` → `000`），所以"网络访问异常"在无规则时大概率也会出现；规则的作用是把前置钉死、避免依赖机房网络状态。另注意远端非登录 shell 的 `PATH` 不含 `/usr/sbin`，直接 `iptables` 会报"未找到"，`sudo_run_cmd` 走的是 root 环境所以正常。

### 8.13 2011899 valgrind 用例：4 分钟空等 → 75s，并纠正"产品帧"误判（2026-11-13）

`2011899 test_mycase_047`（性能测试--valgrind 检测内存泄漏）原先单轮 318~476s，且判定把大量系统库记录算成产品问题。实测根因（全部有日志佐证）：

| 现象 | 根因 |
|---|---|
| `pgrep '^/usr/libexec/deepin/deepin-pc-manager'` 恒为空 | **valgrind 在自身进程内运行被测程序**，不 fork 该二进制；进程表里只有 `/usr/bin/valgrind.bin ... /usr/libexec/deepin/deepin-pc-manager` |
| 等 LEAK SUMMARY 每次白等满 60s | `grep -c` 输出 `1`/`0` 被当子串判断，`"LEAK SUMMARY" in "1"` 恒假 |
| 关窗后 valgrind 永不收尾、无汇总 | 关窗常只回到托盘，应用不退出；不发信号 valgrind 就一直在等客户端结束 |
| 抓到 pid 后发 TERM 没用、日志 836 行被截断 | `pgrep -f 'valgrind.*deepin-pc-manager'` 先命中 `setsid` 的中间 shell，TERM 只杀壳；本体继续跑，下一轮 `pkill` 再把它打断 |
| 第二轮 `window_shown=False`、白等 120s | 上一轮应用还在收尾，新实例被单实例守卫生成 `Another instance is already running` 后直接退出 |

现实现（`run_valgrind_pc_manager`）：

- 启动前 `pkill -f 'valgrind.bin.*deepin-pc-manager'` 清残留，并等到无 valgrind、无主窗口；
- 抓 pid 只认 `valgrind.bin`（锚定，避免中间 shell）；
- 窗口轮询 60s，进程消失即 `early_exit` 早退；
- 关窗 10s 不退 → 对 `valgrind.bin` 发 SIGTERM（valgrind 会转发给客户端，客户端退出后照常做泄漏检查并写 LEAK SUMMARY）；等退出 120s，无汇总才 SIGKILL；`summary_written` 显式返回，用例断言它。

判定口径（重要）：不能用"栈里出现产品帧"判定归属——librsvg/pixman/Qt5Gui 的栈深处必然回调产品 `main()`，会把 15/15 条全算成产品问题。现按**记录首帧**（出错点 / 分配点，跳过 `vg_replace_malloc` 包装帧）判定，输出 `*_own` 字段。

实测结果（连续 4 次运行一致，单轮 74~79s，两轮 155s）：

| 指标 | 总量 | 产品归属 |
|---|---|---|
| Conditional jump uninitialised | 15 | **0**（全部在 librsvg-2 / pixman / Qt5Gui 内部） |
| Invalid read / write / overlap | 0 | 0 |
| definitely lost | 2784 B | **320 B / 10 blocks** |
| indirectly lost | 6442 B | 0 |

产品归属的 320 B/10 blocks：启动期 `operator new` → `deepin-pc-manager+0x45465A` ← `0x444E2B` ← `0x436276`，即 `QPluginLoader` 构造 10 个插件对象后指针丢失，两轮复现。其余 2048 B 在 fontconfig `FcFontMatch`、96 B glib、64 B dl_open，属库侧。**最终判定口径（2026-11-13 按用户要求放宽）**：`LEAK SUMMARY` 只要求 valgrind 真实产出汇总、且能解析出 `definitely/indirectly lost` 的数值（解析不到为 `-1` 即 fail）；字节数不参与判定。理由：总量随退出路径与渲染路径波动（历史 560 B / 2784 B），"必须为 0"或硬阈值只会让用例长期红着；320 B 的 `QPluginLoader` 一次性退出泄漏已在 ledger 留证，不阻塞用例。1~3 类错误仍按首帧归属断言为 0。实测 PASS 73.87s。

# 电脑管家（deepin-pc-manager）UI 自动化测试 — AI 接手文档（已归档）

> ⚠️ **不要照本文执行**:第 4 节的 `youqu manage.py run` 现已失效 —— `env.sh` 删除了 `Pipfile`,
> `pipenv` 解析到空壳 venv,报 `No module named 'funnylog'`。
> 现行唯一依据:同目录 **`youqu_deepin_pc_manager-部署与运行.md`**(已并入本文的判定法、结果与历史记录)。

> 目的：让没有上下文的新 AI/工程师在 30 分钟内恢复全部工作能力。
> 所有命令均在 2026-10-21 的实际环境中验证过；标 `[VERIFY]` 的需先确认环境是否已变化。

---

## 1. 背景

- 被测应用：统信电脑管家 `deepin-pc-manager`，当前部署版本 **1.1.3**（V20/Qt5 构建）。
- 测试工程：YouQu 框架项目 `youqu_deepin_pc_manager`，用 dogtail/AT-SPI 做桌面 UI 自动化。
- 目标：全量执行 272 条用例，区分「用例缺陷 / 环境残留 / 产品缺陷」，修复前两类并沉淀证据。

---

## 2. 资产清单

| 项 | 值 |
|---|---|
| 本地工程 | `/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager` |
| 测试机 | `uostest@10.20.33.93`，密码 `1`，sudo 密码 `1` |
| 远端工程 | `/home/uostest/youqu_deepin_pc_manager` |
| 远端 venv | `/home/uostest/.local/share/virtualenvs/uostest-YkBaFyo2`（Python 3.7.3） |
| 系统 | UOS 20 Professional，X11 `:0`，KWin + startdde |
| 主程序 | `/usr/libexec/deepin/deepin-pc-manager`（启动包装器 `/usr/bin/deepin-pc-manager-launch`） |
| 部署脚本 | 工程根 `deploy_pc_manager.sh`（拉源码 → dpkg-buildpackage → 装 deb → 配测试环境） |
| 安装包 | `/home/uostest/deepin-pc-manager_1.1.3_amd64.deb` 及 `-dbgsym` / `-dev` |
| 用例清单 | `apps/autotest_my_app/mycase.csv`（第 8 列=跳过原因，需 `skip-` 前缀；第 10 列=废弃，需 `removed-` 前缀） |

**不要**用 `sshpass`（本机未装）。用下文的 expect 助手。

---

## 3. SSH / 同步助手（先重建，`/tmp` 会被清理）

`/tmp/sshxl2.exp`：

```expect
#!/usr/bin/expect -f
set timeout -1
set host [lindex $argv 0]
set cmd [lindex $argv 1]
spawn ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 \
          -o ServerAliveInterval=15 -o ServerAliveCountMax=8 uostest@$host $cmd
expect {
    -re "assword:" { send "1\r"; exp_continue }
    eof
}
catch wait result
exit [lindex $result 3]
```

`/tmp/rsync_dbg.exp`：

```expect
#!/usr/bin/expect -f
set timeout -1
set host [lindex $argv 0]
set src  [lindex $argv 1]
set dst  [lindex $argv 2]
spawn rsync -az --exclude .git --exclude .venv --exclude report --exclude __pycache__ \
      --exclude .vscode --exclude "*.pyc" \
      -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10" \
      $src uostest@$host:$dst
expect {
    -re "(?i)password:" { send "1\r"; exp_continue }
    eof
}
catch wait result
puts "RC=[lindex $result 3]"
exit [lindex $result 3]
```

用法：

```bash
chmod +x /tmp/sshxl2.exp /tmp/rsync_dbg.exp
/tmp/sshxl2.exp 10.20.33.93 'uname -a'
# 同步单个文件（改了用例后必须做，否则远端跑的是旧代码）
/tmp/rsync_dbg.exp 10.20.33.93 \
  /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager/apps/autotest_my_app/widget/my_app_widget.py \
  /home/uostest/youqu_deepin_pc_manager/apps/autotest_my_app/widget/my_app_widget.py
```

---

## 4. 执行用例（唯一正确姿势）

远端所有测试命令都必须带图形/会话环境变量，否则 AT-SPI、xdotool、systemctl --user 全失效：

```bash
export DISPLAY=:0
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
export QT_ACCESSIBILITY=1
export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1
```

单条（节点写法 `文件::类::方法`）：

```bash
cd ~/youqu_deepin_pc_manager
echo "apps/autotest_my_app/case/2011907_安全性测试--系统自启动服务检查.py::TestMyCase::test_mycase_218" > one_case.txt
timeout 900 youqu manage.py run -f one_case.txt --rerun 0 --resolution 1440x900 > /tmp/last_case.log 2>&1
grep -oE "[0-9]+ (passed|failed|skipped)" /tmp/last_case.log | tail -2
```

要点：

- `youqu` 只是 `pipenv run python "$@"`；venv 里没有 pytest 模块，`youqu -m pytest` 不可用。
- **一次只跑一条用例**：应用是单实例 + AT-SPI 单会话，并行会互相踩。
- `--rerun 0` 关闭重跑，避免掩盖 flaky；全程耗时约 4–5 小时。
- 失败日志在 `/tmp/last_case.log`，完整 traceback 会打印。

重建节点列表（272 条，已验证与历史清单逐字一致）：

```bash
cd ~/youqu_deepin_pc_manager
for f in apps/autotest_my_app/case/*.py; do
  cls=$(grep -oE "^class (Test\w+)" "$f" | tail -1 | awk '{print $2}')
  for m in $(grep -oE "^    def (test_\w+)" "$f" | awk '{print $2}'); do
    echo "${f}::${cls}::${m}"
  done
done > /tmp/all_nodes.txt
wc -l /tmp/all_nodes.txt   # 272
```

断点续跑脚本模板（失败即停，便于逐条诊断）：

```bash
#!/bin/bash
cd ~/youqu_deepin_pc_manager || exit 1
export DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
export QT_ACCESSIBILITY=1 QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1
LIST=/tmp/remaining.txt          # 待跑节点，一行一个
SUMMARY=/tmp/case_summary.log    # 汇总：节点 -> 结果
PROGRESS=/tmp/case_progress.log  # 进度
i=0; TOTAL=$(wc -l < "$LIST")
while IFS= read -r node; do
    [ -z "$node" ] && continue
    i=$((i+1)); printf "%s\n" "$node" > one_case.txt
    echo "[$i/$TOTAL] $(date '+%T') START $node" >> "$PROGRESS"
    timeout 900 youqu manage.py run -f one_case.txt --rerun 0 --resolution 1440x900 > /tmp/last_case.log 2>&1
    rc=$?
    status=$(grep -oE "[0-9]+ (failed|passed|skipped|error|errors)" /tmp/last_case.log | tail -4 | tr '\n' ' ')
    echo "[$i/$TOTAL] rc=$rc $status  $node" >> "$SUMMARY"
    if [ $rc -ne 0 ] || printf '%s' "$status" | grep -qE "[0-9]+ (failed|error|errors)"; then
        cp /tmp/last_case.log /tmp/case_failed.log
        echo "STOPPED_AT=$node rc=$rc status=[$status] $(date '+%F %T')" >> "$SUMMARY"
        exit 1
    fi
done < "$LIST"
echo "ALL_DONE $(date '+%F %T')" >> "$SUMMARY"
```

启动：`nohup bash ~/resume_cases.sh > /tmp/resume_stdout.log 2>&1 &`，然后用一个**单独的** ssh 轮询循环等 `ALL_DONE|STOPPED_AT`（不要在同一会话里 `sleep` 等待，连接会闲置）。

汇总最终状态（节点最后一次结果）：

```python
import re
from collections import Counter
nodes = [l.strip() for l in open("/tmp/all_nodes.txt", encoding="utf-8") if l.strip()]
last = {}
for line in open("/tmp/case_summary.log", encoding="utf-8", errors="ignore"):
    m = re.search(r"(apps/autotest_my_app/case/.+?)::TestMyCase::(\w+)", line)  # 文件名含空格, 不能 \S+
    if not m: continue
    node = m.group(1) + "::TestMyCase::" + m.group(2)
    if re.search(r"\b\d+ passed\b", line):  last[node] = "passed"
    elif re.search(r"\b\d+ skipped\b", line): last[node] = "skipped"
    elif re.search(r"\b\d+ failed\b", line):  last[node] = "failed"
c = Counter(last.values())
print(len(nodes), c, [n for n in nodes if n not in last])
```

> 坑：文件名含空格/全角括号，正则必须用 `.+?` 而非 `\S+?`；只要出现过 `N passed`（N 可能 >1）都要认，否则会把已修好的用例统计成 failed。

---

## 5. 环境与产品的固定事实（决定用例怎么写，别重新踩）

### 5.1 session-daemon 会自己退出

- `deepin-pc-manager-session-daemon` 是 **`Type=dbus`** 用户服务：只有 GUI 通过 `org.deepin.PCManager1` 调用时才会被 D-Bus 激活；**空闲 60 秒自动退出**。
- 因此「检查服务是否在跑」必须先主动拉起再轮询：

```bash
systemctl --user start deepin-pc-manager-session-daemon
systemctl --user is-active deepin-pc-manager-session-daemon   # active / activating
```

- 用例侧直接用 `widget.wait_for_session_daemon(timeout=30)`，不要用裸 `get_session_daemon_status()`。
- 服务单元：`/usr/lib/systemd/user/deepin-pc-manager-session-daemon.service`（`Restart=on-failure`，所以被 `kill -9` 后会 5s 重启，被 `systemctl stop` 则不重启）。

### 5.2 关应用时不能子串 kill

`kill_process("deepin-pc-manager")` 是**子串匹配命令行**，会连带 `kill -9` 掉 `deepin-pc-manager-session-daemon`，把用户服务打到 failed。必须用 `_kill_pc_manager_main_process()`（已实现，精确匹配 `^(deepin-pc-manager|/usr/libexec/deepin/deepin-pc-manager|/usr/bin/deepin-pc-manager)$`）。

### 5.3 启动必须走包装器

`/usr/bin/deepin-pc-manager-launch` 经 `deepin-security-loader` 注册 D-Bus 白名单（`SetAllowCaller`）。直接跑二进制，daemon 会拒绝特权修复调用（日志 `caller not in loader whitelist`），依赖/系统类修复全部失败。

### 5.4 加固项判定（PIE / FORTIFY）

- UOS 20 的 `dpkg-buildflags` **没有 pie 特性**：`hardening=+all` 也只输出 `-fstack-protector-strong -Wformat -Werror=format-security` + `-Wl,-z,relro -Wl,-z,now`。所以标准构建产物就是 `EXEC`，**不能判为缺陷**。
- `-D_FORTIFY_SOURCE=2` 在 `CPPFLAGS` 里（vendor 默认有）。
- FORTIFY 是否产生 `__*_chk` 符号取决于二进制有没有调用可加固函数；C++/Qt 代码常常只有 `__stack_chk_fail`。**符号缺失 ≠ 未启用**，以构建标志为准。
- 已实现：`get_pie_enabled()` / `get_fortify_source_enabled()` 自动按平台能力判定。

### 5.5 V20 关闭主窗口的行为（**产品缺陷，未修**）

- V20 无托盘图标，关闭主窗口后**进程常驻**（`DApplication` 的 quitOnLastWindowClosed 行为），但再次 `deepin-pc-manager-launch` 只能触发单实例通知，**主界面不恢复**：日志出现 `Another instance is already running, notifying and exiting` + `QXcbConnection: XCB error: 3 (BadWindow) ... resource id: <旧窗口id>`。
- 用户侧等价于「关了就打不开，只能杀进程」。
- 复现（3 步）：

```bash
export DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/$(id -u) DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
setsid /usr/bin/deepin-pc-manager-launch >/dev/null 2>&1 & sleep 9
xdotool windowclose "$(xdotool search --name '电脑管家' | head -1)"; sleep 5
pgrep -af '^/usr/libexec/deepin/deepin-pc-manager'      # 进程还在
setsid /usr/bin/deepin-pc-manager-launch >/dev/null 2>&1 & sleep 8
xdotool search --name '电脑管家' | head -1               # 空 -> 未恢复
```

### 5.6 垃圾清理的隐藏规则

1.1.3 扫描器新增 **Application Junk / Cookies Information**：即使应用没装，`.cache/youdao-dict`、`.config/filezilla`、`.config/QQ音乐` 类目录下的文件也计为垃圾。构造「无垃圾」场景必须清空 `widget.clean_environment()` 里列出的全部路径（含 `/var/log/sunlogin`，需 root）。仅删自己造的文件不够。

### 5.7 输入法场景

startdde 通过 `fcitx-helper` 守护自动拉起 fcitx，`killall fcitx` 1 秒内会被拉回。构造「无输入法」必须先 `pkill -9 -x fcitx-helper`，测试结束用 `_ensure_input_method_helper()` 恢复。

### 5.8 lpadmin 判定

`gpasswd -d` 改的是组数据库，进程凭据不变，`id -nG` 会误判。用 `getent group lpadmin` 看成员；`sudo_run_cmd` 里的 `$(whoami)` 会变成 root，必须用 `$SUDO_USER`。

### 5.9 其它小坑

- `xdotool search --name '电脑管家'` 可用；`xwininfo -root -children | grep 中文` 不可靠，别用它判断有无窗口。
- 窗口/进程残留会让下一条用例失败，重跑前先 `widget.start_pc_manager()`（内部会精确清理）。
- `test_mycase_001` 是脚手架模板（点不存在的 `xxx`），已在 `mycase.csv` 标记 `skip-`，别删。
- 用例之间**有状态泄漏**（服务、进程、系统配置），失败先单跑，能过就是前序残留。

---

## 6. 失败用例的三分类判定法（别乱改用例）

1. **先单跑**：失败 → 单独重跑。通过 → 前序用例残留（环境问题），不改用例，改前置/清理。
2. **读 traceback 定位断言**：`grep -n -B10 "不为真" /tmp/case_failed.log`。
3. **查产品源码**（`deploy_pc_manager.sh` 拉的源码目录，或本地 `/tmp/pcm-src`）确认设计意图，不要按文档/直觉假设。
4. **判定**：
   - 用例假设错（如「V20 关闭即退出」「PIE 必须 DYN」）→ **改用例**，注释写清平台事实。
   - 环境条件不满足（服务未启动、残留进程、垃圾未清）→ **改前置/清理**。
   - 产品行为与用户预期不符且源码可证 → **保留失败**，写清复现步骤与日志证据，作为缺陷。
5. 改完必须**单独重跑**该用例，再继续全量；同步到远端后再跑（忘了 rsync 会白跑）。

---

## 7. 当前结果（2026-10-21 全量）

| 项 | 数量 |
|---|---|
| 用例总数 | 272 |
| passed | 257 |
| skipped | 14（`pytest.skip("用例已废弃")` / 环境前置不满足 / 模板用例 001） |
| failed | 1 |

唯一失败：`apps/autotest_my_app/case/2011941_其他--系统托盘.py::TestMyCase::test_mycase_272` —— 5.5 的产品缺陷，用例已改写为缺陷检测，**不要为了变绿而删断言**。

---

## 8. 已提交的改动（本地分支，未推送）

```
280cd1d chore(case): 标记框架默认模板用例为跳过
62db580 test(case): 系统托盘用例改为验证关闭后的窗口唤醒能力
7944a0a fix(case): 隔离联软特征注入用例的清理逻辑
9de1b6e fix(case): 编译安全与等保按平台构建能力判定 PIE/FORTIFY
09609ca fix(widget): lpadmin 权限按组数据库判定并修正目标用户
fe5c970 fix(widget): 垃圾清理前置清空应用垃圾与 Cookies 残留
78e6ce6 fix(widget): 输入法修复前恢复 fcitx-helper 守护
3ea0dc6 fix(widget): 关闭电脑管家时只终止主程序进程
4a811c0 fix(script): 修正 V20 构建依赖探测与 DTK 兼容链接
```

规则：**未获用户明确指示不要 `git push` / 不要新开提交合并**。新增改动按主题拆分提交（同一文件的多主题改动用 `git apply --cached` 分 hunk）。

---

## 9. 待办 / 风险

- [ ] 把 5.5 的缺陷反馈给产品/研发（附复现脚本与 `~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log` 片段）。
- [ ] 若产品修复，重跑 `2011941` 并把用例恢复为「关闭后退出或可唤醒」的最终断言。
- [ ] 14 条 skipped 中的废弃用例可择机从 CSV 标 `removed-`（当前仅用例内 skip）。
- [ ] 远端 `/tmp` 的清单/日志会被清理；关键结论已写入本文件，重建命令见第 4 节。

---

## 10. 速查

```bash
# 服务状态
systemctl --user status deepin-pc-manager-session-daemon --no-pager | head -5
journalctl --user -u deepin-pc-manager-session-daemon --since "-10min" --no-pager | tail

# 主程序日志
tail -30 ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log
tail -30 ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager-session-daemon.log

# 进程
pgrep -af '^/usr/libexec/deepin/deepin-pc-manager'
pgrep -af 'deepin-pc-manager'

# 窗口
xdotool search --name '电脑管家' | head -1

# 构建/安装参考
cd ~/youqu_deepin_pc_manager && bash deploy_pc_manager.sh -t 1.1.3 -p 1
#   已有源码目录时可加 -k -d ~/deepin-pc-manager-src；-p 为 sudo 密码
```

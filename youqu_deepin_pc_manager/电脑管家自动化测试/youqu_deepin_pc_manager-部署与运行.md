# youqu_deepin_pc_manager 在测试环境的部署与运行经验

> 面向:在这台测试机上重新部署、排障、跑用例的人/AI。
> 本文是**唯一交付物**:部署、运行、判定法、结果与历史记录都在这里。
> `AI接手文档.md` 已归档(其第 4 节的 `youqu manage.py run` 已失效),只作历史参考。
> 全部命令在本机与测试机 **实测过**(2026-10-21 ~ 10-23)。
> 结论先行: **不要用 `youqu` 命令跑用例,用 `.venv/bin/python manage.py run`** —— 原因见 §4。

---

## 1. 环境事实(部署前先对齐)

| 项 | 值 |
|---|---|
| 测试机 | `10.20.33.93` |
| SSH 登录 | `ssh uostest@10.20.33.93`,密码 `1`(sudo 密码同为 `1`) |
| 系统 | UOS 20 Professional,内核 4.19,x86_64 |
| 桌面 | X11,`DISPLAY=:0`,鼠标可用(远程操作会抢占鼠标) |
| 系统 Python | `/usr/bin/python3` = 3.7.3(系统自带 pytest 7.4.4,但**项目不用它**) |
| 项目路径 | `/home/uostest/youqu_deepin_pc_manager` |
| 被测应用 | 统信电脑管家 `deepin-pc-manager` 1.1.3(V20/Qt5) |
| 主程序 | `/usr/libexec/deepin/deepin-pc-manager` |
| 本地项目 | `/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager` |

**SSH 密码登录**:固定为 `ssh uostest@10.20.33.93`(密码 `1`)。本机没有 `sshpass`,自动化用 `expect`(脚本见 §12.1)。

---

## 2. 部署全流程(首次 / 重建)

### 2.1 上传代码

```bash
# 本地 → 远端,保留删除、排除产物
/tmp/sshxl2.exp 'mkdir -p ~/youqu_deepin_pc_manager'
rsync -az --delete \
  -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
  /home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager/ \
  uostest@10.20.33.93:~/youqu_deepin_pc_manager/
```

> rsync 走 ssh 同样要密码,执行后会**交互提示输入**(输 `1`)。本机没有 `sshpass`,
> 不要尝试自动化 `rsync`;手工输一次最快。远端目录已存在时 rsync 只传差异,几秒完成。

### 2.2 安装系统 + Python 依赖:`bash env.sh`

```bash
cd ~/youqu_deepin_pc_manager
bash env.sh -p 1        # -p 为 sudo 密码;不要用 root 执行
```

`env.sh` → `src/utils/env_vir.sh` 实际做的事(读脚本确认):

1. `sudo apt update` + 安装:
   `python3-pip python3-tk scrot openjdk-11-jdk-headless gir1.2-atspi-2.0 libatk-adaptor at-spi2-core python3-opencv`
   - 若 `python3 sub_env_cut.py` 判定为精简环境,只装 `python3-pip openjdk-11-jdk-headless`。
2. 安装 `pipenv`(华为云源,`--break-system-packages`)。
3. `pipenv --python 3.x` 创建虚拟环境。
4. 从 deb 包里抽取并**复制进 venv**:
   `python3-gi python3-pyatspi python3-dbus python3-cairo python3-pil python3-ptyprocess
    python3-pexpect python3-numpy python3-opencv python3-gi-cairo`
   (venv 是 `include-system-site-packages = false` 的隔离环境,所以靠这种"拷贝 deb 内容"的方式提供 AT-SPI/GTK 绑定)
5. `pipenv run pip install`:
   `pyscreeze==0.1.28 PyAutoGUI==0.9.53 pytest==6.2.5 pytest-rerunfailures==10.2
    pytest-timeout==2.1.0 allure-pytest==2.9.45 funnylog pdocr-rpc image-center allure-custom`
   精简环境只装 `pytest/pytest-rerunfailures/pytest-timeout/allure-pytest/allure-custom/funnylog`。
6. 尝试装内网包 `auto_uos`(走内网私有 PyPI 源)。**该源在测试机不可达,这一步必然失败并跳过**,
   `public/` 不会生成 —— 不影响本项目(项目不用 `public/`)。
7. **`rm -rf Pipfile`**(重要:之后 `pipenv` 失去项目描述文件,行为会漂移,见 §4)。
8. `system_env()`:
   - 往 `~/.bashrc` 追加 `DISPLAY=:0`、`QT_ACCESSIBILITY=1`、`QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1`、`QT_QPA_PLATFORM=`
   - 生成 `/usr/bin/sniff`、`/usr/bin/youqu`、`/usr/bin/youqu-shell`、`/usr/bin/youqu-rm`
   - `gsettings set org.gnome.desktop.interface toolkit-accessibility true`
   - 启用并启动 sshd

预计 10~30 分钟(取决于 apt 下载 openjdk 等包的速度)。脚本末尾打印 venv 路径。

### 2.3 验证运行环境(**必做**)

```bash
cd ~/youqu_deepin_pc_manager
.venv/bin/python -c "import pytest,funnylog,allure_custom;print('OK')"
# 期望: OK;pytest 6.2.5
pipenv --venv
# 观察到什么就说明 pipenv 指向哪个 venv(可能不是 .venv)
```

两种 venv 会同时存在:

| 路径 | 内容 | 用途 |
|---|---|---|
| `~/youqu_deepin_pc_manager/.venv` | pytest 6.2.5、funnylog、allure、pyatspi 等**全套** | **实际运行环境** |
| `~/.local/share/virtualenvs/uostest-YkBaFyo2` | 只有 pip/setuptools/wheel(**空壳**) | `pipenv` 默认解析到这里 |

只要 `.venv` 的校验通过,就用 §4 的方式运行;不要被 `youqu` 报错误导。

### 2.4 安装被测应用(如机上没有 1.1.3)

```bash
cd ~/youqu_deepin_pc_manager
bash deploy_pc_manager.sh -t 1.1.3 -p 1
# 已有源码目录可加 -k -d ~/deepin-pc-manager-src
# Gerrit 用户名/密码运行时交互输入;自动化场景可 export PCM_GIT_USER / PCM_GIT_PASSWORD
```

脚本流程:装 Qt5/DTK5 编译依赖 → 拉取 `https://gerrit.uniontech.com/deepin-pc-manager`
(tag 1.1.3)→ `dpkg-buildpackage` → 安装 deb → 配 polkit 策略权限 → 准备 youqu 环境。

常用开关:已有源码 `-k -d ~/deepin-pc-manager-src`;只重装应用不碰测试环境 `-n`;
`.venv` 已存在时脚本默认跳过 env.sh,要强制重跑加 `-e`;
Gerrit 凭据也可 `export PCM_GIT_USER=... PCM_GIT_PASSWORD=...` 免交互。

产物:`/home/uostest/deepin-pc-manager_1.1.3_amd64.deb`,安装校验:

```bash
dpkg -l | grep deepin-pc-manager
ls -l /usr/libexec/deepin/deepin-pc-manager /usr/bin/deepin-pc-manager-launch
```

> **V20 构建注意**:`dpkg-buildflags` 的 `-Werror=format-security` 与 DTK 5 头文件、
> `-fstack-protector-strong -D_FORTIFY_SOURCE=2` 组合会出问题;项目已分别用
> `patch: 屏蔽 -fcheck=all 加固` 与 `debian/rules` 的 `-U_FORTIFY_SOURCE` 处理,重新打包时不要回退。

### 2.5 配置 `setting/globalconfig.ini`

```ini
[run]
PASSWORD = 1            # 本机 sudo 密码,用例里会用到
RESOLUTION = ...        # 跑单条建议命令行覆盖为 1440x900
RERUN = 1
MAX_FAIL = 1
CASE_TIME_OUT = 1800
```

### 2.6 冒烟(1 条,验证整条链路)

```bash
cd ~/youqu_deepin_pc_manager
cat > one_case.txt <<'EOF'
apps/autotest_my_app/case/test_mycase_002.py::TestMyCase::test_mycase_002
EOF

export DISPLAY=:0
export XAUTHORITY=$HOME/.Xauthority
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
export QT_ACCESSIBILITY=1 QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1

.venv/bin/python manage.py run -f one_case.txt --rerun 0 --resolution 1440x900
# 实测输出:1 passed in 2.38s
```

冒烟不过,先看 §6 排障,不要直接跑全量。

---

## 3. 运行前置(每次执行都要)

```bash
export DISPLAY=:0
export XAUTHORITY=$HOME/.Xauthority
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
export QT_ACCESSIBILITY=1
export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1
```

- `DISPLAY` 缺失 → `src/depends/pyautogui` 导入即 `NameError: Xlib`(不是缺包,是连不上 X)。
- AT-SPI 不可用 → 所有 `dogtail` 查找元素失败/用例全红;用
  `gsettings set org.gnome.desktop.interface toolkit-accessibility true` 修复。
- **不要并行跑**:UI 单实例 + 全局鼠标/窗口,并行必互相干扰。

---

## 4. 运行用例(两种方式,只用第一种)

### ✅ 方式 A(`.venv/bin/python`,已验证)

```bash
cd ~/youqu_deepin_pc_manager
.venv/bin/python manage.py run -f one_case.txt --rerun 0 --resolution 1440x900
```

即 `manage.py` 直接由项目内 venv 解释器执行,`src/rtk/local_runner.py` 里的
`import pytest` / `import allure_custom` 都能解析。

### ❌ 方式 B(`youqu` / `pipenv run`,当前不可用)

`/usr/bin/youqu` 内容就是 `pipenv run python "$@"`。而 `env.sh` 删掉了 `Pipfile`,
`pipenv` 会解析到空壳 venv,导致:

```
ModuleNotFoundError: No module named 'funnylog'
```

**不要把这条当环境坏了的证据**;`.venv/bin/python` 能跑就是好的。
若要恢复 `youqu`,需在有 `Pipfile` 的前提下重跑 `env.sh`(或手动 `pipenv install` 全部依赖),
没必要 —— 直接用方式 A。

### 4.1 单条/小批量

`one_case.txt` 每行一个 pytest 节点 ID:

```
apps/autotest_my_app/case/test_mycase_002.py::TestMyCase::test_mycase_002
apps/autotest_my_app/case/test_mycase_003.py::TestMyCase::test_mycase_003
```

### 4.2 全量(272 条;单条实测 2~90 秒,需分多段执行)

生成节点清单(与历史 `/tmp/all_nodes.txt` **逐行 diff = 0**,已验证):

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

> 不能用 `pytest --collect-only` 生成:收集阶段就会 import `src.depends.pyautogui`,
> 在无 DISPLAY 的 shell 里直接崩(`NameError: name 'Xlib' is not defined`)。

分段 + 断点续跑(避免一次会话被 SSH 断开):

```bash
#!/bin/bash
# /tmp/run_all.sh  —— 每段 10 条,失败即停,记录进度
cd ~/youqu_deepin_pc_manager || exit 1
export DISPLAY=:0 XAUTHORITY=$HOME/.Xauthority
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
export QT_ACCESSIBILITY=1 QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1

START=${1:-1}
BATCH=${2:-10}
PROGRESS=/tmp/case_progress.log
REMAIN=/tmp/all_nodes_remaining.txt
: > "$REMAIN"
tail -n +"$START" /tmp/all_nodes.txt > "$REMAIN"

i=0
while IFS= read -r node && [ "$i" -lt "$BATCH" ]; do
  i=$((i + 1))
  echo "$node" > one_case.txt
  echo "=== [$START/$i] $(date '+%F %T') $node" >> "$PROGRESS"
  timeout 900 .venv/bin/python manage.py run -f one_case.txt --rerun 0 \
      --resolution 1440x900 > /tmp/last_case.log 2>&1
  grep -oE "[0-9]+ (passed|failed|skipped)" /tmp/last_case.log | tail -1 >> "$PROGRESS"
  if grep -qE "[1-9][0-9]* failed" /tmp/last_case.log; then
    echo "STOPPED_AT=$((START + i - 1))" >> "$PROGRESS"
    exit 2          # 失败即停,先分析再续跑
  fi
done < <(head -n "$BATCH" "$REMAIN")

echo "DONE_UP_TO=$((START + i - 1))" >> "$PROGRESS"
```

```bash
# 续跑:从上次 DONE_UP_TO+1 开始
bash /tmp/run_all.sh 1 10     # 第一次
bash /tmp/run_all.sh 11 10    # 之后每次把起点后移
```

日志:`/tmp/case_progress.log`(逐条)、`/tmp/last_case.log`(最后一条详情)。

### 4.3 结果与报告

```bash
# 快速统计
grep -oE "[0-9]+ (passed|failed|skipped)" /tmp/last_case.log | tail -1
# 或从进度日志汇总
awk '/passed|failed|skipped/' /tmp/case_progress.log | sort | uniq -c
```

- Allure HTML:`report/allure_html/index.html`
- JSON:`report/json/`
- 明细日志:`report/logs/`
- 失败录屏:`report/record/`

---

## 5. 用例跳过/废弃的维护方式

`apps/autotest_my_app/mycase.csv`:
- 第 8 列填 `skip-xxx` → 跳过该条
- 第 10 列填 `removed-xxx` → 标记废弃

全量清单 `/tmp/all_nodes.txt` 是静态快照,**不会**自动排除 CSV 里的跳过项;
需要时用 `manage.py csvctl` 重新生成或在清单里手工剔除。

---

## 6. 运行期硬事实(判定用例结果为"环境问题"还是"产品问题"的前提)

| # | 事实 | 对用例的影响 |
|---|---|---|
| 1 | `deepin-pc-manager-session-daemon` 是 `Type=dbus` + `Restart=on-failure`,**idle 60s 自动退出** | 用例执行前 `systemctl --user start deepin-pc-manager-session-daemon`;执行中别指望它一直在 |
| 2 | 启动必须走 `/usr/bin/deepin-pc-manager-launch`(安全加载器,`--fd1/--fd2`) | 直接 exec `/usr/libexec/deepin/deepin-pc-manager` 会少安全上下文,用例会误判 |
| 3 | 有单实例机制(`SingleInstanceGuard`) | 上一个进程没退干净 → 新启动无窗口;用例启动前必须清理残留进程/窗口 |
| 4 | 主程序关闭窗口后进程可能常驻(V20 上唤醒失败,BadWindow) | 这是**产品缺陷**(见 §7),不要用"重试"掩盖 |
| 5 | V20 `dpkg-buildflags` 不含 PIE;`CPPFLAGS` 含 `-D_FORTIFY_SOURCE=2` | 加固用例按此断言,别照搬 V25 |
| 6 | `kill_process` 是子串匹配 | 断言进程退出时要精确进程名,否则误杀/误判 |
| 7 | 垃圾清理会把 AT-SPI/日志残留算作垃圾 | "清理结果为 0 垃圾"类用例必须先清残留,否则稳定失败 |
| 8 | `fcitx-helper` 被 kill 后自动重启 | 输入法修复类用例要以"守护进程自动重启"为预期 |
| 9 | `lpadmin` 能力由组权限决定 | 打印机权限用例先确认用户组,再断言 |
| 10 | 单实例 + 全局 UI | 禁止并行执行用例 |

---

## 7. 已知产品缺陷(唯一一条,用例 2011941 连续失败)

**场景**:打开电脑管家 → `xdotool windowclose` 关闭主窗口 → 进程仍驻留 →
再次 `/usr/bin/deepin-pc-manager-launch` → **不出现窗口**,日志报 `BadWindow`。

```bash
# 复现
/usr/bin/deepin-pc-manager-launch &
sleep 5
xdotool search --name '电脑管家' | head -1 | xargs -r xdotool windowclose
pgrep -af deepin-pc-manager          # 进程还在
/usr/bin/deepin-pc-manager-launch &  # 无窗口
grep -i badwindow ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log | tail
```

**判定**:产品缺陷(关闭窗口未释放实例/未退出,再次启动被单实例守卫拦截且未恢复窗口)。
用例 `2011941_其他--系统托盘.py` 因此失败,**不要改用例迁就**。

---

## 8. 失败用例判定法(别乱改用例)

1. **先单跑**:失败 → 单独重跑。通过 → 前序用例残留(环境问题),不改用例,改前置/清理。
2. **读 traceback 定位断言**:`grep -n -B10 "不为真" /tmp/last_case.log`。
3. **查产品源码**(`deploy_pc_manager.sh` 拉的源码目录)确认设计意图,不要按文档/直觉假设。
4. **判定三类**:
   - 用例假设错(如「V20 关闭即退出」「PIE 必须 DYN」)→ **改用例**,注释写清平台事实。
   - 环境条件不满足(服务未启动、残留进程、垃圾未清)→ **改前置/清理**。
   - 产品行为与用户预期不符且源码可证 → **保留失败**,写清复现步骤与日志证据,作为缺陷。
5. 改完必须**单独重跑**该用例,再继续全量;同步到远端后再跑(忘了 rsync 会白跑)。

### 8.1 §6 表格的详细依据

- **session-daemon**:`Type=dbus`,空闲 60 秒自动退出;单元在
  `/usr/lib/systemd/user/deepin-pc-manager-session-daemon.service`(`Restart=on-failure`,
  被 `kill -9` 后 5s 重启,被 `systemctl stop` 则不重启)。用例侧用
  `widget.wait_for_session_daemon(timeout=30)`,不要用裸 `get_session_daemon_status()`。
- **精确 kill**:`kill_process("deepin-pc-manager")` 是子串匹配命令行,会连带杀掉
  `deepin-pc-manager-session-daemon` 并把它打成 failed。必须用
  `_kill_pc_manager_main_process()`(匹配 `^(deepin-pc-manager|/usr/libexec/deepin/deepin-pc-manager|/usr/bin/deepin-pc-manager)$`)。
- **启动包装器**:`/usr/bin/deepin-pc-manager-launch` 经 `deepin-security-loader` 注册
  D-Bus 白名单(`SetAllowCaller`);直接跑二进制,daemon 会拒绝特权修复调用
  (日志 `caller not in loader whitelist`),依赖/系统类修复全部失败。
- **加固判定**:UOS 20 的 `dpkg-buildflags` **没有 pie 特性**,标准产物就是 `EXEC`;
  `-D_FORTIFY_SOURCE=2` 在 `CPPFLAGS` 里。FORTIFY 是否产生 `__*_chk` 符号取决于是否调用可加固函数,
  **符号缺失 ≠ 未启用**,以构建标志为准。已实现 `get_pie_enabled()` / `get_fortify_source_enabled()`。
- **垃圾清理**:1.1.3 扫描器含 Application Junk / Cookies Information,`.cache/youdao-dict`、
  `.config/filezilla` 等即使应用没装也计为垃圾。构造「无垃圾」必须清
  `widget.clean_environment()` 列出的全部路径(含 `/var/log/sunlogin`,需 root)。
- **输入法**:startdde 经 `fcitx-helper` 守护自动拉起 fcitx,`killall fcitx` 1 秒内被拉回。
  构造「无输入法」先 `pkill -9 -x fcitx-helper`,结束用 `_ensure_input_method_helper()` 恢复。
- **lpadmin**:`gpasswd -d` 只改组数据库,进程凭据不变,`id -nG` 会误判;用 `getent group lpadmin`
  看成员。`sudo_run_cmd` 里的 `$(whoami)` 会变 root,必须用 `$SUDO_USER`。
- **窗口检测**:`xdotool search --name '电脑管家'` 可用;`xwininfo -root -children | grep 中文` 不可靠。
- `test_mycase_001` 是脚手架模板(点不存在的 `xxx`),已在 `mycase.csv` 标 `skip-`,别删。
- 用例之间**有状态泄漏**(服务、进程、系统配置),失败先单跑,能过就是前序残留。

---

## 9. 当前结果(2026-10-21 全量)

| 项 | 数量 |
|---|---|
| 用例总数 | 272 |
| passed | 257 |
| skipped | 14(`pytest.skip("用例已废弃")` / 环境前置不满足 / 模板用例 001) |
| failed | 1 |

唯一失败:`apps/autotest_my_app/case/2011941_其他--系统托盘.py::TestMyCase::test_mycase_272`
—— §7 的产品缺陷,用例已改写为缺陷检测,**不要为了变绿删断言**。

---

## 10. 已提交的改动(本地分支,未推送)

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

规则:未获用户明确指示**不要 `git push`**、不要新开提交合并;新增改动按主题拆分提交。

---

## 11. 待办 / 风险

- [ ] 把 §7 的缺陷反馈给产品/研发(附复现脚本与
      `~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log` 片段)。
- [ ] 产品修复后重跑 `2011941`,恢复为「关闭后退出或可唤醒」的最终断言。
- [ ] 14 条 skipped 中的废弃用例可择机在 CSV 标 `removed-`(当前仅用例内 skip)。
- [ ] 远端 `/tmp` 的清单/日志会被清理;重建命令见 §4.2。

---

## 12. 附录

### 12.1 SSH 密码登录助手(本机无 sshpass)

本机 `/usr/bin/ssh` 有,`sshpass` 没有,`~/.local/bin` 又不在 PATH。用 expect,目标固定为
`uostest@10.20.33.93`、密码 `1`:

```expect
#!/usr/bin/expect -f
# /tmp/sshxl2.exp <command...>   —— 固定连接 uostest@10.20.33.93,密码 1
set timeout 600
set cmd [join $argv " "]
spawn ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=8 \
    uostest@10.20.33.93 $cmd
expect {
    -re {(?i)password:} { send "1\r"; exp_continue }
    eof
}
catch wait result
exit [lindex $result 3]
```

```bash
chmod +x /tmp/sshxl2.exp
/tmp/sshxl2.exp 'hostname; id -u'
```

> 注意:传给 `ssh` 的命令里含 `$` 时要单引号包裹,避免本机 shell 先展开。

### 12.2 常用排查命令

```bash
# 服务状态
systemctl --user status deepin-pc-manager-session-daemon
# 主程序日志
tail -50 ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log
tail -50 ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager-session-daemon.log
# 残留进程/窗口
pgrep -af deepin-pc-manager
xdotool search --name '电脑管家'
# AT-SPI 自检
gsettings get org.gnome.desktop.interface toolkit-accessibility
# venv 自检
.venv/bin/python -c "import pytest,funnylog,allure_custom,pyatspi;print('OK')"
```

### 12.3 部署检查清单

- [ ] `bash env.sh -p 1` 跑完,输出 "安装成功 √"
- [ ] `.venv/bin/python -c "import pytest,funnylog,allure_custom"` → OK
- [ ] `dpkg -l | grep deepin-pc-manager` → 1.1.3
- [ ] `/usr/bin/deepin-pc-manager-launch` 存在
- [ ] `gsettings get org.gnome.desktop.interface toolkit-accessibility` → true
- [ ] 冒烟 1 条 `1 passed`
- [ ] `/tmp/all_nodes.txt` 行数 = 272
- [ ] 报告目录 `report/` 可写

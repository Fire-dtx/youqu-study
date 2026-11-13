# youqu_deepin_pc_manager

基于 [YouQu（有趣）](https://github.com/linuxdeepin/youqu) 自动化测试框架的 **统信电脑管家（deepin-pc-manager）** UI 自动化测试项目。

## 项目简介

本项目使用 YouQu v2.14.0 框架，对统信电脑管家应用进行桌面 UI 自动化测试，覆盖应用启动、导航切换、系统优化等功能场景。

### YouQu 能做什么

- 💻 Linux 桌面应用 UI 自动化测试
- 🌏 Web UI 自动化测试
- 🚌 Linux DBus 接口自动化测试
- 🚀 命令行自动化测试
- 🕷️ HTTP 接口自动化测试

## 环境要求

- Python 3.7 及以上（推荐 3.12）
- Deepin / UOS 操作系统（同时兼容 openEuler、openAnolis）
- YouQu 框架 v2.14.0

## 快速开始

### 1. 安装 YouQu 框架

```shell
$ sudo pip3 install youqu
```

<details>
    <summary><b>不加 sudo ?</b></summary>

不加 sudo 也可以：

```shell
pip3 install youqu
```

但可能出现 `youqu-startproject` 命令无法使用；

这是因为不加 `sudo` 时，`youqu-startproject` 命令会生成在 `$HOME/.local/bin` 下，

而此路径可能不在环境变量（`PATH`）中，因此您需要添加环境变量：

```shell
export PATH=$PATH:$HOME/.local/bin
```

</details>

### 2. 克隆项目

```shell
$ git clone <本项目仓库地址>
$ cd youqu_deepin_pc_manager
```

### 3. 安装依赖

```shell
$ bash env.sh
# 使用的默认密码是 1；
# 您可以使用 -p 选项传入密码：bash env.sh -p ${my_password}；
# 也可以修改配置文件 setting/globalconfig.ini 里面的 PASSWORD 配置项；
```

> **注意：** 所有命令不要以 `root` 用户执行！

### 4. 部署被测应用（deepin-pc-manager）

一键完成：拉取电脑管家源码 → 安装编译依赖 → 打包 → 安装 → 配置测试环境（polkit 权限、youqu 虚拟环境）。

```shell
$ bash deploy_pc_manager.sh
```

运行时交互输入 Gerrit 用户名和密码（密码不回显；凭据写入权限 `600` 的临时文件，退出即删，不写入 git remote）。常用参数：

```shell
$ bash deploy_pc_manager.sh                          # 默认构建 develop/refactor 最新提交
$ bash deploy_pc_manager.sh -c <commit>               # 固定提交
$ bash deploy_pc_manager.sh -b <branch>               # 指定分支（构建该分支最新提交）
$ bash deploy_pc_manager.sh -t <tag>                 # 按标签构建
$ bash deploy_pc_manager.sh -d ~/src/pcm             # 指定源码目录
$ bash deploy_pc_manager.sh -k -d ~/dpm-build/src    # 跳过拉取，使用现有源码
$ bash deploy_pc_manager.sh -A                       # 直接装系统仓库版本（1.0.10，不推荐）
$ bash deploy_pc_manager.sh -n                       # 跳过 env.sh（只部署应用）
$ bash deploy_pc_manager.sh -h                       # 查看全部参数
```

> UOS 20 测试机上的 Qt5/DTK5 运行时是 `+sign` 版本（如 `libqt5core5a 5.11.3.81`），
> 仓库中的 `qtbase5-dev` 等 dev 包要求精确同版本运行时，`apt` 会因版本约束拒绝
> 安装（历史上表现为 `g++` 依赖冲突后回退到仓库 1.0.10）。脚本现在：
> - `g++` 元包按 eagle 8.3 版本降级安装（只降元包，编译器仍是已装 `gcc-8`）；
> - 把 Qt5/DTK5/GL 开发包（头文件、CMake 配置、`.so` 链接）解包到 `/usr`，
>   不注册 dpkg 依赖，不降级系统运行时；
> - 按 `debian/control.1` 生成 V20 安装包，构建完成后校验安装版本与源码一致。

脚本会：
1. 装包前按系统版本写入 `/etc/apt/sources.list`（V20=eagle / V25=snipe，
   备份后**保持生效、不还原**），随后自动执行 `apt-get update` 刷新索引
   （`-U` 跳过，失败仅告警不中止），并隔离 `sources.list.d` 中不匹配的
   V25 源，避免构建期装包把 `libc6`/`systemd`/`sshd` 连带升级；该逻辑由
   `src/utils/apt_sources.sh` 提供，`env.sh` 复用同一实现。原始配置保留在
   `/var/backups/youqu-apt-sources/*.orig` 与 `*.youqu.bak`，需要回滚时
   `bash -c 'APT_SRC_SUDO_CMD=sudo; source src/utils/apt_sources.sh; restore_apt_sources'`；
2. 自动识别 V20（Qt5/DTK5）或 V25（Qt6/DTK6）构建配置并安装对应依赖；
3. 处理常见构建环境问题（dev 包版本约束、DTK soname 差异、`lrelease` 路径）；
4. `dpkg-buildpackage` 打包并安装 deb，校验版本与可执行文件；
5. 将 polkit 策略文件权限修正为 644，并为当前测试用户预授权
   `org.deepin.PCManager1.doAction`、`org.deepin.PCManager1.run-repair-tool`
   （后者由 env.sh 的 polkit 配置写入，UI 自动化无法应答系统认证弹窗）；
6. 安装用例依赖的外部命令（`iputils-arping`，IP 冲突检测用例使用）；
7. 若 `.venv` 不存在则执行 `env.sh` 完成 youqu 测试环境部署；`.venv` 已存在时
   只校验虚拟环境依赖。框架依赖只装在 `.venv`，**不写系统 site-packages**
   (`numpy`/`Pillow`/`cryptography` 等同名 `.so` 会触发电脑管家「关键库检测」的
   本地库冲突 3012)，改为把 `.venv/bin` 前置到 `~/.profile`、`~/.bashrc` 的
   `PATH`，裸 `python3` 即虚拟环境解释器，部署后可直接
   `python3 manage.py run -a apps/autotest_my_app`。

   > `ssh host 'cmd'`、cron 等非登录 shell 不读 `~/.profile`：改用
   > `bash -lc '...'` 或显式 `.venv/bin/python manage.py ...`（`manage.py`
   > 发现当前解释器不在 `.venv` 时会自动 `execv` 到 `.venv/bin/python3`）。

> 源码构建失败时直接报错并保留日志，不再静默回退系统仓库（仓库版本 `1.0.10`
> 低于源码版本，会导致用例覆盖不到新功能）。

> sudo 密码默认读取 `setting/globalconfig.ini` 的 `PASSWORD`；Gerrit 凭据也可通过
> `PCM_GIT_USER` / `PCM_GIT_PASSWORD` 环境变量提供（用于自动化）。

## 项目结构

```
youqu_deepin_pc_manager/
├── apps/                          # 测试用例工程目录
│   └── autotest_my_app/           # 电脑管家测试工程
│       ├── case/                  # 测试用例
│       │   ├── base_case.py       # 用例基类
│       │   └── assert_res/       # 断言资源目录
│       ├── widget/               # 页面方法层（PO 模式）
│       │   ├── base_widget.py    # 方法基类
│       │   ├── my_app_widget.py  # 电脑管家操作方法
│       │   ├── ui.ini            # 元素定位配置
│       │   └── pic_res/          # 图片资源
│       ├── my_app_assert.py      # 断言类
│       ├── config.py             # 应用工程配置
│       ├── config.ini            # 应用配置文件
│       ├── control               # 框架版本依赖声明
│       └── mycase.csv            # 用例标签管理文件
├── src/                           # YouQu 框架核心源码
│   ├── assert_common.py          # 断言模块
│   ├── button_center.py          # 元素操作中心
│   ├── cmdctl.py                 # 命令行工具
│   ├── dbus_utils.py             # DBus 工具
│   ├── dogtail_utils.py          # AT-SPI 元素操作
│   ├── image_utils.py            # 图像识别
│   ├── ocr_utils.py              # OCR 文字识别
│   ├── shortcut.py               # 快捷键操作
│   ├── mouse_key.py              # 鼠标键盘操作
│   ├── rtk/                      # 本地/远程执行器
│   ├── pms/                      # PMS 用例管理
│   ├── git/                      # Git 子命令
│   ├── plugins/                   # 插件
│   └── depends/                  # 依赖工具
├── setting/                       # 全局配置
│   ├── globalconfig.ini          # 全局配置文件
│   ├── globalconfig.py           # 配置解析
│   └── skipif.py                 # 跳过条件
├── report/                        # 测试报告输出
│   ├── allure/                   # Allure 原始数据
│   ├── allure_html/              # Allure HTML 报告
│   ├── json/                     # JSON 格式报告
│   ├── logs/                     # 日志文件
│   └── record/                   # 录屏文件
├── conftest.py                    # pytest 全局 fixture 和钩子
├── manage.py                     # 执行管理器入口
├── pytest.ini                    # pytest 配置
├── env.sh                        # 环境部署脚本
├── deploy_pc_manager.sh          # 被测应用一键部署脚本（拉源码/编译/安装）
├── CURRENT                       # 框架版本标记
└── Pipfile                       # Python 依赖管理
```

## 运行测试

### 本地执行

```shell
$ python3 manage.py run
```

#### 命令行参数

```shell
# 指定执行 apps/autotest_my_app 下的用例，支持关键词和标签过滤
$ python3 manage.py run -a apps/autotest_my_app -k "xxx" -t "yyy"
```

更多用法使用 `-h` 或 `--help` 查看。

#### 配置文件

在 [setting/globalconfig.ini](setting/globalconfig.ini) 中配置执行参数，主要包括：

| 配置项 | 说明 |
|--------|------|
| `APP_NAME` | 执行的应用名称，为空表示执行 apps/ 下所有应用 |
| `KEYWORDS` | 关键词过滤（模块名、文件名、类名、函数名均可） |
| `TAGS` | 用例标签过滤，支持 and/or/not 逻辑组合 |
| `CASE_TIME_OUT` | 单条用例超时时间（秒），默认 1800 |
| `RERUN` | 失败用例重跑次数，默认 1 |
| `RECORD_FAILED_CASE` | 失败录屏起始次数 |
| `REPORT_FORMAT` | 报告格式，支持 allure/xml/json |

### 远程执行

远程执行以本地作为服务端控制远程机器执行相同用例：

```shell
$ python3 manage.py remote
```

在 `setting/globalconfig.ini` 的 `[remote]` 段配置远程测试机信息。

## 测试用例说明

| 用例文件 | 说明 |
|----------|------|
| `test_mycase_<脚本ID>_<PMS用例ID>_<描述>.py` | 一条用例一个文件，脚本ID/PMS 用例ID/级别/废弃标记登记在同目录 `mycase.csv` |

### 清理类用例的环境隔离

"智能选择 → 彻底删除"（`2001989`、`2001991`）会一次性选中结果列表中的所有组，
大文件清理用例则断言"结果集为空/只有测试文件"。若测试机家目录已有真实重复文件或
大文件（构建产物、报告副本、录屏等），前者会永久删除真实数据，后者会造成与产品
缺陷无关的误报；重复文件用例还会因真实记录过多而滚动定位超时。用例在前置阶段
把这类文件临时移出扫描范围，结束再原样恢复：

| 方法 | 阈值 | 暂存位置 | 判据 |
|------|------|----------|------|
| `isolate_foreign_dup_files()` | ≥ 1 MB | `$HOME/.autotest_dup_staged` | 尺寸 + 首尾各 64 KB 采样 MD5 一致且成组（比产品"全量 MD5"更严） |
| `isolate_foreign_large_files()` | ≥ 100 MB | `/tmp/autotest_scan_isolated` | 文件尺寸 |

- 用例自己的测试文件（`$HOME/autotest_dup*`、`$HOME/autotest_large_file*`）不移动；
  重复文件隔离还排除项目自身目录和隐藏目录。
- 用例 `finally` 调用 `restore_foreign_dup_files()` / `restore_foreign_large_files()`
  按原路径恢复；进程被强杀等异常中断时，下一个同类用例开始前自动恢复遗留文件。
- 重复文件候选超过 200 个时直接报错并要求清理测试机，不做静默的部分隔离。

### 空间清理：系统垃圾分类的 6 个扫描项

`test_mycase_337`（`2001729`）覆盖系统垃圾分类下的全部扫描项：

| ID | 显示名称 | 对应测试垃圾 |
|----|----------|--------------|
| `sys-cache` | 系统缓存 | `/var/cache/apt/archives/autotest-sysjunk_1.0_amd64.deb` |
| `sys-log-large` | 超过100MB的系统日志 | `/var/log/autotest_sysjunk_large.log`（120 MB） |
| `sys-log-journal` | journal 日志（日志转储/归档文件） | `/var/log/journal/autotest_sysjunk@probe.journal` |
| `sys-log-rotated` | 轮转日志文件 | `/var/log/syslog.99` |
| `sys-license-log` | uos-license-agent 轮转日志 | `/var/log/uos/uos-license-agent/autotest_sysjunk.log.1` |
| `sys-trash` | 回收站 | `~/.local/share/Trash/files/autotest_sysjunk/junk.dat` |

判据来自产品 `space_clean_detector` 的 `ScanRule`，用例用
`create_all_system_junk_items()` 为每一项各构造一份垃圾。1.1.7 的 AT-SPI
**不暴露 itemId**：产品把 id 存在 QWidget 的 `accessibleIdentifier` 动态属性里，
该属性不上 AT-SPI；`accessibleName` 对所有子项都是固定值 `spaceClean_itemName`，
显示文本也读不到（`queryText` 为空）。因此断言改为三者交叉验证：

- 系统垃圾分类下子项数量为 6（6 份前置垃圾各对应一项）；
- 分类内按大小降序（产品 `categoryItemLess`），120 MB 的测试日志即第一项；
- 取消"系统垃圾"复选框后只勾选第一项并立即清理，只有 `sys-log-large` 消失
  （`/var/log` 大日志清理方式是截断为 0），其余 5 项仍在。

### 系统检测：分项卡片 / 检测项 / 检测 ID 对照

1.1.7 版本界面实测（`MyAppWidget.run_detection_item` 点击卡片后读取
`detectionCheckList_listView` 的 accessibleDescription 得到检测项清单）：

| 分项卡片 | 检测项 | 检测 ID（会话 / 系统总线） |
|----------|--------|----------------------------|
| 系统环境检测 | 备份与快照检查 / SSH密钥 / 时间配置 / 系统版本检测 / 核心包检查 / 关键库检测 | `backup_partition` `system_version` `core_packages`（系统）`ssh_key` `time_config` `critical_libraries`（会话） |
| 更新环境检测 | boot分区空间检测 / 仓库地址检查 / 仓库地址权限检查 / 本地环境检查 | `boot_partition_space` `repository_url` `repository_permission` `local_environment` |
| 硬件检测 | 磁盘健康 / CPU温度 / 内存 / 声卡 / 电池健康检查 / 磁盘空间 | `disk_health` `cpu_temperature` `memory` `sound_card` `battery_health` `disk_space` |
| 网络检测 | 网络设备检测 / 网络设置检测 / DHCP服务 / DNS服务 / hosts文件配置 / 网络访问 / IP 地址冲突 | `network_hardware` `network_settings` `dhcp_service` `dns` `hosts_file` |

要点：

- V20（Qt/Dtk 5）下 QML 的 Label、ListView 列表项都不向 AT-SPI 暴露文本和单项状态，
  界面层只能拿到每个分项的问题总数（`get_detection_group_state`）。
- 需要单项结论时用 `MyAppWidget.get_detection_item_verdict(<检测ID>)`：走电脑管家自身的
  D-Bus 接口 `org.deepin.PCManager1.Detect` + `Task.GetResult`，返回 `(ok, 原始结果)`。
  检测项分散在两条总线上：会话总线（会话守护进程，如 `time_config`）与系统总线
  （系统守护进程 `org.deepin.PCManager1` on system bus，如 `backup_partition`、
  `system_version`、`core_packages`、`repository_url`）。方法先查会话总线，
  收到 `unknown operable item` 后回退系统总线；两条总线都不实现时返回 `None`，
  用例退回分项级断言。
- 用例必须先点击目标分项卡片（`run_detection_item(<卡片名>)`）触发该分项，
  再用 `is_only_group_detected(<卡片名>)` 断言"该分项跑完且其它 4 张卡片的已检查数为 0"，
  避免用例实际执行的是全面检测（`click_detection_full_scan_button`）而不自知。
- 安装类型判定用 `get_install_partition_type()` 读取
  `/etc/deepin-installer/deepin-installer.conf` 的 `DI_PARTITION_TYPE`
  （1 = 手动/非全盘，2/3/6/7 = 全盘，0 = 安装器未记录）。
- 场景前置无法满足时（硬件缺失、安装类型不符、服务被系统自动拉起）用例 `pytest.skip`
  并给出实测值，不以"页面能显示"替代检测结论断言。

## 报告查看

测试执行完成后，报告生成在 `report/` 目录下：

- **Allure HTML 报告**：`report/allure_html/index.html`
- **JSON 报告**：`report/json/`
- **日志**：`report/logs/`
- **录屏**：`report/record/`

## 贡献

[贡献文档](https://youqu.uniontech.com/CONTRIBUTING.html)

## 开源许可证

本项目在 [GPL-2.0](https://github.com/linuxdeepin/youqu/blob/master/LICENSE) 下发布。

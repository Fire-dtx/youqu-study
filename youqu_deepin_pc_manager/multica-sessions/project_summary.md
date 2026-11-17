## 电脑管家自动化测试用例项目信息汇总

### 一、项目概述

本项目基于 **YouQu（有趣）v2.14.0** 自动化测试框架，使用 AI 大模型辅助构建了 **统信电脑管家（deepin-pc-manager）** 的 UI 自动化测试用例集。项目仓库 `youqu_deepin_pc_manager` 位于内部代码评审平台，开发周期为 2026 年 9 月 11 日至 10 月 26 日，共产出 **709 个非合并提交**、**470 个合并提交**，涉及 **481 个分支**，覆盖 **268 条测试用例**（207 条一级用例 + 61 条二级用例），PMS 系统关联用例总数 **498 条**，PMS 产品 ID 为 **555**。

会话数据已打包压缩：`pc_manager_sessions.tar.zst`（476MB 压缩 / 3.3GB 解压，zstd 压缩），共 559 个会话文件，其中 466 个与本项目相关。

---

### 二、使用的 AI 模型

在项目开发过程中，共使用了以下 AI 模型参与测试用例的编写与调试：

| 模型 | 调用路径 | 主要用途 |
|------|----------|----------|
| **glm-5.2** | `gateway/glm-5.2`、`local/glm-5.2` | 测试用例代码编写、调试、问题分析（主力模型） |
| **deepseek-v4-flash** | `local/deepseek-v4-flash` | 测试用例代码编写辅助、快速原型生成 |

AI 模型通过 Multica 平台以 issue 驱动方式分配子任务，每个子任务对应一条或多条 PMS 测试用例，由 agent 在远程测试机上完成用例编写、调试和提交，最终通过 MR（Merge Request）合并到主分支。

---

### 三、YouQu（有趣）框架介绍

**YouQu** 是统信软件开源的 Linux 桌面应用自动化测试框架（GitHub: https://github.com/linuxdeepin/youqu），支持以下测试类型：

- 💻 Linux 桌面应用 UI 自动化测试（基于 AT-SPI/dogtail）
- 🌏 Web UI 自动化测试（基于 Playwright）
- 🚌 Linux DBus 接口自动化测试
- 🚀 命令行自动化测试
- 🕷️ HTTP 接口自动化测试

**核心特性：**

1. **PO（Page Object）模式**：`case/`（测试逻辑）→ `widget/`（页面操作方法）→ `assert/`（断言）三层架构，职责清晰
2. **AT-SPI 元素操作**：通过 dogtail 库访问 AT-SPI 无障碍树，精确定位 UI 元素（`focus_windows()`、`find_object()` 等）
3. **图像识别 + OCR**：集成 pyscreenshot + OpenCV 模板匹配 + PaddleOCR，支持图像坐标定位和文字识别断言
4. **CSV 标签管理**：每条用例通过 CSV 文件管理跳过条件（`skip-`、`skipif_`）、修复状态（`fixed-`）、废弃标记（`removed-`）、PMS 用例 ID 映射
5. **条件跳过机制**：`setting/skipif.py` 提供按平台（V20/V25）、CPU 架构（x86_64/loongarch64）、显示协议（Wayland/X11）条件跳过用例
6. **PMS 数据回填**：与 PMS（ZenTao）测试管理系统集成，支持测试结果自动回填到测试单/测试套件
7. **失败录屏**：从指定失败次数开始录制测试过程视频，失败时自动截图并附加模板图片和 OCR 识别区域
8. **Allure 报告**：生成 HTML 可视化测试报告，支持 severity 标签、用例关联链接
9. **远程执行**：支持本地控制远程测试机执行相同用例（`youqu manage.py remote`）
10. **框架内嵌**：`src/` 目录直接包含框架源码，无需 pip 安装，便于在离线环境（V20）部署

**框架模块清单：**
- `dogtail_utils` — AT-SPI 元素操作
- `image_utils` — 图像识别（模板匹配）
- `ocr_utils` — OCR 文字识别
- `video_utils` — 录屏录像
- `dbus_utils` — DBus 接口调用
- `cmdctl` — 命令行执行
- `button_center` — 元素操作中心
- `shortcut` — 快捷键操作
- `mouse_key` — 鼠标键盘模拟
- `read_csv` — CSV 用例数据读取
- `pinyin` — 拼音工具
- `pms/` — PMS 用例管理（csv2pms, pms2csv, send2pms, suite, task）
- `rtk/` — 本地/远程执行器（local_runner, remote_runner, api_client）

---

### 四、youqu_deepin_pc_manager 项目介绍

#### 4.1 项目结构

```
youqu_deepin_pc_manager/
├── apps/autotest_my_app/         # 电脑管家测试工程
│   ├── case/                     # 测试用例（按 PMS_ID_用例名.py 命名）
│   │   ├── base_case.py          # 用例基类 BaseCase(MyAppAssert)
│   │   ├── test_mycase_001-003   # 模板/示例用例
│   │   ├── 2000535_打开.py       # PMS 用例：打开电脑管家
│   │   ├── 2000537_发送到桌面.py # PMS 用例：发送到桌面
│   │   └── ...                   # 更多 PMS 用例
│   ├── widget/                   # 页面方法层
│   │   ├── base_widget.py        # BaseWidget(Src) 基类
│   │   ├── my_app_widget.py      # 电脑管家操作方法
│   │   ├── ui.ini                # 元素坐标配置
│   │   └── pic_res/              # 图片资源
│   ├── my_app_assert.py          # MyAppAssert 断言类
│   ├── config.py                 # 应用工程配置
│   ├── mycase.csv                # 用例标签管理
│   └── control                   # 框架版本依赖声明
├── src/                           # YouQu 框架核心源码（内嵌）
├── setting/                       # 全局配置
│   ├── globalconfig.ini          # 运行参数配置
│   ├── globalconfig.py           # 配置解析
│   └── skipif.py                 # 条件跳过函数
├── conftest.py                    # pytest 全局钩子（PMS 集成、录屏、报告）
├── manage.py                     # 执行管理入口
├── pytest.ini                    # pytest 配置
├── env.sh                        # 环境部署脚本
└── Pipfile                       # Python 3.12 依赖
```

#### 4.2 测试覆盖范围

测试用例覆盖电脑管家的核心功能模块：

- **应用启动与导航**：应用打开、导航切换、发送到桌面、入口检测
- **系统优化**：磁盘空间检测、boot 分区检查、内存使用率检测、大文件清理、重复文件清理、玲珑环境空间清理
- **系统安全检测**：关键系统文件权限检测、SSH 主机密钥检测、关键库冲突检测、IP 地址冲突检测
- **系统环境检测**：系统快照扫描、电池寿命检测、声卡检测、文件描述符检测、时间配置检测、仓库地址检查
- **可清理项分析**：扫描项占比分析、联想响应测试

#### 4.3 技术实现要点

- **元素定位**：`MyAppWidget(BaseWidget)` 继承 YouQu 的 `Src` 基类，通过 AT-SPI `showing` 属性判断页面是否显示
- **断言机制**：`BaseCase(MyAppAssert)` → `MyAppAssert` 继承链，提供应用级断言方法
- **配置驱动**：`globalconfig.ini` 集中管理 `APP_NAME`、`KEYWORDS`、`CASE_TIME_OUT=1800`、`RERUN=1`、`RECORD_FAILED_CASE=1`、`CLEAN_ALL=yes`、分辨率检查等
- **环境自适应**：`env.sh` 自动检测显示协议（Wayland/X11），通过 `~/.xsession-errors` 中的 `XDG_SESSION_TYPE` 判断，回退到 `kwin_x11` 进程检查

---

### 五、踩坑经验与解决方案

#### 5.1 V20/V25 版本兼容性 — "第一道门"

**问题**：父任务要求"每个子任务添加的测试用例都要支持 V20 和 V25"，但 V20（x86_64）和 V25（loongarch64）在系统库版本、AT-SPI 可用性、包管理器等方面存在差异。部分 agent 未在第一时间确认目标版本，导致用例在错误环境上调试后需要返工。

**解决**：将版本检查确立为测试用例开发的"第一道门"——agent 接到任务后必须先确认目标系统版本（V20/V25）、CPU 架构、应用版本号（如 1.0.10-1），再开始编写代码。通过 `skipif.py` 中的 `skipif_platform`、`skipif_not_platform`、`skipif_cpu_name` 等条件跳过函数，实现同一套用例在不同版本上按需执行。

#### 5.2 AT-SPI/dogtail 可用性差异

**问题**：dogtail 依赖 AT-SPI 无障碍服务，不同系统版本的 AT-SPI 支持程度不同。V20 上 dogtail 可能不可用或行为不一致，导致元素查找失败。

**解决**：
- 框架在 `src/depends/dogtail/` 中内嵌了 dogtail 源码，减少版本依赖
- `conftest.py` 在 `pytest_sessionstart` 中检测并记录当前显示协议（Wayland/X11）
- 对 AT-SPI 不可用的场景，回退到图像识别（`image_utils`）和 OCR（`ocr_utils`）方案

#### 5.3 Wayland vs X11 兼容

**问题**：Wayland 和 X11 下窗口管理、输入事件模拟行为不同，部分用例在 X11 下正常但在 Wayland 下失败。

**解决**：
- `env.sh` 自动检测显示协议并设置相应环境变量
- `skipif.py` 提供 `skipif_xdg_type` 函数，可按 `wayland`/`x11` 条件跳过用例
- `conftest.py` 设置 `DISPLAY=:0` 和 `XAUTHORITY` 环境变量确保 X11 会话可用

#### 5.4 远程测试机访问

**问题**：测试需要在远程物理机上进行，agent 需要通过 SSH 连接远程机器执行测试。

**解决**：
- 使用 `sshpass` 配合凭据实现非交互式 SSH 访问（凭据不入库）
- `env.sh` 脚本支持从参数或配置文件读取凭据
- `conftest.py` 中的 `slaves` fixture 支持远程测试机配置（凭据由本地配置提供）

#### 5.5 多 Agent 并发机器冲突

**问题**：多个 agent 同时在远程测试机上执行用例，可能出现窗口冲突、进程竞争等问题。

**解决**：通过 Multica 平台的 issue 任务分配机制，将不同功能模块的用例拆分到不同子任务，由不同 agent 在不同时间段执行。`letmego` 模块记录用例执行状态，避免重复执行。

#### 5.6 框架内嵌 vs pip 安装

**问题**：V20 环境可能无法访问 PyPI，`pip install youqu` 失败。

**解决**：项目将 YouQu 框架源码直接内嵌在 `src/` 目录中，包括 dogtail、colorama、cfonts 等依赖，实现零 pip 安装部署。`control` 文件声明框架版本依赖。

#### 5.7 大文件压缩性能

**问题**：559 个会话文件总计 3.3GB，使用 gzip 压缩超时（>300s 未完成）。

**解决**：改用 zstd 压缩（`tar --use-compress-program="zstd -3 -T8"`），298 秒完成，压缩至 476MB，压缩比约 7:1。

---

### 六、经验总结

1. **AI 驱动 + 框架规范 = 高效产出**：709 个非合并提交、268 条用例在一个半月内完成，得益于 YouQu 框架的标准化 PO 模式和 CSV 标签管理，AI agent 可以按统一模板高效生成用例代码。

2. **Issue 驱动的任务分解**：通过 Multica 平台将大任务拆分为子 issue，每个子 issue 对应一条 PMS 用例，agent 独立完成后通过 MR 合并。这种模式实现了高度并行化开发。

3. **环境信息是第一优先级**：V20/V25 版本、CPU 架构、显示协议等环境信息必须在任务开始时明确，否则会导致大量返工。`skipif.py` 机制是处理环境差异的有效手段。

4. **内嵌框架提升可移植性**：将框架源码内嵌到项目中，避免了对外部 pip 源的依赖，特别适合离线/受限网络环境部署。

5. **多模态断言提升鲁棒性**：AT-SPI + 图像识别 + OCR 三种定位/断言方式的组合，使得在元素树不可用或 UI 变化时仍有回退方案。

6. **失败录屏 + Allure 报告**：失败时自动录屏并截图模板图片和 OCR 区域，配合 Allure HTML 报告，大幅提升了问题定位效率。

---

### 七、对其他桌面项目的借鉴价值

1. **PO 模式三层架构可直接复用**：`case/ → widget/ → assert/` 的分层模式适用于任何 Linux 桌面应用，新建项目只需替换 `APP_NAME` 和 `DESC` 即可快速起步。

2. **CSV 标签管理体系**：通过 CSV 文件管理用例的跳过条件、修复状态、废弃标记和 PMS ID 映射，无需修改代码即可控制用例执行范围，适合需要频繁调整用例集的 CI/CD 场景。

3. **条件跳过框架**：`skipif.py` 提供的平台/CPU/显示协议条件跳过机制，是多版本兼容测试的通用解决方案，其他项目可直接引入。

4. **框架内嵌部署模式**：对于需要在多种部署环境（在线/离线/受限网络）中运行的测试项目，内嵌框架源码是一种值得借鉴的可移植性策略。

5. **AI + Multica 平台协作模式**：Issue 驱动 → Agent 并行执行 → MR 合并的工作流，可推广到其他需要大规模测试用例编写的桌面项目，显著提升开发效率。

6. **PMS 集成方案**：`conftest.py` 中与 ZenTao PMS 系统的集成逻辑（用例 ID 映射、结果回填、测试单关联）可作为测试管理平台对接的参考实现。

7. **env.sh 环境自适应脚本**：自动检测显示协议、Python 版本、凭据配置的部署脚本模式，可降低测试环境搭建的门槛。

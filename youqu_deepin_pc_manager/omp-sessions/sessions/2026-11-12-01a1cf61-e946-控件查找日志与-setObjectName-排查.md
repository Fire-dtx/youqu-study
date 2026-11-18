# 控件查找日志与 setObjectName 排查

- 会话 ID: `01a1cf61-e946`
- 类型: 顶层会话
- 项目目录: `/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager`
- 创建时间: 2026-11-12T18:51:02+08:00
- 最后活动: 2026-11-13T10:11:23+08:00
- 消息: 用户提示词 12 / 助手文本 15 / 模型请求 209
- 模型: deepseek-v4.1-flash-1017 × 209
- Token: input=704,915, output=148,609, cacheRead=17,119,104, total=17,972,628
- 工具调用 Top: bash×161, edit×58, read×16, todo×14, wait×8, eval×2
- 原始记录: `/home/ut000635@uos/.omp/agent/sessions/-Documents-TestCode-youqu_deepin_pc_manager/2026-11-12T10-51-02-854Z_01a1cf61-e946-7000-9e5b-e304f314dba7.jsonl`

## 用户提示词

### U1

先不要改代码，结合“/home/ut000635@uos/Documents/test/log/电脑管家自动化测试/report_2026_1106”来查看，当前项目中用例存在找不到控件setObjectName设置的名称问题吗？

### U2

先不改代码，现在需要统计一下有多少用例存在此问题，然后对于存在找不到控件名称的地方要格式化打印日志，找不到或者找得到都要打日志，应该怎
  么改代码？

### U3

按这个方案落地，然后在测试环境ssh uostest10.20.33.103 密码是 1 上单用例执行一次执行一条用例验证修改后的输出，最后批量全跑涉及日志改动的用例检查日志输出

### U4

区分候选回退与真实未命中，这个在日志中是怎么体现的？

### U5

直观一点，直接在日志里中文说明走了回退、候选、真实未命中

### U6

现在回退 探测的手段是什么？

### U7

我是问 现在回退探测用的是界面截图吗？

### U8

对，我的意思就是日志要体现AT-SPI 树里没有设置name/objectName的控件

### U9

对于没有设置name/objectName的控件，你可以在日志中打印这个控件的文本内容吗？

### U10

把没有设置name/objectName的控件，打印这个控件的文本内容这些日志写到一行里，方便后面grep查找日志？

### U11

当前修改是否足够收敛，有没有更简洁的改法？

### U12

find_element_by_attr的 probe=True是否所有用例都应该加上？

## 助手输出（按时间顺序，已省略 thinking 与工具参数）

### A1

结论：**存在，并且已经稳定复现，但当前没有一条用例因它失败。**

\## 1. 日志事实

`report_2026_1106/report/logs` 中 `====未找到“$//…”元素！====` 来自 `src/custom_exception.py:53`，由 `src/dogtail_utils.py:188-221` 在 AT-SPI 表达式返回空列表时抛出并**无条件 `logger.error`**。

| 日志 | 未找到次数 | 涉及用例 | 涉及名称 |
|---|---|---|---|
| 2026-11-04_debug.log | 121 | 52 | 37 |
| 2026-11-05_debug.log | 108 | 49 | 34 |
| 2026-10-30 / 11-02 | 各 1 | 2 | 2 |

两天集合几乎一致（11-05 少 13 次），说明可稳定复现，并非偶发。11-05 该轮共 362 条用例、6 条失败（`1999177`/`2032619`/`2032623`/`2032625` 网络检测 issues=1、`2010553` dde-printer 安装、`2032433` 日志查看器未启动），**没有一条根因是控件名找不到**。

\## 2. 按性质拆解

| 未命中名称 | 次数(11-04/11-05) | 实际命中名 | 性质 |
|---|---|---|---|
| `$//repair_runtimePage//开始修复` | 19/17 | `$//repair_startBtn` | 写的是 V25 名，V20 不存在 |
| `$//detectionFullScanPage` | 13/14 | `$//detection_fullScanPage` | snake/camel 版本差异 |
| `$//repairOfflineOnlySwitch` | 6/6 | `$//repair_offlineSwitch` | 同上 |
| `$//startup_电脑管家` | 4/4 | `$//startup_PC Manager` | accessibleName 取 GenericName |
| `$//detectionScoreTimeText` | 5/5 | `$//detection_scoreLabel` | 版本差异 |
| `$//detectionRuntimePage` | 3/3 | `$//detection_runtimePage` | 版本差异 |
| `$//detectionResultPage(sPage)` | 1/1 | `$//detection_resultPage` | 版本差异 |
| `$//dupFile_actionCombo` | 2/2 | 遍历 `roleName == "combo box"` | 有回退 |
| `$//设置` / `$//Settings` | 2/2 | 坐标点击菜单项 | 有回退 |
| `$//帮助` | 1/1 | `dman` 命令兜底 | 有回退 |
| `$//shellRepair_outputLog` / `shellRepair_inputEdit` | 5+1/5+1 | 无（对话框已关闭） | 清理阶段预期不存在 |
| `$//spaceCleanCategory*_{linglong,snapshot}`、`$//categoryCard

…（截断，原文 3139 字符）

### A2

未改动任何代码。以下统计来自 11-04/11-05 两轮日志，方案部分只给设计。

\## 一、统计：53 条用例（当前仓库存活 51）

口径：日志中只要出现一次 `====未找到“$//…”元素！====` 即计入；仅能按未命中反推（当前无命中日志）。

| 口径 | 用例数 | 结果 |
|---|---|---|
| 2026-11-04 | 52 | 51 PASS / 1 FAIL（`test_mycase_185`，11-05 复跑 PASS，失败与控件名无关） |
| 2026-11-05 | 49 | 全部 PASS |
| 两天并集 | **53** | 11-04 独有 4 条：`032/126/315/317` |
| 当前仓库存活 | **51** | `133`=2005697、`134`=2005699 文件已删除 |

按性质归类（主类优先，互斥）：

| 类别 | 用例数 | 说明 |
|---|---|---|
| A. V20/V25 命名差异，主名不命中、靠二/三候选命中 | 48 | 兼容层已覆盖，属预期日志噪声 |
| B. 负向断言/预期不存在 | 2 | `084`（验证无空间清理入口）、`139`（对话框关闭后查找） |
| C. 场景缺失 | 1 | `280`：V20 无玲珑/快照分类数据 |
| D. 两候选全失败且无回退 | 1 | `257`：`utility_categoryTabs//全部`、`//磁盘工具` 四候选全空仍 PASS |
| E. 功能已下线 | 1 | `134`：离线导入入口，文件已删 |

按未命中名称聚合（A 类）：

| 未命中名称 | 用例数 |
|---|---|
| `$//repair_runtimePage//开始修复` | 18 |
| `$//detectionFullScanPage` | 13 |
| `$//detectionScoreTimeText` | 5 |
| `$//spaceCleanScanningPage` / `scanProgressBar` / `backGroundWidget_scanProgressBar` | 3 |
| `$//设置` / `$//Settings` | 2 |
| `$//dupFile_actionCombo` | 2 |
| `$//detectionResultsPage` / `detectionResultPage` / `detectionRuntimePage` | 各 1 |
| `$//repairOfflineOnlySwitch` / `startup_电脑管家` / `$//帮助` | 各 1 |
| `$//utility_categoryTabs//*`、`spaceCleanCategory*`、`detection_page//空间清理`、`shellRepair_outputLog/inputEdit`、`repair*Import*` | 各 1 |

`237` 同时命中 `detectionFullScanPage` 与 `detectionScoreTimeText`，按名称相加会重复。

注意：这是**日志口径**。11-05 之后 `2032417` 已改为直接点卡片、`2010049` 已改走 `_find_showing_menu_item` 遍历、`2032299` 不再调用 `spaceCleanCategory*`，所以当前代码实

…（截断，原文 5999 字符）

### A3

落地完成，测试机实测验证通过。

\## 一、改动内容（8 个文件）

| 文件 | 改动 |
|---|---|
| `src/dogtail_utils.py` | 新增 `_lookup_log` / `_lookup_caller` / `set_current_case` / `log_lookup_summary`；`find_elements_by_attr(expr, probe=False, _caller=None)`、`find_element_by_attr(expr, index=0, probe=False)` 统一埋点；命中 INFO、未命中 WARNING、重复静默（`UI_LOOKUP_VERBOSE=1` 全量）；`probe` 只影响日志，不影响返回值 |
| `src/custom_exception.py` | `ElementNotFound` 不再 `logger.error`（原来每次未命中固定打 `[__init__]`，丢掉调用点） |
| `conftest.py` | setup 记录 `item.nodeid`、teardown 清空、sessionfinish 输出汇总 |
| `my_app_widget.py` | `_find_element_in_exprs`/`_find_repair_element` 改 `probe=True`；分类 tab 未命中 WARNING 并返回 `False`；`_any_visible`/`_elements_exist`/`_find_first_element`/`get_detection_full_scan_button_showing`/`get_detection_cards_view_showing`/`get_detection_card_count`/`get_detection_card_names`/`open_settings_dialog`/`get_repair_completion_status` 的候选查找标记 probe |
| 4 个用例 | `2001991`、`2005491`、`2005857`、`2032379` 内多候选查找标记 probe |

实测日志（21:17:07 起）：

```
[控件查找] hit=1 expr=$//mainWindow_navList count=1 name='mainWindow_navList' role='list' size=(180, 176) cost=0.49s caller=my_app_widget.py:2955:click_repair_nav
[控件查找] hit=0 expr=$//detectionFullScanPage count=0 cost=0.85s caller=my_app_widget.py:2596:get_detection_full_scan_page_showing
[控件查找汇总] 表达式=114 直接未命中表达式=14 直接未命中用例=32 回退探测未命中次数=10
```

\## 二、验证结果

| 验证项 | 结果 |
|---|---|
| 单用例 `2005705` | 首跑 PASSED；命中日志 4 条、`2026-11-12_error.log` 为空（重复 ERROR 已消失） |
| 批量：直接调用查找 API 的 63 条用例（59 分钟） | 41 通过 / 22 失败；汇总输出

…（截断，原文 2296 字符）

### A4

三层体现，均已实测。

\## 1. 日志行：`probe=` 字段

```python
\# src/dogtail_utils.py:76
def _lookup_log(expr, elements, cost, probe, caller):
    key = ("probe_" if probe else "") + ("hit" if hit else "miss")
    stat[key] += 1
    if not hit and not probe and _CURRENT_CASE:
        _CASE_MISS[_CURRENT_CASE].add(expr)   # 只有直接未命中记入“问题用例”
    if probe and not verbose:
        return                                 # 候选探测默认静默
```

默认模式实测（测试机 09:36:35）：

```
[控件查找] hit=1 probe=0 expr=$//direct_hit count=1 name='开始修复' role='push button' ...
[控件查找] hit=0 probe=0 expr=$//direct_miss count=0 cost=0.52s caller=x.py:2:g
```

候选回退的行默认**根本不出现**；`UI_LOOKUP_VERBOSE=1` 时才出现且带 `probe=1`：

```
[控件查找] hit=0 probe=1 expr=$//probe_miss count=0 cost=0.10s caller=x.py:3:h
[控件查找] hit=1 probe=1 expr=$//probe_hit count=1 name='检测' role='filler' ...
```

所以单行判定规则：`hit=0` + `probe=0` = 真实未命中；`probe=1` = 候选回退（预期）。

\## 2. 汇总：两套计数不混

```
[控件查找汇总] 表达式=4 直接未命中表达式=1 直接未命中用例=1 回退探测未命中次数=1
[控件查找汇总] expr=$//direct_miss hit=0 miss=1 probe_hit=0 probe_miss=0
[控件查找汇总] case=case_A miss=1 exprs=$//direct_miss
```

- `直接未命中表达式`、`直接未命中用例`：只统计 `probe=0`，即"用例要的控件真的不存在"。
- `回退探测未命中次数`：`probe=1` 的未命中，仅计数，不列表达式、不算用例。
- 表达式行给出 `hit/miss/probe_hit/probe_miss` 四列，同一表达式两种用途可分开看。

\## 3. 调用侧：由调用方声明语义

是否候选回退由调用点传 `probe=True` 决定（日志层无法自动推断）：

| 位置 | 判定 |
|---|---|
| `_find_element_in_exprs`、`_find_repair_element`、`_any_visible`、`_elements_exist`、`_find_first_element` | 多候选回退 → `probe=True` |
| `get_detection_full_scan_button_showing` / `get_

…（截断，原文 2150 字符）

### A5

两项均已完成并核验：

- 日志行新增 `probe=0/1`（`src/dogtail_utils.py:76`），默认模式候选探测静默、只有 `probe=0` 的未命中出 WARNING；`UI_LOOKUP_VERBOSE=1` 时全量输出且每行带 `probe=1`。
- 已 rsync 到 `uostest@10.20.33.103:~/youqu_deepin_pc_manager/src/dogtail_utils.py`，并在测试机用 .venv 脚本跑通四种组合：
  - 默认：`hit=1 probe=0`、`hit=0 probe=0`，probe 行不出现；
  - VERBOSE：`hit=0 probe=1`、`hit=1 probe=1`；
  - 汇总输出 `直接未命中表达式=1 直接未命中用例=1 回退探测未命中次数=1`，probe 未命中不计入用例维度。

未提交任何 git 写操作。

### A6

已改为中文结果字段，行首直接可读。测试机实测（09:41）：

```
[控件查找] 结果=直接命中 hit=1 probe=0 expr=$//direct_hit count=1 name='开始修复' role='push button' ...
[控件查找] 结果=真实未命中 hit=0 probe=0 expr=$//direct_miss count=0 cost=0.52s caller=x.py:2:g
```

`UI_LOOKUP_VERBOSE=1` 时补齐候选路径：

```
[控件查找] 结果=候选未命中(回退探测) hit=0 probe=1 expr=$//probe_miss count=0 cost=0.10s caller=x.py:3:h
[控件查找] 结果=候选命中(回退命中) hit=1 probe=1 expr=$//probe_hit count=1 name='检测' role='filler' ...
```

| 场景 | 日志 | 默认是否输出 |
|---|---|---|
| 单表达式找到 | `结果=直接命中 ...` | INFO，首个 |
| 单表达式找不到 | `结果=真实未命中 ...` | **WARNING，首个** |
| 候选回退中命中 | `结果=候选命中(回退命中) ...` | 否（VERBOSE 才输出） |
| 候选回退中未命中 | `结果=候选未命中(回退探测) ...` | 否（VERBOSE 才输出） |

汇总同步加中文：

```
[控件查找汇总] 表达式=4 直接未命中表达式=1 直接未命中用例=1 回退探测未命中次数=1
[控件查找汇总] expr=$//direct_miss 结果=真实未命中 hit=0 miss=1 probe_hit=0 probe_miss=0
[控件查找汇总] case=case_A miss=1 exprs=$//direct_miss
```

`hit=/probe=` 数字字段保留，便于脚本统计；中文 `结果=` 在前，肉眼直接读。改动已同步 `10.20.33.103`，`py_compile` 通过，未做 git 写操作。

### A7

没有隐式探测机制。回退由**调用方显式给候选列表**，`probe=True` 只是告诉日志“这是候选尝试”，不参与查找逻辑。

\## 1. 实现手段

**统一入口**（`my_app_widget.py:1811`）：

```python
def _find_element_in_exprs(self, exprs):
    for expr in exprs:                                   # 按顺序逐个试
        elements = self.dog.find_elements_by_attr(expr, probe=True)
        if elements:
            return elements[0]                           # 首个命中即返回
    return None                                          # 全未中
```

**语义化封装**，全部走同一手段：

| 函数 | 语义 | 全未命中时 |
|---|---|---|
| `_find_element_in_exprs`（1811） | 取第一个存在的元素 | 返回 `None` |
| `_find_repair_element`（2814） | 同上，带异常 | 抛 `Exception` |
| `_any_visible`（19221） | 任一候选 size 非零（V20 隐藏页 size=(0,0)） | 返回 `False` |
| `_elements_exist` / `_elements_exist_any`（19254/19266） | 任一候选存在 | 返回 `False` |
| `_find_first_element`（19273） | 取第一个存在的元素 | 返回 `None` |

**V20/V25 双写**也是同一模式的展开（`for attr in (...)`）：`get_detection_full_scan_button_showing`、`get_detection_cards_view_showing`、`get_detection_card_count/names`、`open_settings_dialog` 的 `("设置", "Settings")`、`get_repair_completion_status` 的 `$//修复完成`。

**用例内候选**同理：`2001991` 先 `dupFile_actionCombo`、再按 role 找 `combo box` 兜底；`2005857` 多表达式；`2032379` 先 `settings_extendedScanPartition` 再 `extendedScanPartitionRow`；`2005491` 的 `_find`。

\## 2. 底层执行

`find_elements_by_attr(expr, probe=False, _caller=None)`（`src/dogtail_utils.py:305`）→ `__trace` 逐级解析 `$//`：`SearchError` 转 `ElementNotFound`。`probe` 只传给 `_lookup_log`：

```python
caller = _caller or _lookup_caller(skip=1)

…（截断，原文 2107 字符）

### A8

不是。回退探测全程用 **AT-SPI 控件树**，不截图、不做图像匹配。

证据链：

1. 定位内核（`src/dogtail_utils.py:277`）直接在 dogtail 节点上按名称/角色查子树：

```python
element = element.findChildren(predicate.GenericPredicate(name), recursive=recursive)
```

2. 回退只是把多个表达式依次丢给同一内核（`my_app_widget.py:1818`）：

```python
for expr in exprs:
    elements = self.dog.find_elements_by_attr(expr, probe=True)
    if elements:
        return elements[0]
```

3. 可见性判定用的是 AT-SPI 元素属性，不是像素：`_any_visible` 读 `element.size`，`(0,0)` 视为隐藏。

4. 兜底手段也不是截图：
   - `open_settings_dialog`：`xdotool key Down/Return` 键盘导航；
   - `2001991`：`findChildren(lambda n: n.roleName == "combo box")` 按 role 扫；
   - `2005857`/`2032379`：更多候选表达式。

5. `src/dogtail_utils.py` 无 `image`/`ocr`/`screenshot`/`pyautogui` 引用（已 grep 确认）。

项目里的 `src/image_utils.py`、`src/filter_image.py`、`src/ocr_utils.py` 用于截图断言、失败取证、OCR 文本识别，**不参与控件定位**。因此“真实未命中”的判定含义是：该 `name/objectName` 没有出现在 AT-SPI 树里（或 size 为 0 不可见），而不是截图里没找到。

### A9

已完成改动并验证诊断逻辑本身：

- 真实未命中行追加 `AT-SPI树:` 字段，实测真实应用树（09:53）：
```
[控件查找] 结果=真实未命中 ... AT-SPI树:目标name='绝对不存在的控件XYZ'
  同名控件=无 匿名控件=48(未设name/objectName) 已命名控件=187 遍历节点=331
```
- 目标存在同名时显示 `同名控件=有` 并列出相近名称；诊断耗时 0.38~0.43s/次，仅直接未命中且每表达式首次执行，候选回退不做扫描。
- mock 与真实树均已验证，`py_compile` 通过，已同步测试机。

`2032447` 端到端回归正在测试机运行，结果稍后补上。

### A10

完整链路已验证，日志现在直接说明 AT-SPI 树里有没有这个 name。

真实应用实测（`find_elements_by_attr` 异常路径）：
```
[控件查找] 结果=真实未命中 hit=0 probe=0 expr=$//绝对不存在的控件XYZ count=0 cost=0.28s caller=... 
AT-SPI树:目标name='绝对不存在的控件XYZ' 同名控件=无 匿名控件=48(未设name/objectName) 已命名控件=187 遍历节点=331
```

命中对照：
```
[控件查找] 结果=直接命中 hit=1 probe=0 expr=$//mainWindow_navList count=1 name='mainWindow_navList' role='list' ...
```

字段含义：

| 字段 | 说明 |
|---|---|
| `目标name='x'` | 表达式末段，即本次查找依赖的 name/objectName |
| `同名控件=无/有` | AT-SPI 树内是否存在同名控件；`无` 即产品没设置该名称 |
| `匿名控件=N(未设name/objectName)` | 树内 name 为空的控件数量，可直接确认“产品未设 setObjectName” |
| `已命名控件=M` | 树内非空 name 的控件数 |
| `遍历节点=K` | 诊断扫描范围（上限 3000） |
| `相近name=...` | 相似度 ≥0.6 的名称，暴露 V20/V25 命名变体或拼写差异 |

行为约束：

- 只对 `probe=0` 的直接未命中做扫描；候选回退未命中不扫（避免噪声与开销）。
- 每个表达式每会话只输出一次；单次扫描 0.28~0.43s（真实树 331 节点）。
- 扫描异常时静默降级，只输出原始未命中行，不影响查找返回值。

回归：`2032447` PASSED（71.77s），汇总 `表达式=11 直接未命中表达式=0 直接未命中用例=0 回退探测未命中次数=10`。改动在 `src/dogtail_utils.py`，已同步测试机，未做 git 写操作。

### A11

已加上。匿名控件（`name` 为空）会尝试读取文本内容，读不到文本时给出 role 分布。

实现（`src/dogtail_utils.py:89`、`:104`）：

```python
def _node_text(node, max_len=30):
    text = str(node.text or "").strip()        # AT-SPI Text 接口
    if not text:
        text = str(getattr(node, "description", "") or "").strip()
    return text[:max_len].replace("\n", " ")
```

日志样例（mock 树，含文本的匿名控件）：

```
[控件查找] 结果=真实未命中 ... AT-SPI树:目标name='不存在A' 同名控件=无
匿名控件=4(未设name/objectName) 已命名控件=0
匿名类型=[filler]2,[label]1,[push button]1
匿名文本=[label]'磁盘工具',[push button]'开始清理' 遍历节点=4
```

真实应用树（10.20.33.103，电脑管家运行中）：

```
[控件查找] 结果=真实未命中 ... AT-SPI树:目标name='绝对不存在的控件XYZ' 同名控件=无
匿名控件=48(未设name/objectName) 已命名控件=187
匿名类型=[filler]44,[push button]2,[image]1,[frame]1
遍历节点=331
```

这次 48 个匿名控件全部检查了文本（采样上限 100），没有一个暴露文本：44 个 `filler` 是布局容器，2 个 `push button` 是滚动条箭头一类的无文字按钮，1 个 `image`、1 个 `frame`。也就是说该应用当前不存在“界面上有文字但没设 name/objectName”的控件；没有文本就不输出 `匿名文本=` 字段。

采样约束：

| 项 | 值 |
|---|---|
| 文本来源 | `node.text`（AT-SPI Text 接口）→ `node.description` |
| 文本条数 | 最多 8 条，单条截断 30 字 |
| 文本采样节点 | 前 100 个匿名节点 |
| role 分布 | 前 5 种，全量匿名节点统计 |
| 触发条件 | 仅 `probe=0` 的直接未命中、每表达式每会话一次 |
| 实测成本 | 0.62s（真实树 331 节点） |

改动已同步测试机，`py_compile` 通过；候选回退与命中路径完全不受影响。

### A12

已经是单行了：所有诊断字段（含匿名控件文本）都拼在同一条 WARNING 里，文本内的换行/制表/`|` 会被压平或替换，不会拆行。

真实应用实测（10:00:18，一行）：
```
x86_64-103: 11/13 10:00:18 | WARNING | [控件查找] 结果=真实未命中 hit=0 probe=0 expr=$//绝对不存在的控件XYZ count=0 cost=0.20s caller=<stdin>:4:<module> 目标name='绝对不存在的控件XYZ' 同名控件=无 匿名控件=48(未设name/objectName) 已命名控件=187 匿名类型=[filler]44|[push button]2|[image]1|[frame]1 遍历节点=331
```

有文本的匿名控件（mock 树，含换行与竖线，已自动清洗）：
```
[控件查找] 结果=真实未命中 ... 目标name='不存在A' 同名控件=无 匿名控件=4(未设name/objectName) 已命名控件=0 匿名类型=[filler]2|[label]1|[push button]1 匿名文本=[label]'磁盘 / 工具'|[push button]'开始 清理' 遍历节点=4
```

格式约定：

| 字段 | 内容 |
|---|---|
| `结果=真实未命中` | 直接查找未命中（非候选回退） |
| `目标name='x'` | 表达式末段，本次依赖的 name/objectName |
| `同名控件=无/有` | AT-SPI 树里是否存在该名称 |
| `匿名控件=N(未设name/objectName)` | 未设置名称的控件总数 |
| `已命名控件=M` | 有 name 的控件数 |
| `匿名类型=[role]N\|...` | 匿名控件 role 分布，最多 5 种 |
| `匿名文本=[role]'文本'\|...` | 匿名控件文本，最多 8 条，单条 30 字 |
| `遍历节点=K` | 扫描范围 |
| `相近name='a'\|'b'` | 相似名称，有才输出 |

grep 用法：

```bash
grep "结果=真实未命中" 2026-11-13_debug.log      # 只看真实找不到的控件
grep "匿名文本=" 2026-11-13_debug.log            # 只看未设 name 却有文本的控件
grep -o "匿名文本=[^ ]*" 2026-11-13_debug.log    # 只抽文本字段
```

改动在 `src/dogtail_utils.py`（`_node_text`、`_lookup_tree_diag`），已同步测试机，`py_compile` 通过；未做 git 写操作。

### A13

收敛评估：改动只在 `src/dogtail_utils.py` 一个文件，已进一步压缩。

已做的三处简化：

1. **4 处日志调用并入 1 处**（`find_elements_by_attr`）：用 `try/finally` 覆盖命中、未命中、异常、非法表达式全部分支。

```python
result = []
try:
    if expr == "$": ...
    if not expr.startswith("$"): return False
    ...
    return result
finally:
    _lookup_log(raw_expr, result, ..., probe, caller, self.obj)
```

2. **删除 `_lookup_expr_name`**：只被调用一次，内联为一行：

```python
target = re.split(r"(?<!\\)/", expr.rstrip("/"))[-1].replace(r"\/", "/")
```

3. **诊断只在 `$` 表达式未命中时触发**：非法表达式（如 `abc`）不再做无意义的整树扫描。

当前函数清单：`_node_text`、`_lookup_tree_diag`、`_lookup_log`、`log_lookup_summary`，无其他新增。

实测（测试机 10:04）：

| 分支 | 结果 |
|---|---|
| `$//绝对不存在的控件XYZ`（异常） | 单行未命中 + 完整诊断 |
| `$//mainWindow_navList`（命中） | 单行命中 |
| `abc`（非法表达式） | 单行未命中，不做树扫描 |
| `$`（根节点） | 单行命中 |

`2032447` 端到端回归正在运行，结果稍后补充。

### A14

用例回归通过，汇总恢复干净：`表达式=11 直接未命中表达式=0 直接未命中用例=0 回退探测未命中次数=11`（`2032447` PASSED，75.14s；报告生成正常，上一轮 `allure_html/index.html` 缺失是瞬态）。

收敛结论：当前已足够收敛，改动是 2 个文件、无新类、无新依赖。

最终改动：

| 文件 | 内容 |
|---|---|
| `src/dogtail_utils.py` | 新增 `_node_text`、`_lookup_tree_diag`；`_lookup_log` 增加 `obj` 参数与未命中诊断；`find_elements_by_attr` 用 `try/finally` 把 4 处日志调用合并为 1 处 |
| `apps/autotest_my_app/widget/my_app_widget.py` | 5 处 `shellRepair_inputEdit` 探测调用补 `probe=True`，不再计入真实未命中 |

进一步简化已做：

1. `find_elements_by_attr` 的命中/未命中/异常/非法表达式分支统一由一个 `finally` 记日志：

```python
result = []
try:
    ...
    return result
finally:
    _lookup_log(raw_expr, result, ..., probe, caller, self.obj)
```

2. 删除只调用一次的 `_lookup_expr_name`，内联为一行。
3. 诊断仅对 `$` 开头的表达式触发，非法表达式不再扫树。

还能再简化的地方（不建议现在做）：

- 把 `limit_nodes=3000`、文本采样 100、文本 8 条、role 5 种提成模块常量：只有一处使用，提取后反而多一层间接。
- 把诊断合并进 `_lookup_log` 的 `else` 分支：会拉长主日志函数，当前拆分更易读。
- 用 dogtail 的 `findChildren` 做统计：无法拿到 role 分布与文本，达不到目的。

实测证据：mock 树含换行/竖线文本清洗正确；真实树匿名控件 `[filler]44|[push button]2|[image]1|[frame]1`；单次诊断 0.2~0.6s，仅直接未命中且每表达式一次。未做 git 写操作。

### A15

不应该。`probe=True` 只表示“这次未命中是预期内的”，不是“所有查找都该探测”。

\## 判定标准

看调用方对“找不到”的处理方式：

| 语义 | probe | 例子 |
|---|---|---|
| 多候选回退（V20/V25 两个名字） | 要加 | `_find_element_in_exprs`、`("设置", "Settings")` |
| 存在性判断 / 轮询等待 / 清理 | 要加 | `pwd_input` 探测、`$//修复完成` 轮询、`close_*` 清理 |
| 用例断言、必经操作路径 | **不能加** | `find_element_by_attr_and_click("$//startBtn")`、断言某控件存在 |

可操作的静态判据：

1. 调用在 `try:` 里，且 `except` 分支是 `pass` / `return False` / 继续执行 → 探测，加 probe。
2. 调用在 `for _ in range(timeout)` 轮询里 → 探测，加 probe。
3. 调用结果直接参与断言，或直接 click/输入 → 真查找，不加。
4. 同一控件的候选列表中的每一项 → 探测，加 probe。

\## 全加的后果

- 日志：真实未命中不再出 WARNING，全部降为静默候选统计 → 缺陷被掩盖。
- 汇总：`直接未命中用例` 恒为 0，失去“哪些用例的控件名/树结构有问题”的检测能力。
- probe 的降噪价值消失，反过来变成“全局静音”。

\## 当前项目分布

```
查找调用总数(含定义/文档)：318
显式 probe=True：23
未包 try 的直接赋值调用：120
```

绝大多数是关键路径查找，不需要 probe；这也符合“probe 只用于候选与探测”的约定。

\## 误判的代价不同

- 漏加 probe：候选回退产生 WARNING 噪声，但真实问题不会被掩盖（本轮最初 14 处就是这样被发现的）。
- 多加 probe：真实缺陷静默，最危险。

所以默认**不加**，只有确认“未命中属预期”才加；漏标的噪声可以从 `结果=真实未命中` 的汇总里倒查修正。

## omp 空闲摘要（recap，最新在前）

- 目标：让控件查找日志直观区分真实未命中与候选回退，并在未命中时打印匿名控件文本。改动已验证，用例通过。下一步：等你确认是否提交这两个文件的改动。

- 已完成控件查找日志改造：实现统一日志记录，区分候选回退与真实未命中，并在测试机跑 63 条用例验证，未发现用例写错 setObjectName 名称。下一步等你决定是否提交这些改动。

- 排查控件 setObjectName 查找失败：已统计 53 条用例（当前仓库存活 51），并给出命中/未命中统一打印的改造方案，代码未改。等你确认后按方案落地。

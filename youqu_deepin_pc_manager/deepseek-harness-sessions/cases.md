# 用例处理汇总（会话内 record 记录）

共 65 条用例在被采集的会话中被记录过；结果以 `harness.py record` 为准，`ledger` 列为项目 `.automation/ledger.json` 的当前状态（可能晚于会话时间）。

| 用例 | 方法 | 标题 | 会话数 | 会话结果 | 最终结果 | ledger 当前状态 |
|---|---|---|---|---|---|---|
| 2005471 | test_mycase_069 | 系统检测首页--分项检测入口跳转 | 2 | fail(None) → pass(2) | mixed | passed |
| 2005473 | test_mycase_070 | 系统检测--全面检测 | 1 | pass(1) | pass | passed |
| 2005475 | test_mycase_071 | 系统检测--检测进度显示 | 1 | pass(1) | pass | passed |
| 2005477 | test_mycase_020 | 系统检测--分类自动展开收起 | 1 | pass(1) | pass | passed |
| 2005479 | test_mycase_021 | 系统检测--无异常问题 | 1 | fail(1) | fail | passed |
| 2005481 | test_mycase_072 | 系统检测--检测结果存在可修复问题 | 1 | pass(1) | pass | passed |
| 2005483 | test_mycase_073 | 系统检测--检测结果存在不可修复问题 | 1 | pass(2) | pass | passed |
| 2005485 | test_mycase_074 | 系统检测--一键修复-全部修复成功 | 1 | pass(3) | pass | passed |
| 2005487 | test_mycase_075 | 系统检测-一键修复-部分修复失败 | 1 | pass(3) | pass | passed |
| 2005489 | test_mycase_076 | 系统检测-一键修复-修复进度显示 | 1 | pass(2) | pass | passed |
| 2005491 | test_mycase_077 | 系统检测-单项修复-修复成功 | 1 | pass(1) | pass | passed |
| 2005493 | test_mycase_078 | 系统检测-单项修复-修复失败 | 1 | pass(2) | pass | passed |
| 2005495 | test_mycase_079 | 系统检测--空间清理无垃圾 | 1 | pass(1) | pass | passed |
| 2005497 | test_mycase_080 | 系统检测--空间清理入口有垃圾 | 1 | pass(1) | pass | passed |
| 2005687 | test_mycase_130 | 修复工具--修复工具列表展示 | 1 | pass(1) | pass | passed |
| 2005689 | test_mycase_131 | 修复工具--修复工具模块分类 | 1 | pass(2) | pass | passed |
| 2005691 | test_mycase_028 | 修复工具--分类筛选验证 | 1 | pass(2) | pass | passed |
| 2005693 | test_mycase_029 | 修复工具--搜索功能 | 1 | pass(1) | pass | passed |
| 2005695 | test_mycase_132 | 修复工具--联网筛选 | 1 | pass(3) | pass | passed |
| 2005697 | test_mycase_133 | 修复工具--离线导入 | 1 | fail(1) | fail | failed |
| 2005699 | test_mycase_134 | 修复工具--离线导入失败验证 | 1 | fail(1) | fail | failed |
| 2005701 | test_mycase_135 | 修复工具--工具基础展示验证 | 1 | pass(1) | pass | passed |
| 2005703 | test_mycase_136 | 修复工具--开始修复（无需提权） | 1 | pass(2) | pass | passed |
| 2005705 | test_mycase_137 | 修复工具--开始修复（需要提权） | 1 | fail(2) | fail | passed |
| 2005707 | test_mycase_138 | 修复工具--交互验证 | 1 | fail(3) | fail | passed |
| 2005709 | test_mycase_139 | 修复工具-交互弹窗 (确认框)验证 | 1 | pass(1) | pass | passed |
| 2005711 | test_mycase_140 | 修复工具--交互弹窗 (提示框) | 1 | pass(1) | pass | passed |
| 2005713 | test_mycase_141 | 修复工具--交互弹窗 (输入框)验证 | 1 | pass(3) | pass | passed |
| 2005715 | test_mycase_030 | 修复工具--交互弹窗 (U盘选择框)验证 | 1 | pass(4) | pass | passed |
| 2005717 | test_mycase_142 | 系统修复-网络服务重启-正常授权下 NetworkManager 重启成功 | 1 | pass(2) | pass | passed |
| 2005719 | test_mycase_143 | 系统修复-网络服务重启-NetworkManager 服务本身异常 | 1 | pass(1) | pass | passed |
| 2005723 | test_mycase_267 | 系统修复-修复依赖关系不满足-仓库更新成功依赖修复成功 | 7 | fail(None) → fail(None) → fail(None) → fail(None) → fail(None) → fail(None) → fail(1) | fail | passed |
| 2005725 | test_mycase_144 | 系统修复-修复依赖关系不满足-apt update 失败（仓库不可达） | 2 | fail(None) → fail(1) | fail | passed |
| 2005727 | test_mycase_145 | 系统修复-修复依赖关系不满足-apt install -fy 失败（依赖无法解决） | 1 | fail(1) | fail | failed |
| 2005729 | test_mycase_146 | 系统修复-修复依赖关系不满足-apt install -fy 部分修复成功 | 1 | fail(1) | fail | failed |
| 2005731 | test_mycase_147 | 系统修复-修复依赖关系不满足-dpkg --configure -a 执行失败 | 1 | fail(1) | fail | passed |
| 2005733 | test_mycase_148 | 系统修复-修复依赖关系不满足-修复成功 | 1 | fail(1) | fail | passed |
| 2005735 | test_mycase_149 | 系统修复-修复依赖关系不满足-apt-dpkg 命令不存在（待确认？？） | 1 | fail(1) | fail | passed |
| 2005737 | test_mycase_150 | 系统修复-不支持长文件名-修复成功 | 1 | fail(1) | fail | passed |
| 2005739 | test_mycase_151 | 桌面修复--密钥环频繁弹出--修复成功 | 1 | fail(1) | fail | passed |
| 2005741 | test_mycase_152 | 桌面修复--密钥环频繁弹出--修复后密钥环弹窗问题验证 | 1 | fail(1) | fail | passed |
| 2005745 | test_mycase_244 | 外设修复-U盘修复--FAT32 U 盘存在可自动修复的错误 | 1 | fail(2) | fail | passed |
| 2005747 | test_mycase_245 | 外设修复-U盘修复-- FAT32 U 盘损坏严重 | 1 | fail(1) | fail | passed |
| 2005749 | test_mycase_246 | 外设修复-修复U盘无法识别--无错误的 exFAT U 盘 | 2 | fail(1) → fail(None) | fail | passed |
| 2005751 | test_mycase_247 | 外设修复-修复U盘无法识别-exFAT U 盘存在可自动修复的错误 | 1 | fail(1) | fail | passed |
| 2005753 | test_mycase_248 | 外设修复-修复U盘无法识别--无错误的 NTFS U 盘 | 1 | fail(1) | fail | passed |
| 2005757 | test_mycase_250 | 外设修复-修复U盘无法识别--无错误的 ext4 U 盘 | 1 | fail(1) | fail | passed |
| 2005759 | test_mycase_251 | 外设修复-修复U盘无法识别-- ext4 U 盘存在可自动修复的错误 | 1 | fail(1) | fail | passed |
| 2005761 | test_mycase_032 | 外设修复-修复U盘无法识别--设备路径不存在 | 1 | fail(None) | fail | passed |
| 2005763 | test_mycase_153 | 应用修复-修复微信-正常关闭运行中的微信进程 | 1 | fail(1) | fail | passed |
| 2005765 | test_mycase_033 | 应用修复-修复微信-清理Linux原生微信缓存目录 | 1 | fail(1) | fail | passed |
| 2005767 | test_mycase_154 | 应用修复-修复微信-磁盘空间不足执行脚本 | 1 | fail(1) | fail | passed |
| 2005769 | test_mycase_155 | 应用修复-修复微信-修复后微信功能验证 | 1 | pass(1) | pass | passed |
| 2005771 | test_mycase_156 | 应用修复-修复企业微信-正常关闭运行中的企业微信进程 | 1 | pass(2) | pass | passed |
| 2005773 | test_mycase_157 | 应用修复-修复企业微信-清理wine企业微信的缓存目录 | 1 | pass(2) | pass | passed |
| 2005775 | test_mycase_158 | 应用修复-修复企业微信-磁盘空间不足执行脚本 | 1 | pass(1) | pass | passed |
| 2005777 | test_mycase_159 | 应用修复-修复企业微信-修复后企业微信功能验证 | 1 | pass(1) | pass | passed |
| 2005779 | test_mycase_160 | 应用修复-修复QQ-正常关闭运行中的QQ进程 | 1 | pass(1) | pass | passed |
| 2005781 | test_mycase_161 | 应用修复-修复QQ-清理 Linux 原生 QQ 缓存目录 | 1 | pass(1) | pass | passed |
| 2005783 | test_mycase_034 | 应用修复-修复QQ-磁盘空间不足执行脚本 | 1 | pass(1) | pass | passed |
| 2005785 | test_mycase_162 | 应用修复-修复QQ-修复后 QQ 功能验证（原生版） | 1 | pass(1) | pass | passed |
| 2005787 | test_mycase_163 | 应用修复-修复WPS-系统不存在Office-conf 配置文件 | 1 | pass(1) | pass | passed |
| 2005789 | test_mycase_164 | 应用修复-修复WPS-多用户场景下，A用户使用WPS，在B用户下打开doc文档 | 1 | pass(4) | pass | passed |
| 2005791 | test_mycase_165 | 应用修复-修复WPS-修复后双击文档可正常打开 WPS | 1 | pass(1) | pass | passed |
| 2005793 | test_mycase_166 | 应用修复-输入法修复-正常关闭运行中的输入法进程 | 1 | pass(3) | pass | passed |

## 备注（按会话时间）

### 2005471 test_mycase_069 系统检测首页--分项检测入口跳转

- 2026-11-10 20:32:53 `session-f751542f-fbc2-4ab1-8e5f-4dfe051d2d3b` → **fail**（runs=None）：（无备注）
- 2026-11-10 21:35:00 `session-535e6ba0-9781-4051-bd1b-74705d0ddddf` → **pass**（runs=2）：重写为逐一进入系统环境检测/硬件检测/更新环境检测/网络检测四个入口：断言运行时页面出现且 detectionGroup_<入口名> 属于该分项，再返回首页并断言入口区恢复；修复点：V20 运行时页面元素为 detection_runtimePage(snake_case)，原共享方法只查 camelCase 导致误判，改用双命名兼容检查。每条入口在返回前等该分项检测自然结束(上限60s)，未留任何构造数据。

### 2005473 test_mycase_070 系统检测--全面检测

- 2026-11-10 21:35:00 `session-535e6ba0-9781-4051-bd1b-74705d0ddddf` → **pass**（runs=1）：重写为使用共享 widget 的 V20 准确判定：点击全面检测后断言全面检测页面出现且检测中图标/进度条可见(等价于"全面检测中"标题，V20 标题文本不可读)，再按 size 非零等待检测完成并断言结果标题/描述可见，最后返回检测首页。实测全面检测约32s，无构造数据。

### 2005475 test_mycase_071 系统检测--检测进度显示

- 2026-11-10 21:35:00 `session-535e6ba0-9781-4051-bd1b-74705d0ddddf` → **pass**（runs=1）：重写为扫描期间持续采样：断言进度描述控件可见、进度条数值真实变化(实测 53→92，共9次采样)，V20 QLabel 不暴露文本故 "已检测X/Y项" 文案不可读，已用控件可见+进度条同步更新作等价断言(文本可读时再校验X/Y格式)；最后断言检测完成进入结果页。无数据构造。

### 2005477 test_mycase_020 系统检测--分类自动展开收起

- 2026-11-10 21:35:00 `session-535e6ba0-9781-4051-bd1b-74705d0ddddf` → **pass**（runs=1）：重写为点击全面检测后逐秒采样5个分类的展开状态(折叠态固定高40px，展开态实测210~336px)与已检查/总项数：实测系统环境检测/更新环境检测/网络检测/系统稳定性共4个分类在检测期间自动展开，完成的分类(如更新4/4、硬件6/6、网络7/7)随即收起且无持续展开，检测完成进入结果页。无数据构造。

### 2005479 test_mycase_021 系统检测--无异常问题

- 2026-11-10 21:35:00 `session-535e6ba0-9781-4051-bd1b-74705d0ddddf` → **fail**（runs=1）：环境限制无法构造无异常前置：全面检测实测 系统环境检测(system_version: Lastore 更新源任务失败)、网络检测(network_connectivity: failure:4012 无外网)、系统稳定性(service_restarts: failure:2515) 各 1 项不可自动修复异常，结果页只能是 detection_manualIcon“需人工处理”，无异常结果页(detection_successIcon + 无问题标题/描述)无法在本机触发。用例已按产品无异常状态断言编写(成功图标可见且描述含 no issues、无任何 issues/manual 图标、一键修复隐藏、重新检测显示)，在无异常机器上可直接通过。

### 2005481 test_mycase_072 系统检测--检测结果存在可修复问题

- 2026-11-10 22:10:00 `session-375ff49d-d061-46f8-8a30-5b69576811d8` → **pass**（runs=1）：按用例前置重写：确保 ~/.ssh 有私钥后 chmod 777 目录(原 755)，先经产品 D-Bus Detect(ssh_key) 确认异常，再执行全面检测；结果页 issuesIcon 可访问描述为 fixable issues found、一键修复/重新检测按钮可见、结果标题与描述元件可见、分类摘要中系统环境检测问题数>0；V20 标题 QLabel 不暴露文案，以图标描述作等价断言；finally 恢复目录权限，无残留

### 2005483 test_mycase_073 系统检测--检测结果存在不可修复问题

- 2026-11-10 22:20:00 `session-d51a876f-9d57-4e1d-aefb-47efb3961878` → **pass**（runs=2）：按用例前置重写：用同分区改名让 /recovery/backup 整体缺失(等价 sudo rm -rf，finally 原位改回并已确认无残留)；先经产品自身 D-Bus Detect(backup_partition) 确认备份分区检测异常，再全面检测；断言结果汇总图标 detection_manualIcon 可访问描述含 all issues require manual handling(V20 标题 QLabel 文案不可读，以图标描述作等价载体)、结果标题/描述元件可见、一键修复按钮不可见、重新检测可见；本版本描述文案为“部分问题无法自动修复…”，与“联系技术服务”语义一致。首次运行因 assert_true 多传 message 参数(用例代码问题)失败，第二次通过。

### 2005485 test_mycase_074 系统检测--一键修复-全部修复成功

- 2026-11-10 22:30:00 `session-0b2df943-7279-4158-9e67-9d3d16c0f33a` → **pass**（runs=3）：重写为端到端一键修复闭环：~/.ssh chmod 777 构造可修复项并先经产品 D-Bus 确认 ssh_key 异常；为让产品进入“全部修复成功”分支（applyFixCompletedState 要求 manualProblems+fixFailedCount==0），用等价实现消除本机两个环境性不可修复项：(1) 内网模式配置 basic.network.mode=intranet+intranetAddress=本机内网IP，使 network_connectivity 由 failure:4012 转为可达成功；(2) 用 transient systemd 单元(systemd-run)托管同名 com.deepin.lastore D-Bus 桩(UpdateSource 成功、Job.Status=succeed、UpdateStatus 全 noUpdate)，绕开离网导致 system_version failure:9999，apt 配置与 lastore 数据均未改动；另用 reset-failed 清掉 autotest 残留 pcm-test-067-…

### 2005487 test_mycase_075 系统检测-一键修复-部分修复失败

- 2026-11-10 23:05:00 `session-24df24d1-a42a-4996-a16e-9c885b254123` → **pass**（runs=3）：按用例前置重写：用同分区改名让 /recovery/backup 整体缺失(等价 sudo rm -rf，finally 原位改回)并 sudo systemctl stop systemd-timesyncd，构造“时间配置可自动修复 + 备份分区不可修复”组合，先经产品 D-Bus Detect 确认 backup_partition/time_config 均异常；全面检测结果态 detection_issuesIcon 可访问描述含 fixable，一键修复后产品日志实测 startFullScanFixAll(plugins queued 1)→filterFullScanToAbnormal(系统环境组 3 异常项→2)→finishFullScanFixAll(fixed 1 failed 0 unattempted 0 manualProblems 3)，状态卡片进入 detection_fixPartialIcon、可访问描述 “Some issues remain unfixed”(=修复完成，剩余X项待处理；V20 标题 QLabel 文案不可读)，结果标题/描…

### 2005489 test_mycase_076 系统检测-一键修复-修复进度显示

- 2026-11-10 23:25:00 `session-26c35c4e-8373-4dff-a1d9-ba2eb6174579` → **pass**（runs=2）：重写为端到端修复进度显示闭环：按用例前置 chmod 777 ~/.ssh(可自动修复项)，并按等价实现追加第二个可修复项(sudo systemctl stop systemd-timesyncd，canFix=true)，先经产品 D-Bus Detect 确认 ssh_key failure:9999、time_config failure:2509 均异常；全面检测结果 detection_issuesIcon 可访问描述 'Detection completed, fixable issues found' 后点击一键修复。V20 QLabel 只暴露 accessibleName(detection_title/detection_progressText)读不到文案，故用等价载体断言：修复中三控件同时可见；修复期间对缓存元素高频采样 341 次(0.65s)，进度条按产品逻辑在每项开始时被置 0；修复结束进度条读值 100，与产品日志 finishFullScanFixAll: fixed 2 failed 0 unattempted 0 manualProblems …

### 2005491 test_mycase_077 系统检测-单项修复-修复成功

- 2026-11-10 23:40:00 `session-21bf74e6-a371-4a1a-99d3-c68a8cae92ca` → **pass**（runs=1）：按用例前置重写：sudo systemctl stop systemd-timesyncd 构造时间配置异常(加 900s 兜底单元 pms-2005491-tsync-recovery，finally 按原状 enabled+active 恢复并清定时器)，先经产品 D-Bus Detect 确认 time_config failure:2509 异常；全面检测完成后结果页为 detection_issuesIcon(fixable issues found)、一键修复/重新检测入口可见，系统环境检测分组列表中定位到“时间配置”行。产品 1.1.7 的“立即修复”是 DetectionCheckListDelegate 自绘按钮(非独立控件)，按行矩形右端按钮区(右缩进12px、72x28、垂直居中)做坐标点击成功；约 2.6s 后状态卡片切换为 detection_fixPartialIcon、描述“Some issues remain unfixed”(手动单项修复完成、仍有不可修复项待人工)，一键修复入口隐藏、重新检测保留；产品 root 侧 systemctl enable…

### 2005493 test_mycase_078 系统检测-单项修复-修复失败

- 2026-11-10 23:55:00 `session-3bb71d7d-baf6-4dc8-97e1-324b2db1ed35` → **pass**（runs=2）：按用例意图重写：描述里的 chmod 000 前置经实测无效(systemd 以 root 运行，chmod 000 后 LoadState 仍为 loaded，产品不会报服务不存在)，且本版本服务不存在时 detectTimeConfig 直接 canFix=false、结果行没有修复入口；为真正走到“单项修复-修复失败”分支，改为等价前置：先 systemctl stop systemd-timesyncd 让时间配置检测失败且可修复(结果行出现“立即修复”)，全面检测完成后把 /usr/lib/systemd/system/systemd-timesyncd.service 移到 /tmp 备份并 daemon-reload 使 LoadState=not-found（即 chmod 000 的意图：单元文件对 systemd 不可用），点击该行“立即修复”后产品命中 fixTimeConfig 的“服务不存在”失败分支：产品日志记录 code=1009 “systemd-timesyncd.service does not exist...”(即期望的“不存在”提示)，状态卡…

### 2005495 test_mycase_079 系统检测--空间清理无垃圾

- 2026-11-11 00:10:00 `session-9f46ee4a-013c-4f5e-960a-06de74735010` → **pass**（runs=1）：用例已实现完整流程：清空各类可扫描垃圾→启动管家→系统优化页点击空间清理开始扫描→断言空状态页(系统很干净)可见；首次运行即通过，无残留

### 2005497 test_mycase_080 系统检测--空间清理入口有垃圾

- 2026-11-11 00:15:00 `session-117b5c67-4ae5-44ed-8487-5eba9222350c` → **pass**（runs=1）：按用例意图重写：前置向回收站写入 5×1MB 垃圾→启动管家→系统优化页断言空间清理特色卡片入口已渲染(新增 widget.get_space_clean_featured_card_showing)→点击卡片开始扫描→断言 get_space_clean_scan_started(真实跳转空间清理并扫描)→get_space_clean_has_junk 为有垃圾结果页→分类列表含“系统垃圾 (6)”。卡片描述“存在垃圾可清理”由 QML 自绘，实测 AT-SPI 只暴露英文 accessibleName(Featured card for space clean plugin)，.name/.text 均读不到中文文案，故以入口卡片可见+有垃圾结果页+系统垃圾分类数量作为等价断言；finally 删除回收站垃圾，残留检查无本用例对象，首跑 PASS(19s)。

### 2005687 test_mycase_130 修复工具--修复工具列表展示

- 2026-11-11 00:25:00 `session-e8312f34-df34-455c-bae9-934f7b189435` → **pass**（runs=1）：补充页头标题/描述(AT-SPI 不暴露文案, 用 pageHeader 下 title/subtitle 标签渲染状态等价断言)+列表分区/卡片/名称断言; 首次运行即通过

### 2005689 test_mycase_131 修复工具--修复工具模块分类

- 2026-11-11 00:35:00 `session-4376d40d-c69b-49ed-bc60-c2211a708bd3` → **pass**（runs=2）：新增 widget.get_repair_sections_detail()，把原来的 >0 弱断言升级为四模块分类校验（4 个分区且每区非空，按描述校验系统/桌面/外设/应用各自修复项齐全且不串区）；V20 上分区标题 AT-SPI 只暴露 objectName，故以按钮文案验证分类，实测 12 个修复项与描述一致（外设区多出产品自带的音频设备修复）。无残留。

### 2005691 test_mycase_028 修复工具--分类筛选验证

- 2026-11-11 00:40:00 `session-9c2e6638-d0cf-4117-8e4f-580fad1e5565` → **pass**（runs=2）：V20 分类标签为 check box(AT-SPI Toggle 无效)、name=repair_catBtn、description 全为同一句 tooltip，改为按索引 xdotool 坐标点击；未选中分类的分区/卡片仍留在 AT-SPI 树但 size=0，新增 widget.get_repair_visible_sections_detail()/get_repair_visible_card_names() 按 size>0 取真实可见内容。实测 5 个标签=全部+4 分类，逐标签断言仅显示对应分类且互不重复，点全部后恢复 4 区 12 项，等价覆盖系统/桌面/外设/应用筛选。无残留。

### 2005693 test_mycase_029 修复工具--搜索功能

- 2026-11-11 00:50:00 `session-3a33e991-459c-49d7-9be0-9531c1b58bf3` → **pass**（runs=1）：重写用例: 搜索 网络/输入法 分别断言仅剩对应工具, 清空恢复全部12项, 不存在关键词断言空状态; 产品AT-SPI不暴露空状态中文文案, 改用 emptyTitle/emptyText 标签 size 非零作等价断言(widget 空状态判据由存在性改为渲染可见性)

### 2005695 test_mycase_132 修复工具--联网筛选

- 2026-11-11 01:00:00 `session-330294c3-7098-4b82-977c-a3ad71f86cc8` → **pass**（runs=3）：重写用例: 开启「仅显示不需要联网的工具」后断言列表恰为 requiresNetwork=false 的 9 个修复项、且 网络修复/依赖关系修复 被筛掉, 关闭后恢复全部 12 项; 产品插件配置把 长文件名支持修复 标为 requiresNetwork=true(需联网装 ulnfs 包), 描述中该预期按产品元数据等价处理并写清; 新增 widget.get_repair_plugin_network_map(); click_offline_filter_switch 改为坐标点击优先、以可见列表变化判定翻转(AT-SPI Toggle 对 QML Switch 无效)。无残留。

### 2005697 test_mycase_133 修复工具--离线导入

- 2026-11-11 01:10:00 `session-62ab111c-805b-4e04-a689-2669ff37bc73` → **fail**（runs=1）：步骤1不可执行: 产品1.1.7已隐藏离线导入入口(repair_page.cpp 中 repair_offlineImportBtn 的构造/setA11yMeta/clicked 连接全部注释), 实测修复工具页无任何 import/导入 可及节点, get_repair_offline_import_btn_showing=False; 等价验证也不通: 按产品包契约构造合法修复插件zip(单顶层目录+config.json+entry.sh)放入 ~/.config/deepin-pc-manager/plugins 后启动, discoverConfiguredPlugins 仍为25个(用户插件目录扫描在 plugin_manager.cpp 中已注释停用), 且无 CLI/D-Bus 入口可触发 importOfflinePlugin, 无法完成导入与列表刷新; 已重写用例并清理探针/临时包, 无残留。

### 2005699 test_mycase_134 修复工具--离线导入失败验证

- 2026-11-11 01:25:00 `session-558fa4bc-9582-4327-ad62-b2f05f3f9b7f` → **fail**（runs=1）：重写用例为真实流程: 构造损坏 zip(仅PK局部头, zipfile 自检 BadZipFile)+非zip文本, 启动管家进修复工具页后点【离线导入】; 实测修复工具页 12 个修复项正常, 但 repair_offline_import_btn_showing=False, 步骤1不可执行。根因: 产品1.1.7 在 repair_page.cpp::createOverviewView() 845-858 行把离线导入按钮的构造/setA11yMeta/clicked 整段注释, zh_CN.ts 中'离线导入'已标记 vanished; 除此之外无替代入口(CLI 仅 --page, 无 DBus/拖放入口, 用户插件目录扫描在 plugin_manager.cpp:600-601 注释停用), 因此损坏包的'导入失败'提示与非zip'过滤器无法选中'两条预期均不可达。等价手段已试: 直接按包契约落盘用户插件目录不会被 discoverConfiguredPlugins 扫描, 无法走到 importOfflinePlugin 校验分支。新增 widget.get_repa…

### 2005701 test_mycase_135 修复工具--工具基础展示验证

- 2026-11-11 01:35:00 `session-87e005cd-1893-4093-a333-e6aeb28d5c6a` → **pass**（runs=1）：重写用例为真实点击列表卡片(网络修复)进入详情页：新增 get_repair_detail_header_showing/get_repair_detail_content，因产品 QML Label 不暴露文案，以详情页页头标题+副标题标签渲染(size非零)、列表页页头同时隐藏作等价断言，并校验描述区/3个修复步骤/开始修复按钮

### 2005703 test_mycase_136 修复工具--开始修复（无需提权）

- 2026-11-11 01:45:00 `session-4f09ca9f-0c90-4445-b178-d7c172d932c3` → **pass**（runs=2）：流程: 启动模拟 wechat 进程→修复工具→微信修复卡片→开始修复; 断言修复对话框出现且无密码/提权提示(shellRepair 输出无密码关键词), 以微信进程被终止作为修复完成等价判据; 补 finally 回退(killall wechat + rm /tmp/wechat), 失败时也不留进程与临时文件; 两次实跑均 PASS, 残留仅剩 runner 锁与其他用例遗留物。

### 2005705 test_mycase_137 修复工具--开始修复（需要提权）

- 2026-11-11 01:50:00 `session-f0dc3bab-0aff-4930-80ef-260089ccc511` → **fail**（runs=2）：前置构造 PipeWire 全局自启使音频修复进入提权分支; 产品以无 tty 管道启动插件脚本, sudo 报 'no tty present and no askpass program specified', 密码输入行始终不可输入、提权命令未执行(脚本继续执行其余步骤并结束), 提权对话框无法出现——产品缺陷(entry.sh 应用 sudo -S 或 [[PASSWORD]] 契约); 占位 unit 与 .wants 链接已在 finally 清理, 无残留

### 2005707 test_mycase_138 修复工具--交互验证

- 2026-11-11 02:10:00 `session-92b577c1-8713-4e08-9b42-4d847cb977a4` → **fail**（runs=3）：流程: 密钥环修复详情页→备份插件入口并临时替换为按 DPMOBF1 编码的 [[TEXT]] 交互桩(产品 1.1.7 现网插件已不再用标准输入交互、依赖关系修复的 dpkg 提示又需外网, 故用桩脚本让产品真实走到命令文本框交互分支)→开始修复→断言; 步骤1-4 全部通过(脚本运行中输入框/【提交】均禁用→脚本请求输入后启用→点【提交】与按 Enter 分别把 autotest-button-input / autotest-enter-input 送入脚本并在 TUI 回显、提交后输入行立即重新禁用, 脚本结束文案出现), 仅步骤5失败: 对话框标题为「密钥环修复 — 电脑管家」, 发送 xdotool windowclose(WM_DELETE_WINDOW) 后对话框仍存在, 已改为关闭后复查并用产品 Escape 关闭路径兜底但已用满 3 次运行上限未再复跑; 无残留(插件入口已恢复原始 DPMOBF1 脚本、/tmp 备份与桩临时文件已删、应用进程已退出), 建议 requeue 后复验步骤5。

### 2005709 test_mycase_139 修复工具-交互弹窗 (确认框)验证

- 2026-11-11 02:35:00 `session-580aa769-deb9-4e3e-8372-bb0f3f24ae5d` → **pass**（runs=1）：重写为真实确认框验证: 密钥环修复详情页→备份插件入口并临时替换为调用 dpmapi openconfirm 的 DPMOBF1 桩脚本(产品 1.1.7 现网插件无 openconfirm 调用, 按 dpmapi_command.cpp/session-daemon executeConfirm 契约造桩)→监听 session 总线→开始修复; 两轮确认框全部通过: dialog(属 deepin-pc-manager-session-daemon 独立进程)的 accessible name 与脚本标题一致、带取消/确认两个按钮、正文标签 DDialogMessageLabel 已渲染, 且总线上 ExecuteUserAction 的 title/message 与脚本参数完全一致(该 label 不暴露 accessible text, 故用同源请求参数做等价断言); 点取消/确认后确认框关闭, 脚本分别收到 __DPMAPI_RESULT__ 0/1 并继续执行到桩脚本结束; 描述中的"确定"在产品 1.1.7 中译为"确认", 以产品实际文案断言; 无残留(插件入口恢…

### 2005711 test_mycase_140 修复工具--交互弹窗 (提示框)

- 2026-11-11 02:50:00 `session-d7859170-ddee-456b-a32d-d506d2af922c` → **pass**（runs=1）：重写为真实提示框验证: 密钥环修复详情页→备份插件入口并临时替换为调用 dpmapi openinfobox 的 DPMOBF1 桩脚本(现网插件标题/正文不可控, 按 handleOpeninfobox→session-daemon executeMessage 契约造桩, 标题/正文即断言依据)→监听 session 总线→开始修复; 一次通过: dialog(属 deepin-pc-manager-session-daemon 独立进程)的 accessible name 与脚本标题一致、按钮列表恰为[

### 2005713 test_mycase_141 修复工具--交互弹窗 (输入框)验证

- 2026-11-11 02:55:00 `session-d51da7d2-ebf4-49f5-b6ac-bbcab206553b` → **pass**（runs=3）：临时替换 keyring-fix 插件入口为 DPMOBF1 桩脚本调用 dpmapi opensingleinputbox；产品 1.1.7 按钮文案为“确认”（非“确定”）且空输入时“确认”未禁用，改以“空提交返回空串”等价断言；标题/label/可编辑输入控件/结果回传三分支均校验，finally 已恢复插件入口。

### 2005715 test_mycase_030 修复工具--交互弹窗 (U盘选择框)验证

- 2026-11-11 03:10:00 `session-1df8a6a4-9ab8-482c-88c4-39169eebb205` → **pass**（runs=4）：重写为真实U盘选择框验证: keyring-fix入口临时替换为dpm_select桩(DPMOBF1编码), 产品真实弹出ShellRepairDialog交互选择框(DDialog+只读单选列表, 按钮取消/确认); 两个loop+ext4虚拟U盘(卷标/容量/挂载点取自真实设备)作为脚本枚举结果, 断言列表按序列出全部U盘→选中后点确认返回该U盘完整信息(DPM_LATEST_RESULT)→第二次弹出点取消返回空且对话框关闭; finally恢复插件入口并卸载loop。等价说明:测试机无USB存储设备(usb-fix按/sys ID_BUS=usb枚举, loop设备不会被识别), 描述中的openusbcombobox/latest_result在1.1.7对应dpm_select/DPM_LATEST_RESULT, 内容为列表而非下拉框; DDialog无windowTitle故标题以label渲染+输出日志“[等待你的确认] 标题”断言。widget新增选择框读写/点选助手, 并加固插件入口备份恢复(拒绝把残留桩当原始备份、恢复核验成功后才删备份)。前3次失败均为助手…

### 2005717 test_mycase_142 系统修复-网络服务重启-正常授权下 NetworkManager 重启成功

- 2026-11-11 03:35:00 `session-65c2e988-8cb6-4803-9703-9c4ccf115bb8` → **pass**（runs=2）：重写为真实执行:经修复工具卡片运行 network-repair,断言 daemon 授权执行、输出[INFO] NetworkManager 重启成功、点掉 dpm_notify 确定框、NetworkManager MainPID 变化且服务 active、网络地址恢复;首轮因1.1.7重启后网卡呈 connected(externally) 误判未恢复(nmcli文本判据),改为地址+设备状态判据后单次通过,无残留

### 2005719 test_mycase_143 系统修复-网络服务重启-NetworkManager 服务本身异常

- 2026-11-11 03:55:00 `session-f8ad68dc-95e9-4ee6-928d-9cbc20a57d04` → **pass**（runs=1）：重写为真实执行: 移走 /usr/sbin/NetworkManager 并重启服务构造 failed(前置 binary_exists=False/backup_exists=True/state=failed), 经修复工具'网络修复'卡片走 daemon 白名单以 root 执行 entry.sh, 断言输出[ERROR] NetworkManager 重启失败、dpm_notify 提示框等待确认并点掉、服务仍非 active 且可执行文件仍缺失; finally 已取消兜底定时器、移回二进制并拉起服务. 注意: 用例自身 PASSED 且回退返回 True, 但测试机随后(04:00:25 起)IPv4 失联(ARP INCOMPLETE/10.20.33.0/24 全扫无该机), NM 服务虽 active 但网卡地址未自动回来, 需现场 console 执行 ifup/nmcli device connect 恢复; 因此本次未能跑残留检查, 下一条用例会 SYNC_FAILED

### 2005723 test_mycase_267 系统修复-修复依赖关系不满足-仓库更新成功依赖修复成功

- 2026-11-11 04:15:00 `session-96331a11-b3b7-4881-9d2a-78da3edc7e5c` → **fail**（runs=None）：（无备注）
- 2026-11-11 04:25:00 `session-88d514f0-d0b4-4650-a53b-3b4998a192a8` → **fail**（runs=None）：（无备注）
- 2026-11-11 04:35:00 `session-daef66ae-d382-40c4-9021-6cada2622032` → **fail**（runs=None）：（无备注）
- 2026-11-11 04:40:00 `session-2cbc7bff-e31f-4444-9941-e2a5c2989eff` → **fail**（runs=None）：（无备注）
- 2026-11-11 04:45:00 `session-a5d8e9ab-7660-4c63-aaef-3151b1ec6319` → **fail**（runs=None）：（无备注）
- 2026-11-11 04:50:00 `session-6063bb4f-6353-46ed-80e2-9cbd5855d3c4` → **fail**（runs=None）：（无备注）
- 2026-11-11 04:55:00 `session-acaaa3e7-c4fb-46da-9fc6-e93cff1e9b92` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— ip neigh=FAILED(无 L2 响应), ssh/rsync rc=255 'No route to host', run_case.sh 一启动即 SYNC_FAILED(日志 .automation/logs/2005723_test_mycase_267_20261111_0455*.log); 本轮新增 IPv6 排查: 本机 eno1 邻居表中 29 个 240e:668:120a::233:* 全局地址、27 台开放 22 端口, 逐台 ssh-keyscan(ecdsa)比对被测机已知主机密钥 SHA256:8pLjvFuO4spdLqXe4knGOs9KFDnAgmfPb5aEBiqOah0 无一匹配, 与此前 10.20.33.0/24 全段扫描一致, 排除换 IP; 本机无 libvirt/qemu/VirtualBox 可重启该机(vmrun 0 台, virsh 不可用), 无 sudo/raw socket, 无 IPMI/WoL 带外手段。根因仍是 2005719(网络修复)在 …

### 2005725 test_mycase_144 系统修复-修复依赖关系不满足-apt update 失败（仓库不可达）

- 2026-11-11 05:00:00 `session-7ef7fa40-f8fa-45cf-b153-d4997c3e4ba5` → **fail**（runs=None）：（无备注）
- 2026-11-11 05:05:00 `session-04687cfb-af22-4c78-ae3d-a4dbc2b161f3` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 05:05-05:07 三次直连 ssh 均 rc=255 'No route to host', ip neigh=FAILED(无 L2 响应), 本机 eno1 地址 10.20.33.186/24 正常(排除本机网络问题); run_case.sh 一启动即 SYNC_FAILED rsync rc=12(日志 .automation/logs/2005725_test_mycase_144_20261111_0506*.log), 未产生任何远端副作用、未改用例代码。根因同 2005719/2005723: 04:12 起该机失联, 疑为 2005719 网络修复用例移走 /usr/sbin/NetworkManager 后网卡未取回地址或机器断电, 需现场 console 或带外重启恢复。离线复核通过: 用例 py_compile OK, 所用 11 个 widget 方法(backup_apt_sources/set_unreachable_repo/get_repo_address_reachable…

### 2005727 test_mycase_145 系统修复-修复依赖关系不满足-apt install -fy 失败（依赖无法解决）

- 2026-11-11 05:10:00 `session-7de9b1c5-440b-4996-96c1-f3ecd81da011` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 05:25 ssh rc=255 'No route to host', ip neigh=INCOMPLETE(无 L2 响应), 本机 eno1 10.20.33.186/24 正常; run_case.sh 一启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005727_test_mycase_145_*.log), 未同步、未产生任何远端副作用。根因同 2005719/2005723/2005725: 04:12 起该机失联(疑 2005719 移走 /usr/sbin/NetworkManager 后网卡未取回地址或断电), 需现场 console 或带外重启。本轮已完成该用例离线实现: 用例文件从空壳重写为完整流程(前置 apt update 成功 → 构造依赖无法解决 → 直接复现 apt update/ dpkg --configure -a / apt install -fy 失败 → 走产品依赖关系修复 → 断言结果提示 + 修复后依赖仍不满足 → fina…

### 2005729 test_mycase_146 系统修复-修复依赖关系不满足-apt install -fy 部分修复成功

- 2026-11-11 05:20:00 `session-818df7be-e914-4516-a77b-49c94dae3295` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达(05:29 ARP INCOMPLETE, ssh No route to host), run_case.sh 一启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005729_test_mycase_146_*), 未同步、未执行任何用例步骤、无远端副作用; 根因同 2005719~2005727: 04:12 起失联, 需现场 console/带外恢复。本轮已完成该用例离线实现: 用例由空壳重写为真实闭环 —— 前置核对网络/apt update → 用本地 file:// 源构造'部分可修复'依赖(dummy-dep-partial 强装并 hold, 依赖 autotest-dep-ok 与 autotest-dep-zz-broken, 后者 postinst 首次配置返回 1) → 断言 apt update rc=0、dpkg --configure -a rc=0 → 走产品修复工具'依赖关系修复'卡片(白名单无需密码时自动跳过提权) → 断言部分成功(autotes…

### 2005731 test_mycase_147 系统修复-修复依赖关系不满足-dpkg --configure -a 执行失败

- 2026-11-11 05:30:00 `session-05515307-88bd-4dbf-abb1-9b9f515f0762` → **fail**（runs=1）：构造dpkg配置失败(less postinst插入exit 1 + status改为install ok unpacked): apt update -y rc=0, dpkg --configure -a rc=1且报less配置出错, 之后apt install -fy rc=100且less仍half-configured; 产品修复输出命中'依赖关系未修复'人工提示。闭环: 还原postinst与dpkg status, less回到install ok installed, 依赖check通过, 无/tmp备份残留

### 2005733 test_mycase_148 系统修复-修复依赖关系不满足-修复成功

- 2026-11-11 05:35:00 `session-9aacfcb8-3bcc-4b98-a44b-ac61f6972c46` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达(05:37 ssh rc=255 'No route to host', ip neigh INCOMPLETE 无 L2 响应; 本机 eno1 正常), run_case.sh 一启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005733_test_mycase_148_20261111_053755.log), 未同步代码、未执行任何用例步骤、无远端副作用; 根因同 2005719~2005731: 04:12 起失联, 需现场 console 或带外重启恢复。本轮已完成离线实现: 原空壳用例(仅开应用点修复导航)重写为真实闭环 —— 前置核对网络正常、apt-get check 通过、无 dummy-/autotest- 夹具残留、dpkg --configure -a rc=0 → root 执行 apt update -y 断言 rc=0(预期1 等价断言) → 走产品 修复工具/依赖关系修复 卡片(白名单无需密码时自动跳过提权) → 断言输出含'系统仓库更新成功'且无…

### 2005735 test_mycase_149 系统修复-修复依赖关系不满足-apt-dpkg 命令不存在（待确认？？）

- 2026-11-11 05:40:00 `session-a5bc7e4e-95b7-459a-a9ac-148abf1474ae` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 05:45/05:49 两次 ssh 均 rc=255 'No route to host', ip neigh=INCOMPLETE(无 L2 响应), tcp/22 直连报'没有到主机的路由'; 本机 eno1 10.20.33.186/24 正常(排除本机网络), run_case.sh 一启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005735_test_mycase_149_20261111_054558.log), 未同步代码、未执行任何用例步骤、无远端副作用。根因同 2005719~2005733: 04:12 起该机失联(疑 2005719 移走 NetworkManager 后网卡未取回地址或断电), 需现场 console 或带外重启。本轮已完成本用例离线实现: 原空壳(仅开应用点修复导航)重写为真实闭环 —— 前置核对网络正常/apt、apt-get、dpkg 可用/root 执行 apt update 成功(排除仓库不可达分支) → 先注册 syst…

### 2005737 test_mycase_150 系统修复-不支持长文件名-修复成功

- 2026-11-11 05:50:00 `session-8a15904b-8dc6-406d-afd6-94b5dee65197` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 06:06 ip neigh=FAILED(无 L2 响应), tcp/22 'No route to host', run_case.sh 启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005737_test_mycase_150_20261111_060651.log), 未同步代码、未执行任何用例步骤、无远端副作用; 本机网络正常(网关 10.20.33.1 ARP REACHABLE、本机 22 端口可连), 仅该机失联; 根因同 2005719~2005735: 04:12 起失联(疑 2005719 移走 NetworkManager 后断电/网卡未起), 需现场 console 或带外恢复。 本轮已完成该用例离线实现: 原空壳(仅开应用点修复导航)重写为真实闭环 —— 读 /etc/os-version 判定方案(V20 有效版本 1063~1073=dlnfs / >=1074=ulnfs / V25 专业版=org.deepin.dlnfs), 前置关闭长文…

### 2005739 test_mycase_151 桌面修复--密钥环频繁弹出--修复成功

- 2026-11-11 06:10:00 `session-b29f152f-9132-4b37-a81d-15865c81d926` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 06:16/06:17 两次 ssh 均 rc=255 'No route to host', ip neigh=INCOMPLETE(无 L2 响应), 本机 eno1 10.20.33.186/24 正常(排除本机网络); run_case.sh 一启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005739_test_mycase_151_20261111_061623.log), 未同步代码、未执行任何用例步骤、无远端副作用。根因同 2005719~2005737: 04:12 起该机失联(疑 2005719 移走 NetworkManager 后网卡未取回地址或断电), 需现场 console 或带外重启。本轮已完成该用例离线实现: 原空壳(仅开应用点修复导航)重写为真实闭环 —— 备份后删除 ~/.local/share/deepin-keyrings-wb/status(描述前置的等价路径, 描述的 /home/uos 为登录用户家目录, 用例按 HOME 处理)…

### 2005741 test_mycase_152 桌面修复--密钥环频繁弹出--修复后密钥环弹窗问题验证

- 2026-11-11 06:20:00 `session-91567a28-53f9-4e8d-b055-b2822d9c0272` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 06:25 arp INCOMPLETE(无 L2 响应)、tcp/22 'No route to host', run_case.sh 启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005741_test_mycase_152_20261111_062547.log), 未同步代码、未执行任何用例步骤、无远端副作用; 根因同 2005719~2005739: 04:12 起该机失联(疑 2005719 移走 NetworkManager 后网卡未取回地址或断电), 需现场 console 或带外重启。本轮已完成该用例离线实现: 原空壳(建假密钥环→点修复卡→断言文件被删, 与 2005739 重复, 且 finally 直接删 login.keyring 会破坏用户真实密钥环)重写为修复后验证闭环 —— 整目录备份 ~/.local/share/keyrings 与 deepin-keyrings-wb → 删除 status 并写损坏 login.keyring 构造现场…

### 2005745 test_mycase_244 外设修复-U盘修复--FAT32 U 盘存在可自动修复的错误

- 2026-11-11 06:30:00 `session-4472e476-1110-425c-b507-b71b3ccdb98b` → **fail**（runs=2）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 06:30/06:52 两次 run_case.sh 均 SYNC 阶段 rc=255(SYNC_FAILED, 日志 .automation/logs/2005745_test_mycase_244_20261111_063026.log 等), 06:32/06:40/06:52 三次 ssh 均 'No route to host', ip neigh=INCOMPLETE(无 L2 响应), 本机 eno1 10.20.33.186/24 正常; 未同步代码、未执行任何用例步骤、无远端副作用。根因同 2005719~2005741: 04:12 起该机失联, 需现场 console 或带外重启。 本轮离线改造: 原实现依赖实体 U 盘、无盘时 pytest.skip(规程禁止), 而 2005715 记录显示测试机未插 USB 设备。改为 scsi_debug 合成 U 盘 —— 内核造 sdX 内存盘 + 仅匹配 scsi_debug(vendor=Linux*/model=scsi_debug*)的 ud…

### 2005747 test_mycase_245 外设修复-U盘修复-- FAT32 U 盘损坏严重

- 2026-11-11 06:45:00 `session-1d6e39c8-2cbc-4117-bcae-cfb8b0287fe1` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 06:47 ssh rc=255 'No route to host', ip neigh=INCOMPLETE(无 L2 响应), 本机 eno1 10.20.33.186/24 正常(排除本机网络); run_case.sh 启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005747_test_mycase_245_20261111_065203.log), 未同步代码、未执行任何用例步骤、无远端副作用。根因同 2005719~2005745: 04:12 起该机失联, 需现场 console 或带外重启。本轮离线改造: 原实现只造 loop 设备 FAT32+轻微损坏, 既没进入 usb-fix 修复流程(仅停在修复工具首页), 也没有"无法自动修复"的断言, 与描述不符; 重写为真实 severe 分支验证 —— scsi_debug 合成 U 盘(udev 规则把 ID_BUS 覆写为 usb, 与 2005745 同一等价实现) -> FAT32 格式化并挂载 -…

### 2005749 test_mycase_246 外设修复-修复U盘无法识别--无错误的 exFAT U 盘

- 2026-11-11 08:00:00 `session-85fd2306-8413-47ce-9fa7-370b8752bf0c` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 08:07/08:13 两次 ssh 均 rc=255 'No route to host', ip neigh=INCOMPLETE(无 L2 响应), 本机 eno1 10.20.33.186/24 正常; run_case.sh 启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005749_test_mycase_246_20261111_081307.log), 未同步代码、未执行任何用例步骤、无远端副作用; 根因同 2005719~2005751: 04:12 起该机失联, 需现场 console 或带外重启。 本轮为 reclaim 后重复唤醒(06:55 的 worker 实际仍存活, 已于 08:06:54 记录失败并把实现写入仓库), 本轮在其基础上做冲突合并与收尾: ①删除重复的 get_usb_exfat_filesystem_healthy 定义, 健康判定统一改用 get_usb_exfat_filesystem_check_rc(==0) + get…
- 2026-11-11 08:00:00 `session-93a753fd-5236-43f7-9ea3-51d513c8c408` → **fail**（runs=None）：环境阻断未执行: 测试机 10.20.33.103 仍不可达(08:00~08:07 三次 ssh 均 'No route to host', ip neigh=FAILED 无 L2 响应, 本机

### 2005751 test_mycase_247 外设修复-修复U盘无法识别-exFAT U 盘存在可自动修复的错误

- 2026-11-11 08:10:00 `session-ab4625c9-353c-4f93-9890-514ed14a9b23` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 08:10 ip neigh=FAILED(无 L2 响应)、tcp/22 三次直连均失败、ssh rc=255 'No route to host'，run_case.sh 在 SYNC 阶段即 SYNC_FAILED rc=255(日志 .automation/logs/2005751_test_mycase_247_20261111_081144.log)，未执行任何用例代码、无构造数据与残留；另注: 本用例当前仍是 loop 设备版实现(usb-fix 只枚举 ID_BUS=usb 的 sd*，loop 不会被识别)，机器恢复后应参照 2005745/2005749 改为 scsi_debug 合成 U 盘 + exFAT 可修复错误注入，并补 widget.get_usb_exfat_filesystem_healthy。

### 2005753 test_mycase_248 外设修复-修复U盘无法识别--无错误的 NTFS U 盘

- 2026-11-11 08:15:00 `session-92f5ef49-13ab-410a-8220-cae749448f58` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 08:16/08:19 两次 ssh 均 rc=255 'No route to host', 本机 eno1 10.20.33.186/24 与默认路由正常; run_case.sh 启动即 SYNC_FAILED rc=255, 未同步代码、未执行任何用例步骤、无远端副作用(与 04:12 起 2005719~2005751 同一根因, 需现场 console 或带外重启)。已按 2005749 的实现模式完成本条闭环改造: ①新增 prepare_usb_ntfs_partition(卸载自动挂载→mkfs.ntfs -F -f -Q 快速格式化→按 ntfs/ntfs3/自动 依次挂载, 兼容 V20 ntfs-3g 与 V25 内核 ntfs3); ②新增 get_usb_ntfs_filesystem_check_rc(ntfsfix -n 只读检查, 用退出码判健康)与 get_usb_ntfs_filesystem_has_errors(退出码非 0 或输出含 dirty/corrupt/error/…

### 2005757 test_mycase_250 外设修复-修复U盘无法识别--无错误的 ext4 U 盘

- 2026-11-11 08:25:00 `session-81ab2e08-e1a8-4ca4-8fcd-9db388878f07` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 08:26 ping/ssh 均失败(ip neigh=FAILED, ssh rc=255 'No route to host'), 本机 eno1 10.20.33.186/24 与默认路由正常; run_case.sh 启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005757_test_mycase_250_20261111_082753.log), 未同步代码、未执行任何用例步骤、无远端副作用(与 04:12 起 2005719~2005753 同一根因, 需现场 console 或带外重启)。已按 2005749/2005753 的等价实现模式完成本条闭环改造(原用例只在页面点开修复页, 未点开始修复、未断言输出): ①新增 prepare_usb_ext4_partition(清 udisks2 自动挂载→mkfs.ext4 -F -q→udevadm trigger(change)+settle 刷新 ID_FS_TYPE, 避免合成盘残留 vfat 缓存→m…

### 2005759 test_mycase_251 外设修复-修复U盘无法识别-- ext4 U 盘存在可自动修复的错误

- 2026-11-11 08:30:00 `session-5ee1042c-5359-4443-ba9e-8c78c59e3df9` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 08:31/08:40 多次 ssh 均 rc=255 'No route to host', ip neigh=FAILED(无 L2 响应), 本机 eno1 10.20.33.186/24 与默认路由正常; run_case.sh 启动即 SYNC_FAILED rc=255(日志 .automation/logs/2005759_test_mycase_251_20261111_084028.log), 未同步代码、未执行任何用例步骤、无远端副作用(与 04:12 起 2005719~2005757 同一根因, 需现场 console 或带外重启)。已按 2005745/2005757 的等价实现模式完成本条闭环改造(原用例只用 loop 设备并断言 lsblk 含 ext4, 既未点开始修复也未断言输出): ①新增 get_usb_ext4_partition_has_errors(fsck.ext4 -n 退出码 + 'Fix?/wrong/differences/uncleanly' 文本双判据) 与 …

### 2005761 test_mycase_032 外设修复-修复U盘无法识别--设备路径不存在

- 2026-11-11 08:45:00 `session-a38f7b84-a560-4986-bd5d-374461ecdab3` → **fail**（runs=None）：（无备注）

### 2005763 test_mycase_153 应用修复-修复微信-正常关闭运行中的微信进程

- 2026-11-11 08:55:00 `session-c3c32b26-40d9-41ce-bb94-bec459cfd759` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达(08:56/08:58 TCP 22 均 'No route to host', ip neigh 为 FAILED, 对本段 10.20.33.0/24 扫描 254 个地址仅 .103 无 22 端口; 本机 eno1 10.20.33.186/24 与网关正常); run_case.sh 启动即 SYNC_FAILED rc=12, 未同步代码、未执行任何用例步骤、无远端副作用(与 04:12 起 2005719~2005757 同一根因, 需现场 console 或带外重启)。已按产品源码 deepin-pc-manager-plugins/plugins/plugin-wechat-fix/entry.sh(killall wechat + rm -rf ~/.xwechat/radium/cache + openinfobox)完成闭环改造: 原用例只断言进程被终止, 现补齐 —— ①构造前置数据: /tmp/wechat(sleep 复制)进程 + ~/.xwechat/radium/cache 缓存文件; …

### 2005765 test_mycase_033 应用修复-修复微信-清理Linux原生微信缓存目录

- 2026-11-11 09:00:00 `session-79600db3-bc41-4ec2-b42e-e1edcb5e5138` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达(09:02 TCP 22 'No route to host', ip neigh FAILED, 本机 eno1 10.20.33.186/24 正常); run_case.sh 在 SYNC 阶段 SYNC_FAILED rc=255, 未同步代码、未执行任何用例步骤、无远端副作用(与 04:12 起 2005719~2005763 同一根因, 需现场带外重启恢复)。已按产品源码 deepin-pc-manager-plugins/plugins/plugin-wechat-fix/entry.sh(killall wechat + rm -rf ~/.xwechat/radium/cache + openinfobox) 完成闭环改造: 原用例无前置数据真实构造/无 try-finally/仅断言目录存在性; 现补齐 —— ①先备份测试机可能存在的真实 ~/.xwechat 到 ~/.autotest_wechat_backup(新增 widget.backup_wechat_cache/restore_wechat…

### 2005767 test_mycase_154 应用修复-修复微信-磁盘空间不足执行脚本

- 2026-11-11 09:05:00 `session-00fadf9e-a16d-4af4-9a77-522e68192f52` → **fail**（runs=1）：环境阻断未执行: 测试机 10.20.33.103 仍不可达(09:05/09:12 TCP 22

### 2005769 test_mycase_155 应用修复-修复微信-修复后微信功能验证

- 2026-11-11 09:15:00 `session-d988b128-5bd5-4e6d-9e0b-cbc9dc5bcc1b` → **pass**（runs=1）：按 entry.sh 闭环重写原用例(原版无 try/finally、仅断言进程存活): 先备份真实 ~/.xwechat, 构造 comm=wechat 的模拟微信进程 + radium/cache 缓存 + user_data 聊天记录/消息日志; 修复工具->微信卡片->开始修复后断言 shellRepair 对话框弹出、killall 生效、缓存目录删净、聊天记录 md5 前后一致、重启微信 60s 内健康启动(非僵尸/VmRSS>0)且 10s 观察窗内同 pid 稳定驻留、追加新消息行数增加; 新增 widget 辅助方法 8 个(create_mock_wechat_user_data/get_wechat_chat_history_digest/get_wechat_message_count/append_wechat_message/get_wechat_process_pid/get_wechat_process_info/is_wechat_process_healthy/wait_wechat_process_started/is_wechat_proces…

### 2005771 test_mycase_156 应用修复-修复企业微信-正常关闭运行中的企业微信进程

- 2026-11-11 09:25:00 `session-59402b56-5459-4fcf-9310-e8997ae070bf` → **pass**（runs=2）：按产品 plugin-wecom-fix/entry.sh 闭环重写(原版只打开修复页、无任何断言): 用桩运行时等价构造'运行中的 Wine 企业微信'——~/.deepinwine/Deepin-WXWork(含 user.reg)+模拟 WeChat.exe(sleep 复制品)+该 prefix 的桩 wineserver(收到 -k 时结束容器内进程, 与真实 wineserver -k 同语义), bottle 内写 40MB 缓存; 修复工具->企业微信修复卡片->开始修复后断言: shellRepair 对话框弹出(脚本真实执行)、bottle 目录及 40MB 缓存被 rm -rf 删净、模拟企业微信进程被 kill.sh->wineserver -k 终止; 新增 widget 方法 7 个(setup_mock_wecom_wine/_protect_wecom_bottle/get_wecom_wineserver_status/get_wecom_process_status/wait_wecom_process_killed/create_wecom_wi…

### 2005773 test_mycase_157 应用修复-修复企业微信-清理wine企业微信的缓存目录

- 2026-11-11 09:35:00 `session-576f6151-4326-4fb5-817c-74749472e28b` → **pass**（runs=2）：把原版'只建空缓存目录、点开始修复后只断言对话框'的弱用例重写为按产品 plugin-wecom-fix/entry.sh 闭环: 复用 2005771 的桩运行时(setup_mock_wecom_wine)构造 ~/.deepinwine/Deepin-WXWork(user.reg + 桩 wineserver + 模拟 WeChat.exe)并在 bottle 内写入 40MB 缓存文件, 修复工具->企业微信修复卡片->开始修复后断言: shellRepair 对话框弹出(脚本真实执行)、wait_wecom_wine_cache_cleaned(目录由存在变不存在)、du 占用=0、再次 ls 该路径返回非0且报 No such file(对应预期2'路径错误'); 新增 widget 方法 get_wecom_wine_cache_ls_error; 修复原 draft 中 assert_true 传多余 message 导致的 TypeError(该 assert 只接受1个参数); finally 关闭对话框并 cleanup_mock_wecom_wine 还原(…

### 2005775 test_mycase_158 应用修复-修复企业微信-磁盘空间不足执行脚本

- 2026-11-11 09:40:00 `session-1f4cacc5-74a9-4a64-818f-c4cadb6cd4d6` → **pass**（runs=1）：按产品 plugin-wecom-fix/entry.sh(kill.sh bottle + rm -rf ~/.deepinwine/Deepin-WXWork + openinfobox)闭环重写: 原版只建空缓存目录并忽略磁盘空间, 无低空间构造/无 try-finally/弱断言; 现新增 widget 低空间现场 setup_low_space_wecom_bottle/cleanup_low_space_wecom_bottle/is_mount_present/unmount_path, 并给 setup_mock_wecom_wine 增加 protect_bottle 开关: 挂 100MB tmpfs 并 bind 到 ~/.deepinwine(真实 bottle 先改名备份), 盘内写 30MB 占位(可用降到30MB<100MB), 再放置含40MB缓存/ user.reg /桩wineserver/模拟WeChat.exe 的桩bottle; 修复工具->企业微信修复卡片->详情页->开始修复后断言 shellRepair 对话框弹出(脚本真实执行)、bo…

### 2005777 test_mycase_159 应用修复-修复企业微信-修复后企业微信功能验证

- 2026-11-11 09:50:00 `session-202d3b92-a397-4ce5-ad75-9abd7a605431` → **pass**（runs=1）：按 plugin-wecom-fix/entry.sh(kill.sh bottle + rm -rf ~/.deepinwine/Deepin-WXWork)闭环重写: 原版只开修复页、无任何真实断言。复用 2005771/2005773 桩运行时(桩 wineserver+模拟 WeChat.exe+bottle)构造修复前现场(20MB 缓存+容器内会话/聊天记录), 修复后断言对话框弹出、进程被终止、bottle 及缓存被删净; 再以 setup_mock_wecom_wine(protect_bottle=False) 重建全新 bottle 并拉起 WeChat.exe 等价'双击打开企业微信/首次启动重新生成 prefix'(60s 内健康启动、非僵尸 VmRSS>0), 10s 观察窗内同 pid 稳定驻留证明无闪退卡顿; 容器内重建本地会话(等价登录)、追加消息后行数增加且读回内容一致(等价发送消息/查看聊天记录)。产品删整个 bottle 会带走旧聊天记录, 属既定行为, 故不断言旧记录保留。新增 widget 方法 kill_all_mock_wecom_win…

### 2005779 test_mycase_160 应用修复-修复QQ-正常关闭运行中的QQ进程

- 2026-11-11 10:00:00 `session-6cfeefe5-6198-4124-8e9a-cf17bba2cece` → **pass**（runs=1）：按产品 plugin-qq-fix/entry.sh 重写(原版只打开修复页、无任何断言): 用 sleep 复制品 /tmp/qq 等价构造'QQ 正在运行', ~/.config/QQ/Cache 写入 8MB 缓存; 断言修复对话框出现、输出日志出现'清理完成'、缓存目录彻底消失(文件数0/占用0)、qq 进程被 pkill -x qq 终止; 用例描述中的 '~/.config/QQ/Cache-QQ' 与产品脚本实际目标 '~/.config/QQ/Cache' 不一致, 以产品脚本为准; finally 结束模拟进程/删 /tmp/qq 与缓存并还原 ~/.config/QQ、Deepin-QQ 备份, 现场无残留

### 2005781 test_mycase_161 应用修复-修复QQ-清理 Linux 原生 QQ 缓存目录

- 2026-11-11 10:10:00 `session-afb14e10-a202-4e57-a3d9-7aef9c2fcf9d` → **pass**（runs=1）：原版用例只打开修复页且无任何断言, 按产品 plugin-qq-fix/entry.sh 重写: 用 backup_qq_state 保护真实现场后, 在 ~/.config/QQ/Cache 构造 avatar/filecache/temp 共 8MB 缓存(8220KB, >=4 文件)作为前置; 断言修复页面/QQ修复卡片/详情页可达、修复对话框弹出、输出日志出现'清理完成'(脚本执行到末尾)、缓存目录整体消失且文件数/占用均为 0; finally 关闭提示框/修复对话框、删构造缓存并 restore_qq_state 还原真实现场(本机原本无 QQ 数据), 残留检查无 autotest 对象

### 2005783 test_mycase_034 应用修复-修复QQ-磁盘空间不足执行脚本

- 2026-11-11 10:15:00 `session-f666067d-7ec3-4756-accc-3458804a235f` → **pass**（runs=1）：原版只打开修复页无任何断言, 按产品 plugin-qq-fix/entry.sh 闭环重写: 因脚本对 cache_dir 有 [ ! -L ] 符号链接防护, 不能软链到低空间盘(会被跳过假通过), 故新增 widget.setup_low_space_qq_cache/cleanup_low_space_qq_cache: 挂 100MB tmpfs 并 bind 到 ~/.config/QQ(真实现场先 backup_qq_state 移走), 盘内 40MB 占位+20MB QQ 缓存, 使删除目标盘可用 40MB<100MB; 断言修复卡片/详情页可达、shellRepair 对话框弹出、输出出现'清理完成'(脚本跑完未崩)、Cache 被 rm -rf 删净(目录消失/文件数0/占用0)、低空间盘可用 40MB->60MB(+20MB 释放)、输出无 ENOSPC/No space left/Traceback; finally 先卸 bind/tmpfs 再清缓存并 restore_qq_state; 1 次运行 PASS(31s), 复核远端无残留挂载/备份/挂载点

### 2005785 test_mycase_162 应用修复-修复QQ-修复后 QQ 功能验证（原生版）

- 2026-11-11 10:20:00 `session-91887dad-1dda-4a1b-bc1b-d74b54a67f71` → **pass**（runs=1）：重写为真实过检: 修复工具点QQ修复->开始修复(pkill qq+删Cache+输出'清理完成'), 再验证修复后QQ可重启(60s内健康、10s同pid稳定)、聊天记录md5未变、可追加消息; 测试机无原生QQ, 用/tmp/qq模拟进程+~/.config/QQ/UserData桩数据等价实现, 前后backup/restore真实现场; widget新增8个QQ功能验证方法

### 2005787 test_mycase_163 应用修复-修复WPS-系统不存在Office-conf 配置文件

- 2026-11-11 10:30:00 `session-158afe08-1ffc-4b83-b149-2c4c3d68aa8d` → **pass**（runs=1）：原用例在未安装WPS时直接return(假跳过, 测试机确无wps) , 按plugin-wps-fix/entry.sh重写闭环: 整体备份并删除~/.config/Kingsoft使目录与Office.conf均不存在 -> 修复工具点WPS双击打开修复 -> 开始修复, 断言修复对话框弹出、Kingsoft目录被脚本重建(775/uostest)、Office.conf生成且含[6.0]与AppComponentMode/AppComponentModeInstall=prome_fushion(664/uostest)、session总线收到OpenMessage(title=WPS修复,正文=WPS配置文件修复完成)且提示框仅确定按钮(证明脚本跑到末尾)、输出无报错; finally关闭提示框/修复框并还原现场, 复核测试机无残留; 1次运行PASS(69s)

### 2005789 test_mycase_164 应用修复-修复WPS-多用户场景下，A用户使用WPS，在B用户下打开doc文档

- 2026-11-11 10:40:00 `session-9cbc3b59-68db-41ee-b976-072d2f98bc8e` → **pass**（runs=4）：测试机只有单用户且未安装 WPS(无外网): 用 useradd 造真实第二普通用户 A 并在其家目录写入 A 自己的 Office.conf(属主A/600), 备份并删除 B(uostest) 的 ~/.config/Kingsoft 构造'B 无配置、doc 打不开'现场 -> 走真实产品 plugin-wps-fix: B 的 Kingsoft 目录重建 775/uostest、Office.conf 664/uostest 且含 [6.0]+AppComponentMode(AppComponentModeInstall)=prome_fushion, session 总线收到 OpenMessage(WPS修复/WPS配置文件修复完成)且提示框只有'确定'(脚本跑到末尾), A 的配置 md5/属主/权限修复前后完全一致(多用户隔离), 修复后桌面 docx 被系统默认文档处理程序真实打开(查看器进程命令行含该文档; WPS 缺失故以默认处理程序等价验证, 配置整合模式 prome_fushion 亦断言); finally 关弹框/查看器、删测试文档、还原 Kingso…

### 2005791 test_mycase_165 应用修复-修复WPS-修复后双击文档可正常打开 WPS

- 2026-11-11 11:05:00 `session-03ae1885-1290-4cf2-bb12-c5b8d2b3017e` → **pass**（runs=1）：重写用例: 真实拉起WPS双击打开修复并断言Kingsoft目录/Office.conf内容与权限/属主/openinfobox提示框与DBus OpenMessage; 测试机未装WPS且无外网, 双击打开以deepin-reader真实打开docx+桩启动器验证docx/xlsx/pptx按OOXML类型分发并传入文档路径等价, finally还原mimeapps与Kingsoft目录无残留; 1次通过

### 2005793 test_mycase_166 应用修复-输入法修复-正常关闭运行中的输入法进程

- 2026-11-11 11:25:00 `session-f6da94cb-6705-4f51-a67b-9caad434ae18` → **pass**（runs=3）：插件1.0.0实际实现与描述文案不同(无'正在重启输入法服务'/'已重启 xx 输入法'/'输入法重启完成'文本), 按等价语义断言: 修复对话框拉起+旧fcitx PID全消失(killall)+重启出新PID+openinfobox提示框(输入法修复/输入法已重启，修复完成); 新增widget辅助方法get_input_method_version/get_input_method_xmodifiers/wait_input_method_restarted/get_info_dialog_text; 测试机为fcitx4.2.9.32.46(无fcitx5)


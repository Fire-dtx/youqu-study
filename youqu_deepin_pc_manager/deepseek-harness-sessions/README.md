# 电脑管家自动化测试用例 · DeepSeek Harness 会话汇总

> 生成时间：2026-11-17 14:48:47+0800　来源：`/home/ut000635@uos/.dsh/sessions`

## 1. 采集口径

- 扫描本机 `~/.dsh/sessions` 下全部项目目录，仅保留会话 `cwd` 位于 `youqu_deepin_pc_manager` 的会话。
- 每个会话解压 `session.v4.jsonl.zstd`，提取标题、调度提示、领取用例、`record` 结果、执行命令、最终结语、token/模型用量。
- 原始副本保留在 `raw/`（可直接用 `zstd -dc` 复读）；`digests/` 为逐会话摘要；`index.json` 为全量结构化数据。
- 结果以会话内 `harness.py record`（含监控通过脚本记录）为准；项目 `.automation/ledger.json` 当前状态单独标注。

## 2. 总览

| 指标 | 数值 |
|---|---|
| 命中会话 | **212** |
| 时间范围 | 2026-11-10 20:32:53 ~ 2026-11-11 11:35:00 |
| 解压后文本量 / 压缩包体积 | 119.3 MiB / 28.5 MiB |
| 轮次 / 工具错误 | 218 / 53 |
| 用例记录（pass/fail） | 39 / 35（70 个会话，覆盖 65 条用例，含重试） |
| 环境阻断会话 | 45 |
| ledger 当前状态 | failed 4，passed 223，pending 1，skipped 1（更新于 2026-11-16T18:05:57+08:00） |

## 3. 会话分类

| 类型 | 会话数 | 说明 |
|---|---|---|
| 单条处理-recorded | 68 | 领取并处理 1 条用例，最终执行 `record` |
| 单条处理-忙等待 | 64 | `next` 返回 busy（他人在处理），按规程立即结束 |
| 单条处理-环境阻断 | 35 | 领到用例但测试机不可达，未真正执行 |
| 单条处理-队列完成 | 0 | `next` 返回 done，仅汇报统计 |
| 单条处理-其他 | 0 | 有领取动作但无明确结论 |
| 监控恢复-巡检 | 41 | 心跳/测试机巡检，未改代码 |
| 监控恢复-介入 | 1 | 接管超时用例、改代码或记录结果 |
| 编排任务 | 1 | 主控/汇总会话 |
| 未执行-鉴权失败 | 2 | 模型/凭据鉴权错误，未开始 |
| 未执行-运行错误 | 0 | 会话因错误中断 |

> 上表按会话主类型归类；另有编排会话与监控接管会话也调用了 record，因此含记录的会话共 70 个。

## 4. 时间线（按小时）

| 小时 | 会话数 | 忙等待 | 已记录 | 监控 |
|---|---|---|---|---|
| 2026-11-10 20:00 | 1 | 0 | 1 | 0 |
| 2026-11-10 21:00 | 6 | 2 | 1 | 1 |
| 2026-11-10 22:00 | 15 | 4 | 3 | 3 |
| 2026-11-10 23:00 | 15 | 6 | 4 | 3 |
| 2026-11-11 00:00 | 15 | 5 | 6 | 3 |
| 2026-11-11 01:00 | 15 | 4 | 6 | 3 |
| 2026-11-11 02:00 | 15 | 3 | 4 | 3 |
| 2026-11-11 03:00 | 15 | 9 | 3 | 3 |
| 2026-11-11 04:00 | 15 | 2 | 7 | 3 |
| 2026-11-11 05:00 | 15 | 1 | 8 | 3 |
| 2026-11-11 06:00 | 15 | 5 | 4 | 3 |
| 2026-11-11 07:00 | 15 | 8 | 0 | 3 |
| 2026-11-11 08:00 | 15 | 4 | 8 | 3 |
| 2026-11-11 09:00 | 15 | 2 | 7 | 3 |
| 2026-11-11 10:00 | 15 | 4 | 6 | 3 |
| 2026-11-11 11:00 | 10 | 5 | 2 | 2 |

## 5. 关键发现

1. **高频空转**：64 个 worker 会话（2026-11-10 21:45:00 ~ 2026-11-11 11:30:00）在 `next` 阶段遇到 busy，未处理用例；这是 5 分钟/10 分钟定时唤醒叠加单条串行处理的直接结果。
2. **测试机失联**：45 个会话的结语显示 `10.20.33.103` 不可达；20 条用例的 record 备注明确标注“环境阻断未执行”。worker 仍在离线状态重写用例代码，机器恢复后需 `requeue-failed` 重跑。
3. **监控接管**：1 个监控会话实际介入（93a753fd）；其中心跳超时后 reclaim 并重写了同一用例代码，存在两个会话同时修改同一文件的情况。
4. **鉴权失败**：2 个会话（5a30eb1d, de8d4c0a） 因 provider/凭据错误未执行。
5. **ledger 后续变化**：会话期记录为 pass 39 / fail 35，而 ledger 当前为 failed 4，passed 223，pending 1，skipped 1（2026-11-16T18:05:57+08:00），说明 11-11 之后还有会话外操作（如 requeue-failed、手工修复）。

## 6. 失败/混合用例清单（27 条）

| 用例 | 方法 | 会话结果 | ledger 当前 | 环境阻断 | 备注摘要 |
|---|---|---|---|---|---|
| 2005471 | test_mycase_069 | mixed | passed | 否 | 重写为逐一进入系统环境检测/硬件检测/更新环境检测/网络检测四个入口：断言运行时页面出现且 detectionGroup_<入口名> 属于该分项，再返回首页并… |
| 2005479 | test_mycase_021 | fail | passed | 否 | 环境限制无法构造无异常前置：全面检测实测 系统环境检测(system_version: Lastore 更新源任务失败)、网络检测(network_conne… |
| 2005697 | test_mycase_133 | fail | failed | 否 | 步骤1不可执行: 产品1.1.7已隐藏离线导入入口(repair_page.cpp 中 repair_offlineImportBtn 的构造/setA11y… |
| 2005699 | test_mycase_134 | fail | failed | 否 | 重写用例为真实流程: 构造损坏 zip(仅PK局部头, zipfile 自检 BadZipFile)+非zip文本, 启动管家进修复工具页后点【离线导入】; … |
| 2005705 | test_mycase_137 | fail | passed | 否 | 前置构造 PipeWire 全局自启使音频修复进入提权分支; 产品以无 tty 管道启动插件脚本, sudo 报 'no tty present and no… |
| 2005707 | test_mycase_138 | fail | passed | 否 | 流程: 密钥环修复详情页→备份插件入口并临时替换为按 DPMOBF1 编码的 [[TEXT]] 交互桩(产品 1.1.7 现网插件已不再用标准输入交互、依赖关… |
| 2005723 | test_mycase_267 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— ip neigh=FAILED(无 L2 响应), ssh/rsync rc=255 'N… |
| 2005725 | test_mycase_144 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 05:05-05:07 三次直连 ssh 均 rc=255 'No route to ho… |
| 2005727 | test_mycase_145 | fail | failed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 05:25 ssh rc=255 'No route to host', ip neigh… |
| 2005729 | test_mycase_146 | fail | failed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达(05:29 ARP INCOMPLETE, ssh No route to host), run… |
| 2005731 | test_mycase_147 | fail | passed | 否 | 构造dpkg配置失败(less postinst插入exit 1 + status改为install ok unpacked): apt update -y … |
| 2005733 | test_mycase_148 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达(05:37 ssh rc=255 'No route to host', ip neigh IN… |
| 2005735 | test_mycase_149 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 05:45/05:49 两次 ssh 均 rc=255 'No route to host… |
| 2005737 | test_mycase_150 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 06:06 ip neigh=FAILED(无 L2 响应), tcp/22 'No ro… |
| 2005739 | test_mycase_151 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 06:16/06:17 两次 ssh 均 rc=255 'No route to host… |
| 2005741 | test_mycase_152 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 06:25 arp INCOMPLETE(无 L2 响应)、tcp/22 'No rout… |
| 2005745 | test_mycase_244 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 06:30/06:52 两次 run_case.sh 均 SYNC 阶段 rc=255(S… |
| 2005747 | test_mycase_245 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 06:47 ssh rc=255 'No route to host', ip neigh… |
| 2005749 | test_mycase_246 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达(08:00~08:07 三次 ssh 均 'No route to host', ip neig… |
| 2005751 | test_mycase_247 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 08:10 ip neigh=FAILED(无 L2 响应)、tcp/22 三次直连均失败… |
| 2005753 | test_mycase_248 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 08:16/08:19 两次 ssh 均 rc=255 'No route to host… |
| 2005757 | test_mycase_250 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 08:26 ping/ssh 均失败(ip neigh=FAILED, ssh rc=25… |
| 2005759 | test_mycase_251 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达 —— 08:31/08:40 多次 ssh 均 rc=255 'No route to host… |
| 2005761 | test_mycase_032 | fail | passed | 否 | 新代码实跑 PASS(test_mycase_032): mask 前记录 USB 盘快照, 删除默认密码兜底与 notify 兜底, 收尾比对快照 |
| 2005763 | test_mycase_153 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达(08:56/08:58 TCP 22 均 'No route to host', ip neig… |
| 2005765 | test_mycase_033 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达(09:02 TCP 22 'No route to host', ip neigh FAILED… |
| 2005767 | test_mycase_154 | fail | passed | 是 | 环境阻断未执行: 测试机 10.20.33.103 仍不可达(09:05/09:12 TCP 22 |

## 7. 目录结构

```text
.deepseek-harness-sessions/
├── README.md                 # 本文件
├── index.json                # 全量会话（含摘要、记录、命令、token）
├── sessions.csv / .md        # 会话级清单
├── cases.json / .md          # 用例级聚合与备注
├── digests/<日期>/<时分>_<sessionId>.md  # 单会话摘要
├── raw/<projectKey>/<sessionId>/session.v4.jsonl.zstd  # 原始压缩副本
└── scripts/collect_sessions.py           # 可重复执行的采集脚本
```

## 8. 复现

```bash
python3 .deepseek-harness-sessions/scripts/collect_sessions.py
# 只读查看原始会话：
zstd -dc .deepseek-harness-sessions/raw/<projectKey>/<sessionId>/session.v4.jsonl.zstd | less
```

## 9. 模型与 token（仅会话内统计）

| 模型 | assistant 消息数 |
|---|---|
| deepseek-v4.1-flash-1017 | 3751 |

输入 7,762,417，输出 2,832,036，缓存读 268,475,648，合计 279,070,101。

> 说明：busy 会话与监控巡检轮次数量大、单轮 token 低；token 为 assistant/message 事件 `usage` 字段累加，缺失字段按 0 计。

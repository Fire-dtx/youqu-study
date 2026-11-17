# 建设期会话存档（2026-09-28 → 2026-10-26）

本目录保存**建设期**（issue 驱动、多 Agent 并行写用例）的会话导出，用于支撑 `.share/` 分享稿中的统计与案例。含内部信息，**不要提交或外发**。

## 1. 数据来源

- 内部 issue 平台的会话导出包：`pc_manager_sessions.tar.zst.part.00` ~ `.part.05`（共 6 个分卷，约 476MB）。
- 合并解压后约 3.3GB，目录结构 `home/uos/.multica/pi-sessions/*.jsonl`。
- 平台生成的汇总说明：`project_summary.md`（已脱敏）；分卷说明：`新建文本.txt`。

合并与解压：

```bash
cd .multica-sessions
cat pc_manager_sessions.tar.zst.part.* > pc_manager_sessions.tar.zst
tar --use-compress-program=zstd -xvf pc_manager_sessions.tar.zst
```

> 解压产物较大，建议解压到 `/tmp` 并在用完后删除，避免仓库目录膨胀。

## 2. 采集口径

导出包共 559 个会话文件（含其他桌面项目的 issue）。纳入本项目的条件：会话全文命中以下任一标志——

1. `youqu_deepin_pc_manager` 仓库路径；
2. `autotest_my_app`（用例工程目录）；
3. `test_mycase_`（旧用例命名）；
4. `mycase.csv`（用例登记表）。

最终 **466 个会话**纳入统计；其余为其他产品（文件管理器、安装器等）的 issue 会话，均不纳入。

## 3. 统计（按 assistant 消息的 `model` / `usage` 字段聚合）

| 指标 | 数值 |
|---|---|
| 会话数 | 466（其中 461 个在 2026-10-10） |
| 用户评论/指令 | 494 |
| 助手消息 | 12,694 |
| 模型请求 | 12,694 |
| 输入 tokens | 530,536,020 |
| 输出 tokens | 6,268,125 |
| 缓存读 tokens | 36,661,120 |
| 总 tokens | 573,465,265 |

模型分布：

| 模型 | 请求数 | 输入 | 输出 | 缓存读 |
|---|---:|---:|---:|---:|
| `deepseek-v4-flash` | 11,935 | 529,389,550 | 6,025,830 | 2,513,344 |
| `glm-5.2` | 759 | 1,146,470 | 242,295 | 34,147,776 |

日期分布：2026-09-28（2）、2026-10-08（1）、2026-10-09（1）、2026-10-10（461）、2026-10-26（1）。

任务规模：会话文本中共出现 **305 个不同的 `WS-*` 子任务编号**（编号范围 WS-1 ~ WS-461）；出现 **235 个不同的 `ID_标题.py` 用例文件名**。状态流转：出现 `blocked` 状态变更的会话 77 个；命中"版本未确认"关键词的会话 385 个（文本计数，非逐条人工核验）。

## 4. 会话结构

每行一个 JSON 事件，关键字段：

- `type`: `message` / 其他（工具结果、状态等）；
- `message.role`: `user` / `assistant` / `tool`；
- `message.content`: 文本或分块数组；
- `message.model` / `message.usage`: 模型与 token（assistant 消息）；
- 首条 user 消息是任务模板（`Your assigned issue ID is ...`），正文与评论通过 `multica issue get` / `comment list` 工具结果进入上下文。

## 5. 注意事项

1. 会话中的测试机地址、账号、密码、内部仓库地址仅为历史记录；引用时必须脱敏，分享稿只保留"测试机 A/B"。
2. 平台生成的 `project_summary.md` 中的提交数、分支数、用例数是**导出时快照**（2026-10-26），与仓库当前状态存在时间差；引用时注明口径。
3. 这里只做只读存档，不在此目录运行脚本或写入导出产物。

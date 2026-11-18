# CaseSurface：归类 youqu_deepin_pc_manager 的 347 条用例

- 会话 ID: `01a1ec6b-6449`
- 类型: 子代理/分片会话（父会话 `01a1e30c-7fe9`，片段 `CaseSurface`）
- 项目目录: `/home/ut000635@uos/Documents/TestCode/youqu_deepin_pc_manager`
- 创建时间: 2026-11-18T10:10:23+08:00
- 最后活动: 2026-11-18T10:29:24+08:00
- 消息: 用户提示词 1 / 助手文本 1 / 模型请求 41
- 模型: deepseek-v4.1-flash-1017 × 41
- Token: input=553,387, output=72,622, cacheRead=2,839,552, total=3,465,561
- 工具调用 Top: read×59, grep×56, glob×12, yield×1
- 原始记录: `/home/ut000635@uos/.omp/agent/sessions/-Documents-TestCode-youqu_deepin_pc_manager/2026-11-16T06-30-09-641Z_01a1e30c-7fe9-7000-b6dc-f2a8e9788be6/CaseSurface.jsonl`

## 用户提示词

### U1

Complete assignment thoroughly:

\# Target
归类 youqu_deepin_pc_manager 的 347 条用例，提炼每条用例实际断言的产品行为与依赖的构造。

\# Change
1. 扫描 apps/autotest_my_app/case/*.py 全部文件名与类内断言（重点 assert 的期望对象），按主题聚合（系统检测、清理、修复、网络、工具、设置、性能、兼容性、安全等）。
2. 统计每个主题的用例数、代表 ID、断言对象（UI 文案/数据/D-Bus 返回/进程状态/文件状态）。
3. 读 apps/autotest_my_app/widget/my_app_widget.py 的方法名清单（不必逐行读），归纳测试侧具备的操作能力：启动、页面导航、检测项执行、清理执行、修复执行、工具页操作、配置读写。
4. 找出用例文件名主题无法归入产品插件/页面的条目，单列。

\# Acceptance
输出 StrictJSON：domains[] 覆盖全部 347 条（条数合计一致），widget_capabilities[]，unmapped[]。

## 助手输出（按时间顺序，已省略 thinking 与工具参数）

### A1

我先查看仓库结构和用例文件。

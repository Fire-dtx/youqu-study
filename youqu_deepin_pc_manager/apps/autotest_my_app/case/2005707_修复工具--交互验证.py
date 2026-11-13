#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

# 本次使用的修复工具(用户态执行, 不依赖网络/硬件, 适合做交互桩)
PLUGIN_NAME = "keyring-fix"
PLUGIN_TITLE = "密钥环修复"
# 插件入口脚本备份路径(用例结束后必须删除)
BACKUP_PATH = "/tmp/autotest_2005707_keyring_entry.sh.bak"
FIRST_INPUT = "autotest-button-input"
SECOND_INPUT = "autotest-enter-input"

# 交互桩脚本说明(为什么需要它):
# 产品(deepin-pc-manager 1.1.7)已把修复脚本的用户交互统一改为 dpm_prompt/
# dpm_confirm 结构化弹窗, 现网 12 个修复插件的入口脚本都不再输出 [[TEXT]]
# 标记, 也没有脚本在标准输入上等待自由文本; 依赖关系修复里的 dpkg/debconf
# 提示又需要联网 apt update 才能走到(本测试机无外网)。因此这里按产品
# [[TEXT]] 契约注入一段桩脚本, 让"修复窗口的命令执行文本框"真正被产品
# 启用/提交/回显, 验证的是产品 ShellRepairDialog 的真实交互代码路径,
# 而不是断言常量。脚本第一段 sleep 用于观察"脚本运行中输入框禁用"。
FIXTURE_SCRIPT = """#!/usr/bin/env bash
# AUTOTEST_INTERACTIVE_FIXTURE
# 交互桩脚本: 仅用于 2005707 用例验证 ShellRepairDialog 的命令执行文本框。
echo "=================================================="
echo "=== 密钥环修复 · 交互输入验证桩 ==="
echo "=================================================="
echo "1. 正在准备修复环境..."
sleep 10
printf "2. 请输入任意内容后点击【提交】：[[TEXT]]"
IFS= read -r first_text || true
echo ""
echo "   收到输入: ${first_text}"
sleep 2
printf "3. 请再次输入内容并回车确认？(Y/N) "
IFS= read -r second_text || true
echo ""
echo "   回车收到: ${second_text}"
sleep 1
echo "=================================================="
echo "=== 交互输入验证完成 ==="
exit 0
"""


class TestMyCase(BaseCase):

    def test_mycase_138(self):
        """修复工具--交互验证：验证修复窗口的 TUI 输出与命令执行文本框交互

        覆盖描述中的 5 个步骤:
        1. 修复窗口显示工具标题、脚本 TUI 输出; 命令文本框与【提交】按钮禁用;
        2. 脚本请求用户输入后, 文本框被启用(产品 1.1.7 的提示文案是固定的
           "在此输入并按回车键确认", 没有"等待脚本执行..."的占位文案, 故以
           "请求前禁用 / 请求后启用"作为等价断言);
        3. 输入内容并点击【提交】: 内容进入脚本(回显到 TUI), 文本框与按钮重新禁用;
        4. 再次输入内容并按 Enter: 与提交按钮等价(产品把 returnPressed 接到
           submitInput), 内容同样进入脚本并回显, 输入行重新禁用;
        5. 点击窗口关闭按钮, 修复窗口关闭。

        实现说明: 产品 1.1.7 的现网修复插件已不再使用标准输入的自由文本交互,
        链路只保留 [[TEXT]]/密码提示/debconf 提示三种触发方式。为了让产品真实
        走到"启用命令文本框 → 提交 → 回显"的分支, 用例临时把密钥环修复插件
        入口脚本替换为按 [[TEXT]] 契约实现的交互桩脚本(已按 DPMOBF1 编码,
        否则插件启动时会被跳过), 结束后在 finally 用备份原样恢复并删除备份。
        """
        widget = MyAppWidget(check_start=False)
        try:
            # 自愈: 上次异常退出若遗留了插件入口备份, 先恢复, 避免桩脚本残留
            self.assert_true(
                widget.restore_stale_repair_plugin_backup(PLUGIN_NAME, BACKUP_PATH)
            )
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            # 前置: 进入密钥环修复详情页, 确认工具标题与描述正常展示
            widget.click_keyring_fix_card()
            self.assert_true(widget.get_repair_detail_showing())
            self.assert_true(widget.get_repair_detail_header_showing())
            # 前置: 备份原始插件入口并把入口临时替换为交互桩脚本
            self.assert_true(
                widget.backup_repair_plugin_entry(PLUGIN_NAME, BACKUP_PATH)
            )
            self.assert_true(
                widget.install_repair_plugin_entry(PLUGIN_NAME, FIXTURE_SCRIPT)
            )
            widget.click_start_repair_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=15))

            # 步骤1: 修复窗口显示工具标题与脚本 TUI 输出, 输入框/提交按钮禁用
            assert widget.wait_repair_dialog_window_showing(
                PLUGIN_TITLE, timeout=10
            ), "修复对话框窗口未出现"
            self.assert_true(
                widget.get_repair_output_contains("交互输入验证桩", timeout=10)
            )
            input_state = widget.get_shell_repair_input_state()
            print(f"[2005707] 脚本运行中命令文本框状态: {input_state}")
            self.assert_true(input_state["exists"] and input_state["showing"])
            self.assert_false(input_state["enabled"])
            submit_state = widget.get_shell_repair_submit_state()
            print(f"[2005707] 脚本运行中提交按钮状态: {submit_state}")
            self.assert_true(submit_state["exists"] and submit_state["showing"])
            self.assert_false(submit_state["enabled"])

            # 步骤2: 脚本请求输入后, 命令文本框启用(提示文案由产品固定)
            self.assert_true(widget.wait_shell_repair_input_enabled(timeout=30))
            self.assert_true(
                widget.get_repair_output_contains("请输入任意内容后点击【提交】", timeout=10)
            )
            self.assert_true(widget.get_shell_repair_submit_state()["enabled"])

            # 步骤3: 输入内容 + 点击【提交】→ 内容进入脚本(TUI 回显), 恢复禁用
            self.assert_true(widget.set_shell_repair_input(FIRST_INPUT, PLUGIN_TITLE))
            self.assert_true(widget.click_shell_repair_submit())
            self.assert_true(
                widget.get_repair_output_contains(f"收到输入: {FIRST_INPUT}", timeout=20)
            )
            self.assert_true(widget.wait_shell_repair_input_disabled(timeout=10))
            self.assert_false(widget.get_shell_repair_submit_state()["enabled"])

            # 步骤4: 再次输入 + Enter 提交(产品的 returnPressed 等价路径)
            self.assert_true(widget.wait_shell_repair_input_enabled(timeout=30))
            self.assert_true(widget.set_shell_repair_input(SECOND_INPUT, PLUGIN_TITLE))
            self.assert_true(widget.press_shell_repair_enter(PLUGIN_TITLE))
            self.assert_true(
                widget.get_repair_output_contains(f"回车收到: {SECOND_INPUT}", timeout=20)
            )
            self.assert_true(widget.wait_shell_repair_input_disabled(timeout=10))

            # 脚本执行结束, TUI 输出完整收尾信息
            self.assert_true(widget.get_repair_output_contains("交互输入验证完成", timeout=20))

            # 步骤5: 点击窗口关闭按钮, 修复窗口关闭, 主程序仍正常
            print(f"[2005707] 关闭前窗口标题: {widget.get_pc_manager_window_titles()}")
            assert widget.wait_repair_dialog_window_showing(
                PLUGIN_TITLE, timeout=10
            ), "修复对话框窗口未出现"
            closed = widget.close_repair_dialog_window(PLUGIN_TITLE)
            assert closed, "未找到修复对话框窗口, 无法点击关闭按钮"
            # 收尾: 统一走 finish_repair_flow —— 桩脚本/产品可能补一条
            # dpm_notify 无标题提示框或 openinfobox(timeoutMs=0, 无超时),
            # 不点掉会一直留在桌面; 同时由它关闭修复窗口, 替代原来
            # close_repair_dialog_window + close_repair_completion_dialog
            # 两套写法(两套混用容易漏关提示框, 也难判断窗口是否真的退出)
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])
            # 窗口是否真的关闭以 X11 窗口标题为准: 窗口销毁后 AT-SPI 节点
            # 仍会残留 showing=True, 直接用 get_repair_dialog_showing 会误判。
            assert widget.wait_repair_dialog_window_closed(
                PLUGIN_TITLE, timeout=10
            ), "修复对话框窗口未关闭"
            self.assert_true(widget.get_pc_manager_process_status())

            # 立即恢复插件入口脚本, 缩短桩脚本生效时间
            self.assert_true(
                widget.restore_repair_plugin_entry(PLUGIN_NAME, BACKUP_PATH)
            )
        finally:
            # 回退: 收尾修复流程(点掉 timeoutMs=0 的提示框并关闭修复窗口) →
            # 恢复插件入口(含上次遗留备份) → 删除备份 → 关闭应用
            widget.finish_repair_flow()
            widget.restore_stale_repair_plugin_backup(PLUGIN_NAME, BACKUP_PATH)
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

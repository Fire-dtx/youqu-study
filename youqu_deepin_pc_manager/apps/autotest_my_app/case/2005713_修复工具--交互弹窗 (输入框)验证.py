#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

# 载体插件: 密钥环修复为用户态修复, 不依赖网络/硬件, 适合做交互桩
PLUGIN_NAME = "keyring-fix"
PLUGIN_TITLE = "密钥环修复"
# 插件入口备份(用例结束后必须删除)
BACKUP_PATH = "/tmp/autotest_2005713_keyring_entry.sh.bak"
# 输入框标题前缀, 与 widget.SINGLE_INPUT_DIALOG_TITLE_PREFIX 保持一致
DIALOG_TITLE_PREFIX = "自动测试输入框"
# 三个分支的标题/说明(label)/断言内容
INPUT_TITLE = "自动测试输入框-输入内容"
INPUT_LABEL = "请输入测试内容后点击确认"
INPUT_TEXT = "autotest-input-123"
EMPTY_TITLE = "自动测试输入框-空内容"
EMPTY_LABEL = "请保持输入框为空后点击确认"
CANCEL_TITLE = "自动测试输入框-取消"
CANCEL_LABEL = "点击取消后应返回空字符串"

# 交互桩脚本说明(为什么需要它):
# 本用例验证 dpmapi opensingleinputbox 的单行输入框交互。产品 1.1.7 现网 12 个
# 修复插件里没有调用该接口的脚本, 且"输入后确定返回所输入内容/取消返回空串"
# 需要可控的标题与参数, 因此按产品契约(dpmapi handleOpensingleinputbox ->
# session-daemon ActionExecutor::executeSingleInput)注入一段桩脚本, 依次触发
# "输入内容后确认""空内容确认""取消"三个分支, 并把结果回显到修复窗口 TUI:
# - 有 DPM_LATEST_RESULT 时取该变量(产品给插件注入的最近一次返回值);
# - 没有该变量时回退解析 dpmapi 直出的 __DPMAPI_RESULT__ 行(现网 dpmapi 是
#   二进制, /usr/bin/dpmapi -> /usr/lib/dpmapi/dpmapi-bin, 只打标记行)。
FIXTURE_SCRIPT = """#!/usr/bin/env bash
# AUTOTEST_INTERACTIVE_FIXTURE
echo "=================================================="
echo "=== 单行输入框 opensingleinputbox 交互验证桩 ==="
echo "=================================================="

read_result() {
    local captured="$1"
    local value="${DPM_LATEST_RESULT-}"
    if [ -z "$value" ] && [ -n "$captured" ]; then
        value="$(printf '%s\\n' "$captured" | sed -n 's/^__DPMAPI_RESULT__://p' | tail -1)"
    fi
    printf '%s' "$value"
}

echo "1. 请求单行输入框(输入内容分支)..."
out1="$(dpmapi opensingleinputbox "@@INPUT_TITLE@@" "@@INPUT_LABEL@@" "0")"
rc1=$?
echo "输入分支返回码: $rc1"
echo "输入分支结果: [$(read_result "$out1")]"

echo "2. 请求单行输入框(空内容分支)..."
out2="$(dpmapi opensingleinputbox "@@EMPTY_TITLE@@" "@@EMPTY_LABEL@@" "0")"
rc2=$?
echo "空内容分支返回码: $rc2"
echo "空内容分支结果: [$(read_result "$out2")]"

echo "3. 请求单行输入框(取消分支)..."
out3="$(dpmapi opensingleinputbox "@@CANCEL_TITLE@@" "@@CANCEL_LABEL@@" "0")"
rc3=$?
echo "取消分支返回码: $rc3"
echo "取消分支结果: [$(read_result "$out3")]"

echo "=== 单行输入框交互验证完成 ==="
exit 0
"""
# 脚本里的标题/label 用占位符带入, 避免与 bash 的 ${...} 展开语法冲突
FIXTURE_SCRIPT = (
    FIXTURE_SCRIPT.replace("@@INPUT_TITLE@@", INPUT_TITLE)
    .replace("@@INPUT_LABEL@@", INPUT_LABEL)
    .replace("@@EMPTY_TITLE@@", EMPTY_TITLE)
    .replace("@@EMPTY_LABEL@@", EMPTY_LABEL)
    .replace("@@CANCEL_TITLE@@", CANCEL_TITLE)
    .replace("@@CANCEL_LABEL@@", CANCEL_LABEL)
)


class TestMyCase(BaseCase):

    def test_mycase_141(self):
        """修复工具--交互弹窗 (输入框)验证：验证 dpmapi opensingleinputbox
        弹出的单行输入框, 输入内容/空内容/取消三个分支的行为

        覆盖描述中的步骤与预期:
        1. 运行调用 dpmapi opensingleinputbox 的修复脚本, 弹出带单行输入框的
           对话框: 标题与 label 分别与脚本前两个参数一致, 输入控件真实可编辑;
        2. 输入内容后点击"确定": 对话框关闭, 脚本拿到的结果(DPM_LATEST_RESULT)
           与输入内容一致;
        3. 不输入内容点击"确定": 产品 1.1.7 的"确认"按钮此时仍为 enabled(未置灰),
           按等价语义断言——空内容提交后对话框关闭且返回空字符串, 不会把空内容
           或上一次的残留内容传给脚本;
        4. 点击"取消": 对话框关闭, 返回空字符串;
        三个分支 dpmapi 退出码均为 0, 脚本继续执行到结束。

        实现说明: 标题/按钮文案以产品实际为准——description 的"确定"在
        1.1.7 的中文翻译里是"确认"(与确认框同一按钮文案)。插件入口临时替换为
        桩脚本时必须按 DPMOBF1 编码, 否则产品启动时会跳过该插件; 结束后在
        finally 用备份原样恢复并删除备份。
        """
        widget = MyAppWidget(check_start=False)
        try:
            # 自愈: 上次异常退出若遗留插件入口备份则先恢复; 遗留输入框先关闭
            self.assert_true(
                widget.restore_stale_repair_plugin_backup(PLUGIN_NAME, BACKUP_PATH)
            )
            widget.close_single_input_dialogs(DIALOG_TITLE_PREFIX)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            # 前置: 进入密钥环修复详情页, 确认工具详情正常展示
            widget.click_keyring_fix_card()
            self.assert_true(widget.get_repair_detail_showing())

            # 前置: 备份原始插件入口, 替换为调用 opensingleinputbox 的交互桩
            self.assert_true(
                widget.backup_repair_plugin_entry(PLUGIN_NAME, BACKUP_PATH)
            )
            self.assert_true(
                widget.install_repair_plugin_entry(PLUGIN_NAME, FIXTURE_SCRIPT)
            )

            # 步骤1: 点击开始修复, 修复窗口启动桩脚本并弹出单行输入框
            widget.click_start_repair_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=15))
            input_state = widget.get_single_input_dialog_state(
                INPUT_TITLE, INPUT_LABEL, timeout=30
            )
            print(f"[2005713] 输入内容分支输入框状态: {input_state}")
            self.assert_true(input_state["exists"] and input_state["showing"])
            # 预期: 标题与脚本第一个参数一致, 说明文案与第二个参数一致
            self.assert_true(input_state["title"] == INPUT_TITLE)
            self.assert_true(input_state["label_showing"])
            # 预期: 真实存在可编辑的单行输入控件, 初始为空
            self.assert_true(input_state["text_exists"])
            self.assert_true(input_state["text_showing"])
            self.assert_true(input_state["text_editable"])
            self.assert_true(input_state["text_value"] == "")
            # 预期: 带"取消"和"确认"(description 的"确定")两个按钮
            self.assert_true(
                widget.SINGLE_INPUT_CANCEL_TEXT in input_state["buttons"]
            )
            self.assert_true(widget.SINGLE_INPUT_OK_TEXT in input_state["buttons"])

            # 步骤2: 输入内容后点击"确认", 对话框关闭且结果回传输入内容
            self.assert_true(widget.set_single_input_text(INPUT_TITLE, INPUT_TEXT))
            self.assert_true(
                widget.click_single_input_button(
                    INPUT_TITLE, widget.SINGLE_INPUT_OK_TEXT
                )
            )
            self.assert_true(
                widget.wait_single_input_dialog_closed(INPUT_TITLE, timeout=10)
            )
            self.assert_true(
                widget.get_repair_output_contains("输入分支返回码: 0", timeout=30)
            )
            self.assert_true(
                widget.get_repair_output_contains(
                    f"输入分支结果: [{INPUT_TEXT}]", timeout=30
                )
            )

            # 步骤3: 不输入内容点击"确认"(等价断言: 返回空字符串)
            empty_state = widget.get_single_input_dialog_state(
                EMPTY_TITLE, EMPTY_LABEL, timeout=30
            )
            print(f"[2005713] 空内容分支输入框状态: {empty_state}")
            self.assert_true(empty_state["exists"] and empty_state["showing"])
            self.assert_true(empty_state["title"] == EMPTY_TITLE)
            self.assert_true(empty_state["label_showing"])
            self.assert_true(empty_state["text_exists"])
            # 预期: 输入框为空(产品 1.1.7 此处不禁用"确认"按钮, 见方法 docstring)
            self.assert_true(empty_state["text_value"] == "")
            self.assert_true(
                widget.click_single_input_button(
                    EMPTY_TITLE, widget.SINGLE_INPUT_OK_TEXT
                )
            )
            self.assert_true(
                widget.wait_single_input_dialog_closed(EMPTY_TITLE, timeout=10)
            )
            self.assert_true(
                widget.get_repair_output_contains("空内容分支返回码: 0", timeout=30)
            )
            self.assert_true(
                widget.get_repair_output_contains("空内容分支结果: []", timeout=30)
            )

            # 步骤4: 点击"取消", 对话框关闭且返回空字符串
            cancel_state = widget.get_single_input_dialog_state(
                CANCEL_TITLE, CANCEL_LABEL, timeout=30
            )
            print(f"[2005713] 取消分支输入框状态: {cancel_state}")
            self.assert_true(cancel_state["exists"] and cancel_state["showing"])
            self.assert_true(cancel_state["title"] == CANCEL_TITLE)
            self.assert_true(cancel_state["label_showing"])
            self.assert_true(
                widget.click_single_input_button(
                    CANCEL_TITLE, widget.SINGLE_INPUT_CANCEL_TEXT
                )
            )
            self.assert_true(
                widget.wait_single_input_dialog_closed(CANCEL_TITLE, timeout=10)
            )
            self.assert_true(
                widget.get_repair_output_contains("取消分支返回码: 0", timeout=30)
            )
            self.assert_true(
                widget.get_repair_output_contains("取消分支结果: []", timeout=30)
            )
            # 脚本被三次输入框阻塞后均正常继续, 最终执行结束
            self.assert_true(
                widget.get_repair_output_contains("单行输入框交互验证完成", timeout=30)
            )

            # 收尾: 脚本 exit 0 后修复窗口不会自己关; 若脚本/产品再补一条
            # 提示框, openinfobox 的 timeoutMs=0 表示没有超时, 不点就永远留在
            # 桌面并阻塞脚本。finish_repair_flow 清掉全部提示框形态并关闭修复
            # 窗口, 并断言窗口已消失
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])

            # 立即恢复插件入口脚本, 缩短桩脚本生效时间
            self.assert_true(
                widget.restore_repair_plugin_entry(PLUGIN_NAME, BACKUP_PATH)
            )
        finally:
            # 回退: 关闭残留输入框 -> 收尾修复流程(提示框 + 修复窗口)
            # -> 恢复插件入口 -> 关闭应用 -> 再兜底关窗
            widget.close_single_input_dialogs(DIALOG_TITLE_PREFIX, rounds=3)
            widget.finish_repair_flow()
            widget.restore_stale_repair_plugin_backup(PLUGIN_NAME, BACKUP_PATH)
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()
            widget.close_single_input_dialogs(DIALOG_TITLE_PREFIX, rounds=2)

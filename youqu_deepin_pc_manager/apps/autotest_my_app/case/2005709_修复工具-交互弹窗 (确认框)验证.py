#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

# 载体插件: 密钥环修复为用户态修复, 不依赖网络/硬件, 适合做交互桩
PLUGIN_NAME = "keyring-fix"
PLUGIN_TITLE = "密钥环修复"
# 插件入口备份(用例结束后必须删除)
BACKUP_PATH = "/tmp/autotest_2005709_keyring_entry.sh.bak"
# 两轮确认框的标题/正文(脚本参数即断言依据)
CANCEL_TITLE = "自动测试确认框-取消分支"
CANCEL_MESSAGE = "脚本参数内容-取消分支，点击取消后脚本应继续执行"
OK_TITLE = "自动测试确认框-确认分支"
OK_MESSAGE = "脚本参数内容-确认分支，点击确认后脚本应继续执行"

# 交互桩脚本说明(为什么需要它):
# 本用例验证的是 dpmapi openconfirm 的结构化确认框交互。产品 1.1.7 现网
# 12 个修复插件只用 dpmapi openinfobox(提示框)/dpm_prompt, 没有任何插件调用
# openconfirm, 因此按产品契约(dpmapi_command.cpp handleOpenconfirm ->
# session-daemon ActionExecutor::executeConfirm)注入一段桩脚本, 依次触发
# "取消"和"确认"两轮确认框, 并把 dpmapi 打印的 __DPMAPI_RESULT__ 回显到修复
# 窗口 TUI, 证明按钮选择结果确实回传给了脚本(0=取消, 1=确认)。
FIXTURE_SCRIPT = (
    "#!/usr/bin/env bash\n"
    "# AUTOTEST_INTERACTIVE_FIXTURE\n"
    'echo "=================================================="\n'
    'echo "=== 确认框 openconfirm 交互验证桩 ==="\n'
    'echo "=================================================="\n'
    'echo "1. 请求确认框(取消分支)..."\n'
    f'cancel_output="$(dpmapi openconfirm "{CANCEL_TITLE}" "{CANCEL_MESSAGE}")"\n'
    'echo "取消分支 dpmapi 返回码: $?"\n'
    'echo "取消分支结果: ${cancel_output#__DPMAPI_RESULT__:}"\n'
    'echo "2. 请求确认框(确认分支)..."\n'
    f'ok_output="$(dpmapi openconfirm "{OK_TITLE}" "{OK_MESSAGE}")"\n'
    'echo "确认分支 dpmapi 返回码: $?"\n'
    'echo "确认分支结果: ${ok_output#__DPMAPI_RESULT__:}"\n'
    'echo "=== 确认框交互验证完成 ==="\n'
    "exit 0\n"
)


class TestMyCase(BaseCase):

    def test_mycase_139(self):
        """修复工具-交互弹窗 (确认框)验证

        覆盖描述中的步骤与预期:
        1. 运行一个调用 dpmapi openconfirm 的修复脚本, 观察脚本执行过程;
        2. 脚本请求确认时弹出带"取消"和"确认"按钮的确认对话框
           (描述中的"确定"在产品 1.1.7 的 DDialog 翻译里是"确认", 属同一
           按钮的译名差异, 以产品实际文案断言);
        3. 对话框标题与正文与脚本参数一致: 标题取 dialog 的 accessible name
           (即 DDialog windowTitle), 正文取 session 总线上 ExecuteUserAction
           请求体里的 message(与 executeConfirm() 传给 setMessage 的数据同源,
           因 DDialogMessageLabel 不暴露 accessible text);
        4. 点击"取消"/"确认"后确认框关闭, 脚本收到对应结果(0/1)并继续执行,
           证明交互结果真实回传。

        实现说明: 产品现网修复插件都不调用 openconfirm, 因此把密钥环修复插件
        入口临时替换为调用 dpmapi openconfirm 的桩脚本(按 DPMOBF1 编码, 否则
        插件启动时会被跳过), 结束后在 finally 用备份原样恢复并删除备份。
        """
        widget = MyAppWidget(check_start=False)
        try:
            # 自愈: 上次异常退出若遗留插件入口备份则先恢复; 遗留确认框先关闭
            self.assert_true(
                widget.restore_stale_repair_plugin_backup(PLUGIN_NAME, BACKUP_PATH)
            )
            widget.close_confirm_dialogs("自动测试确认框")

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            # 前置: 进入密钥环修复详情页, 确认工具详情正常展示
            widget.click_keyring_fix_card()
            self.assert_true(widget.get_repair_detail_showing())

            # 前置: 备份原始插件入口, 替换为调用 dpmapi openconfirm 的交互桩
            self.assert_true(
                widget.backup_repair_plugin_entry(PLUGIN_NAME, BACKUP_PATH)
            )
            self.assert_true(
                widget.install_repair_plugin_entry(PLUGIN_NAME, FIXTURE_SCRIPT)
            )

            # 脚本触发 openconfirm 前先启动 session 总线监听, 用于核对弹窗
            # 标题/正文与脚本参数完全一致
            self.assert_true(widget.start_confirm_dbus_monitor())

            # 步骤1: 点击开始修复, 修复窗口启动桩脚本
            widget.click_start_repair_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=15))

            # 步骤2: 第一轮确认框(取消分支)弹出
            cancel_state = widget.get_confirm_dialog_state(CANCEL_TITLE, timeout=30)
            print(f"[2005709] 取消分支确认框状态: {cancel_state}")
            self.assert_true(cancel_state["exists"] and cancel_state["showing"])
            # 预期: 标题与脚本参数一致
            self.assert_true(cancel_state["title"] == CANCEL_TITLE)
            # 预期: 带"取消"和"确认"两个按钮
            self.assert_true(
                widget.CONFIRM_DIALOG_CANCEL_TEXT in cancel_state["buttons"]
            )
            self.assert_true(widget.CONFIRM_DIALOG_OK_TEXT in cancel_state["buttons"])
            # 预期: 正文已真实渲染, 且总线请求参数与脚本参数一致
            self.assert_true(cancel_state["message_label_showing"])
            self.assert_true(
                widget.wait_confirm_dbus_request(CANCEL_TITLE, CANCEL_MESSAGE, timeout=10)
            )

            # 步骤3: 点击"取消", 确认框关闭, 脚本收到 0 并继续
            self.assert_true(
                widget.click_confirm_dialog_button(
                    CANCEL_TITLE, widget.CONFIRM_DIALOG_CANCEL_TEXT
                )
            )
            self.assert_true(widget.wait_confirm_dialog_closed(CANCEL_TITLE, timeout=10))
            self.assert_true(widget.get_repair_output_contains("取消分支结果: 0", timeout=30))

            # 步骤4: 第二轮确认框(确认分支)弹出, 标题/正文同样与脚本参数一致
            ok_state = widget.get_confirm_dialog_state(OK_TITLE, timeout=30)
            print(f"[2005709] 确认分支确认框状态: {ok_state}")
            self.assert_true(ok_state["exists"] and ok_state["showing"])
            self.assert_true(ok_state["title"] == OK_TITLE)
            self.assert_true(widget.CONFIRM_DIALOG_CANCEL_TEXT in ok_state["buttons"])
            self.assert_true(widget.CONFIRM_DIALOG_OK_TEXT in ok_state["buttons"])
            self.assert_true(ok_state["message_label_showing"])
            self.assert_true(
                widget.wait_confirm_dbus_request(OK_TITLE, OK_MESSAGE, timeout=10)
            )

            # 步骤5: 点击"确认", 确认框关闭, 脚本收到 1 并执行结束
            self.assert_true(
                widget.click_confirm_dialog_button(OK_TITLE, widget.CONFIRM_DIALOG_OK_TEXT)
            )
            self.assert_true(widget.wait_confirm_dialog_closed(OK_TITLE, timeout=10))
            self.assert_true(widget.get_repair_output_contains("确认分支结果: 1", timeout=30))
            self.assert_true(
                widget.get_repair_output_contains("确认框交互验证完成", timeout=30)
            )

            # 收尾: 修复脚本结束(exit 0)后修复窗口不会自己关; 且脚本/产品可能
            # 追加 dpm_notify 无标题提示框或 openinfobox(其 timeoutMs=0 表示没有
            # 超时, 不点会一直留在桌面并阻塞脚本)。finish_repair_flow 清掉全部
            # 提示框形态并关闭修复窗口, 明确验证窗口已消失, 避免遗留污染后续用例
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])

            # 立即恢复插件入口脚本, 缩短桩脚本生效时间
            self.assert_true(
                widget.restore_repair_plugin_entry(PLUGIN_NAME, BACKUP_PATH)
            )
        finally:
            # 回退: 停监听 -> 关闭残留确认框 -> 收尾修复流程(提示框 + 修复窗口)
            # -> 恢复插件入口 -> 关闭应用
            widget.stop_confirm_dbus_monitor()
            widget.close_confirm_dialogs("自动测试确认框", rounds=3)
            widget.finish_repair_flow()
            widget.restore_stale_repair_plugin_backup(PLUGIN_NAME, BACKUP_PATH)
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()
            widget.close_confirm_dialogs("自动测试确认框", rounds=2)

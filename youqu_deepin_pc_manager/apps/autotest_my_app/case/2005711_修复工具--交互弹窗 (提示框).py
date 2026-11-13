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
# 插件入口备份(用例结束后必须删除)
BACKUP_PATH = "/tmp/autotest_2005711_keyring_entry.sh.bak"
# 提示框标题/正文(脚本参数即断言依据)
INFO_TITLE = "自动测试提示框-参数校验"
INFO_MESSAGE = "脚本参数内容-提示框：仅应出现一个确定按钮"

# 交互桩脚本说明(为什么需要它):
# 本用例验证的是 dpmapi openinfobox(提示框)的结构化交互。现网插件虽然普遍
# 调用 openinfobox, 但标题/正文由插件内部逻辑决定, 无法让"标题和内容与脚本
# 参数一致"这一预期在固定参数上被精确核对; 因此按产品契约
# (dpmapi_command.cpp handleOpeninfobox -> session-daemon
# ActionExecutor::executeMessage)注入一段桩脚本, 用可控的标题/正文触发一次
# 提示框, 并把 dpmapi 的返回码回显到修复窗口 TUI, 证明脚本确实被提示框阻塞、
# 点击"确定"后拿到 ok(退出码 0)继续执行。
FIXTURE_SCRIPT = (
    "#!/usr/bin/env bash\n"
    "# AUTOTEST_INTERACTIVE_FIXTURE\n"
    'echo "=================================================="\n'
    'echo "=== 提示框 openinfobox 交互验证桩 ==="\n'
    'echo "=================================================="\n'
    'echo "1. 请求提示框(仅确定按钮)..."\n'
    f'dpmapi openinfobox "{INFO_TITLE}" "{INFO_MESSAGE}"\n'
    "rc=$?\n"
    'echo "提示框 dpmapi 返回码: $rc"\n'
    'if [ "$rc" -ne 0 ]; then\n'
    '    echo "提示框请求失败, 脚本中止"\n'
    '    exit "$rc"\n'
    "fi\n"
    'echo "=== 提示框交互验证完成 ==="\n'
    "exit 0\n"
)


class TestMyCase(BaseCase):

    def test_mycase_140(self):
        """修复工具--交互弹窗 (提示框)：验证修复脚本调用 dpmapi openinfobox
        时弹出信息提示框, 且标题/内容与脚本参数一致、只含"确定"一个按钮

        覆盖描述中的步骤与预期:
        1. 运行一个调用 dpmapi openinfobox 的修复脚本(描述举例"修复依赖关系
           不满足", 该脚本依赖外网/apt 仓库, 测试机不可达; 按等价实现改用
           密钥环修复插件作为载体注入调用 openinfobox 的桩脚本, 产品仍真实
           走到 session-daemon 的提示框分支);
        2. 脚本请求提示框时弹出信息提示框, 标题取 dialog 的 accessible name
           (即 DDialog windowTitle), 正文取 session 总线上 ExecuteUserAction
           请求体里的 message(与 executeMessage() 传给 setMessage 的数据同源,
           因 DDialogMessageLabel 不暴露 accessible text);
        3. 提示框只含"确定"一个按钮(产品 1.1.7 该按钮文案为 OK 的中文翻译
           "确定"), 点击后提示框关闭, 脚本拿到 dpmapi 退出码 0 并继续执行,
           证明交互结果真实回传。

        实现说明: 插件入口临时替换为桩脚本时必须按 DPMOBF1 编码, 否则产品
        启动时会跳过该插件; 结束后在 finally 用备份原样恢复并删除备份。
        """
        widget = MyAppWidget(check_start=False)
        try:
            # 自愈: 上次异常退出若遗留插件入口备份则先恢复; 遗留提示框先关闭
            self.assert_true(
                widget.restore_stale_repair_plugin_backup(PLUGIN_NAME, BACKUP_PATH)
            )
            widget.close_info_dialogs("自动测试提示框")

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            # 前置: 进入密钥环修复详情页, 确认工具详情正常展示
            widget.click_keyring_fix_card()
            self.assert_true(widget.get_repair_detail_showing())

            # 前置: 备份原始插件入口, 替换为调用 dpmapi openinfobox 的交互桩
            self.assert_true(
                widget.backup_repair_plugin_entry(PLUGIN_NAME, BACKUP_PATH)
            )
            self.assert_true(
                widget.install_repair_plugin_entry(PLUGIN_NAME, FIXTURE_SCRIPT)
            )

            # 脚本触发提示框前先启动 session 总线监听, 用于核对弹窗标题/正文
            # 与脚本参数完全一致, 并确认走的是 OpenMessage(提示框)分支
            self.assert_true(widget.start_confirm_dbus_monitor())

            # 步骤1: 点击开始修复, 修复窗口启动桩脚本
            widget.click_start_repair_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=15))

            # 步骤2: 脚本调用 openinfobox, 提示框弹出
            info_state = widget.get_info_dialog_state(INFO_TITLE, timeout=30)
            print(f"[2005711] 提示框状态: {info_state}")
            self.assert_true(info_state["exists"] and info_state["showing"])
            # 预期: 标题与脚本参数一致
            self.assert_true(info_state["title"] == INFO_TITLE)
            # 预期: 仅包含"确定"一个按钮
            self.assert_true(info_state["buttons"] == [widget.INFOBOX_OK_TEXT])
            # 预期: 正文已真实渲染, 且总线请求参数与脚本参数一致
            self.assert_true(info_state["message_label_showing"])
            self.assert_true(
                widget.wait_confirm_dbus_request(INFO_TITLE, INFO_MESSAGE, timeout=10)
            )
            # 预期: 请求类型为 OpenMessage(openinfobox 对应分支), 非确认框
            self.assert_true(
                'string "OpenMessage"' in widget.get_confirm_dbus_request_text()
            )

            # 步骤3: 点击"确定", 提示框关闭, 脚本拿到退出码 0 并继续执行
            self.assert_true(
                widget.click_confirm_dialog_button(
                    INFO_TITLE, widget.INFOBOX_OK_TEXT
                )
            )
            self.assert_true(widget.wait_info_dialog_closed(INFO_TITLE, timeout=10))
            self.assert_true(
                widget.get_repair_output_contains("提示框 dpmapi 返回码: 0", timeout=30)
            )
            self.assert_true(
                widget.get_repair_output_contains("提示框交互验证完成", timeout=30)
            )

            # 收尾: 脚本 exit 0 后修复窗口不会自己关; 若产品/脚本再补一条
            # 提示框, 其 openinfobox 的 timeoutMs=0 表示没有超时, 不点就永远
            # 留在桌面并阻塞脚本。finish_repair_flow 清掉全部提示框形态并关闭
            # 修复窗口, 并明确断言窗口已消失
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])

            # 立即恢复插件入口脚本, 缩短桩脚本生效时间
            self.assert_true(
                widget.restore_repair_plugin_entry(PLUGIN_NAME, BACKUP_PATH)
            )
        finally:
            # 回退: 停监听 -> 关闭残留提示框 -> 收尾修复流程(提示框 + 修复窗口)
            # -> 恢复插件入口 -> 关闭应用
            widget.stop_confirm_dbus_monitor()
            widget.close_info_dialogs("自动测试提示框", rounds=3)
            widget.finish_repair_flow()
            widget.restore_stale_repair_plugin_backup(PLUGIN_NAME, BACKUP_PATH)
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()
            widget.close_info_dialogs("自动测试提示框", rounds=2)

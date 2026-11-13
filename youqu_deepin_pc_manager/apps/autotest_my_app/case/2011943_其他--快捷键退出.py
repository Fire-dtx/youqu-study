#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_229(self):
        """其他--快捷键退出：连续按 Alt+F4 后电脑管家自动关闭

        V20 上 Alt+F4 由 kglobalaccel5 托管, start_pc_manager 为避免该快捷键
        持续触发会先结束它; 用例按其前提恢复 kglobalaccel5 后再发送快捷键,
        连按两次确保窗口与进程均退出, 结束后清理快捷键守护进程。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        self.assert_true(widget.get_main_page_modules_showing())
        try:
            widget.exit_pc_manager_by_shortcut()
            # 连续按第二次: 窗口已关闭时应无副作用
            widget.run_cmd(
                "xdotool key --clearmodifiers alt+F4",
                timeout=5,
                out_debug_flag=False,
            )
            self.assert_true(widget.wait_pc_manager_exit(timeout=15))
            self.assert_false(widget.get_pc_manager_process_status())
            self.assert_false(bool(widget.get_main_window_id()))
        finally:
            # 恢复用例开始时的环境: start_pc_manager 会结束 kglobalaccel5
            widget.run_cmd(
                "pkill -x kglobalaccel5 >/dev/null 2>&1; true",
                timeout=5,
                out_debug_flag=False,
            )

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/09/28
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_005(self):
        """应用窗口最大化设置：最大化后还原，验证窗口状态切换"""
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        # 通过 Super+Up 最大化窗口
        widget.maximize_window_by_shortcut()
        # 断言窗口已最大化
        self.assert_true(widget.get_window_maximized_status())
        # 通过 Super+Down 还原窗口
        widget.restore_window_by_shortcut()
        sleep(1)
        # 断言窗口已取消最大化
        self.assert_false(widget.get_window_maximized_status())

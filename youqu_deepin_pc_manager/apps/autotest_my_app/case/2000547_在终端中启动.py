#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/09/28
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_014(self):
        """在终端中启动：打开终端，在终端命令行中输入命令启动电脑管家，
        验证主进程启动且主界面四大模块正常显示"""
        widget = MyAppWidget(check_start=False)
        # 确保先关闭已运行的电脑管家
        widget.kill_pc_manager()
        # 打开终端, 在终端中输入命令启动电脑管家
        self.assert_true(widget.launch_from_terminal())
        # 断言电脑管家主进程已启动
        self.assert_true(widget.get_pc_manager_process_status())
        # 断言主界面四大模块已显示
        self.assert_true(widget.get_main_page_modules_showing())

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/09/28
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

# 主界面左侧导航栏的四个模块(界面顺序)
MAIN_NAV_ITEMS = ["系统检测", "系统优化", "修复工具", "实用工具"]


class TestMyCase(BaseCase):

    def test_mycase_004(self):
        """应用主页显示：打开电脑管家, 主界面显示四大块
        (左侧导航栏: 系统检测、系统优化、修复工具、实用工具), 主进程正常启动。"""
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        # 断言电脑管家主进程已启动
        self.assert_true(widget.get_pc_manager_process_status())
        # 断言左侧导航栏恰好是四大模块, 且名称与顺序正确
        self.assert_equal(MAIN_NAV_ITEMS, widget.get_main_nav_item_names())
        # 断言四大模块均以非零尺寸可见
        self.assert_true(widget.get_main_page_modules_showing())

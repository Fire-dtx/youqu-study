#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_061(self):
        """电脑管家--功能模块：验证系统检测相关功能正常"""
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        widget.get_detection_cards_view_showing()
        self.assert_true(widget.get_detection_page_showing())

    def test_mycase_274(self):
        """电脑管家--功能模块：点击系统检测导航，验证系统检测页面及功能模块正常显示"""
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        # 断言电脑管家主进程已启动
        self.assert_true(widget.get_pc_manager_process_status())
        # 点击左侧导航"系统检测"
        widget.click_detection_nav_by_attr()
        # 断言系统检测页面已显示
        self.assert_true(widget.get_detection_page_showing())
        # 断言系统检测页面功能模块(立即检测按钮)已显示
        self.assert_true(widget.get_detection_functional_modules_showing())

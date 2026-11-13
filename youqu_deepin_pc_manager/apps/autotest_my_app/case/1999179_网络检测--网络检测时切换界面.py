#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

class TestMyCase(BaseCase):

    def test_mycase_108(self):
        """网络检测时切换界面：点击"网络检测"卡片后立即切换到修复工具页再切回,
        断言应用进程存活、系统检测页可再次正常显示, 检测状态不导致界面崩溃。"""
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        self.assert_true(widget.run_detection_item("网络检测"))
        widget.click_repair_nav()
        self.assert_true(widget.get_repair_page_showing(timeout=15))
        self.assert_true(widget.get_pc_manager_process_status())

        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing(timeout=20))
        self.assert_true(widget.get_pc_manager_process_status())

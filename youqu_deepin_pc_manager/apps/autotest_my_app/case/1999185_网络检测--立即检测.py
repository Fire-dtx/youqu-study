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

    def test_mycase_026(self):
        """网络检测立即检测：在系统检测首页点击"网络检测"卡片(立即检测入口)
        真实触发检测, 断言检测页面进入运行时态并完成 7 项检测。"""
        widget = MyAppWidget(check_start=False)

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        self.assert_true(widget.run_detection_item("网络检测"))
        self.assert_true(widget.get_detection_item_present("网络检测", "网络访问"))
        state = widget.get_detection_group_state("网络检测")
        self.assert_equal(state["total"], state["checked"])
        self.assert_true(widget.get_detection_page_showing(timeout=20))

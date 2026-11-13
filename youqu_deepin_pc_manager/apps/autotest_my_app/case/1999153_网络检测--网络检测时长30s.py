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

    def test_mycase_096(self):
        """网络检测时长：网络连接正常时点击"网络检测"卡片执行真实检测,
        断言检测跑完(7/7 项)且总耗时不超过 30s。"""
        widget = MyAppWidget(check_start=False)
        import time

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        start = time.time()
        self.assert_true(widget.run_detection_item("网络检测"))
        elapsed = time.time() - start
        logger.info(f"网络检测耗时: {elapsed:.1f}s")

        state = widget.get_detection_group_state("网络检测")
        self.assert_equal(state["total"], state["checked"])
        self.assert_true(elapsed <= 30)

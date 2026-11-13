#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_126(self):
        """空间清理-扫描进度显示：验证点击扫描按钮后扫描开始
        (进度条出现, 或数据量小导致扫描瞬间完成而直接显示结果页)"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.create_all_space_clean_junk()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_scan_started(timeout=30))
            self.assert_true(widget.get_space_clean_has_junk(timeout=180))
        finally:
            widget.remove_all_space_clean_junk()

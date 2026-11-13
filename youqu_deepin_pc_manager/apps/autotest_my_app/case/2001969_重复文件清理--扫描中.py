#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_277(self):
        """重复文件清理--扫描中：验证点击重复文件清理卡片后扫描自动开始
        (扫描进度条出现, 或数据量小导致扫描瞬间完成而直接显示结果页)"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_optimization_card_by_name("重复文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_dup_file_scan_started(timeout=30))
            self.assert_true(widget.get_dup_file_scan_completed(timeout=120))
        finally:
            widget.kill_pc_manager()

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from datetime import datetime

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_068(self):
        """系统检测首页--当天检测时间显示：全面检测完成后返回首页，验证当天检测时间已显示"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav_by_attr()
        self.assert_true(widget.get_detection_page_showing())
        widget.click_detection_full_scan_button()
        sleep(2)
        self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
        self.assert_true(widget.get_detection_page_showing())
        self.assert_true(widget.get_last_score_displayed())
        time_text = widget.get_detection_scan_time_text()
        if time_text:
            today_str = datetime.now().strftime("%Y-%m-%d")
            self.assert_true(today_str in time_text)

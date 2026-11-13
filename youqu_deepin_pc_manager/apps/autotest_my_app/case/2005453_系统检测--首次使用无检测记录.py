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

    def test_mycase_062(self):
        """系统检测--首次使用无检测记录：验证首次进入系统检测页面时，
        页面正常显示且无历史检测记录（无上次检测分数和时间）"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        # 导航到系统检测页面
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        # 验证检测卡片视图显示（检测概览页正常）
        self.assert_true(widget.get_detection_cards_view_showing())
        # 验证全面检测按钮可用
        self.assert_true(widget.get_detection_full_scan_button_showing())
        # 验证首次使用无检测记录：评分标签文本为空或不含"上次检测分数"
        score_text = widget.get_detection_score_text()
        self.assert_true(not score_text or "上次检测分数" not in score_text)
        # 再次确认检测页面仍然正常显示
        self.assert_true(widget.get_detection_page_showing())

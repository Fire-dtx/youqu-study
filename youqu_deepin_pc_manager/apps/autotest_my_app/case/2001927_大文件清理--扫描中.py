#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_282(self):
        """大文件清理--扫描中：验证进入大文件清理页面后自动开始扫描
        (扫描进度出现, 或数据量小导致扫描瞬间完成而直接显示结果页)"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        # 导航到系统优化页面
        widget.click_optimization_nav_by_attr()
        self.assert_true(widget.get_optimization_page_showing())
        # 点击"大文件清理"卡片进入插件运行时页面
        widget.click_optimization_card_by_name("大文件清理")
        self.assert_true(widget.get_optimization_runtime_page_showing())
        # 进入页面后扫描自动开始, 验证扫描已启动(扫描视图或结果页可见)
        self.assert_true(widget.get_large_file_scan_started(timeout=30))
        # 等待扫描完成, 验证结果页或空状态页显示
        self.assert_true(widget.get_large_file_scan_completed(timeout=120))
        # 清理：关闭电脑管家
        widget.kill_pc_manager()

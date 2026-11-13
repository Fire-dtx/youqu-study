#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_372(self):
        """大文件清理--清理结果无大文件：验证系统无大文件时大文件清理扫描结果显示空状态"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理上一次可能残留的测试大文件，确保系统无大文件
        widget.remove_large_test_file()
        widget.remove_test_large_files()
        isolated = []
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击大文件清理卡片，进入大文件清理页面(扫描自动开始)
            isolated = widget.isolate_foreign_large_files()
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            # 等待扫描完成
            self.assert_true(widget.get_large_file_scan_completed(timeout=180))
            # 验证扫描结果为空(未检测到大文件，显示空状态页)
            self.assert_true(widget.get_large_file_empty_showing())
        finally:
            # 恢复临时移出扫描范围的环境大文件
            widget.restore_foreign_large_files(isolated)
            # 清理测试残留
            widget.remove_large_test_file()
            widget.remove_test_large_files()

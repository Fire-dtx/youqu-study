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

    def test_mycase_336(self):
        """大文件清理--筛选无结果：扫描到大文件后切换大小筛选条件，
        使结果集为空，验证筛选无结果状态正确显示"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：创建测试大文件(110MB, 超过100MB阈值, 满足默认筛选条件)
        widget.create_large_test_file()
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
            # 验证检测到大文件(结果页显示)
            self.assert_true(widget.get_large_file_result_showing())
            # 切换大小筛选为 ≥1GB(索引3), 110MB文件不满足该条件，筛选结果为空
            widget.select_large_file_size_filter(3)
            # 验证筛选无结果状态正确显示
            self.assert_true(widget.get_large_file_no_match_showing(timeout=10))
            # 切换回默认筛选 ≥100MB(索引0)，验证结果重新显示
            widget.select_large_file_size_filter(0)
            self.assert_true(widget.get_large_file_result_showing())
        finally:
            widget.restore_foreign_large_files(isolated)
            # 清理测试大文件
            widget.remove_large_test_file()

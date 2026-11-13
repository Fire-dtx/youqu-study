#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_373(self):
        """大文件清理--有大文件：Documents 目录存在大文件时结果页显示文件列表,
        列表按文件大小倒序排列"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理上一次可能残留的测试大文件
        widget.remove_documents_large_file()
        widget.remove_visible_large_test_file()
        isolated = []
        try:
            # 前置：隔离测试机上已存在的大文件, 避免挤占结果表格可视行
            isolated = widget.isolate_foreign_large_files()
            # 前置：Documents 下创建 200MB 大文件, 家目录下创建 110MB 大文件
            widget.create_documents_large_file(size_mb=200)
            widget.create_visible_large_test_file(size_mb=110)
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 步骤1: 点击"大文件清理"，观察结果页面
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_large_file_scan_completed(timeout=180))
            self.assert_true(widget.get_large_file_result_showing())
            filenames = widget.get_large_file_table_filenames()
            # 两个大文件都出现在列表中
            self.assert_true(
                any("autotest_doc_large.bin" in name for name in filenames)
            )
            self.assert_true(
                any("autotest_large_visible.bin" in name for name in filenames)
            )
            # 列表按大小倒序: 200MB 的 Documents 文件排在 110MB 文件之前
            doc_index = next(
                i for i, name in enumerate(filenames)
                if "autotest_doc_large.bin" in name
            )
            visible_index = next(
                i for i, name in enumerate(filenames)
                if "autotest_large_visible.bin" in name
            )
            self.assert_true(doc_index < visible_index)
        finally:
            widget.remove_documents_large_file()
            widget.remove_visible_large_test_file()
            widget.restore_foreign_large_files(isolated)

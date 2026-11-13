#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_281(self):
        """大文件清理-扫描范围验证：/home 下 >=100MB 的大文件被扫描到,
        /home 隐藏目录(.cache)中的大文件与不足 100MB 的文件不被扫描"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理上一次可能残留的测试大文件
        widget.remove_visible_large_test_file()
        widget.remove_visible_large_test_file("autotest_small_visible.bin")
        widget.remove_hidden_large_test_file()
        isolated = []
        try:
            # 前置：隔离测试机上已存在的大文件, 保证结果表格能直接读到测试文件
            isolated = widget.isolate_foreign_large_files()
            # 前置：/home 下创建 110MB 大文件; 隐藏目录(.cache)创建 110MB 大文件
            widget.create_visible_large_test_file(size_mb=110)
            widget.create_hidden_large_test_file(size_mb=110)
            # 前置：/home 下创建 90MB 文件(不足阈值, 不应出现在结果里)
            widget.create_visible_large_test_file(
                size_mb=90, name="autotest_small_visible.bin"
            )
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 步骤1: 点击"大文件清理"，检查扫描结果
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_large_file_scan_completed(timeout=180))
            self.assert_true(widget.get_large_file_result_showing())
            filenames = widget.get_large_file_table_filenames()
            # /home 下的 110MB 文件被扫描到
            self.assert_true(
                any("autotest_large_visible.bin" in name for name in filenames)
            )
            # 隐藏目录中的文件不被扫描
            self.assert_false(
                any("large_hidden.bin" in name for name in filenames)
            )
            # 只显示 >=100MB 的文件
            self.assert_false(
                any("autotest_small_visible.bin" in name for name in filenames)
            )
        finally:
            widget.remove_visible_large_test_file()
            widget.remove_visible_large_test_file("autotest_small_visible.bin")
            widget.remove_hidden_large_test_file()
            widget.restore_foreign_large_files(isolated)

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_278(self):
        """重复文件清理--扫描范围验证：仅扫描 /home 下非隐藏目录文件,
        /home 隐藏目录与 /home 之外的重复文件不参与扫描"""
        widget = MyAppWidget(check_start=False)
        # 前置：关闭电脑管家
        widget.kill_pc_manager()
        # 前置：在三处各创建一组(2个)内容相同的文件
        widget.create_dup_file_scope_files()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 步骤1: 点击"重复文件清理", 等待扫描完成
            widget.click_optimization_card_by_name("重复文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_dup_file_scan_completed(timeout=240))
            self.assert_true(widget.get_dup_file_result_showing())
            # /home 非隐藏目录中的重复文件被扫描到
            filenames = widget.get_dup_file_table_filenames()
            self.assert_true(
                any("autotest_dup_visible.bin" in name for name in filenames)
            )
            # 隐藏目录与 /home 之外的重复文件不在扫描范围内
            self.assert_false(
                any("autotest_dup_hidden.bin" in name for name in filenames)
            )
            self.assert_false(
                any("autotest_dup_outside.bin" in name for name in filenames)
            )
        finally:
            widget.remove_dup_file_scope_files()
            widget.kill_pc_manager()

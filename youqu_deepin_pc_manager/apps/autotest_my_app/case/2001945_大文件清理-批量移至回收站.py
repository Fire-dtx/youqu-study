#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import glob
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_330(self):
        """大文件清理-批量移至回收站：验证可批量选中多个大文件并移至回收站"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：创建测试用大文件(3个100MB文件, 满足大文件清理>=100MB阈值)
        widget.create_test_large_files()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击大文件清理卡片, 进入大文件清理页面(插件自动开始扫描)
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            # 等待扫描完成并验证结果页面显示
            self.assert_true(widget.get_large_file_result_page_showing(timeout=180))
            # 验证检测到大文件(结果页而非空状态页)
            self.assert_true(widget.get_large_file_has_results(timeout=15))
            # 批量选中多行大文件(选中第0行和第1行)
            widget.click_large_file_table_checkboxes([0, 1])
            # 验证执行按钮可用(选中文件后按钮应启用)
            self.assert_true(widget.get_large_file_execute_button_enabled())
            # 点击执行按钮, 将选中的大文件移至回收站(默认操作为"移至回收站")
            widget.click_large_file_execute_button()
            sleep(5)
            # 验证选中的大文件已被移至回收站(2个文件被移至回收站)
            home = os.path.expanduser("~")
            trash_pattern = os.path.join(
                home, ".local", "share", "Trash", "files", "large_test_*.bin"
            )
            trash_found = False
            for _ in range(10):
                trash_files = glob.glob(trash_pattern)
                if len(trash_files) >= 2:
                    trash_found = True
                    break
                sleep(1)
            self.assert_true(trash_found)
            # 验证未被选中的文件仍在原位(3个中移走2个, 应剩1个)
            remaining_pattern = os.path.join(
                home, "autotest_large_files", "large_test_*.bin"
            )
            remaining_files = glob.glob(remaining_pattern)
            self.assert_true(len(remaining_files) == 1)
        finally:
            # 清理测试大文件(包括回收站中的副本)
            widget.remove_test_large_files()

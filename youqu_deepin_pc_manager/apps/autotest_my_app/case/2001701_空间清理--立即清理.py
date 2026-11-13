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

    def test_mycase_279(self):
        """空间清理--立即清理：回收站存在 3G 大文件时扫描出可清理项,
        点击清理选中项后垃圾全部清理, 点击左上角返回回到系统优化页面"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：按扫描规则预创建全部类型垃圾, 保证多次执行后仍有可清理数据
        widget.create_all_space_clean_junk()
        # 前置：回收站创建 3G 大文件(对应用例前置条件)
        widget.create_large_trash_file("3G")
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击空间清理特色卡片的开始扫描按钮, 触发自动扫描
            widget.click_space_clean_featured_card()
            # 等待扫描完成并验证检测到垃圾
            self.assert_true(widget.get_space_clean_has_junk(timeout=240))
            # 验证结果页面已显示, 回收站大文件被扫描到
            self.assert_true(
                widget.get_space_clean_result_page_showing(timeout=10)
            )
            self.assert_true(widget.get_large_trash_file_exist())
            # 验证清理按钮可用, 点击立即清理
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            widget.click_space_clean_clean_button()
            # 回收站大文件与测试垃圾文件均被清理
            self.assert_true(widget.wait_large_trash_file_cleaned(timeout=120))
            self.assert_true(widget.wait_test_junk_files_cleaned(timeout=60))
            self.assert_false(widget.get_large_trash_file_exist())
            # 步骤3: 点击左上角返回, 回到系统优化页面
            widget.click_back_button()
            sleep(1)
            self.assert_true(widget.get_optimization_page_showing())
        finally:
            # 清理测试垃圾与大文件残留
            widget.remove_all_space_clean_junk()
            widget.remove_large_trash_file()

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

    def test_mycase_128(self):
        """空间清理--空间清理结果有垃圾：进入空间清理后扫描结果显示有垃圾文件"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：创建测试垃圾文件确保扫描能检测到垃圾
        widget.create_all_space_clean_junk()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击空间清理特色卡片的开始扫描按钮
            widget.click_space_clean_featured_card()
            # 等待扫描完成并验证检测到垃圾
            self.assert_true(widget.get_space_clean_has_junk(timeout=180))
            # 结果页显示"扫描结果", 按分类展示可清理项目, 清理按钮可用
            self.assert_true(
                widget.get_space_clean_result_page_showing(timeout=10)
            )
            self.assert_true(
                len(widget.get_space_clean_category_checkboxes(retries=10)) > 0
            )
            self.assert_true(
                len(widget.get_space_clean_item_checkboxes(retries=10)) > 0
            )
            self.assert_true(widget.get_space_clean_clean_button_enabled())
        finally:
            # 清理测试垃圾文件
            widget.remove_all_space_clean_junk()

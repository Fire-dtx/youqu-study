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

    def test_mycase_335(self):
        """垃圾清理--清理cookies：验证空间清理扫描能检测到浏览器Cookie分类并清理"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理系统中所有可被空间清理检测到的垃圾，确保扫描结果只反映本次创建的 Cookie
        widget.clean_system_for_no_junk()
        # 前置：创建测试用浏览器 Cookie 文件，确保扫描能检测到 Cookies 分类
        widget.create_test_cookie_files()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击空间清理特色卡片的开始扫描按钮，触发扫描
            widget.click_space_clean_featured_card()
            # 等待扫描完成并验证检测到垃圾
            self.assert_true(widget.get_space_clean_has_junk(timeout=120))
            # 验证结果页面已显示
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=10))
            # 验证扫描结果中存在 Cookies 分类
            self.assert_true(widget.has_space_clean_category("Cookie", retries=10))
            # 确保所有分类复选框已勾选，使清理按钮可用
            category_checkboxes = widget.get_space_clean_category_checkboxes(retries=10)
            for idx, cb in enumerate(category_checkboxes):
                if not widget._get_checkbox_checked(cb):
                    widget.click_space_clean_category_checkbox(
                        idx, checkboxes=category_checkboxes
                    )
                    sleep(1)
            # 验证清理按钮可用
            self.assert_true(widget.get_space_clean_clean_button_enabled(retries=15))
            # 点击立即清理按钮
            widget.click_space_clean_clean_button()
            # 验证测试 Cookie 文件已被清理
            self.assert_true(widget.wait_test_cookie_files_cleaned(timeout=60))
        finally:
            # 清理测试残留
            widget.remove_test_cookie_files()

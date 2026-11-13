#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_127(self):
        """空间清理--空间清理结果无垃圾：验证系统无垃圾时空间清理扫描结果页显示空状态"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理系统中所有可被空间清理检测到的垃圾，确保无垃圾状态
        widget.clean_system_for_no_junk()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击空间清理特色卡片的开始扫描按钮，触发扫描
            widget.click_space_clean_featured_card()
            # 等待扫描完成并验证无垃圾
            self.assert_true(widget.get_space_clean_no_junk(timeout=120))
        finally:
            # 清理测试残留
            widget.remove_test_junk_files()

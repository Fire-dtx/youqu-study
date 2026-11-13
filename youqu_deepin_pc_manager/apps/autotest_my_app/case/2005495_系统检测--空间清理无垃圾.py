#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_079(self):
        """系统检测--空间清理无垃圾：进入空间清理后扫描结果显示无垃圾文件"""
        widget = MyAppWidget(check_start=False)
        try:
            # 前置：确保电脑管家已关闭
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())
            # 前置：清理系统中所有可被空间清理检测到的垃圾，确保无垃圾状态
            widget.clean_system_for_no_junk()
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击空间清理特色卡片的开始扫描按钮
            widget.click_space_clean_featured_card()
            # 扫描确实开始(进入进度页或直接落到结果页), 排除"没反应却读到空状态"
            self.assert_true(widget.get_space_clean_scan_started(timeout=120))
            # 等待扫描完成并验证无垃圾
            self.assert_true(widget.get_space_clean_no_junk(timeout=120))
            # 反向断言: 结果页确实不是"有垃圾"页
            self.assert_false(widget.get_space_clean_has_junk(timeout=10))
        finally:
            # 清理测试垃圾文件, 并关闭本用例启动的电脑管家
            widget.remove_test_junk_files()
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())

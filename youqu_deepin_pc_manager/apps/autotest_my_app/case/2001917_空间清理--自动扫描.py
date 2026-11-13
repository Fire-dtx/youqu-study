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

    def test_mycase_125(self):
        """空间清理--自动扫描：验证点击扫描按钮后自动完成扫描并显示结果"""
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
            # 点击空间清理特色卡片的开始扫描按钮，触发自动扫描
            widget.click_space_clean_featured_card()
            # 等待扫描自动完成并验证结果页面显示（检测到垃圾或无垃圾均算扫描成功）
            self.assert_true(widget.get_space_clean_has_junk(timeout=180))
        finally:
            # 清理测试垃圾文件
            widget.remove_all_space_clean_junk()

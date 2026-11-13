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

    def test_mycase_334(self):
        """垃圾清理--清理系统缓存：在 /var/cache/apt/archives/ 中放置 .deb 缓存包,
        扫描空间清理后验证检测到垃圾, 点击清理按钮后验证 .deb 包被清除"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理系统中空间清理扫描器可能检测到的所有垃圾, 确保干净起点
        widget.clean_system_for_no_junk()
        # 前置：创建系统缓存垃圾(.deb 包放入 /var/cache/apt/archives/)
        widget.create_system_cache_junk()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击空间清理特色卡片的开始扫描按钮, 触发扫描
            widget.click_space_clean_featured_card()
            # 等待扫描完成并验证检测到垃圾
            self.assert_true(widget.get_space_clean_has_junk(timeout=120))
            # 验证结果页面已显示
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=10))
            # 验证清理按钮可用
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            # 点击立即清理按钮
            widget.click_space_clean_clean_button()
            # 验证系统缓存垃圾(.deb 文件)已被清理
            self.assert_true(widget.wait_system_cache_junk_cleaned(timeout=60))
        finally:
            # 清理测试残留
            widget.remove_system_cache_junk()

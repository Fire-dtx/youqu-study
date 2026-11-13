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

    def test_mycase_369(self):
        """垃圾清理--系统日志超过100MB可清理：构造超过100MB的系统日志文件,
        验证空间清理扫描能检测到该日志, 清理后日志文件被截断或删除"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理系统中所有可被扫描器检测到的垃圾, 确保初始无垃圾状态
        widget.clean_system_for_no_junk()
        # 前置：创建超过 100MB 的系统日志文件, 使扫描器能检测到系统日志分类
        widget.create_large_system_log()
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
            # 验证扫描结果中存在系统日志相关分类
            self.assert_true(widget.has_space_clean_category("系统", retries=10))
            # 验证清理按钮可用
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            # 点击立即清理按钮
            widget.click_space_clean_clean_button()
            # 验证大型系统日志文件已被清理(截断或删除)
            self.assert_true(widget.wait_large_system_log_cleaned(timeout=120))
        finally:
            # 清理测试创建的大型系统日志文件
            widget.remove_large_system_log()

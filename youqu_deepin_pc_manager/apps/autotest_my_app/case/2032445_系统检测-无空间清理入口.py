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

    def test_mycase_084(self):
        """系统检测-无空间清理入口：验证系统检测页面不显示空间清理入口"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理测试垃圾文件，确保无垃圾状态
        widget.remove_test_junk_files()
        try:
            # 启动电脑管家（使用 launch_from_launcher 确保 AT-SPI 注册正常）
            widget.launch_from_launcher()
            sleep(3)
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统检测页面
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            # 验证检测页面卡片视图正常显示
            self.assert_true(widget.get_detection_cards_view_showing())
            # 验证系统检测页面不显示空间清理入口
            # 空间清理属于系统优化模块，不应出现在系统检测页面
            self.assert_true(not widget.get_detection_space_clean_entry_showing())
        finally:
            # 清理测试垃圾文件
            widget.remove_test_junk_files()
            # 关闭电脑管家
            widget.kill_pc_manager()

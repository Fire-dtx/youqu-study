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

    def test_mycase_299(self):
        """垃圾清理--清理痕迹信息：验证空间清理扫描能检测到痕迹信息分类并清理痕迹文件"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：创建痕迹信息测试垃圾
        widget.create_trace_junk()
        # 前置：创建系统垃圾确保清理按钮可用
        widget.create_test_junk_files()
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
            # 验证痕迹信息分类存在
            self.assert_true(widget.has_space_clean_category("痕迹"))
            # 1.1.6 起默认只勾选 系统垃圾/应用垃圾/玲珑环境,
            # 痕迹等分类需手动勾选后才会被清理
            category_checkboxes = widget.get_space_clean_category_checkboxes()
            for idx, info in enumerate(widget.get_space_clean_category_info()):
                if not info.get("checked"):
                    widget.click_space_clean_category_checkbox(
                        idx, category_checkboxes
                    )
            # 验证清理按钮可用
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            # 点击立即清理按钮
            widget.click_space_clean_clean_button()
            # 验证痕迹信息文件已被清理
            self.assert_true(widget.wait_trace_junk_cleaned(timeout=60))
        finally:
            # 清理测试残留
            widget.remove_trace_junk()
            widget.remove_test_junk_files()

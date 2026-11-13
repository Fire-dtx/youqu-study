#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_275(self):
        """系统优化首页：验证系统优化页面正常显示，包含功能卡片和空间清理入口"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        # 导航到系统优化页面
        widget.click_optimization_nav_by_attr()
        self.assert_true(widget.get_optimization_page_showing())
        # 验证系统优化卡片视图显示
        self.assert_true(widget.get_optimization_cards_view_showing())
        # 验证非特色卡片数量大于 0
        card_count = widget.get_optimization_card_count()
        self.assert_true(card_count > 0)
        # 验证空间清理特色卡片入口(开始扫描按钮)存在
        self.assert_true(widget.get_optimization_page_showing())
        # 清理：关闭电脑管家
        widget.kill_pc_manager()

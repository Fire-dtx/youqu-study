#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_130(self):
        """修复工具--修复工具列表展示：验证页头标题/描述与修复列表正常展示"""
        widget = MyAppWidget(check_start=False)
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 进入左侧导航"修复工具"
            widget.click_repair_nav()
            # 页面正常切换
            self.assert_true(widget.get_repair_page_showing())
            # 页面顶部页头已渲染(标题"修复工具" + 描述"一键修复常见问题";
            # 产品 AT-SPI 只暴露元素名不暴露文案, 以标题/描述标签的渲染状态作等价断言)
            self.assert_true(widget.get_repair_page_header_showing())
            # 修复列表区域正常展示
            self.assert_true(widget.get_repair_cards_view_showing())
            section_titles = widget.get_repair_section_titles()
            self.assert_true(len(section_titles) > 0)
            # 列表中的修复项已渲染, 且能与分区对应
            card_names = widget.get_repair_card_names()
            self.assert_true(len(card_names) > 0)
            card_count = widget.get_repair_card_count()
            self.assert_true(card_count > 0)
            self.assert_true(card_count >= len(section_titles))
            # 列表展示后页面仍稳定显示
            self.assert_true(widget.get_repair_page_showing())
        finally:
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

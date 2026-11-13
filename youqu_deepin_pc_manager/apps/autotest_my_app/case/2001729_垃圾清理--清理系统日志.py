#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_337(self):
        """垃圾清理--清理系统日志：系统垃圾分类包含 6 个扫描项(sys-cache/
        sys-log-large/sys-log-journal/sys-log-rotated/sys-license-log/
        sys-trash), 取消"系统垃圾"复选框后只勾选"超过100MB的系统日志"
        并立即清理, 验证仅选中的日志被清理, 其余系统垃圾保持原样"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：构造 6 个系统垃圾扫描项对应的垃圾(sys-log-large 为 120MB,
        # 在分类内按大小降序排第一位)
        widget.create_all_system_junk_items()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())

            # 第一步：开始扫描
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_has_junk(timeout=180))
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=30))
            self.assert_true(widget.has_space_clean_category("系统垃圾"))
            # 系统垃圾分类应包含全部 6 个扫描项。1.1.7 的 AT-SPI 不暴露
            # itemId 与显示文本, 以子项数量断言(6 个前置垃圾各对应一项)
            self.assert_equal(6, widget.get_space_clean_item_total_count())

            # 第二步：取消"系统垃圾"复选框(分类内子项随之全部取消),
            # 再只勾选"超过100MB的系统日志"
            widget.click_space_clean_category_checkbox(0)
            self.assert_equal(0, widget.get_space_clean_checked_category_count())
            item_checkboxes = widget.get_space_clean_item_checkboxes()
            self.assert_equal(6, len(item_checkboxes))
            self.assert_equal(0, widget.get_space_clean_checked_item_count())
            # 分类内按大小降序, 120MB 的测试日志即第一项
            widget.click_space_clean_item_checkbox(0, checkboxes=item_checkboxes)
            self.assert_equal(1, widget.get_space_clean_checked_item_count())
            # 立即清理
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            widget.click_space_clean_clean_button()

            # 断言：选中的"超过100MB的系统日志"被清理(truncate 为 0)
            self.assert_true(
                widget.wait_system_junk_item_cleaned("sys-log-large", timeout=180)
            )
            # 断言：未勾选的其余 5 个系统垃圾项保持原样
            cleaned_unexpectedly = [
                item_id
                for item_id in widget.SYSTEM_JUNK_ITEM_IDS
                if item_id != "sys-log-large"
                and not widget.get_system_junk_item_exists(item_id)
            ]
            self.assert_equal([], cleaned_unexpectedly)
        finally:
            # 清理测试残留
            widget.remove_all_system_junk_items()

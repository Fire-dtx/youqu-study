#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):
    def test_mycase_129(self):
        """空间清理--空间清理结果页-不同功能项进行选择：同一分类内支持全选,
        分类复选框只作用于本分类子项, 不支持跨分类全选"""
        widget = MyAppWidget(check_start=False)
        # 前置：关闭电脑管家并按扫描规则预创建全部类型垃圾
        widget.kill_pc_manager()
        widget.create_all_space_clean_junk()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_has_junk(timeout=180))
            self.assert_true(
                widget.get_space_clean_result_page_showing(timeout=10)
            )
            self.assert_true(
                len(widget.get_space_clean_category_checkboxes()) >= 4
            )
            # 取消所有分类: 分类内子项全部取消, 清理按钮置灰
            self.assert_true(widget.uncheck_all_space_clean_categories())
            self.assert_true(
                widget.get_space_clean_checked_item_count() == 0
            )
            self.assert_false(
                widget.get_space_clean_clean_button_enabled(retries=3)
            )
            # 同一分类内支持全选: 勾选系统垃圾分类, 其子项全部勾选
            self.assert_true(
                widget.keep_only_space_clean_category_checked(0)
            )
            self.assert_true(
                widget.get_space_clean_checked_item_count() > 0
            )
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            # 不支持跨分类全选: 勾选系统垃圾后痕迹/cookies 分类仍未勾选
            states = widget.get_space_clean_category_checked_states()
            self.assert_true(states[0])
            self.assert_false(states[2])
            self.assert_false(states[3])
            # 分类内全选可取消: 取消系统垃圾分类后子项全部取消
            category_boxes = widget.get_space_clean_category_checkboxes()
            widget.click_space_clean_category_checkbox(
                0, checkboxes=category_boxes
            )
            self.assert_true(
                widget.get_space_clean_checked_item_count() == 0
            )
            self.assert_false(
                widget.get_space_clean_clean_button_enabled(retries=3)
            )
            # 勾选 cookies 分类只勾选该分类子项, 不影响其它分类
            self.assert_true(
                widget.keep_only_space_clean_category_checked(3)
            )
            states = widget.get_space_clean_category_checked_states()
            self.assert_false(states[0])
            self.assert_true(states[3])
            self.assert_true(
                widget.get_space_clean_checked_item_count() > 0
            )
            self.assert_true(widget.get_space_clean_clean_button_enabled())
        finally:
            widget.remove_all_space_clean_junk()

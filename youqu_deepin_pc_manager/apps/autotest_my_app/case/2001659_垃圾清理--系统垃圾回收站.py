#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_333(self):
        """垃圾清理--系统垃圾回收站：仅勾选系统垃圾分类中的回收站并清理,
        验证回收站文件被全部清理; 重新扫描后系统垃圾中不再出现回收站"""
        widget = MyAppWidget(check_start=False)
        # 前置: 关闭电脑管家
        widget.kill_pc_manager()
        # 前置: 按扫描规则预创建全部类型垃圾(系统/应用/痕迹/cookies),
        # 保证用例多次执行后仍有可清理数据
        widget.create_all_space_clean_junk()
        # 前置: 清理回收站之外的其它系统垃圾, 使系统垃圾分类下只剩回收站
        # (结果页系统垃圾按大小降序, 否则回收站未必是第一项, 无法精确单选)
        widget.clean_other_system_junk_items()
        try:
            # 启动电脑管家, 进入系统优化 → 空间清理
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 步骤1: 点击开始扫描, 扫描结果出现系统垃圾(回收站)
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_has_junk(timeout=180))
            self.assert_true(
                widget.get_space_clean_result_page_showing(timeout=10)
            )
            self.assert_true(widget.has_space_clean_category("系统垃圾"))
            # 步骤2: 取消系统垃圾复选框, 仅勾选回收站
            category_count_before = widget.get_space_clean_category_count()
            item_count_before = len(widget.get_space_clean_item_checkboxes())
            self.assert_true(category_count_before >= 1)
            self.assert_true(item_count_before >= 1)
            self.assert_true(widget.uncheck_all_space_clean_categories())
            self.assert_false(
                widget.get_space_clean_clean_button_enabled(retries=3)
            )
            # 前置已保证回收站是系统垃圾分类下的唯一子项(item 0)
            item_boxes = widget.get_space_clean_item_checkboxes()
            widget.click_space_clean_item_checkbox(0, checkboxes=item_boxes)
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            # 点击立即清理
            widget.click_space_clean_clean_button()
            # 回收站文件全部被清理
            self.assert_true(widget.wait_test_junk_files_cleaned(timeout=60))
            self.assert_false(widget.get_test_junk_files_exist())
            # 结果页更新: 回收站项从列表移除
            # (系统垃圾分类下可能仍有其它系统垃圾, 因此只校验选中项减少)
            self.assert_true(
                widget.get_space_clean_result_page_showing(timeout=30)
            )
            item_count_after = len(widget.get_space_clean_item_checkboxes())
            self.assert_true(item_count_after <= item_count_before - 1)
            # 步骤3: 点击重新扫描, 扫描完成后系统垃圾-回收站无垃圾
            widget.click_space_clean_rescan_button()
            self.assert_equal(
                "result", widget.wait_space_clean_scan_finished(timeout=180)
            )
            self.assert_false(widget.get_test_junk_files_exist())
            self.assert_true(
                len(widget.get_space_clean_item_checkboxes())
                <= item_count_after
            )
        finally:
            # 清理全部测试垃圾残留
            widget.remove_all_space_clean_junk()

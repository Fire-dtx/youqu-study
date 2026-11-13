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

    def test_mycase_287(self):
        """清理玲珑环境、系统快照-系统快照清理交互：验证玲珑环境和系统快照分类存在,
        V25 上验证快照清理确认对话框交互; V20 上验证分类显示及复选框交互"""
        widget = MyAppWidget(check_start=False)
        is_v25 = widget.is_v25_environment()

        # 前置: 确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置: 为全部扫描分类构造测试数据(含玲珑不可达对象), 使结果页
        # 出现多个带复选框的分类
        widget.create_all_category_junk()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击空间清理特色卡片的开始扫描按钮, 触发自动扫描
            widget.click_space_clean_featured_card()
            # 等待扫描完成并验证检测到垃圾
            self.assert_true(widget.get_space_clean_has_junk(timeout=120))
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=10))

            # 获取分类名称列表(包含所有分类, 含无复选框的分类)
            category_names = widget.get_space_clean_category_names()
            self.assert_true(len(category_names) > 0)

            # 验证玲珑环境分类存在(已创建不可达对象)
            self.assert_true(widget.has_space_clean_category("玲珑"))
            # 验证系统快照分类: V20 未编译快照扫描, 结果页不含含项的快照分类
            if is_v25:
                self.assert_true(widget.has_space_clean_category("快照"))
            else:
                self.assert_false(widget.has_space_clean_category("快照"))

            # 获取有复选框的分类(仅 fileCount>0 的分类才有复选框)
            category_checkboxes = widget.get_space_clean_category_checkboxes()
            self.assert_true(len(category_checkboxes) > 0)

            if is_v25:
                # ===== V25: 验证系统快照分类清理确认对话框交互 =====
                snapshot_idx = widget.find_space_clean_category_index_by_keyword("快照")
                self.assert_true(snapshot_idx >= 0)

                # 取消选中所有分类
                checked_indices = [
                    i for i, cb in enumerate(category_checkboxes)
                    if widget._get_checkbox_checked(cb)
                ]
                for idx in checked_indices:
                    widget.click_space_clean_category_checkbox(
                        idx, checkboxes=category_checkboxes
                    )
                # 确认清理按钮不可用(全部取消选中)
                self.assert_true(not widget.get_space_clean_clean_button_enabled())

                # 仅选中快照分类, 点击清理按钮
                widget.click_space_clean_category_checkbox(
                    snapshot_idx, checkboxes=category_checkboxes
                )
                self.assert_true(widget.get_space_clean_clean_button_enabled())
                widget.click_space_clean_clean_button()

                # 验证确认对话框出现(包含系统快照的项目会弹出确认)
                self.assert_true(
                    widget.get_space_clean_snapshot_confirm_dialog_showing(timeout=10)
                )

                # 点击"让我再想想"取消, 验证清理未执行
                self.assert_true(
                    widget.click_space_clean_confirm_dialog_button("让我再想想")
                )
                sleep(2)
                # 对话框关闭后仍在结果页, 未执行清理
                self.assert_true(
                    widget.get_space_clean_result_page_showing(timeout=5)
                )

                # 再次点击清理, 验证对话框再次出现
                widget.click_space_clean_clean_button()
                self.assert_true(
                    widget.get_space_clean_snapshot_confirm_dialog_showing(timeout=10)
                )

                # 点击"继续删除"确认, 验证清理执行
                self.assert_true(
                    widget.click_space_clean_confirm_dialog_button("继续删除")
                )
                sleep(3)
                # 清理后应重新扫描或显示结果
                self.assert_true(
                    widget.get_space_clean_has_junk(timeout=120)
                    or widget.get_space_clean_no_junk(timeout=30)
                )
            else:
                # ===== V20: 验证分类显示及复选框交互 =====
                # V20 上玲珑环境/系统快照分类可能无复选框(fileCount==0),
                # 验证有复选框的分类的勾选/取消交互和清理按钮状态

                # 清理按钮应可用(有默认选中的分类)
                self.assert_true(widget.get_space_clean_clean_button_enabled())

                # 取消选中所有分类
                checked_indices = [
                    i for i, cb in enumerate(category_checkboxes)
                    if widget._get_checkbox_checked(cb)
                ]
                for idx in checked_indices:
                    widget.click_space_clean_category_checkbox(
                        idx, checkboxes=category_checkboxes
                    )
                sleep(1)

                # 全部取消选中后, 清理按钮应不可用
                self.assert_true(not widget.get_space_clean_clean_button_enabled())

                # 勾选多个分类后清理按钮可用(勾选状态可保留)
                self.assert_true(len(category_checkboxes) >= 2)
                widget.click_space_clean_category_checkbox(
                    0, checkboxes=category_checkboxes
                )
                widget.click_space_clean_category_checkbox(
                    1, checkboxes=category_checkboxes
                )
                sleep(1)
                self.assert_true(widget.get_space_clean_clean_button_enabled())
                self.assert_true(
                    widget.get_space_clean_checked_category_count(
                        checkboxes=category_checkboxes
                    ) >= 2
                )
        finally:
            # 清理测试垃圾文件、玲珑不可达对象, 关闭应用
            widget.remove_all_category_junk()
            widget.kill_pc_manager()

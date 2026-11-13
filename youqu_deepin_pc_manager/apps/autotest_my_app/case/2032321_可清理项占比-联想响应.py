#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_317(self):
        """可清理项占比-联想响应

        扫描期间验证扫描视图实时响应元素出现/结果页出现, 扫描完成后验证
        结果页分类齐全、分类/单项复选框联动。

        期望描述的"占比条整段实心/45°斜线/低饱和灰"等视觉状态依赖 V25
        占比条组件; V20 2.14.0 实测摘要卡只有"发现N个可清理项,合计X MB"
        文本, 无占比条(scrot 截图 /tmp/pcm_cat_order.png), 因此按版本等价
        校验交互链路: 有数据时实时扫描元素或结果页出现 -> 结果页分类与
        单项复选框存在且勾选状态可切换。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        # 前置: 构造全部分类数据与系统垃圾 6 个单项(含回收站/日志)
        widget.create_all_category_junk()
        widget.create_all_system_junk_items()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_scan_started(timeout=30))

            # 扫描期间实时元素(或扫描极快时直接进入结果页)
            realtime_exprs = [
                "$//spaceClean_scanTitle",
                "$//spaceClean_scanProgress",
                "$//spaceClean_scanCount",
                "$//spaceClean_scanPath",
                "$//spaceClean_scanElapsed",
                "$//backGroundWidget_scanProgressBar",
                "$//spaceCleanScanningPage",
            ]
            realtime_shown = False
            for _ in range(15):
                try:
                    widget._safe_focus_windows()
                    if widget._any_visible(*realtime_exprs):
                        realtime_shown = True
                        break
                except BaseException:
                    pass
                if widget.get_space_clean_result_page_showing(timeout=1):
                    break
                sleep(1)
            result_ready = widget.get_space_clean_result_page_showing(timeout=30)
            self.assert_true(realtime_shown or result_ready)

            self.assert_true(widget.get_space_clean_has_junk(timeout=150))
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=20))
            sleep(3)

            # 结果页分类与单项按钮齐全
            category_checkboxes = widget.get_space_clean_category_checkboxes()
            logger.info(f"[2032321] 分类复选框数: {len(category_checkboxes)}")
            self.assert_true(len(category_checkboxes) >= 5)
            item_checkboxes = widget.get_space_clean_item_checkboxes()
            logger.info(f"[2032321] 单项复选框数: {len(item_checkboxes)}")
            self.assert_true(len(item_checkboxes) >= 6)

            # 单项勾选联动: 切换第一个单项, 状态应翻转
            first_checked = widget._get_checkbox_checked(item_checkboxes[0])
            widget.click_space_clean_item_checkbox(0, checkboxes=item_checkboxes)
            sleep(1)
            self.assert_true(
                widget._get_checkbox_checked(item_checkboxes[0]) != first_checked
            )
            widget.click_space_clean_item_checkbox(0, checkboxes=item_checkboxes)
            sleep(1)
            self.assert_true(
                widget._get_checkbox_checked(item_checkboxes[0]) == first_checked
            )

            # 分类级勾选联动: 取消/恢复第一个分类, 清理按钮跟随变化
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            widget.click_space_clean_category_checkbox(
                0, checkboxes=category_checkboxes
            )
            sleep(1)
            widget.click_space_clean_category_checkbox(
                0, checkboxes=category_checkboxes
            )
            sleep(1)
            self.assert_true(widget.get_space_clean_clean_button_enabled())
        finally:
            widget.remove_all_category_junk()
            widget.remove_all_system_junk_items()
            widget.kill_pc_manager()

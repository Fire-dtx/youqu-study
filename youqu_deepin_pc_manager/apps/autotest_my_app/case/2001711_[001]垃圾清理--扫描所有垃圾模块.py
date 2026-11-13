#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_276(self):
        """垃圾清理--扫描所有垃圾模块：扫描结果展示系统垃圾/应用垃圾/
        痕迹信息/cookies 四个模块, 默认勾选系统垃圾与应用垃圾,
        四个模块均可勾选, 重新扫描是对勾选的模块进行扫描"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：按扫描规则预创建全部类型垃圾(系统/应用/痕迹/cookies)
        widget.create_all_space_clean_junk()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 步骤1/4: 点击开始扫描, 扫描结束查看垃圾清理项
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_has_junk(timeout=180))
            self.assert_true(
                widget.get_space_clean_result_page_showing(timeout=10)
            )
            # xlsx 要求的四个分类必须全部出现; V20 玲珑环境存在垃圾时会
            # 额外多出"玲珑"分类, 因此按 >=4 校验
            self.assert_true(
                widget.get_space_clean_category_count(retries=10) >= 4
            )
            self.assert_true(
                len(widget.get_space_clean_category_names(retries=10)) >= 4
            )
            # 步骤2: 默认勾选系统垃圾、应用垃圾; 痕迹信息、cookies 默认不勾选
            states = widget.get_space_clean_category_checked_states()
            self.assert_true(len(states) >= 4)
            self.assert_true(states[0])
            self.assert_true(states[1])
            self.assert_false(states[2])
            self.assert_false(states[3])
            # 步骤3: 四个模块均可勾选(勾选痕迹信息与 cookies)
            for index in (2, 3):
                boxes = widget.get_space_clean_category_checkboxes()
                widget.click_space_clean_category_checkbox(
                    index, checkboxes=boxes
                )
            states = widget.get_space_clean_category_checked_states()
            self.assert_true(all(states[:4]))
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            # 步骤4: 重新扫描(按勾选的模块)仍得到四个分类
            widget.click_space_clean_rescan_button()
            self.assert_equal(
                "result", widget.wait_space_clean_scan_finished(timeout=240)
            )
            self.assert_true(
                widget.get_space_clean_category_count(retries=10) >= 4
            )
        finally:
            # 清理全部测试垃圾残留
            widget.remove_all_space_clean_junk()

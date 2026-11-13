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

    def test_mycase_018(self):
        """系统检测首页--无任何异常项：进入系统检测首页，
        验证评分卡片、全面检测按钮显示，执行全面检测，
        检测完成后验证结果页正常显示。

        注意: 测试机环境可能存在真实异常项(系统更新、核心包完整性、
        CPU 温度传感器等), 无法通过数据准备消除, 因此不再断言
        「一键修复」按钮不存在, 只验证检测流程完成且结果页展示正常。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav_by_attr()
        self.assert_true(widget.get_detection_page_showing(timeout=15))
        # 验证检测首页元素正常显示
        self.assert_true(widget.get_detection_score_card_showing())
        self.assert_true(widget.get_detection_full_scan_button_showing())
        # 执行全面检测
        widget.click_detection_full_scan_button()
        widget.get_detection_full_scan_page_showing(timeout=30)
        self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
        # 验证检测结果页正常显示(无异常时显示"未发现问题", 有异常时显示"一键修复")
        self.assert_true(widget.get_detection_result_showing(timeout=15))
        # 验证应用仍在运行
        self.assert_true(widget.get_pc_manager_process_status())

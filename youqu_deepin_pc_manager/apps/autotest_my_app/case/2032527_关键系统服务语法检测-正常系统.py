#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log


class TestMyCase(BaseCase):

    def test_mycase_361(self):
        """关键系统服务语法检测-正常系统：默认安装的正常系统 service 单元文件
        语法正确，执行「系统稳定性」分项检测，服务语法检测项结论应为通过"""
        widget = MyAppWidget(check_start=False)

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        self.assert_true(widget.get_detection_functional_modules_showing())

        # ===== 执行「系统稳定性」分项检测并校验服务语法结论 =====
        self.assert_true(widget.get_detection_cards_view_showing())
        self.assert_true(widget.run_detection_item("系统稳定性", timeout=300))
        log("期望: " + ("系统稳定性分项中缺少「服务语法检测」检测项"))
        self.assert_true(widget.get_detection_item_present("系统稳定性", "服务语法检测"))
        ok, detail = widget.get_detection_item_verdict("service_syntax")
        log("期望: " + (f"service_syntax 预期通过(正常系统), 实际 {ok}: {detail}"))
        self.assert_true(ok is True)

        self.assert_true(widget.get_detection_page_showing())

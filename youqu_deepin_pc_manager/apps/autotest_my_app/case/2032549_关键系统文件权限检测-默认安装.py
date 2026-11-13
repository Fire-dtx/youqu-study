#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log


class TestMyCase(BaseCase):

    def test_mycase_339(self):
        """关键系统文件权限检测-默认安装：默认安装环境下关键系统文件权限符合预期，
        执行「系统稳定性」分项检测，文件权限检测项结论应为通过"""
        widget = MyAppWidget(check_start=False)

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        self.assert_true(widget.get_detection_functional_modules_showing())

        # ===== 执行「系统稳定性」分项检测并校验文件权限结论 =====
        self.assert_true(widget.get_detection_cards_view_showing())
        self.assert_true(widget.run_detection_item("系统稳定性", timeout=300))
        log("期望: " + ("系统稳定性分项中缺少「文件权限检测」检测项"))
        self.assert_true(widget.get_detection_item_present("系统稳定性", "文件权限检测"))
        ok, detail = widget.get_detection_item_verdict("file_permissions")
        log("期望: " + (f"file_permissions 预期通过(默认安装), 实际 {ok}: {detail}"))
        self.assert_true(ok is True)

        self.assert_true(widget.get_detection_page_showing())

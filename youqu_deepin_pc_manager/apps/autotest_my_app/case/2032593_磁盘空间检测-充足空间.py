#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_293(self):
        """磁盘空间检测-充足空间：根分区可用空间充足时，
        执行「硬件检测」分项检测，磁盘空间检测项结论应为通过"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing(timeout=15))
        self.assert_true(widget.get_detection_cards_view_showing())

        # ===== 执行「硬件检测」分项检测并校验磁盘空间结论 =====
        self.assert_true(widget.run_detection_item("硬件检测", timeout=300))
        log("期望: " + ("硬件检测分项中缺少「磁盘空间」检测项"))
        self.assert_true(widget.get_detection_item_present("硬件检测", "磁盘空间"))
        ok, detail = widget.get_detection_item_verdict("disk_space")
        log("期望: " + (f"disk_space 预期通过(空间充足), 实际 {ok}: {detail}"))
        self.assert_true(ok is True)

        widget.click_detection_nav()
        sleep(2)
        widget.reconnect_dogtail()
        widget.ui.focus_windows()
        self.assert_true(widget.get_detection_page_showing(timeout=15))
        self.assert_true(widget.get_detection_cards_view_showing())
        widget.get_detection_scan_time_text()
        widget.get_detection_score_text()
        self.assert_true(widget.get_detection_page_showing())

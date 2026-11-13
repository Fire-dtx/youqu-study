#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_353(self):
        """磁盘空间检测-swap排除：/etc/fstab 中存在 swap 分区时，
        执行「硬件检测」分项检测，磁盘空间检测项结论为通过，
        且结论中不包含 swap 分区（swap 不纳入磁盘空间统计）"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        # 前置确认：/etc/fstab 中存在 swap 分区条目
        fstab_swap = widget.run_cmd(
            "grep -v '^#' /etc/fstab | awk '{print $3}' | grep -ix swap | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        self.assert_true(bool(fstab_swap.strip()))

        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing(timeout=15))
        self.assert_true(widget.get_detection_cards_view_showing())

        # ===== 执行「硬件检测」分项检测并校验磁盘空间结论 =====
        self.assert_true(widget.run_detection_item("硬件检测", timeout=300))
        log("期望: " + ("硬件检测分项中缺少「磁盘空间」检测项"))
        self.assert_true(widget.get_detection_item_present("硬件检测", "磁盘空间"))
        ok, detail = widget.get_detection_item_verdict("disk_space")
        log("期望: " + (f"disk_space 预期通过, 实际 {ok}: {detail}"))
        self.assert_true(ok is True)

        # 核心断言：swap 分区不进入磁盘空间检测结论
        log("期望: " + (f"swap 分区不应纳入磁盘空间检测结论: {detail}"))
        self.assert_true("swap" not in (detail or "").lower())

        widget.click_detection_nav()
        sleep(2)
        widget.reconnect_dogtail()
        widget.ui.focus_windows()
        self.assert_true(widget.get_detection_page_showing(timeout=15))
        self.assert_true(widget.get_detection_cards_view_showing())
        widget.get_detection_scan_time_text()
        widget.get_detection_score_text()

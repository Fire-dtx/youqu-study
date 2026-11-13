#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

class TestMyCase(BaseCase):

    def test_mycase_296(self):
        """单声卡检测正常：前置要求 aplay -l 只识别到 1 块声卡。点击"硬件检测"
        卡片真实执行检测, 断言声卡项存在、整组跑完无问题, 单项结论正常。"""
        widget = MyAppWidget(check_start=False)

        cards = widget.run_cmd("aplay -l 2>/dev/null | grep -c \"^card\"", timeout=15, out_debug_flag=False)
        cards = int(cards.strip() or 0)
        if cards != 1:
            pytest.skip(f"前置不满足: 当前识别到 {cards} 块声卡, 需单声卡环境")

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        self.assert_true(widget.run_detection_item("硬件检测"))

        self.assert_true(widget.get_detection_item_present("硬件检测", "声卡"))
        state = widget.get_detection_group_state("硬件检测")
        self.assert_equal(state["total"], state["checked"])
        self.assert_equal(0, state["issues"])

        verdict, detail = widget.get_detection_item_verdict("sound_card")
        logger.info(f"声卡单项结论: {verdict}, 原始结果: {detail}")
        self.assert_true(verdict)

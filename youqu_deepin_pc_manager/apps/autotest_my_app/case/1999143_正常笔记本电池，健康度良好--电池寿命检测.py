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

    def test_mycase_348(self):
        """正常笔记本电池健康度良好：前置要求存在 BAT* 电池设备且设计容量/实际
        容量可读。点击"硬件检测"卡片真实执行检测, 断言电池健康检查项存在、
        整组跑完无问题, 单项结论正常。"""
        widget = MyAppWidget(check_start=False)

        battery = widget.run_cmd(
            "ls -d /sys/class/power_supply/BAT* 2>/dev/null | head -1", timeout=10, out_debug_flag=False
        ).strip()
        if not battery:
            pytest.skip("前置不满足: 当前为无电池设备(台式机/虚拟机), 无法覆盖笔记本电池场景")

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        self.assert_true(widget.run_detection_item("硬件检测"))

        self.assert_true(widget.get_detection_item_present("硬件检测", "电池健康检查"))
        state = widget.get_detection_group_state("硬件检测")
        self.assert_equal(state["total"], state["checked"])
        self.assert_equal(0, state["issues"])

        verdict, detail = widget.get_detection_item_verdict("battery_health")
        logger.info(f"电池健康单项结论: {verdict}, 原始结果: {detail}")
        self.assert_true(verdict)

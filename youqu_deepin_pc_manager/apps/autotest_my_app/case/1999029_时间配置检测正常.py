#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/04
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_328(self):
        """时间配置检测正常：systemd-timesyncd 已加载、运行中且已启用时，
        点击"系统环境检测"卡片真实执行检测，"时间配置"项存在、
        整组跑完，单项结论为正常。"""
        widget = MyAppWidget(check_start=False)

        load_state = widget.run_cmd(
            "systemctl show --property=LoadState --value systemd-timesyncd.service 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        if load_state != "loaded":
            pytest.skip("当前环境无 systemd-timesyncd 服务, 跳过此用例")
        active_state = widget.run_cmd(
            "systemctl is-active systemd-timesyncd.service 2>/dev/null", timeout=10, out_debug_flag=False
        ).strip()
        enabled_state = widget.run_cmd(
            "systemctl is-enabled systemd-timesyncd.service 2>/dev/null", timeout=10, out_debug_flag=False
        ).strip()
        if active_state != "active" or enabled_state != "enabled":
            pytest.skip(
                f"前置不满足: systemd-timesyncd 状态为 {active_state}/{enabled_state}, "
                "需运行中且开机自启"
            )

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        self.assert_true(widget.get_detection_functional_modules_showing())

        # 点击"系统环境检测"卡片, 真实触发该分项检测
        self.assert_true(widget.run_detection_item("系统环境检测"))

        self.assert_true(widget.get_detection_item_present("系统环境检测", "时间配置"))
        self.assert_true(widget.is_only_group_detected("系统环境检测"))

        verdict, detail = widget.get_detection_item_verdict("time_config")
        logger.info(f"时间配置单项结论(服务运行中且自启): {verdict}, 原始结果: {detail}")
        self.assert_true(verdict)

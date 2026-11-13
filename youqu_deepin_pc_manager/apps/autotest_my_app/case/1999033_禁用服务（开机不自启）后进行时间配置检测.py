#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/04
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep, logger


class TestMyCase(BaseCase):

    def test_mycase_364(self):
        """禁用服务（开机不自启）后进行时间配置检测：禁用 systemd-timesyncd 开机自启
        （服务仍运行）后，点击"系统环境检测"卡片真实执行检测，
        "时间配置"项存在且结论为异常，用例结束后恢复开机自启。"""
        widget = MyAppWidget(check_start=False)

        load_state = widget.run_cmd(
            "systemctl show --property=LoadState --value systemd-timesyncd.service 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        if load_state != "loaded":
            pytest.skip("当前环境无 systemd-timesyncd.service，跳过此用例")

        origin_enabled = widget.run_cmd(
            "systemctl is-enabled systemd-timesyncd.service 2>/dev/null", timeout=10, out_debug_flag=False
        ).strip()
        widget.sudo_run_cmd("systemctl disable systemd-timesyncd.service 2>/dev/null", timeout=10, out_debug_flag=False)
        sleep(1)
        self.assert_equal(
            "disabled",
            widget.run_cmd(
                "systemctl is-enabled systemd-timesyncd.service 2>/dev/null", timeout=10, out_debug_flag=False
            ).strip(),
        )

        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.get_detection_functional_modules_showing())

            self.assert_true(widget.run_detection_item("系统环境检测"))

            self.assert_true(widget.get_detection_item_present("系统环境检测", "时间配置"))
            self.assert_true(widget.is_only_group_detected("系统环境检测"))

            verdict, detail = widget.get_detection_item_verdict("time_config")
            logger.info(f"时间配置单项结论(服务未开机自启): {verdict}, 原始结果: {detail}")
            self.assert_false(verdict)
        finally:
            widget.kill_pc_manager()
            if origin_enabled != "disabled":
                widget.sudo_run_cmd(
                    "systemctl enable systemd-timesyncd.service 2>/dev/null", timeout=15, out_debug_flag=False
                )

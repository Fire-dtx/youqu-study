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
    TIMESYNCD = "systemd-timesyncd.service"

    def _service_state(self, widget):
        active = widget.run_cmd(
            f"systemctl is-active {self.TIMESYNCD} 2>/dev/null", timeout=10, out_debug_flag=False
        ).strip()
        enabled = widget.run_cmd(
            f"systemctl is-enabled {self.TIMESYNCD} 2>/dev/null", timeout=10, out_debug_flag=False
        ).strip()
        return active, enabled

    def _mask_service(self, widget):
        """mask + stop：单纯 stop 会被 socket/依赖按需拉起，mask 后可稳定保持停止"""
        widget.sudo_run_cmd(
            f"systemctl mask --now {self.TIMESYNCD} 2>&1", timeout=30, out_debug_flag=False
        )
        active, enabled = self._service_state(widget)
        self.assert_true(active != "active")
        self.assert_true(enabled != "enabled")
        logger.info(f"已构造时间同步服务停止场景: is-active={active}, is-enabled={enabled}")

    def _restore_service(self, widget, origin_active, origin_enabled):
        widget.sudo_run_cmd(f"systemctl unmask {self.TIMESYNCD} 2>&1", timeout=30, out_debug_flag=False)
        if origin_enabled == "enabled":
            widget.sudo_run_cmd(
                f"systemctl enable {self.TIMESYNCD} >/dev/null 2>&1", timeout=30, out_debug_flag=False
            )
        if origin_active == "active":
            widget.sudo_run_cmd(
                f"systemctl start {self.TIMESYNCD} >/dev/null 2>&1", timeout=30, out_debug_flag=False
            )
        active, enabled = self._service_state(widget)
        logger.info(
            f"时间同步服务已还原: is-active={active}(原始 {origin_active}), "
            f"is-enabled={enabled}(原始 {origin_enabled})"
        )
        self.assert_true(active == origin_active)
        self.assert_true(enabled == origin_enabled)

    def test_mycase_356(self):
        """停止时间同步服务后进行时间配置检测：mask 并停止 systemd-timesyncd
        以稳定构造"服务停止"场景，点击"系统环境检测"卡片真实执行检测，
        "时间配置"项存在且结论为异常；执行完成后还原服务的
        enabled/active 状态。"""
        widget = MyAppWidget(check_start=False)

        load_state = widget.run_cmd(
            "systemctl show --property=LoadState --value systemd-timesyncd.service 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        if load_state != "loaded":
            pytest.skip("当前环境无 systemd-timesyncd 服务, 跳过此用例")

        origin_active, origin_enabled = self._service_state(widget)
        masked = False
        try:
            self._mask_service(widget)
            masked = True

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.get_detection_functional_modules_showing())

            self.assert_true(widget.run_detection_item("系统环境检测"))

            self.assert_true(widget.get_detection_item_present("系统环境检测", "时间配置"))
            self.assert_true(widget.is_only_group_detected("系统环境检测"))

            verdict, detail = widget.get_detection_item_verdict("time_config")
            logger.info(f"时间配置单项结论(服务已停止): {verdict}, 原始结果: {detail}")

            active, _ = self._service_state(widget)
            self.assert_true(active != "active")
            self.assert_false(verdict)
        finally:
            widget.kill_pc_manager()
            if masked:
                self._restore_service(widget, origin_active, origin_enabled)

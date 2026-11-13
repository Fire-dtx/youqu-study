#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log


class TestMyCase(BaseCase):

    def test_mycase_298(self):
        """网络正常、源正常、无更新包--系统版本检测：
        在网络正常、apt 源正常且无可用更新包的环境下，
        执行「系统环境检测」分项检测，系统版本检测项结论应为通过（当前已是最新）"""
        widget = MyAppWidget(check_start=False)

        # ===== 前置条件验证 =====
        self.assert_true(widget.get_network_connection_status())
        self.assert_true(widget.get_repo_address_reachable())

        # 测试机源中可能有大量可升级包(如混入 V25 源)，
        # 该场景无法由用例构造，环境不满足时跳过而非误报失败。
        if widget.get_package_update_status():
            pytest.skip("当前环境存在可升级包, 无法构造『无更新包』场景")

        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.get_detection_cards_view_showing())

            # ===== 执行「系统环境检测」分项检测 =====
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            log("期望: " + ("系统环境检测分项中缺少「系统版本检测」检测项"))
            self.assert_true(widget.get_detection_item_present("系统环境检测", "系统版本检测"))

            # ===== 校验系统版本检测结论：无更新包应为通过 =====
            ok, detail = widget.get_detection_item_verdict("system_version")
            log("期望: " + (f"system_version 预期通过(当前已是最新), 实际 {ok}: {detail}"))
            self.assert_true(ok is True)
        finally:
            widget.kill_pc_manager()

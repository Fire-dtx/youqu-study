#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import pytest
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request
from urllib.request import urlopen

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

# “网络检测全部无异常”以存在可用外网为前提: 本机代理/网关对
# https://www.uniontech.com 返回 reset 时, 产品的“网络访问”项必然报异常,
# 与锁屏/界面自动化无关, 因此在用例开始时直接 skip, 避免误记产品缺陷。
PUBLIC_NETWORK_PROBE = "www.uniontech.com"


def _is_public_network_reachable(host, timeout=5):
    """当前测试网络能否通过 HTTP(S) 访问公网探测地址。"""
    for scheme in ("https", "http"):
        try:
            request = Request(
                f"{scheme}://{host}", headers={"User-Agent": "pc-manager-autotest"}
            )
            with urlopen(request, timeout=timeout) as response:
                if response.status < 500:
                    return True
        except HTTPError as exc:
            if exc.code < 500:
                return True
        except (URLError, OSError):
            continue
    return False

class TestMyCase(BaseCase):

    def test_mycase_107(self):
        """网络检测全部无异常：网络正常(有默认路由、DNS 可用、无冲突)时点击
        "网络检测"卡片执行真实检测, 断言 7 项全部跑完、0 项问题, 且各可读
        检测项单项结论均为正常。"""
        if not _is_public_network_reachable(PUBLIC_NETWORK_PROBE):
            pytest.skip(
                f"前置不满足: {PUBLIC_NETWORK_PROBE} 在当前测试网络 HTTP(S) "
                "不可达, 无法验证网络检测全部无异常"
            )
        widget = MyAppWidget(check_start=False)

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        self.assert_true(widget.run_detection_item("网络检测"))
        self.assert_true(widget.get_detection_item_present("网络检测", "网络访问"))
        state = widget.get_detection_group_state("网络检测")
        self.assert_equal(state["total"], state["checked"])
        self.assert_equal(0, state["issues"])

        for detection_id in (
            "network_hardware",
            "network_settings",
            "dhcp_service",
            "dns",
            "hosts_file",
            "network_connectivity",
        ):
            verdict, detail = widget.get_detection_item_verdict(detection_id)
            logger.info(f"{detection_id} 单项结论: {verdict}, 原始结果: {detail}")
            if verdict is not None:
                self.assert_true(verdict)

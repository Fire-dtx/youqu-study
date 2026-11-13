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

    def test_mycase_097(self):
        """网络访问异常：用 iptables 阻断到公网的 80/443 端口(管理链路为同网段,
        不受影响), 点击"网络检测"卡片执行真实检测, 断言检出问题;
        用例结束移除规则恢复网络。"""
        widget = MyAppWidget(check_start=False)
        widget.sudo_run_cmd(
            "iptables -I OUTPUT 1 -p tcp -m multiport --dports 80,443 "
            "-d 0.0.0.0/0 -m addrtype ! --dst-type LOCAL -j DROP; true",
            timeout=20,
            out_debug_flag=False,
        )
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("网络检测"))
            self.assert_true(widget.get_detection_item_present("网络检测", "网络访问"))

            state = widget.get_detection_group_state("网络检测")
            self.assert_equal(state["total"], state["checked"])
            self.assert_true(state["issues"] > 0)

            verdict, detail = widget.get_detection_item_verdict("network_connectivity")
            logger.info(f"网络访问单项结论: {verdict}, 原始结果: {detail}")
            if verdict is not None:
                self.assert_true(verdict is False)
        finally:
            widget.sudo_run_cmd("iptables -D OUTPUT 1; true", timeout=20, out_debug_flag=False)

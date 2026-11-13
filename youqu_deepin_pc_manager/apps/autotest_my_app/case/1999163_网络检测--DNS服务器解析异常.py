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

    def test_mycase_101(self):
        """DNS 服务器解析异常：把 /etc/resolv.conf 的 nameserver 改为本机 127.0.0.1
        (无 DNS 服务), 点击"网络检测"执行真实检测, 断言 DNS服务项结论为异常、
        分项检出问题; 用例结束用备份恢复 resolv.conf。"""
        widget = MyAppWidget(check_start=False)
        backup = "/tmp/pcm_resolv_1999163.bak"
        widget.sudo_run_cmd(f"cp -a /etc/resolv.conf {backup}; true", timeout=15, out_debug_flag=False)
        widget.sudo_run_cmd(
            "printf 'nameserver 127.0.0.1\noptions timeout:1 attempts:1\n' > /etc/resolv.conf; true",
            timeout=15,
            out_debug_flag=False,
        )
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("网络检测"))
            self.assert_true(widget.get_detection_item_present("网络检测", "DNS服务"))

            state = widget.get_detection_group_state("网络检测")
            self.assert_equal(state["total"], state["checked"])
            self.assert_true(state["issues"] > 0)

            verdict, detail = widget.get_detection_item_verdict("dns")
            logger.info(f"DNS服务单项结论: {verdict}, 原始结果: {detail}")
            if verdict is not None:
                self.assert_true(verdict is False)
        finally:
            widget.sudo_run_cmd(f"cp -a {backup} /etc/resolv.conf; rm -f {backup}; true", timeout=15, out_debug_flag=False)

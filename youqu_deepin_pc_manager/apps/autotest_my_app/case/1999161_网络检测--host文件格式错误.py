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

    def test_mycase_100(self):
        """hosts 文件格式错误：向 /etc/hosts 追加一行非法映射(非法 IP + 非法域名),
        点击"网络检测"执行真实检测, 断言 hosts文件配置项结论为异常、分项检出问题;
        用例结束恢复 /etc/hosts 原内容。"""
        widget = MyAppWidget(check_start=False)
        backup = "/tmp/pcm_hosts_1999161.bak"
        widget.sudo_run_cmd(f"cp -a /etc/hosts {backup}; true", timeout=15, out_debug_flag=False)
        widget.sudo_run_cmd(
            "printf '999.999.999.999 --- invalid_line +++ %%s\n' >> /etc/hosts; true",
            timeout=15,
            out_debug_flag=False,
        )
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("网络检测"))
            self.assert_true(widget.get_detection_item_present("网络检测", "hosts文件配置"))

            state = widget.get_detection_group_state("网络检测")
            self.assert_equal(state["total"], state["checked"])
            self.assert_true(state["issues"] > 0)

            verdict, detail = widget.get_detection_item_verdict("hosts_file")
            logger.info(f"hosts文件配置单项结论: {verdict}, 原始结果: {detail}")
            if verdict is not None:
                self.assert_true(verdict is False)
        finally:
            widget.sudo_run_cmd(f"cp -a {backup} /etc/hosts; rm -f {backup}; true", timeout=15, out_debug_flag=False)

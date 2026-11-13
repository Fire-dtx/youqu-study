#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_103(self):
        """DHCP 服务异常：产品 DHCP 检测在 dhclient/dhcpcd 均未运行时要求
        /var/lib/dhcp 与 /etc/dhcp/dhclient.conf 至少一项可访问, 因此前置把两者
        临时移走构造 DHCP 异常。该操作不影响已获取的 IP(管理链路不断),
        点击"网络检测"执行真实检测, 断言 DHCP服务项结论为异常、分项检出问题;
        用例结束恢复原文件。
        """
        widget = MyAppWidget(check_start=False)
        bak_dir = "/tmp/pcm_dhcp_dir_bak_103"
        bak_conf = "/tmp/pcm_dhclient_conf_bak_103"
        widget.sudo_run_cmd(
            f"rm -rf {bak_dir} {bak_conf}; "
            f"[ -e /var/lib/dhcp ] && mv /var/lib/dhcp {bak_dir}; "
            f"[ -e /etc/dhcp/dhclient.conf ] && mv /etc/dhcp/dhclient.conf {bak_conf}; true",
            timeout=15,
            out_debug_flag=False,
        )
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            self.assert_true(widget.run_detection_item("网络检测"))
            self.assert_true(widget.get_detection_item_present("网络检测", "DHCP服务"))

            state = widget.get_detection_group_state("网络检测")
            self.assert_equal(state["total"], state["checked"])
            self.assert_true(state["issues"] > 0)

            verdict, detail = widget.get_detection_item_verdict("dhcp_service")
            logger.info(f"DHCP服务单项结论: {verdict}, 原始结果: {detail}")
            self.assert_true(verdict is False)
        finally:
            widget.sudo_run_cmd(
                f"[ -e {bak_dir} ] && {{ rm -rf /var/lib/dhcp && mv {bak_dir} /var/lib/dhcp; }}; "
                f"[ -e {bak_conf} ] && mv {bak_conf} /etc/dhcp/dhclient.conf; true",
                timeout=15,
                out_debug_flag=False,
            )

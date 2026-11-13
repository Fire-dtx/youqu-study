#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from time import sleep

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_106(self):
        """网络设备被禁用：用 nmcli networking off 关闭全局网络开关(等价于在
        控制中心关闭网络开关, 不弹控制中心), 使在用网卡 DOWN。点击"网络检测"
        执行真实检测, 断言网络设备检测结论为"网络设备被禁用"(failure:4002);
        用例结束打开网络开关并校验地址取回。
        """
        widget = MyAppWidget(check_start=False)
        dev = widget.run_cmd(
            "nmcli -t -f DEVICE,TYPE,STATE device | awk -F: '$2==\"ethernet\"{print $1; exit}'",
            timeout=15,
            out_debug_flag=False,
        ).strip()
        self.assert_true(dev)
        conn = widget.run_cmd(
            f"nmcli -g GENERAL.CONNECTION device show {dev}",
            timeout=15,
            out_debug_flag=False,
        ).strip()

        widget.sudo_run_cmd("nmcli networking off; true", timeout=30, out_debug_flag=False)
        try:
            net_state = widget.run_cmd("nmcli networking", timeout=15, out_debug_flag=False).strip()
            oper_state = widget.run_cmd(
                f"cat /sys/class/net/{dev}/operstate 2>/dev/null",
                timeout=15,
                out_debug_flag=False,
            ).strip()
            logger.info(f"网络开关状态: {net_state}, {dev} operstate: {oper_state}")
            self.assert_equal("disabled", net_state)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            self.assert_true(widget.run_detection_item("网络检测"))
            self.assert_true(widget.get_detection_item_present("网络检测", "网络设备检测"))

            verdict, detail = widget.get_detection_item_verdict("network_hardware")
            logger.info(f"网络设备检测单项结论: {verdict}, 原始结果: {detail}")
            self.assert_true(verdict is False)
            self.assert_true("4002" in str(detail))

            state = widget.get_detection_group_state("网络检测")
            logger.info(f"网络检测整组状态: {state}")
            self.assert_equal(state["total"], state["checked"])
            self.assert_true(state["issues"] >= 1)
        finally:
            widget.sudo_run_cmd("nmcli networking on; true", timeout=60, out_debug_flag=False)
            restored = ""
            for _ in range(6):
                if conn:
                    widget.sudo_run_cmd(
                        f"nmcli --wait 20 connection up '{conn}'; true",
                        timeout=60,
                        out_debug_flag=False,
                    )
                for _ in range(10):
                    restored = widget.run_cmd(
                        "ip -o -4 addr show | awk '$2!=\"lo\"{print $4}'",
                        timeout=15,
                        out_debug_flag=False,
                    ).strip()
                    if restored:
                        break
                    sleep(2)
                if restored:
                    break
            net_restored = widget.run_cmd("nmcli networking", timeout=15, out_debug_flag=False).strip()
            logger.info(f"网络开关: {net_restored}, 恢复后地址: {restored}")

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

    def test_mycase_025(self):
        """未连接任何网络：用 nmcli 断开有线连接(等价于在控制中心断开连接,
        不弹控制中心), 点击"网络检测"执行真实检测, 断言网络设备检测与
        hosts文件配置正常, 网络设置/DHCP服务/DNS服务/网络访问四项检测失败;
        用例结束用 nmcli 恢复连接并校验地址已取回。
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
        self.assert_true(conn)
        logger.info(f"准备断开的连接: {conn} (设备 {dev})")

        widget.sudo_run_cmd(f"nmcli connection down '{conn}'; true", timeout=30, out_debug_flag=False)
        try:
            down_state = widget.run_cmd(
                f"nmcli -g GENERAL.STATE device show {dev}",
                timeout=15,
                out_debug_flag=False,
            ).strip()
            logger.info(f"断开后设备状态: {down_state}")
            self.assert_true(down_state.startswith("30"))

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            self.assert_true(widget.run_detection_item("网络检测"))
            self.assert_true(widget.get_detection_item_present("网络检测", "网络设备检测"))
            self.assert_true(widget.get_detection_item_present("网络检测", "hosts文件配置"))

            for item, ui_name in (
                ("network_hardware", "网络设备检测"),
                ("hosts_file", "hosts文件配置"),
            ):
                verdict, detail = widget.get_detection_item_verdict(item)
                logger.info(f"{ui_name}单项结论: {verdict}, 原始结果: {detail}")
                self.assert_true(verdict)

            for item, ui_name in (
                ("network_settings", "网络设置检测"),
                ("dhcp_service", "DHCP服务"),
                ("dns", "DNS服务"),
                ("network_connectivity", "网络访问"),
            ):
                verdict, detail = widget.get_detection_item_verdict(item)
                logger.info(f"{ui_name}单项结论: {verdict}, 原始结果: {detail}")
                self.assert_true(verdict is False)

            state = widget.get_detection_group_state("网络检测")
            logger.info(f"网络检测整组状态: {state}")
            self.assert_equal(state["total"], state["checked"])
            self.assert_true(state["issues"] >= 4)
        finally:
            restored = ""
            for _ in range(6):
                widget.sudo_run_cmd(
                    f"nmcli connection up '{conn}' 2>/dev/null; nmcli device connect {dev} 2>/dev/null; true",
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
            logger.info(f"网络恢复后地址: {restored}")

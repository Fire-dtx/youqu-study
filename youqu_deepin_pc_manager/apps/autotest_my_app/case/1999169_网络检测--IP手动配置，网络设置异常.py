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

    def test_mycase_104(self):
        """IP 手动配置导致网络设置异常：产品网络设置检测取当前首个有效 IPv4 与
        默认网关比较网段。因此前置追加一条指向 192.168.0.1(跨网段, onlink)、
        metric 更小的默认路由, 等效于"手动把 IP/网关配到与现有网段不匹配的
        192.168.0.x", 代替在控制中心改网卡配置(会中断管理链路)。
        该路由不影响同网段的管理链路, 检测结束后删除并恢复原路由。
        断言: 网络设备检测正常、网络设置检测异常、整组跑完且有检出问题。
        """
        widget = MyAppWidget(check_start=False)
        dev = widget.run_cmd(
            "ip route show default | awk '/^default/{for(i=1;i<=NF;i++) "
            "if($i==\"dev\"){print $(i+1); exit}}'",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        self.assert_true(dev)
        widget.sudo_run_cmd(
            f"ip route del default via 192.168.0.1 dev {dev} metric 50 2>/dev/null; "
            f"ip route add default via 192.168.0.1 dev {dev} metric 50 onlink",
            timeout=15,
            out_debug_flag=False,
        )
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            self.assert_true(widget.run_detection_item("网络检测"))

            hw_verdict, hw_detail = widget.get_detection_item_verdict("network_hardware")
            logger.info(f"网络设备检测单项结论: {hw_verdict}, 原始结果: {hw_detail}")
            self.assert_true(hw_verdict is True)

            state = widget.get_detection_group_state("网络检测")
            self.assert_equal(state["total"], state["checked"])
            self.assert_true(state["issues"] > 0)

            verdict, detail = widget.get_detection_item_verdict("network_settings")
            logger.info(f"网络设置检测单项结论: {verdict}, 原始结果: {detail}")
            self.assert_true(verdict is False)
        finally:
            widget.sudo_run_cmd(
                f"ip route del default via 192.168.0.1 dev {dev} metric 50 2>/dev/null; true",
                timeout=15,
                out_debug_flag=False,
            )
            route = widget.run_cmd("ip route show default", timeout=10, out_debug_flag=False).strip()
            logger.info(f"默认路由恢复: {route}")

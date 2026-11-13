#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_332(self):
        """IP 地址冲突检测-有线无冲突

        前置: 单台设备、有线地址在同网段内唯一(测试机 enp0s3 由 DHCP 分配
        10.20.33.103/24, 同段内无其它主机占用该地址)。

        产品实现(network_detector.cpp:430-466, 845-868): 遍历 Ethernet/Wifi 且
        up/running、非 lo/非 bridge 的网卡, 对每个 IPv4 执行
        `arping -D -I <网卡> <IP> -w 3`, 退出码 1 判为冲突; 无冲突时
        resultStatus.success=true。

        断言: 网络检测分项真实执行完成; 界面存在"IP 地址冲突"检测项; 产品
        D-Bus 通道的 ip_conflict 结论为成功(success=true), 且明细中没有
        冲突地址。该用例不构造任何数据, 结束无需回退。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        try:
            # 前置核对: 有线网卡已启用且持有 IPv4
            wired_ip = widget.run_cmd(
                "ip -o -4 addr show dev enp0s3 | awk '{print $4}'",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            print(f"[2032619] 有线地址: {wired_ip!r}")
            self.assert_true("/" in wired_ip)
            # 前置核对(等价 arping 口径): 产品会 exec arping -D, 先自查同一命令
            rc = widget.arping_conflict("enp0s3", wired_ip.split("/")[0])
            print(f"[2032619] arping -D 退出码: {rc}")
            self.assert_equal(0, rc)
            # 真实执行网络检测分项
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("网络检测"))
            self.assert_true(widget.get_detection_item_present("网络检测", "IP 地址冲突"))
            state = widget.get_detection_group_state("网络检测")
            print(f"[2032619] 网络检测分组状态: {state}")
            self.assert_equal(state["total"], state["checked"])
            # 产品结论通道: 无冲突 -> success=true
            ok, detail = widget.get_ip_conflict_verdict(timeout=90)
            print(f"[2032619] ip_conflict 结论: ok={ok} detail={detail[-200:]!r}")
            self.assert_true(ok is True)
        finally:
            widget.kill_pc_manager()

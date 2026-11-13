#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_376(self):
        """IP 地址冲突检测-无线无冲突

        前置: 设备通过无线网卡联网, 其 IPv4 在同网段内唯一。

        环境事实: 测试机为 VM, 只有一块以太网卡 enp0s3, 无无线硬件; 而产品
        实现(network_detector.cpp:439-445)只区分 Ethernet/Wifi 两种类型, 后续
        探测(845-868)对两者走同一条 `arping -D -I <网卡> <IP> -w 3` 路径, 没有
        任何无线专属分支。因此用一块独立的虚拟网卡(类型 Ethernet, up/running)
        代表"本机无线网卡", 其净荷与无线网卡完全相同。

        构造: widget.setup_virtual_net_device() 建独立 netns + veth 对,
        主机侧 veth-at 配置 192.168.77.2/24(与办公网 10.20.33.0/24 隔离,
        不影响 SSH), 对端设备不占用该地址 —— 即"同段无第二台设备使用同一 IP"。

        断言: arping -D 自查 rc=0; 真实执行网络检测后, 界面存在"IP 地址冲突"
        项, 产品 D-Bus 通道 ip_conflict 结论 success=true 且冲突地址为空。

        finally: 删除 veth 对与 netns, 校验无残留。
        """
        widget = MyAppWidget(check_start=False)
        net = None
        try:
            net = widget.setup_virtual_net_device(ip="192.168.77.2", conflict=False)
            self.assert_true(net["ok"])
            state = widget.get_virtual_net_device_state(net["name"])
            print(f"[2032621] 虚拟无线网卡状态: {state}")
            self.assert_true(state["exists"])
            self.assert_equal("up", state["operstate"])
            self.assert_true(state["ipv4"].startswith("192.168.77.2/24"))
            # 前置核对(与产品同口径)
            rc = widget.arping_conflict(net["name"], "192.168.77.2")
            print(f"[2032621] arping -D 退出码: {rc}")
            self.assert_equal(0, rc)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("网络检测"))
            self.assert_true(
                widget.get_detection_item_present("网络检测", "IP 地址冲突")
            )
            state = widget.get_detection_group_state("网络检测")
            print(f"[2032621] 网络检测分组状态: {state}")
            self.assert_equal(state["total"], state["checked"])
            ok, detail = widget.get_ip_conflict_verdict(timeout=90)
            print(f"[2032621] ip_conflict 结论: ok={ok} detail={detail[-200:]!r}")
            self.assert_true(ok is True)
            self.assert_true("@as []" in detail)
        finally:
            widget.kill_pc_manager()
            widget.teardown_virtual_net_device(net)
            left = widget.run_cmd(
                "ip -o link show | grep -c veth; ip netns list | grep -c autotest_pcm",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            print(f"[2032621] 清理后残留计数: {left!r}")
            self.assert_equal("0\n0", left)

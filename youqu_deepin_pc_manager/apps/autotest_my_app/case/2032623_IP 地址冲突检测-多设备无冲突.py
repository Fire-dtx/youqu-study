#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_377(self):
        """IP 地址冲突检测-多设备无冲突

        前置: 设备存在有线 + 无线两块网卡(或至少两块网卡), 各自的 IPv4 在同
        网段内唯一, 检测应通过。

        环境事实: 测试机为 VM, 只有一块以太网卡 enp0s3, 无第二块物理网卡。
        产品实现(network_detector.cpp:430-466)对每块 up/running 的非 lo/非
        bridge 网卡逐个探测, 与网卡数量无关, 因此用两块独立虚拟网卡等价
        覆盖"多设备"分支: veth-at(192.168.77.2/24) + veth-at2(192.168.77.3/24),
        各自对端设备均不占用对应地址, 且两者都在独立的 netns 里(与办公网
        10.20.33.0/24 隔离)。

        断言: 两块虚拟网卡都 up 且持有 IPv4; 各自 arping -D rc=0; 真实执行
        网络检测后界面存在"IP 地址冲突"项, 产品 D-Bus ip_conflict 结论
        success=true 且冲突地址列表为空。

        finally: 删除两块虚拟网卡与 netns, 校验无残留。
        """
        widget = MyAppWidget(check_start=False)
        nets = []
        try:
            first = widget.setup_virtual_net_device(
                ip="192.168.77.2", conflict=False, name="veth-at"
            )
            nets.append(first)
            self.assert_true(first["ok"])
            second = widget.setup_virtual_net_device(
                ip="192.168.77.3", conflict=False, name="veth-at2"
            )
            nets.append(second)
            self.assert_true(second["ok"])
            for net in nets:
                state = widget.get_virtual_net_device_state(net["name"])
                print(f"[2032623] {net['name']} 状态: {state}")
                self.assert_true(state["exists"])
                self.assert_equal("up", state["operstate"])
                self.assert_true(state["ipv4"].startswith(net["ip"] + "/24"))
                rc = widget.arping_conflict(net["name"], net["ip"])
                print(f"[2032623] {net['name']} arping -D 退出码: {rc}")
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
            print(f"[2032623] 网络检测分组状态: {state}")
            self.assert_equal(state["total"], state["checked"])
            ok, detail = widget.get_ip_conflict_verdict(timeout=90)
            print(f"[2032623] ip_conflict 结论: ok={ok} detail={detail[-200:]!r}")
            self.assert_true(ok is True)
            self.assert_true("@as []" in detail)
        finally:
            widget.kill_pc_manager()
            for net in nets:
                widget.teardown_virtual_net_device(net)
            left = widget.run_cmd(
                "ip -o link show | grep -c veth; ip netns list | grep -c autotest_pcm",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            print(f"[2032623] 清理后残留计数: {left!r}")
            self.assert_equal("0\n0", left)

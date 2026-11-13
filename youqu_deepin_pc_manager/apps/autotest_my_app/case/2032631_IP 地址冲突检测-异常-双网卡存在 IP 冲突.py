#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_365(self):
        """IP 地址冲突检测-异常-双网卡存在 IP 冲突

        前置: 有线网卡与无线网卡的 IPv4 分别与同网段内另一台设备重复。

        环境事实: 测试机为 VM, 单网卡且无第二台可控主机; 直接改地址会断 SSH。
        产品实现(network_detector.cpp:430-466, 845-868)对每块网卡的每个 IPv4
        逐个 arping -D, 检出任意一个重复即 success=false 并列出全部冲突地址。
        因此用两块独立虚拟网卡 + 各自 netns 内的对端设备构造双冲突:
          veth-at  = 192.168.77.2/24, 对端同址(代表有线冲突)
          veth-at2 = 192.168.77.3/24, 对端同址(代表无线冲突)
        网段 192.168.77.0/24 与办公网 10.20.33.0/24 隔离, 管理链路不受影响。

        断言: 两个地址 arping -D 均为 1; 真实执行网络检测后界面存在"IP 地址
        冲突"项; 产品 D-Bus 结论 ok=False; 守护进程日志同时列出两个冲突地址
        且 success: false。

        finally: 删除两块 veth 与两个 netns, 校验无残留。
        """
        widget = MyAppWidget(check_start=False)
        nets = []
        try:
            first = widget.setup_virtual_net_device(
                ip="192.168.77.2", conflict=True, name="veth-at"
            )
            nets.append(first)
            self.assert_true(first["ok"])
            second = widget.setup_virtual_net_device(
                ip="192.168.77.3", conflict=True, name="veth-at2"
            )
            nets.append(second)
            self.assert_true(second["ok"])
            for net in nets:
                state = widget.get_virtual_net_device_state(net["name"])
                print(f"[2032631] {net['name']} 状态: {state}")
                self.assert_true(state["exists"])
                self.assert_equal("up", state["operstate"])
                self.assert_true(state["ipv4"].startswith(net["ip"] + "/24"))
                rc = widget.arping_conflict(net["name"], net["ip"])
                print(f"[2032631] {net['name']} arping -D 退出码(期望1): {rc}")
                self.assert_equal(1, rc)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("网络检测"))
            self.assert_true(
                widget.get_detection_item_present("网络检测", "IP 地址冲突")
            )
            state = widget.get_detection_group_state("网络检测")
            print(f"[2032631] 网络检测分组状态: {state}")
            self.assert_equal(state["total"], state["checked"])
            self.assert_true(state["issues"] >= 1)
            ok, detail = widget.get_ip_conflict_verdict(timeout=90)
            print(f"[2032631] ip_conflict 结论: ok={ok} detail={detail[-260:]!r}")
            self.assert_false(ok)
            log_tail = widget.get_ip_conflict_log_tail(lines=20)
            print(f"[2032631] 冲突日志: {log_tail[-500:]!r}")
            self.assert_true(
                'probe "192.168.77.2" on "veth-at" exit 1' in log_tail
            )
            self.assert_true(
                'probe "192.168.77.3" on "veth-at2" exit 1' in log_tail
            )
            self.assert_true('"192.168.77.2"' in log_tail)
            self.assert_true('"192.168.77.3"' in log_tail)
            self.assert_true("success: false" in log_tail)
        finally:
            widget.kill_pc_manager()
            for net in nets:
                widget.teardown_virtual_net_device(net)
            left = widget.run_cmd(
                "ip -o link show | grep -c veth; ip netns list | grep -c autotest_pcm",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            print(f"[2032631] 清理后残留计数: {left!r}")
            self.assert_equal("0\n0", left)

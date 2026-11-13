#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_362(self):
        """IP 地址冲突检测-单网卡配置多个辅助 IP, 全部无冲突

        前置: 一块网卡上配置主 IPv4 + 多个辅助 IPv4(同网段), 这些地址在网络
        中都没有被其它设备占用。

        产品实现(network_detector.cpp:451-463): 对每块网卡的所有 IPv4 逐个
        arping -D, 全部 rc!=1 时 resultStatus.success=true。

        构造: 用独立 netns + veth 对构造"本机网卡" veth-at, 主地址
        192.168.77.2/24, 追加辅助地址 192.168.77.3/24、192.168.77.4/24;
        对端设备(netns 内 veth-peer)不占用任何这三个地址, 与办公网
        10.20.33.0/24 隔离, 不影响 SSH。

        断言: 网卡上三个 IPv4 齐全; 三个地址 arping -D 均 rc=0; 真实执行网络
        检测后界面存在"IP 地址冲突"项, 产品 D-Bus ip_conflict 结论
        success=true 且冲突地址列表为空。

        finally: 删除 veth 对(辅助地址随网卡消失)与 netns, 校验无残留。
        """
        widget = MyAppWidget(check_start=False)
        net = None
        helper_ips = ["192.168.77.3/24", "192.168.77.4/24"]
        try:
            net = widget.setup_virtual_net_device(ip="192.168.77.2", conflict=False)
            self.assert_true(net["ok"])
            for addr in helper_ips:
                widget.sudo_run_cmd(
                    f"ip addr add {addr} dev {net['name']}",
                    timeout=15,
                    out_debug_flag=False,
                )
            inet_list = widget.run_cmd(
                f"ip -o -4 addr show dev {net['name']} | awk '{{print $4}}'",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            print(f"[2032625] 网卡 IPv4 列表: {inet_list!r}")
            self.assert_equal(3, len(inet_list.splitlines()))
            for addr in ["192.168.77.2/24"] + helper_ips:
                self.assert_true(addr in inet_list)
            # 前置核对(与产品同口径): 三个地址都无冲突
            for addr in ["192.168.77.2"] + [a.split("/")[0] for a in helper_ips]:
                rc = widget.arping_conflict(net["name"], addr)
                print(f"[2032625] arping -D {addr} 退出码: {rc}")
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
            print(f"[2032625] 网络检测分组状态: {state}")
            self.assert_equal(state["total"], state["checked"])
            ok, detail = widget.get_ip_conflict_verdict(timeout=90)
            print(f"[2032625] ip_conflict 结论: ok={ok} detail={detail[-200:]!r}")
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
            print(f"[2032625] 清理后残留计数: {left!r}")
            self.assert_equal("0\n0", left)

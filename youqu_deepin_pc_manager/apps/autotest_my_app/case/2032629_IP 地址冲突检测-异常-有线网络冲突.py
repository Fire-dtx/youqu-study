#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_323(self):
        """IP 地址冲突检测-异常-有线网络冲突

        前置: 本机有线网卡配置的 IPv4 与同网段另一台设备重复。

        环境事实: 测试机为 VM, 只有一块 enp0s3 且没有第二台可控主机。直接给
        enp0s3 配重复地址或改网络地址会让 SSH 失联, 因此用与产品探测路径
        完全一致的等价构造: 独立 netns 内的 veth 对, 主机侧 veth-at(类型
        Ethernet, 与"有线网卡"同类)配 192.168.77.2/24, netns 内对端设备配置
        同一地址, 即"同网段另一台设备占用同一 IP"。网段 192.168.77.0/24 与
        办公网 10.20.33.0/24 隔离, 管理链路不受影响。

        断言: arping -D 返回 1; 真实执行网络检测后界面存在"IP 地址冲突"项;
        产品 D-Bus ip_conflict 结论 ok=False(failure:4013); 守护进程日志记录
        `probe "192.168.77.2" on "veth-at" exit 1`、`IP address conflict
        detected: ("192.168.77.2"` 与 `success: false`。

        finally: 删除 veth 对与 netns, 校验无残留。
        """
        widget = MyAppWidget(check_start=False)
        net = None
        try:
            net = widget.setup_virtual_net_device(ip="192.168.77.2", conflict=True)
            self.assert_true(net["ok"])
            state = widget.get_virtual_net_device_state(net["name"])
            print(f"[2032629] 虚拟有线网卡状态: {state}")
            self.assert_true(state["exists"])
            self.assert_equal("up", state["operstate"])
            self.assert_true(state["ipv4"].startswith("192.168.77.2/24"))
            rc = widget.arping_conflict(net["name"], "192.168.77.2")
            print(f"[2032629] arping -D 退出码(期望1): {rc}")
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
            print(f"[2032629] 网络检测分组状态: {state}")
            self.assert_equal(state["total"], state["checked"])
            self.assert_true(state["issues"] >= 1)
            ok, detail = widget.get_ip_conflict_verdict(timeout=90)
            print(f"[2032629] ip_conflict 结论: ok={ok} detail={detail[-260:]!r}")
            self.assert_false(ok)
            log_tail = widget.get_ip_conflict_log_tail()
            print(f"[2032629] 冲突日志: {log_tail[-400:]!r}")
            self.assert_true(
                'probe "192.168.77.2" on "veth-at" exit 1' in log_tail
            )
            self.assert_true('IP address conflict detected: ("192.168.77.2"' in log_tail)
            self.assert_true("success: false" in log_tail)
        finally:
            widget.kill_pc_manager()
            widget.teardown_virtual_net_device(net)
            left = widget.run_cmd(
                "ip -o link show | grep -c veth; ip netns list | grep -c autotest_pcm",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            print(f"[2032629] 清理后残留计数: {left!r}")
            self.assert_equal("0\n0", left)

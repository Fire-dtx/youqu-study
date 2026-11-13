#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

class TestMyCase(BaseCase):

    def test_mycase_326(self):
        """磁盘健康状态判定：按 smartctl -H 的返回结果计算期望状态
        (PASSED/OK -> 良好, FAILED -> 损坏, 其它 -> 未知), 再点击"硬件检测"
        卡片真实执行检测, 断言磁盘健康项存在、整组跑完, 且问题数与期望状态一致。"""
        widget = MyAppWidget(check_start=False)

        # 前置: 依赖预检 -- smartmontools 缺失则安装, 再确认 smartctl 可用
        dependency = widget.ensure_package_installed("smartmontools", probe_cmd="smartctl")
        if not dependency["installed"]:
            pytest.skip(
                f"无法安装 smartmontools(依赖输出={dependency['detail'][:120]}), "
                "无法计算磁盘健康期望状态"
            )
        smartctl = widget.run_cmd(
            "command -v smartctl || ls /usr/sbin/smartctl 2>/dev/null", timeout=10, out_debug_flag=False
        ).strip()
        if not smartctl:
            pytest.skip("安装后仍无法定位 smartctl, 无法计算磁盘健康期望状态")
        pkname = widget.run_cmd(
            "lsblk -ndo pkname $(findmnt -n -o SOURCE /) 2>/dev/null | head -1",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        if not pkname:
            pytest.skip("无法确定根分区所在磁盘, 跳过此用例")
        health = widget.sudo_run_cmd(f"{smartctl} -H /dev/{pkname}", timeout=30, out_debug_flag=False)
        health_upper = (health or "").upper()
        if "UNAVAILABLE" in health_upper or "LACKS SMART" in health_upper:
            pytest.skip("磁盘不支持 SMART(虚拟机虚拟盘), 期望状态为'未知', 无法覆盖良好/损坏判定")
        if "PASSED" in health_upper:
            expect_issues_zero = True
        elif "FAILED" in health_upper:
            expect_issues_zero = False
        else:
            pytest.skip(f"smartctl 无法给出可判定状态(输出: {health.strip()[:80]}), 期望状态为'未知', 跳过")

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        # 点击"硬件检测"卡片, 真实触发该分项检测
        self.assert_true(widget.run_detection_item("硬件检测"))

        self.assert_true(widget.get_detection_item_present("硬件检测", "磁盘健康"))
        # 只点了"硬件检测", 其它分项不应被检查(区别于全面检测)
        self.assert_true(widget.is_only_group_detected("硬件检测"))
        state = widget.get_detection_group_state("硬件检测")
        self.assert_true(state["total"] > 0)
        self.assert_equal(state["total"], state["checked"])
        if expect_issues_zero:
            self.assert_equal(0, state["issues"])
        else:
            self.assert_true(state["issues"] > 0)

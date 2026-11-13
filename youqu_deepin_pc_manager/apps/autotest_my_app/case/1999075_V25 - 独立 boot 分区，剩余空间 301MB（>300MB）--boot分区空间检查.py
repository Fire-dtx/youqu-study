#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/04
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep, logger


class TestMyCase(BaseCase):

    def test_mycase_320(self):
        """V25 - 独立 boot 分区，剩余空间 301MB（>300MB）--boot分区空间检查：
        构造 /boot 剩余空间约 301MB（>300MB 的 V25 阈值）后，点击"更新环境检测"卡片，
        "boot分区空间检测"项存在、整组跑完无问题，单项结论为成功(空间充足)。

        阈值（update_detector.cpp kV25BootSpaceThresholdMB）为 300MB。"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        if not widget.is_v25_environment():
            pytest.skip("当前为 V20 环境(阈值 160MB), 请在 V25 环境执行本用例")

        boot_root = widget.run_cmd(
            "findmnt -n -o TARGET --target /boot 2>/dev/null", timeout=5, out_debug_flag=False
        ).strip()
        self.assert_equal("/boot", boot_root)

        boot_avail_bytes = int(widget.run_cmd(
            "df -B1 --output=avail /boot 2>/dev/null | tail -1", timeout=5, out_debug_flag=False
        ).strip())
        threshold_bytes = 300 * 1024 * 1024
        target_avail_bytes = 301 * 1024 * 1024
        fill_file = "/boot/.pcm_test_boot_fill"

        if boot_avail_bytes <= threshold_bytes:
            pytest.skip(
                f"/boot 当前剩余 {boot_avail_bytes // 1048576}MB <= 300MB 阈值, 无法构造 301MB 场景"
            )
        widget.sudo_run_cmd(f"rm -f {fill_file} 2>/dev/null", timeout=10, out_debug_flag=False)

        try:
            if boot_avail_bytes > target_avail_bytes:
                fill_bytes = boot_avail_bytes - target_avail_bytes
                widget.sudo_run_cmd(
                    f"fallocate -l {fill_bytes} {fill_file} 2>/dev/null || "
                    f"dd if=/dev/zero of={fill_file} bs=1M "
                    f"count=$(( ({fill_bytes} + 1048575) / 1048576 )) 2>/dev/null",
                    timeout=60,
                    out_debug_flag=False,
                )
                sleep(1)
            self.assert_true(int(widget.run_cmd(
                "df -B1 --output=avail /boot 2>/dev/null | tail -1", timeout=5, out_debug_flag=False
            ).strip()) > threshold_bytes)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            self.assert_true(widget.run_detection_item("更新环境检测"))

            self.assert_true(widget.get_detection_item_present("更新环境检测", "boot分区空间检测"))
            self.assert_true(widget.is_only_group_detected("更新环境检测"))

            state = widget.get_detection_group_state("更新环境检测")
            self.assert_true(state["total"] > 0)
            self.assert_equal(state["total"], state["checked"])
            self.assert_equal(0, state["issues"])

            verdict, detail = widget.get_detection_item_verdict("boot_partition_space")
            logger.info(f"boot分区空间检测单项结论(剩余约 301MB): {verdict}, 原始结果: {detail}")
            self.assert_true(verdict)
        finally:
            widget.sudo_run_cmd(f"rm -f {fill_file} 2>/dev/null", timeout=10, out_debug_flag=False)
            widget.kill_pc_manager()

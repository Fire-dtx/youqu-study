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

    def test_mycase_321(self):
        """V20 - 独立 boot 分区，剩余空间 161MB（>160MB）--boot分区空间检查：
        构造 /boot 剩余空间约 161MB（>160MB 阈值）后，点击"更新环境检测"卡片，
        "boot分区空间检测"项存在、整组跑完无问题，单项结论为成功(空间充足)。

        产品检测逻辑（update_detector.cpp detectBootPartitionSpace）：
        阈值为 160MB，可用空间 <= 160MB 报不足，> 160MB 判成功。"""
        widget = MyAppWidget(check_start=False)

        # 验证当前为 V20 系统（阈值 160MB）
        version_id = widget.run_cmd(
            ". /etc/os-release && echo $VERSION_ID", timeout=5, out_debug_flag=False
        ).strip()
        if not version_id or version_id.startswith("25"):
            pytest.skip(f"当前系统 VERSION_ID={version_id or '未知'}, 非 V20 环境, 跳过此用例")

        # 验证 /boot 为独立分区
        boot_root = widget.run_cmd(
            "findmnt -n -o TARGET --target /boot 2>/dev/null", timeout=5, out_debug_flag=False
        ).strip()
        self.assert_equal("/boot", boot_root)

        boot_avail_bytes = int(widget.run_cmd(
            "df -B1 --output=avail /boot 2>/dev/null | tail -1", timeout=5, out_debug_flag=False
        ).strip())
        threshold_bytes = 160 * 1024 * 1024
        target_avail_bytes = 161 * 1024 * 1024
        fill_file = "/boot/.pcm_test_boot_fill"
        widget.sudo_run_cmd(f"rm -f {fill_file} 2>/dev/null", timeout=10, out_debug_flag=False)

        try:
            # 构造 /boot 剩余空间约 161MB（仅当当前可用空间大于目标时填充）
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

            current_avail_bytes = int(widget.run_cmd(
                "df -B1 --output=avail /boot 2>/dev/null | tail -1", timeout=5, out_debug_flag=False
            ).strip())
            self.assert_true(current_avail_bytes > threshold_bytes)

            widget.kill_pc_manager()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            # 点击"更新环境检测"卡片, 真实触发该分项检测
            self.assert_true(widget.run_detection_item("更新环境检测"))

            self.assert_true(widget.get_detection_item_present("更新环境检测", "boot分区空间检测"))
            self.assert_true(widget.is_only_group_detected("更新环境检测"))

            state = widget.get_detection_group_state("更新环境检测")
            self.assert_true(state["total"] > 0)
            self.assert_equal(state["total"], state["checked"])
            self.assert_equal(0, state["issues"])

            verdict, detail = widget.get_detection_item_verdict("boot_partition_space")
            logger.info(f"boot分区空间检测单项结论(剩余约 161MB): {verdict}, 原始结果: {detail}")
            self.assert_true(verdict)
        finally:
            widget.sudo_run_cmd(f"rm -f {fill_file} 2>/dev/null", timeout=10, out_debug_flag=False)
            widget.kill_pc_manager()

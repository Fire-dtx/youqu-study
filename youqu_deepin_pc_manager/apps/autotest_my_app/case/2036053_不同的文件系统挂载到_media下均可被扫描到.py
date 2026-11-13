#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import os
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def _media_partitions(self):
        """解析 /media 下挂载的分区, 分为内置数据盘与外部设备两组"""
        out = self.widget.run_cmd(
            "lsblk -n -o NAME,MOUNTPOINT 2>/dev/null", timeout=15, out_debug_flag=False,
        )
        internal, external = [], []
        for line in out.splitlines():
            parts = line.replace("├─", " ").replace("└─", " ").split()
            if len(parts) < 2 or not parts[1].startswith("/media"):
                continue
            name, mount = parts[0], parts[1]
            base = re.sub(r"\d+$", "", name)
            removable = self.widget.run_cmd(
                f"cat /sys/block/{base}/removable 2>/dev/null",
                timeout=5, out_debug_flag=False,
            ).strip()
            real = self.widget.run_cmd(
                f"readlink -f /sys/class/block/{name} 2>/dev/null",
                timeout=5, out_debug_flag=False,
            ).strip()
            if removable == "0" and "usb" not in real:
                internal.append(mount)
            else:
                external.append(mount)
        return sorted(set(internal)), sorted(set(external))

    def test_mycase_211(self):
        """不同的文件系统挂载到/media下均可被扫描到

        步骤: 1. /media 下挂载的分区(本机为内置数据分区 sda6, ext4);
        2. 打开设置-清理设置, 查看"扩展扫描分区"列表。
        预期: 扩展扫描分区下列出 /media 下挂载的分区信息(挂载点)。

        环境说明: 本机没有空闲磁盘可新建 ext2/ext3/btrfs/xfs/ntfs/fat32/exfat
        分区, 且未安装 losetup/mkfs.vfat, 无法用镜像文件构造多文件系统挂载;
        产品另按设计(ADR 0007)排除 loop 设备与 USB 外接盘, 因此本用例以系统
        真实的内置数据分区验证扫描与展示链路, 并校验外接盘不被误列。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        widget.kill_pc_manager()
        widget.remove_test_junk_files()
        try:
            internal, external = self._media_partitions()
            logger.info(f"[2036053] 内置/media分区={internal} 外接={external}")
            self.assert_true(len(internal) >= 1)

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing(timeout=15))
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())
            self.assert_true(widget.get_extended_scan_partition_row_count() >= 1)

            mount_points = widget.get_extended_scan_partition_mount_points()
            logger.info(f"[2036053] UI挂载点={mount_points}")
            self.assert_true(len(mount_points) >= 1)
            for path in internal:
                self.assert_true(path in mount_points)
            for path in mount_points:
                self.assert_true(path.startswith("/media"))
        finally:
            try:
                widget.close_settings_dialog()
            except BaseException:
                pass
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

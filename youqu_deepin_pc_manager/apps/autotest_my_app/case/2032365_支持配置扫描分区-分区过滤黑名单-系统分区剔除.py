#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep

MOUNT_POINT = "/media/autotest_data"
DEVICE = "/dev/sda6"
RESERVED = (
    "/",
    "/home",
    "/boot",
    "/boot/efi",
    "/recovery",
    "/sys",
    "/proc",
    "/dev",
    "/var",
    "/opt",
)


class TestMyCase(BaseCase):

    def test_mycase_041(self):
        """支持配置扫描分区-分区过滤黑名单-系统分区剔除

        前置: fstab 已含 /、/boot、/boot/efi、swap(/home 为 /data 的 bind
        挂载)。构造一块内置数据盘 /dev/sda6 挂到 /media/autotest_data,
        进入设置页观察列表。
        断言: 黑名单挂载点(/、/home、/boot、/boot/efi、swap、/sys、/proc、
        /dev 等)均不在列表; 数据盘正常展示(positive control)。
        清理: umount 并删除挂载点。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            # 前置事实: fstab/实际挂载包含系统分区与 swap
            fstab = widget.run_cmd("cat /etc/fstab", timeout=5, out_debug_flag=False)
            for path in ("/boot", "/boot/efi"):
                self.assert_true(path in fstab)
            swaps = widget.run_cmd(
                "cat /proc/swaps", timeout=5, out_debug_flag=False
            )
            self.assert_true("partition" in swaps or "file" in swaps)

            # 构造内置数据盘(非系统分区)
            widget.sudo_run_cmd(
                f"umount {MOUNT_POINT} 2>/dev/null; rmdir {MOUNT_POINT} 2>/dev/null; true",
                timeout=15,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {MOUNT_POINT} && mount {DEVICE} {MOUNT_POINT} && "
                f"findmnt -n -o SOURCE {MOUNT_POINT}",
                timeout=20,
                return_code=True,
            )
            logger.info(f"[2032365] mount rc={rc} out={out!r}")
            self.assert_true(rc == 0)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())

            rows = []
            for expr in (
                "$//settings_extendedScanPartition",
                "$//extendedScanPartitionRow",
            ):
                rows = widget.dog.find_elements_by_attr(expr) or []
                if rows:
                    break
            mounts = [getattr(r, "description", "") or "" for r in rows]
            logger.info(f"[2032365] mounts={mounts!r}")

            # 黑名单系统分区不得出现
            for path in RESERVED:
                self.assert_true(path not in mounts)
            # 正向对照: 内置数据盘应展示
            self.assert_true(MOUNT_POINT in mounts)
            # 列表项只能来自 /media(扩展扫描范围)
            for mp in mounts:
                self.assert_true(mp.startswith("/media/"))
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"umount {MOUNT_POINT} 2>/dev/null; umount -l {MOUNT_POINT} 2>/dev/null; "
                f"rmdir {MOUNT_POINT} 2>/dev/null; true",
                timeout=20,
            )

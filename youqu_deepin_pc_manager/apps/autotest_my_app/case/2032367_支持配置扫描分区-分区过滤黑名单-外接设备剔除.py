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

INT_MOUNT = "/media/autotest_int"
EXT_MOUNT = "/media/autotest_usb"
INT_DEV = "/dev/sda6"
EXT_DEV = "/dev/sdb1"


class TestMyCase(BaseCase):

    def test_mycase_193(self):
        """支持配置扫描分区-分区过滤黑名单-外接设备剔除

        前置: 测试机 /dev/sdb 是 USB 总线上的移动盘(removable=0, 但
        sysfs 路径含 usb2/2-1, 与 U 盘/移动硬盘同类), 将其分区挂到
        /media/autotest_usb; /dev/sda6 挂到 /media/autotest_int 作内置
        固定盘正向对照。
        断言: 外接 USB 挂载点不展示; 内置盘展示且列表仅含内置盘。
        清理: umount 两处并删除挂载点。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            real = widget.run_cmd(
                "readlink -f /sys/block/sdb", timeout=5, out_debug_flag=False
            ).strip()
            removable = widget.run_cmd(
                "cat /sys/block/sdb/removable", timeout=5, out_debug_flag=False
            ).strip()
            logger.info(f"[2032367] sdb_real={real!r} removable={removable!r}")
            # 前置: sdb 走 USB 总线, 属外接设备
            self.assert_true("/usb" in real)

            widget.sudo_run_cmd(
                f"umount {INT_MOUNT} 2>/dev/null; umount {EXT_MOUNT} 2>/dev/null; "
                f"rmdir {INT_MOUNT} {EXT_MOUNT} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {INT_MOUNT} {EXT_MOUNT} && "
                f"mount {INT_DEV} {INT_MOUNT} && mount {EXT_DEV} {EXT_MOUNT} && "
                f"findmnt -n -o SOURCE {INT_MOUNT} && "
                f"findmnt -n -o SOURCE {EXT_MOUNT}",
                timeout=30,
                return_code=True,
            )
            logger.info(f"[2032367] mount rc={rc} out={out!r}")
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
            logger.info(f"[2032367] mounts={mounts!r}")

            self.assert_true(EXT_MOUNT not in mounts)
            self.assert_true(INT_MOUNT in mounts)
            self.assert_true(mounts == [INT_MOUNT])
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"umount {EXT_MOUNT} 2>/dev/null; umount -l {EXT_MOUNT} 2>/dev/null; "
                f"umount {INT_MOUNT} 2>/dev/null; umount -l {INT_MOUNT} 2>/dev/null; "
                f"rmdir {EXT_MOUNT} {INT_MOUNT} 2>/dev/null; true",
                timeout=30,
            )

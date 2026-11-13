#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep

MOUNT_A = "/media/autotest_a"
MOUNT_B = "/media/autotest_b"
MOUNT_C = "/media/autotest_c"
CONF = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
CONF_BAK = "/tmp/pcm_conf.unmount.bak"


class TestMyCase(BaseCase):

    def test_mycase_200(self):
        """支持配置扫描分区-卸载自动消失

        构造: sda6/sda2/sda4 分别挂到 /media/autotest_a|b|c, 设置页显示 3 行。
        步骤: umount B, 关闭并重新打开设置页。
        断言: 列表变为 2 行, B 不再展示, A/C 仍在。
        清理: umount 其余挂载点、rmdir、还原配置。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.sudo_run_cmd(
                f"umount {MOUNT_A} {MOUNT_B} {MOUNT_C} 2>/dev/null; "
                f"rmdir {MOUNT_A} {MOUNT_B} {MOUNT_C} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {MOUNT_A} {MOUNT_B} {MOUNT_C} && "
                f"mount /dev/sda6 {MOUNT_A} && mount /dev/sda2 {MOUNT_B} && "
                f"mount /dev/sda4 {MOUNT_C}",
                timeout=40,
                return_code=True,
            )
            logger.info(f"[2032389] mounts rc={rc} out={out!r}")
            self.assert_true(rc == 0)
            widget.run_cmd(
                f"cp -a {CONF} {CONF_BAK} && "
                f"grep -v 'extendedScanPaths' {CONF} > {CONF}.tmp && "
                f"mv {CONF}.tmp {CONF}",
                timeout=5,
                out_debug_flag=False,
            )

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())
            count = widget.get_extended_scan_partition_row_count()
            mount_points = widget.get_extended_scan_partition_mount_points()
            logger.info(f"[2032389] initial rows={count} {mount_points}")
            self.assert_true(count == 3)
            for mp in (MOUNT_A, MOUNT_B, MOUNT_C):
                self.assert_true(mp in mount_points)

            # 卸载其中一块(B)
            ok = widget.unmount_partition_by_path(MOUNT_B)
            self.assert_true(ok)
            self.assert_false(
                widget.run_cmd(
                    f"findmnt -n -o TARGET {MOUNT_B}",
                    timeout=5,
                    out_debug_flag=False,
                ).strip()
            )

            # 重新进入页面
            widget.close_settings_dialog()
            sleep(2)
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())
            count2 = widget.get_extended_scan_partition_row_count()
            mount_points2 = widget.get_extended_scan_partition_mount_points()
            logger.info(f"[2032389] after rows={count2} {mount_points2}")
            self.assert_true(count2 == 2)
            self.assert_false(MOUNT_B in mount_points2)
            self.assert_true(MOUNT_A in mount_points2 and MOUNT_C in mount_points2)
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"umount {MOUNT_C} {MOUNT_B} {MOUNT_A} 2>/dev/null; "
                f"umount -l {MOUNT_C} {MOUNT_B} {MOUNT_A} 2>/dev/null; "
                f"rmdir {MOUNT_C} {MOUNT_B} {MOUNT_A} 2>/dev/null; true",
                timeout=40,
            )
            widget.run_cmd(
                f"[ -f {CONF_BAK} ] && cp -a {CONF_BAK} {CONF} && rm -f {CONF_BAK}; true",
                timeout=5,
                out_debug_flag=False,
            )

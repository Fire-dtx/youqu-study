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
FSTAB = "/etc/fstab"
FSTAB_BAK = "/tmp/pcm_fstab.autotest.bak"
CONF = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
CONF_BAK = "/tmp/pcm_conf.newmount.bak"


class TestMyCase(BaseCase):

    def test_mycase_045(self):
        """支持配置扫描分区-新增挂载自动追加

        构造: sda6、sda2 挂到 /media 下形成初始 2 行; 清空勾选配置。
        步骤: 修改 /etc/fstab 新增 sda4 -> /media/autotest_c 并 mount,
        关闭并重新打开设置页。
        断言: 列表自动追加 C(共 3 行), 新行默认未勾选。
        清理: 删除 fstab 新增行(还原备份)、umount 三个挂载点、rmdir、
        还原配置。
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
                f"mount /dev/sda6 {MOUNT_A} && mount /dev/sda2 {MOUNT_B}",
                timeout=40,
                return_code=True,
            )
            logger.info(f"[2032387] initial mounts rc={rc} out={out!r}")
            self.assert_true(rc == 0)
            widget.run_cmd(
                f"cp -a {CONF} {CONF_BAK} && "
                f"grep -v 'extendedScanPaths' {CONF} > {CONF}.tmp && "
                f"mv {CONF}.tmp {CONF}",
                timeout=5,
                out_debug_flag=False,
            )
            widget.sudo_run_cmd(f"cp -a {FSTAB} {FSTAB_BAK}", timeout=10)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())
            first_count = widget.get_extended_scan_partition_row_count()
            first_mp = widget.get_extended_scan_partition_mount_points()
            logger.info(f"[2032387] initial rows={first_count} {first_mp}")
            self.assert_true(first_count == 2)
            self.assert_true(MOUNT_A in first_mp and MOUNT_B in first_mp)

            # 修改 fstab 新增内部数据盘 C 并挂载
            out, rc = widget.sudo_run_cmd(
                f"grep -q '/media/autotest_c' {FSTAB} || "
                f"echo '/dev/sda4 {MOUNT_C} ext4 defaults,nofail 0 2' >> {FSTAB}; "
                f"mount /dev/sda4 {MOUNT_C} && echo MOUNTED",
                timeout=40,
                return_code=True,
            )
            logger.info(f"[2032387] add C rc={rc} out={out!r}")
            self.assert_true(rc == 0 and "MOUNTED" in out)
            self.assert_true(
                MOUNT_C
                in widget.run_cmd("findmnt -n -o TARGET /media/autotest_c",
                                  timeout=5, out_debug_flag=False)
            )

            # 重新进入页面: 关闭设置再打开
            widget.close_settings_dialog()
            sleep(2)
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())
            count = widget.get_extended_scan_partition_row_count()
            mount_points = widget.get_extended_scan_partition_mount_points()
            logger.info(f"[2032387] after rows={count} {mount_points}")
            self.assert_true(count == 3)
            self.assert_true(MOUNT_C in mount_points)
            target = None
            for elem in widget.dog.find_elements_by_attr(
                "$//settings_extendedScanPartition"
            ) or []:
                if (getattr(elem, "description", "") or "") == MOUNT_C:
                    target = elem
                    break
            self.assert_true(target is not None)
            checked = bool(getattr(target, "checked", False))
            logger.info(f"[2032387] C checked={checked}")
            self.assert_false(checked)
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
            widget.sudo_run_cmd(
                f"[ -f {FSTAB_BAK} ] && cp -a {FSTAB_BAK} {FSTAB} && rm -f {FSTAB_BAK}; true",
                timeout=10,
            )
            widget.run_cmd(
                f"[ -f {CONF_BAK} ] && cp -a {CONF_BAK} {CONF} && rm -f {CONF_BAK}; true",
                timeout=5,
                out_debug_flag=False,
            )

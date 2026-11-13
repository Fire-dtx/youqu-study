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
DM_NAME = "pcmvol"
DM_DEV = f"/dev/mapper/{DM_NAME}"
CONF = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
CONF_BAK = "/tmp/pcm_conf.resize.bak"


class TestMyCase(BaseCase):

    def test_mycase_201(self):
        """支持配置扫描分区-容量变更更新

        构造: sda4/sda2 挂 /media/autotest_a|b; 用 device-mapper
        在 sda6 上建 5GB 线性卷并挂 /media/autotest_c, 设置页显示 3 行。
        步骤: 将 dm 卷扩容到 8GB(suspend/reload/resume), 重开设置页。
        断言: C 行容量字段由 5GB 更新为 8GB, A/B 行不变。
        清理: umount、dmsetup remove、rmdir、还原配置。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.sudo_run_cmd(
                f"umount {MOUNT_A} {MOUNT_B} {MOUNT_C} 2>/dev/null; "
                f"/sbin/dmsetup remove {DM_NAME} 2>/dev/null; "
                f"rmdir {MOUNT_A} {MOUNT_B} {MOUNT_C} 2>/dev/null; true",
                timeout=30,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {MOUNT_A} {MOUNT_B} {MOUNT_C} && "
                f"mount /dev/sda4 {MOUNT_A} && mount /dev/sda2 {MOUNT_B} && "
                f"/sbin/dmsetup create {DM_NAME} --table "
                f"'0 10485760 linear /dev/sda6 0' && "
                f"/sbin/mkfs.ext4 -F {DM_DEV} >/dev/null 2>&1 && "
                f"mount {DM_DEV} {MOUNT_C} && echo READY",
                timeout=120,
                return_code=True,
            )
            logger.info(f"[2032391] setup rc={rc} out={out[-200:]!r}")
            self.assert_true(rc == 0 and "READY" in out)
            widget.run_cmd(
                f"cp -a {CONF} {CONF_BAK} && "
                f"grep -v 'extendedScanPaths' {CONF} > {CONF}.tmp && "
                f"mv {CONF}.tmp {CONF}",
                timeout=5,
                out_debug_flag=False,
            )

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            def open_cleanup_settings():
                widget.open_settings_dialog()
                widget.click_settings_nav_item("清理设置")
                widget.scroll_settings_content_to_bottom()
                sleep(1)

            def find_row(mount_point):
                for elem in widget.dog.find_elements_by_attr(
                    "$//settings_extendedScanPartition"
                ) or []:
                    if (getattr(elem, "description", "") or "") == mount_point:
                        return elem
                return None

            def snapshot_row(elem, path):
                # AT-SPI 上该复选框的 accessibleName 被产品固定为
                # settings_extendedScanPartition, 行内容量文案不通过文本接口暴露,
                # 因此用行元素截图像素作为"容量字段是否刷新"的客观证据。
                from PIL import Image

                pos = elem.position
                size = elem.size
                widget.run_cmd(f"scrot -o /tmp/pcm_full.png", timeout=10,
                               out_debug_flag=False)
                img = Image.open("/tmp/pcm_full.png")
                left = int(pos[0])
                top = int(pos[1])
                box = (left, top, left + int(size[0]), top + int(size[1]))
                crop = img.crop(box)
                crop.save(path)
                return crop.tobytes()

            open_cleanup_settings()
            count = widget.get_extended_scan_partition_row_count()
            mount_points = widget.get_extended_scan_partition_mount_points()
            logger.info(f"[2032391] rows before count={count} {mount_points}")
            self.assert_true(count == 3)
            self.assert_true(MOUNT_A in mount_points and MOUNT_B in mount_points
                             and MOUNT_C in mount_points)
            row_c = find_row(MOUNT_C)
            self.assert_true(row_c is not None)
            shot_before = snapshot_row(row_c, "/tmp/pcm_row_5g.png")
            widget.close_settings_dialog()
            sleep(2)

            # 扩容 5GB -> 8GB
            out, rc = widget.sudo_run_cmd(
                f"/sbin/dmsetup suspend {DM_NAME} && "
                f"/sbin/dmsetup reload {DM_NAME} --table "
                f"'0 16777216 linear /dev/sda6 0' && "
                f"/sbin/dmsetup resume {DM_NAME} && "
                f"blockdev --getsize64 {DM_DEV}",
                timeout=60,
                return_code=True,
            )
            logger.info(f"[2032391] resize rc={rc} out={out!r}")
            self.assert_true(rc == 0 and "8589934592" in out)

            open_cleanup_settings()
            count2 = widget.get_extended_scan_partition_row_count()
            mount_points2 = widget.get_extended_scan_partition_mount_points()
            logger.info(f"[2032391] rows after count={count2} {mount_points2}")
            self.assert_true(count2 == 3)
            self.assert_true(MOUNT_C in mount_points2)
            row_c2 = find_row(MOUNT_C)
            self.assert_true(row_c2 is not None)
            shot_after = snapshot_row(row_c2, "/tmp/pcm_row_8g.png")
            self.assert_true(shot_before != shot_after)
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"umount {MOUNT_C} {MOUNT_A} {MOUNT_B} 2>/dev/null; "
                f"umount -l {MOUNT_C} {MOUNT_A} {MOUNT_B} 2>/dev/null; "
                f"/sbin/dmsetup remove {DM_NAME} 2>/dev/null; "
                f"rmdir {MOUNT_C} {MOUNT_A} {MOUNT_B} 2>/dev/null; true",
                timeout=60,
            )
            widget.run_cmd(
                f"[ -f {CONF_BAK} ] && cp -a {CONF_BAK} {CONF} && rm -f {CONF_BAK}; true",
                timeout=5,
                out_debug_flag=False,
            )

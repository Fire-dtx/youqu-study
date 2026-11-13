#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep

INT_MOUNT = "/media/autotest_int"
RO_MOUNT = "/media/autotest_ro"
INT_DEV = "/dev/sda6"
RO_DEV = "/dev/sdb1"


class TestMyCase(BaseCase):

    def test_mycase_194(self):
        """支持配置扫描分区-分区过滤黑名单-只读设备剔除

        构造: /dev/sdb1 以只读方式挂载到 /media/autotest_ro(等价 iso9660
        只读挂载; 测试机无光驱介质), /dev/sda6 读写挂载到
        /media/autotest_int 作正向对照。
        断言: 只读挂载点不在列表; 读写内置盘展示。
        清理: umount 两处并删除挂载点。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.sudo_run_cmd(
                f"umount {INT_MOUNT} 2>/dev/null; umount {RO_MOUNT} 2>/dev/null; "
                f"rmdir {INT_MOUNT} {RO_MOUNT} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {INT_MOUNT} {RO_MOUNT} && "
                f"mount {INT_DEV} {INT_MOUNT} && "
                f"mount -o ro {RO_DEV} {RO_MOUNT} && "
                f"findmnt -n -o SOURCE,OPTIONS {INT_MOUNT} && "
                f"findmnt -n -o SOURCE,OPTIONS {RO_MOUNT}",
                timeout=30,
                return_code=True,
            )
            logger.info(f"[2032369] mount rc={rc} out={out!r}")
            self.assert_true(rc == 0)
            # 前置确认: 一个 rw、一个 ro
            ro_opts = widget.run_cmd(
                f"findmnt -n -o OPTIONS {RO_MOUNT}",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            self.assert_true(ro_opts.startswith("ro"))

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
            logger.info(f"[2032369] mounts={mounts!r}")

            self.assert_true(RO_MOUNT not in mounts)
            self.assert_true(INT_MOUNT in mounts)
            self.assert_true(mounts == [INT_MOUNT])
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"umount {RO_MOUNT} 2>/dev/null; umount -l {RO_MOUNT} 2>/dev/null; "
                f"umount {INT_MOUNT} 2>/dev/null; umount -l {INT_MOUNT} 2>/dev/null; "
                f"rmdir {RO_MOUNT} {INT_MOUNT} 2>/dev/null; true",
                timeout=30,
            )

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

MOUNT = "/media/autotest_a"
HOME_FILE = os.path.expanduser("~/autotest_dup_link/home_copy.bin")
DRIVE_FILE = f"{MOUNT}/drive_copy.bin"
CONF = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
CONF_BAK = "/tmp/pcm_conf.dupfile.bak"


class TestMyCase(BaseCase):

    def test_mycase_198(self):
        """支持配置扫描分区-重复文件扫描联动

        构造: /dev/sda6 挂到 /media/autotest_a; 在 /home 与 A 盘各放一个
        内容完全相同的 3MB 文件(重复组跨扫描根)。
        设置页勾选 A 后触发重复文件清理扫描。
        断言: 结果表格同时包含 home_copy.bin 与 drive_copy.bin。
        清理: 删除两文件、还原配置、umount 并删除挂载点、恢复隔离文件。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        isolated = []
        try:
            widget.sudo_run_cmd(
                f"umount {MOUNT} 2>/dev/null; rmdir {MOUNT} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {MOUNT} && mount /dev/sda6 {MOUNT} && "
                f"dd if=/dev/urandom of={DRIVE_FILE} bs=1M count=3 2>/dev/null",
                timeout=60,
                return_code=True,
            )
            logger.info(f"[2032381] mount+drive_file rc={rc} out={out!r}")
            self.assert_true(rc == 0)
            widget.run_cmd(
                f"mkdir -p {os.path.dirname(HOME_FILE)} && cp {DRIVE_FILE} {HOME_FILE} && "
                f"md5sum {DRIVE_FILE} {HOME_FILE}",
                timeout=15,
                out_debug_flag=False,
            )
            md5s = widget.run_cmd(
                f"md5sum {DRIVE_FILE} {HOME_FILE} | awk '{{print $1}}' | sort -u | wc -l",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            logger.info(f"[2032381] md5_unique={md5s!r}")
            self.assert_true(md5s == "1")

            widget.run_cmd(
                f"cp -a {CONF} {CONF_BAK} && "
                f"grep -v 'extendedScanPaths' {CONF} > {CONF}.tmp && "
                f"mv {CONF}.tmp {CONF}",
                timeout=5,
                out_debug_flag=False,
            )
            isolated = widget.isolate_foreign_dup_files()

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            # 勾选数据盘 A
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())
            target = None
            for expr in (
                "$//settings_extendedScanPartition",
                "$//extendedScanPartitionRow",
            ):
                for elem in widget.dog.find_elements_by_attr(expr) or []:
                    if (getattr(elem, "description", "") or "") == MOUNT:
                        target = elem
                        break
                if target:
                    break
            self.assert_true(target is not None)
            target.click()
            sleep(1)
            conf = widget.run_cmd(f"cat {CONF}", timeout=5, out_debug_flag=False)
            self.assert_true(MOUNT in conf)
            widget.close_settings_dialog()
            sleep(2)

            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_optimization_card_by_name("重复文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_dup_file_scan_completed(timeout=300))
            self.assert_true(widget.get_dup_file_result_showing())
            filenames = widget.get_dup_file_table_filenames()
            logger.info(f"[2032381] filenames={filenames}")
            self.assert_true(
                any("home_copy.bin" in name for name in filenames)
            )
            self.assert_true(
                any("drive_copy.bin" in name for name in filenames)
            )
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.run_cmd(
                f"rm -rf {os.path.dirname(HOME_FILE)}; true",
                timeout=10,
                out_debug_flag=False,
            )
            widget.sudo_run_cmd(
                f"rm -f {DRIVE_FILE}; umount {MOUNT} 2>/dev/null; "
                f"umount -l {MOUNT} 2>/dev/null; rmdir {MOUNT} 2>/dev/null; true",
                timeout=30,
            )
            widget.run_cmd(
                f"[ -f {CONF_BAK} ] && cp -a {CONF_BAK} {CONF} && rm -f {CONF_BAK}; true",
                timeout=5,
                out_debug_flag=False,
            )
            widget.restore_foreign_dup_files(isolated)

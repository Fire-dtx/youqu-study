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
BIG_FILE = f"{MOUNT}/autotest_big_5g.bin"
CONF = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
CONF_BAK = "/tmp/pcm_conf.recheck.bak"


class TestMyCase(BaseCase):

    def test_mycase_199(self):
        """支持配置扫描分区-扫描前二次校验

        构造: A 盘(/dev/sda6)挂载并勾选, 内含 5GB 大文件; 触发扫描前
        手动 umount A。
        断言: 扫描正常结束(无报错/不卡死), 结果中不含 A 盘文件; 重新
        挂载后文件仍在(未被误操作)。
        清理: 删除大文件、还原配置、umount/rmdir。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.sudo_run_cmd(
                f"umount {MOUNT} 2>/dev/null; rmdir {MOUNT} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {MOUNT} && mount /dev/sda6 {MOUNT} && "
                f"fallocate -l 5G {BIG_FILE}",
                timeout=60,
                return_code=True,
            )
            logger.info(f"[2032383] mount rc={rc} out={out!r}")
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
            self.assert_true(
                MOUNT
                in widget.run_cmd(f"cat {CONF}", timeout=5, out_debug_flag=False)
            )
            widget.close_settings_dialog()
            sleep(2)

            # 手动卸载已勾选的分区后再扫描
            ok = widget.unmount_partition_by_path(MOUNT)
            self.assert_true(ok)
            self.assert_false(
                widget.run_cmd(
                    f"findmnt -n -o TARGET {MOUNT}",
                    timeout=5,
                    out_debug_flag=False,
                ).strip()
            )

            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_large_file_scan_completed(timeout=240))
            self.assert_true(
                widget.get_large_file_result_showing()
                or widget.get_large_file_empty_showing()
            )
            self.assert_true(widget.get_pc_manager_process_status())
            filenames = widget.get_large_file_table_filenames()
            logger.info(f"[2032383] filenames={filenames}")
            self.assert_false(
                any("autotest_big_5g.bin" in name for name in filenames)
            )

            # 文件仍在, 未被误操作
            widget.sudo_run_cmd(f"mount /dev/sda6 {MOUNT}", timeout=20)
            size = widget.run_cmd(
                f"stat -c %s {BIG_FILE}", timeout=5, out_debug_flag=False
            ).strip()
            logger.info(f"[2032383] file_size={size!r}")
            self.assert_true(size == "5368709120")
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"rm -f {BIG_FILE}; umount {MOUNT} 2>/dev/null; "
                f"umount -l {MOUNT} 2>/dev/null; rmdir {MOUNT} 2>/dev/null; true",
                timeout=30,
            )
            widget.run_cmd(
                f"[ -f {CONF_BAK} ] && cp -a {CONF_BAK} {CONF} && rm -f {CONF_BAK}; true",
                timeout=5,
                out_debug_flag=False,
            )

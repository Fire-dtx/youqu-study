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
CONF_BAK = "/tmp/pcm_conf.largefile.bak"


class TestMyCase(BaseCase):

    def test_mycase_043(self):
        """支持配置扫描分区-大文件扫描联动

        构造: /dev/sda6 挂到 /media/autotest_a, 在其中创建 5GB 大文件;
        在设置页勾选该分区(配置写入 basic.cleanup.extendedScanPaths),
        进入系统优化->大文件清理触发扫描。
        断言: 扫描完成后结果页显示且文件名包含 autotest_big_5g.bin。
        清理: 删除大文件、还原配置、umount 并删除挂载点。
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
                f"fallocate -l 5G {BIG_FILE} && stat -c %s {BIG_FILE}",
                timeout=60,
                return_code=True,
            )
            logger.info(f"[2032379] mount+file rc={rc} out={out!r}")
            self.assert_true(rc == 0)
            self.assert_true("5368709120" in out)

            widget.run_cmd(
                f"cp -a {CONF} {CONF_BAK} && "
                f"grep -v 'extendedScanPaths' {CONF} > {CONF}.tmp && "
                f"mv {CONF}.tmp {CONF}",
                timeout=5,
                out_debug_flag=False,
            )

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            # 设置页勾选数据盘 A
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
                for elem in widget.dog.find_elements_by_attr(expr, probe=True) or []:
                    if (getattr(elem, "description", "") or "") == MOUNT:
                        target = elem
                        break
                if target:
                    break
            self.assert_true(target is not None)
            target.click()
            sleep(1)
            conf = widget.run_cmd(f"cat {CONF}", timeout=5, out_debug_flag=False)
            logger.info(f"[2032379] conf={conf!r}")
            self.assert_true(MOUNT in conf)
            widget.close_settings_dialog()
            sleep(2)

            # 触发大文件清理扫描
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_large_file_scan_completed(timeout=240))
            self.assert_true(widget.get_large_file_result_showing())
            filenames = widget.get_large_file_table_filenames()
            logger.info(f"[2032379] filenames={filenames}")
            self.assert_true(
                any("autotest_big_5g.bin" in name for name in filenames)
            )
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

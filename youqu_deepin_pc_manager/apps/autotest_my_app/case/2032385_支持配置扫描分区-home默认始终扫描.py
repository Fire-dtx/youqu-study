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

HOME_FILE = os.path.expanduser("~/test1")
CONF = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
CONF_BAK = "/tmp/pcm_conf.homedefault.bak"


class TestMyCase(BaseCase):

    def test_mycase_044(self):
        """支持配置扫描分区-/home 默认始终扫描

        构造: 无扩展分区(配置清空), /home 下放 1GB 文件 test1。
        步骤: 系统优化->大文件清理仅触发扫描。
        断言: 结果包含 /home 下的 test1。
        清理: 删除 test1、还原配置、恢复隔离文件。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        isolated = []
        try:
            widget.run_cmd(f"rm -f {HOME_FILE}", timeout=5, out_debug_flag=False)
            widget.run_cmd(
                f"cp -a {CONF} {CONF_BAK} && "
                f"grep -v 'extendedScanPaths' {CONF} > {CONF}.tmp && "
                f"mv {CONF}.tmp {CONF}",
                timeout=5,
                out_debug_flag=False,
            )
            # 先隔离既有大文件, 再创建本用例的目标文件, 避免目标文件被隔离
            isolated = widget.isolate_foreign_large_files()
            widget.run_cmd(
                f"fallocate -l 1G {HOME_FILE} && stat -c %s {HOME_FILE}",
                timeout=30,
                out_debug_flag=False,
            )

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_large_file_scan_completed(timeout=240))
            self.assert_true(widget.get_large_file_result_showing())
            filenames = widget.get_large_file_table_filenames()
            logger.info(f"[2032385] filenames={filenames}")
            self.assert_true(any("test1" in name for name in filenames))
        finally:
            widget.kill_pc_manager()
            sleep(2)
            widget.run_cmd(f"rm -f {HOME_FILE}", timeout=5, out_debug_flag=False)
            widget.run_cmd(
                f"[ -f {CONF_BAK} ] && cp -a {CONF_BAK} {CONF} && rm -f {CONF_BAK}; true",
                timeout=5,
                out_debug_flag=False,
            )
            widget.restore_foreign_large_files(isolated)

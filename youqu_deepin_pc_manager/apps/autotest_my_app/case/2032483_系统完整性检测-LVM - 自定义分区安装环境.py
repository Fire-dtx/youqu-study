#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_115(self):
        """系统完整性检测-LVM/自定义分区安装环境：检测通过

        步骤: 运行系统完整性检测(系统环境检测分项)。
        预期: 检测通过 -- 分区布局(标准自定义分区)不影响检测, 各完整性检测项
        正常得出 PASS 结论, 无缺失/损坏/异常。
        说明: 测试机为自定义分区(非 LVM)安装, LVM 布局需重装系统才能构造,
        本用例在同一检测路径上验证分区布局不影响完整性检测结果。
        """
        widget = MyAppWidget(check_start=False)
        try:
            layout = widget.run_cmd(
                "lsblk -o NAME,TYPE,FSTYPE,SIZE,MOUNTPOINT 2>/dev/null",
                timeout=10, out_debug_flag=False,
            )
            has_lvm = "lvm" in layout.lower() or "/dev/mapper/" in layout
            logger.info(f"[2032483] has_lvm={has_lvm} layout={layout[:400]}")

            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())

            since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            state = widget.get_detection_group_state("系统环境检测")
            logger.info(f"[2032483] group_state={state}")
            self.assert_true(state["total"] > 0)
            self.assert_true(state["checked"] == state["total"])
            self.assert_true(widget.get_detection_item_present("系统环境检测", "核心包检查"))

            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032483] core_packages verdict={ok} detail={detail}")
            self.assert_true(ok is True)

            logs = widget.sudo_run_cmd(
                f"journalctl -u deepin-pc-manager-daemon --since '{since}' "
                "| grep -a 'detectCorePackages'",
                timeout=30, out_debug_flag=False,
            )
            self.assert_true("completed, missing: 0 corrupted: 0" in logs)
        finally:
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

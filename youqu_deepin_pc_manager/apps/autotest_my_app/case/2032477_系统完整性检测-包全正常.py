#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import re
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def _core_package_logs(self, since):
        return self.widget.sudo_run_cmd(
            f"journalctl -u deepin-pc-manager-daemon --since '{since}' "
            "| grep -a 'detectCorePackages'",
            timeout=30, out_debug_flag=False,
        )

    def test_mycase_112(self):
        """核心包检测-包全正常：默认安装系统上核心包全部通过 dpkg 校验

        步骤: 初始系统上执行系统完整性检测(系统环境检测分项)。
        预期: 核心包检查项结论为通过(全部包 PASS, 无缺失/损坏),
        即产品对核心包清单逐包 dpkg --verify 的结果为 missing:0 corrupted:0。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())

            # ===== 执行「系统环境检测」分项检测 =====
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            self.assert_true(widget.get_detection_item_present("系统环境检测", "核心包检查"))

            # ===== 校验核心包检查结论：包全正常应为通过 =====
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032477] core_packages verdict={ok} detail={detail}")
            self.assert_true(ok is True)

            # ===== 守护进程侧证据: 逐包 dpkg 校验无缺失、无损坏 =====
            logs = self._core_package_logs(since)
            logger.info(f"[2032477] daemon logs(len={len(logs)}): {logs[-300:]}")
            matched = re.search(r"verifying\s+(\d+)\s+core packages", logs)
            self.assert_true(matched is not None)
            self.assert_true(int(matched.group(1)) >= 15)
            self.assert_true("completed, missing: 0 corrupted: 0" in logs)
            self.assert_true("package not installed" not in logs)
            self.assert_true("verify failed" not in logs)
        finally:
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

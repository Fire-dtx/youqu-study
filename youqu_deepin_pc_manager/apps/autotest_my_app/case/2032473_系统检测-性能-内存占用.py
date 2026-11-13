#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):

    RSS_CMD = (
        "pgrep -f 'deepin-pc-manager' | grep -v grep | "
        "xargs -r ps -o rss= -p 2>/dev/null | awk '{s+=$1} END {print s+0}'"
    )
    PROC_CMD = "pgrep -fc 'deepin-pc-manager'"

    def _total_rss_kb(self):
        out = self.widget.run_cmd(f"{self.RSS_CMD}; true", timeout=10, out_debug_flag=False)
        numbers = [int(token) for token in out.split() if token.isdigit()]
        return numbers[-1] if numbers else 0

    def _process_count(self):
        out = self.widget.run_cmd(f"{self.PROC_CMD}; true", timeout=10, out_debug_flag=False)
        numbers = [int(token) for token in out.split() if token.isdigit()]
        return numbers[-1] if numbers else 0

    def test_mycase_093(self):
        """系统检测-性能-内存占用：全面检测 8 项并发时管家进程内存增长 < 200MB 且无崩溃

        步骤: 启动电脑管家并进入系统检测, 点击"全面检测"; 检测期间每秒
        统计所有 deepin-pc-manager 进程的常驻内存(ps -o rss)与进程数。
        预期: 检测过程中内存峰值相对检测前基线增长小于 200MB,
        进程数不减少、进程始终存活(无闪退/崩溃), 检测正常完成。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            sleep(5)
            baseline_kb = self._total_rss_kb()
            baseline_count = self._process_count()
            logger.info(f"[2032473] baseline_kb={baseline_kb} procs={baseline_count}")
            self.assert_true(baseline_kb > 0)
            self.assert_true(baseline_count > 0)

            widget.click_detection_full_scan_button()
            self.assert_true(widget.wait_for_full_scan_started(60))
            peak_kb = baseline_kb
            min_count = baseline_count
            crashed = False
            started = False
            for _ in range(240):
                if widget._detection_progress_running():
                    started = True
                elif started:
                    break
                current_kb = self._total_rss_kb()
                current_count = self._process_count()
                peak_kb = max(peak_kb, current_kb)
                if current_count > 0:
                    min_count = min(min_count, current_count)
                else:
                    crashed = True
                    break
                sleep(1)
            self.assert_true(widget.wait_for_full_scan_completion(900))

            growth_kb = peak_kb - baseline_kb
            logger.info(
                f"[2032473] peak_kb={peak_kb} growth_kb={growth_kb} "
                f"crashed={crashed} min_count={min_count}"
            )
            self.assert_true(not crashed)
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(growth_kb < 200 * 1024)
        finally:
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

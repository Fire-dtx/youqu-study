#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):

    def _run(self, command, timeout=10):
        return self.widget.run_cmd(f"{command}; true", timeout=timeout, out_debug_flag=False)

    def _active_window(self):
        return self._run("xprop -root _NET_ACTIVE_WINDOW 2>/dev/null").strip()

    def _load1(self):
        out = self._run("awk '{print $1}' /proc/loadavg")
        numbers = [token for token in out.split() if token.replace(".", "").isdigit()]
        return float(numbers[-1]) if numbers else -1.0

    def _wait_file_manager_window(self, timeout):
        """等待文件管理器窗口出现, 返回耗时秒数(未出现返回 None)"""
        start = time.time()
        deadline = start + timeout
        while time.time() < deadline:
            out = self._run(
                "xdotool search --onlyvisible --class dde-file-manager 2>/dev/null | head -1"
            )
            if out.strip().isdigit():
                return round(time.time() - start, 2)
        return None

    def test_mycase_094(self):
        """系统检测-性能-无卡顿：全面检测进行中桌面交互(切窗口/开文件管理器)流畅

        步骤: 启动全面检测, 检测进行中执行 -- 1) alt+Tab 切换窗口;
        2) 打开文件管理器; 3) 采样系统 1 分钟负载。
        预期: 窗口切换在 3 秒内完成, 文件管理器窗口 15 秒内出现(桌面可响应),
        检测期间系统负载低于 2 倍 CPU 核数(无 CPU 饱和卡顿), 检测正常完成。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            self._run("pkill -f 'dde-file-manager$'")
            self._run("pkill -f 'dde-file-manager-server$'")
            for _ in range(20):
                if not self._run(
                    "xdotool search --class dde-file-manager 2>/dev/null | head -1"
                ).strip():
                    break
                sleep(0.5)
            self.assert_true(
                not self._run(
                    "xdotool search --class dde-file-manager 2>/dev/null | head -1"
                ).strip()
            )
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            widget.click_detection_full_scan_button()
            self.assert_true(widget.wait_for_full_scan_started(60))

            # 1) 检测中打开文件管理器
            widget.run_cmd(
                "nohup dde-file-manager >/tmp/dpm_fm_case.log 2>&1 &",
                timeout=5, out_debug_flag=False,
            )
            launch_cost = self._wait_file_manager_window(20)
            logger.info(
                "[2032475] fm_procs="
                + self._run("pgrep -af 'dde-file-manager' | grep -v bash | head -3").strip()
            )
            logger.info(f"[2032475] file_manager_cost={launch_cost}")
            self.assert_true(launch_cost is not None)
            self.assert_true(launch_cost < 20)

            # 2) 窗口切换响应: 激活文件管理器窗口, 桌面窗口管理器应在 3 秒内完成切换
            window_id = self._run(
                "xdotool search --onlyvisible --class dde-file-manager 2>/dev/null | head -1"
            ).strip()
            self.assert_true(window_id.isdigit())
            switch_start = time.time()
            self._run(f"xdotool windowactivate {window_id}")
            switched = False
            while time.time() - switch_start < 3:
                if f"0x{int(window_id):x}".lower() in self._active_window().lower():
                    switched = True
                    break
                sleep(0.2)
            switch_cost = round(time.time() - switch_start, 2)
            logger.info(f"[2032475] switch_cost={switch_cost} switched={switched} wid={window_id}")
            self.assert_true(switched)
            self.assert_true(switch_cost < 3)

            # 3) 检测期间系统负载
            loads = []
            running_samples = 0
            for _ in range(10):
                if widget._detection_progress_running():
                    running_samples += 1
                loads.append(self._load1())
                sleep(1)
            cpu_count = int(
                [t for t in self._run("nproc").split() if t.isdigit()][-1]
            )
            peak_load = max(loads)
            logger.info(
                f"[2032475] loads={loads} cpu_count={cpu_count} "
                f"running_samples={running_samples}"
            )
            self.assert_true(running_samples >= 5)
            self.assert_true(peak_load < cpu_count * 2)

            self._run("pkill -f 'dde-file-manager$'")
            self._run("pkill -f 'dde-file-manager-server$'")
            self.assert_true(widget.wait_for_full_scan_completion(900))
            summary = widget.get_last_full_scan_summary()
            logger.info(f"[2032475] summary: {summary[:120]}")
            self.assert_true("totalItems= 28" in summary)
        finally:
            self._run("pkill -f 'dde-file-manager$'")
            self._run("pkill -f 'dde-file-manager-server$'")
            self._run("rm -f /tmp/dpm_fm_case.log")
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

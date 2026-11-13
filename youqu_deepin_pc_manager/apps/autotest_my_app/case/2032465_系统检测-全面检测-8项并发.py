#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    SAMPLER_LOG = "/tmp/dpm_concurrency_sample.log"

    def _start_detection_task_sampler(self, interval=0.1, samples=1500):
        """后台采样守护进程正在执行的检测任务数

        每个检测项在系统守护进程中对应一个任务对象
        (/org/deepin/PCManager1/Task/detection/<key>), 对象存在即表示该项在跑。
        """
        self.widget.run_cmd(f"rm -f {self.SAMPLER_LOG}", timeout=5, out_debug_flag=False)
        self.widget.run_cmd(
            f'nohup bash -c \'for i in $(seq 1 {samples}); do c=$(busctl --system tree '
            f"org.deepin.PCManager1 2>/dev/null | grep -c '/Task/detection/'); "
            f'echo "$(date +%s%3N) $c"; sleep {interval}; done\' > {self.SAMPLER_LOG} 2>&1 &',
            timeout=10, out_debug_flag=False,
        )

    def _stop_detection_task_sampler(self):
        self.widget.run_cmd(
            "pkill -f 'busctl --system tree org.deepin.PCManager1' 2>/dev/null; true",
            timeout=10, out_debug_flag=False,
        )

    def _sampler_max(self):
        result = self.widget.run_cmd(
            f"awk '{{if ($2+0 > m) m = $2+0}} END {{print m+0}}' {self.SAMPLER_LOG}",
            timeout=10, out_debug_flag=False,
        )
        text = result.strip().splitlines()[-1].strip() if result.strip() else "0"
        return int(text) if text.isdigit() else 0

    def test_mycase_024(self):
        """系统检测-全面检测-8项并发：任意时刻最多 8 个检测项并行执行

        步骤: 系统检测页 -> 点击"全面检测"; 检测期间以 100ms 间隔采样系统守护
        进程中存活的检测任务对象数(每个执行中的检测项对应一个
        /org/deepin/PCManager1/Task/detection/<key> 任务对象)。
        预期: 采样到的并发任务数不超过 8(产品 DetectionScheduler 槽位上限),
        且出现过并发(>1), 全部 28 项检测完成后正常返回。
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

            self._start_detection_task_sampler()
            widget.click_detection_full_scan_button()
            self.assert_true(widget.wait_for_full_scan_started(60))
            self.assert_true(widget.wait_for_full_scan_completion(900))
            self._stop_detection_task_sampler()
            summary = widget.get_last_full_scan_summary()
            logger.info(f"[2032465] summary: {summary}")
            self.assert_true("totalItems= 28" in summary)

            max_concurrent = self._sampler_max()
            samples = widget.run_cmd(
                f"wc -l < {self.SAMPLER_LOG}", timeout=10, out_debug_flag=False,
            ).strip()
            logger.info(f"[2032465] samples={samples} max_concurrent={max_concurrent}")
            self.assert_true(int(samples) > 10)
            self.assert_true(max_concurrent >= 2)
            self.assert_true(max_concurrent <= 8)
        finally:
            self._stop_detection_task_sampler()
            widget.run_cmd(f"rm -f {self.SAMPLER_LOG}", timeout=5, out_debug_flag=False)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

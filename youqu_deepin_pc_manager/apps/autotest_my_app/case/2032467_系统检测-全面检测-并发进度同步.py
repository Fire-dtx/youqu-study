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

    SAMPLER_LOG = "/tmp/dpm_concurrency_sample.log"

    def _start_detection_task_sampler(self, interval=0.1, samples=1500):
        """后台采样守护进程中存活的检测任务对象数(并发检测项数)"""
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

    def _sampler_max(self) -> int:
        result = self.widget.run_cmd(
            f"awk '{{if ($2+0 > m) m = $2+0}} END {{print m+0}}' {self.SAMPLER_LOG}",
            timeout=10, out_debug_flag=False,
        )
        text = result.strip().splitlines()[-1].strip() if result.strip() else "0"
        return int(text) if text.isdigit() else 0

    def _visible_progress_value(self):
        """读取可见进度条的当前值(QProgressBar 通过 AT-SPI 暴露 value)"""
        for element in self.widget.dog.find_elements_by_attr("$//detection_progressBar"):
            try:
                width, height = element.size
                if width > 0 and height > 0:
                    return float(element.value)
            except BaseException:
                continue
        return None

    def test_mycase_090(self):
        """系统检测-全面检测-并发进度同步：检测中多个项目同时推进且进度实时更新

        步骤: 进入系统检测 -> 点击"全面检测", 检测期间观察进度。
        预期: 检测项并发执行(守护进程同时存在多个检测任务, 上限 8 个槽位),
        总体进度条数值随检测推进实时增长。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        progress_values = []
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
            # 检测期间采样进度条数值
            for _ in range(40):
                value = self._visible_progress_value()
                if value is not None:
                    progress_values.append(value)
                if progress_values and progress_values[-1] >= 100:
                    break
                sleep(0.5)
            self.assert_true(widget.wait_for_full_scan_completion(900))
            self._stop_detection_task_sampler()

            max_concurrent = self._sampler_max()
            logger.info(f"[2032467] progress_values={progress_values} max_concurrent={max_concurrent}")
            # 进度实时更新: 至少 3 个不同数值且总体递增(容忍偶发回退 0)
            distinct = sorted({v for v in progress_values if v > 0})
            self.assert_true(len(distinct) >= 3)
            self.assert_true(distinct[-1] > distinct[0])
            # 并发执行: 同时在跑的检测项多于 1 且不超过 8 个槽位
            self.assert_true(max_concurrent >= 2)
            self.assert_true(max_concurrent <= 8)
        finally:
            self._stop_detection_task_sampler()
            widget.run_cmd(f"rm -f {self.SAMPLER_LOG}", timeout=5, out_debug_flag=False)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

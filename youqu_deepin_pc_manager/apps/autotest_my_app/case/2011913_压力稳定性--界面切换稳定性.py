#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_051(self):
        """压力稳定性--界面切换稳定性

        描述: 启动电脑管家 -> 依次切换功能模块 -> 多次从上至下切换模块;
        预期主界面正常、切换显示正常、反应及时。

        实现: 4 个功能模块(系统检测/系统优化/修复工具/实用工具)连续切换 20 轮,
        每轮记录
        - 切换耗时(点击到页面元素可见), 断言单次 <= 10s(反应及时);
        - 页面可见, 断言切换显示正常;
        并对比首末内存(RSS)与进程 PID, 断言无泄漏式增长、无崩溃重启。

        闭环: 只做页面切换, 不修改系统状态; 结束关闭电脑管家主进程。
        """
        widget = MyAppWidget(check_start=False)
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_main_page_modules_showing())

            pid_before = widget.get_pc_manager_pid()
            mem_before = widget.get_pc_manager_memory_usage_kb()
            logger.info(f"[2011913] 起始 pid={pid_before} rss={mem_before}KB")

            switches = [
                ("系统检测", widget.click_detection_nav, widget.get_detection_page_showing),
                ("系统优化", widget.click_optimization_nav_by_attr, widget.get_optimization_page_showing),
                ("修复工具", widget.click_repair_nav, widget.get_repair_page_showing),
                ("实用工具", widget.click_utility_nav, widget.get_utility_page_showing),
            ]

            latencies = []
            rounds = 20
            for round_index in range(rounds):
                for name, click, visible in switches:
                    started = time.monotonic()
                    click()
                    shown = visible()
                    elapsed = time.monotonic() - started
                    latencies.append((name, elapsed))
                    if not shown:
                        logger.error(f"[2011913] 第 {round_index + 1} 轮 {name} 未显示")
                    self.assert_true(shown)
                    if elapsed > 10:
                        logger.error(
                            f"[2011913] 第 {round_index + 1} 轮 {name} 切换耗时 {elapsed:.1f}s"
                        )
                    self.assert_true(elapsed <= 10)
                self.assert_true(widget.get_pc_manager_process_status())
                if (round_index + 1) % 5 == 0:
                    logger.info(f"[2011913] 已完成 {round_index + 1}/{rounds} 轮")

            # 反应及时: 平均切换耗时与最慢切换
            avg_latency = sum(x for _, x in latencies) / len(latencies)
            max_name, max_latency = max(latencies, key=lambda x: x[1])
            logger.info(
                f"[2011913] 切换 {len(latencies)} 次: avg={avg_latency:.2f}s "
                f"max={max_latency:.2f}s({max_name})"
            )
            self.assert_true(avg_latency <= 5)

            # 稳定性: 进程未重启、内存无泄漏式增长
            pid_after = widget.get_pc_manager_pid()
            mem_after = widget.get_pc_manager_memory_usage_kb()
            logger.info(f"[2011913] 结束 pid={pid_after} rss={mem_after}KB")
            self.assert_equal(pid_before, pid_after)
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_main_page_modules_showing())
            growth_kb = mem_after - mem_before
            logger.info(f"[2011913] 内存增长 {growth_kb}KB")
            self.assert_true(growth_kb <= 32768)
            self.assert_true(growth_kb <= max(mem_before // 5, 1))
        finally:
            widget.kill_pc_manager()

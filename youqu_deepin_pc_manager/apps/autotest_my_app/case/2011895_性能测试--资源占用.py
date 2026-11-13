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

    def test_mycase_214(self):
        """性能测试--资源占用

        描述: 步骤"电脑管家在运行过程中 / 电脑管家选择全盘扫描",
        预期"使用流畅不卡顿崩溃。资源占用合理, 无因资源占用问题导致的进程卡死,
        其他应用卡死或系统卡死问题"。

        等价实现(系统监视器口径, 采样 60s):
        - 先真正进入系统检测并启动全面扫描(而不是空闲态测资源);
        - 扫描期间每 2s 采样: 电脑管家 CPU/RSS、系统可用内存、1 分钟负载、
          AT-SPI 可访问性(界面流畅不卡顿)、进程存活(不崩溃);
        - 判定: 进程 CPU <= 100%、RSS < 系统总内存 30% 且 < 1GB、
          系统可用内存 > 5%、负载 < 2 倍核数、界面始终可访问、进程不重启;
        - 断言的宽松程度保证"资源占用合理"而不是要求具体数值。

        闭环: 结束时关闭电脑管家主程序(扫描随主进程结束), 并确认无残留进程;
        不修改系统扫描策略/缓存文件(扫描结果仅存应用缓存, 由应用自身管理)。
        """
        widget = MyAppWidget(check_start=False)
        cpu_count = widget.get_cpu_count()
        mem_total = widget.get_system_memory_total_mb()
        self.assert_true(mem_total > 0)

        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_main_page_modules_showing())

            # 1) 进入系统检测并启动全面扫描
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            widget.click_detection_full_scan_button()
            self.assert_true(widget.get_detection_full_scan_page_showing(timeout=30))
            started = widget.wait_for_full_scan_started(timeout=60)
            logger.info(f"[2011895] 全面扫描已启动: {started}")
            self.assert_true(started)

            # 2) 扫描期间持续采样资源(60s, 每 2s 一次)
            samples = []
            for i in range(30):
                pid_before = widget.get_pc_manager_process_status()
                cpu = widget.get_pc_manager_cpu_usage()
                rss_kb = widget.get_pc_manager_memory_usage_kb()
                avail_kb = widget.get_system_memory_available_kb()
                load = widget.get_system_load_average()
                responsive = widget.check_ui_responsive()
                samples.append(
                    {
                        "cpu": cpu,
                        "rss_kb": rss_kb,
                        "avail_kb": avail_kb,
                        "load": load,
                        "alive": pid_before,
                        "responsive": responsive,
                    }
                )
                if i % 10 == 0:
                    logger.info(f"[2011895] 第 {i + 1} 次采样: {samples[-1]}")
                sleep(2)

            logger.info(f"[2011895] 采样汇总: {samples}")
            total_kb = mem_total * 1024

            # 3) 判定资源占用合理 + 不卡顿/不崩溃
            for i, s in enumerate(samples):
                self.assert_true(s["alive"])
                self.assert_true(s["responsive"])
                self.assert_true(0 <= s["cpu"] <= 100)
                self.assert_true(s["rss_kb"] < total_kb * 0.3)
                self.assert_true(s["rss_kb"] < 1024 * 1024)     # < 1GB
                self.assert_true(s["avail_kb"] > total_kb * 0.05)
                self.assert_true(s["load"] < cpu_count * 2)

            max_cpu = max(s["cpu"] for s in samples)
            max_rss_mb = max(s["rss_kb"] for s in samples) / 1024.0
            max_load = max(s["load"] for s in samples)
            logger.info(
                f"[2011895] 峰值: cpu={max_cpu}% rss={max_rss_mb:.1f}MB "
                f"load={max_load} (cpu_count={cpu_count}, total={mem_total}MB)"
            )
            # 扫描仍在进行或已完成都算正常, 但界面必须还能访问
            self.assert_true(widget.check_ui_responsive())
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            widget.kill_pc_manager()
            # 闭环校验: 主进程退出, 扫描随之停止, 无残留
            self.assert_false(widget.get_pc_manager_process_status())

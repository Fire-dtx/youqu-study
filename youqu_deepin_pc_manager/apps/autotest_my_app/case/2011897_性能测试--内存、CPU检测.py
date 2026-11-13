#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):

    def test_mycase_215(self):
        """性能测试--内存、CPU 检测

        描述: 步骤"使用电脑管家时, 查看系统监视器观察电脑管家的内存情况",
        预期"正常使用情况下平均内存占用不得超过 120M"。

        等价实现(系统监视器口径): 按"正常使用"路径连续操作 4 个页面
        (主界面 -> 系统检测 -> 系统优化 -> 修复工具 -> 实用工具),
        每 2s 采样一次电脑管家进程 RSS/CPU, 共 40s; 以算术平均值判定 120MB。

        闭环: 只读采样 + 页面切换, 不修改任何系统状态; 结束关闭电脑管家主进程。
        """
        widget = MyAppWidget(check_start=False)
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_main_page_modules_showing())

            # 正常使用流程: 依次进入各功能页, 制造真实负载
            pages = [
                ("system_detection", widget.click_detection_nav, widget.get_detection_page_showing),
                ("system_optimization", widget.click_optimization_nav_by_attr, widget.get_optimization_page_showing),
                ("repair_tools", widget.click_repair_nav, widget.get_repair_page_showing),
                ("utilities", widget.click_utility_nav, widget.get_utility_page_showing),
            ]

            mem_samples = []
            cpu_samples = []
            page_index = 0
            enter_every = 8  # 每 8 次采样(约 16s)切换一个页面, 共覆盖 4 个页面
            for i in range(40):
                if i % enter_every == 0 and page_index < len(pages):
                    name, click, visible = pages[page_index]
                    click()
                    self.assert_true(visible())
                    logger.info(f"[2011897] 进入页面: {name}")
                    page_index += 1

                mem_mb = widget.get_pc_manager_memory_mb()
                cpu = widget.get_pc_manager_cpu_usage()
                self.assert_true(mem_mb > 0.0)
                self.assert_true(0.0 <= cpu <= 100.0)
                mem_samples.append(mem_mb)
                cpu_samples.append(cpu)
                if i % 10 == 0:
                    logger.info(f"[2011897] 采样 {i + 1}: rss={mem_mb:.1f}MB cpu={cpu}%")
                sleep(2)

            avg_mem = sum(mem_samples) / len(mem_samples)
            max_mem = max(mem_samples)
            avg_cpu = sum(cpu_samples) / len(cpu_samples)
            max_cpu = max(cpu_samples)
            logger.info(
                f"[2011897] 内存: avg={avg_mem:.1f}MB max={max_mem:.1f}MB "
                f"({len(mem_samples)} 次) | CPU: avg={avg_cpu:.1f}% max={max_cpu}%"
            )

            # 预期: 正常使用下平均内存 <= 120MB
            self.assert_true(avg_mem <= 120.0)
            # CPU 在正常使用(页面切换)下不应长期满载
            self.assert_true(avg_cpu < 50.0)

            # 使用过程中进程不崩溃、界面可访问
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.check_ui_responsive())
        finally:
            widget.kill_pc_manager()

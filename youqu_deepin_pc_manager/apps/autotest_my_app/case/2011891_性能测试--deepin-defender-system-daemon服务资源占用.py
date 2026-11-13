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

    def test_mycase_212(self):
        """性能测试--deepin-defender-system-daemon 服务资源占用

        描述: 步骤"长时间运行后, 查看系统监视器中 deepin-service-manager 内存占用",
        预期"内存资源占用正常"。

        等价实现(系统监视器口径): 系统监视器展示的正是进程 RSS/CPU/线程数。
        这里直接按相同口径读取 /proc 与 ps, 并在电脑管家主页面持续运行一段时间后
        采样两次(间隔 60s), 检查:
        - 进程确实处于运行状态, 且已运行较长时间(etimes > 300s, 属于"长时间运行后");
        - RSS 在合理上限内(< 512MB), 且两次采样间没有异常增长(增量 <= 32MB 且 <= 20%);
        - CPU 占用不超过 100%, 线程数保持平稳(波动 <= 4)。

        产品依据: deepin-defender-system-daemon 为系统级常驻服务, 由
        deepin-service-manager 托管; 电脑管家只负责展示/联动, 不存在用例可修改的配置。

        闭环: 只读采样, 不重启/停止系统服务, 结束时关闭电脑管家界面进程。
        """
        widget = MyAppWidget(check_start=False)
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_main_page_modules_showing())

            # 1) 前置: 服务在运行, 且已运行足够长时间(长时间运行后)
            self.assert_true(widget.get_defender_daemon_service_status())
            pid = widget.get_defender_daemon_pid()
            uptime = widget.get_defender_daemon_uptime_seconds()
            logger.info(f"[2011891] pid={pid} uptime={uptime}s")
            self.assert_true(bool(pid))
            self.assert_true(uptime > 300)

            # 2) 第一次采样(主页面打开状态下)
            mem_first = widget.get_defender_daemon_memory_usage_kb()
            threads_first = widget.get_defender_daemon_threads()
            logger.info(f"[2011891] 首次采样: rss={mem_first}KB threads={threads_first}")
            self.assert_true(mem_first > 0)
            self.assert_true(mem_first < 512000)

            # 3) 持续运行 60s(模拟长时间运行后再次查看)
            sleep(60)

            # 4) 第二次采样: 资源占用应正常且基本平稳
            mem_second = widget.get_defender_daemon_memory_usage_kb()
            threads_second = widget.get_defender_daemon_threads()
            cpu = widget.get_defender_daemon_cpu_usage_percent()
            growth_kb = mem_second - mem_first
            logger.info(
                f"[2011891] 二次采样: rss={mem_second}KB threads={threads_second} "
                f"cpu={cpu}% growth={growth_kb}KB"
            )
            self.assert_true(mem_second > 0)
            self.assert_true(mem_second < 512000)          # 合理上限
            self.assert_true(growth_kb <= 32768)           # 60s 内增长 <= 32MB
            self.assert_true(growth_kb <= max(mem_first // 5, 1))  # 增长 <= 20%
            self.assert_true(0 <= cpu <= 100)
            self.assert_true(abs(threads_second - threads_first) <= 4)

            # 5) 采样期间进程未重启(仍是同一 PID, 未崩溃)
            self.assert_equal(pid, widget.get_defender_daemon_pid())
            self.assert_true(widget.get_defender_daemon_service_status())
        finally:
            widget.kill_pc_manager()

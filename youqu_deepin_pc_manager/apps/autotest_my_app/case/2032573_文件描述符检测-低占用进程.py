#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_358(self):
        """文件描述符检测-低占用进程：系统存在低文件描述符占用进程时，
        执行「系统稳定性」分项检测，文件描述符检测项结论应为通过"""
        widget = MyAppWidget(check_start=False)

        widget.stop_low_fd_process()
        widget.kill_pc_manager()

        try:
            # ===== 构造低占用进程: 仅持有标准描述符的后台进程 =====
            self.assert_true(widget.start_low_fd_process(timeout=15))
            low_fd_pid = widget.get_low_fd_process_pid()
            self.assert_true(bool(low_fd_pid))
            low_fd_count = widget.get_process_fd_count(low_fd_pid)
            self.assert_true(low_fd_count >= 0)
            self.assert_true(low_fd_count <= 3)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.get_detection_functional_modules_showing())

            sys_limit = widget.get_system_file_descriptor_limit()
            self.assert_true(sys_limit > 0)
            proc_limit = widget.get_process_file_descriptor_limit()
            self.assert_true(proc_limit > 0)
            self.assert_true(low_fd_count < proc_limit)
            open_count = widget.get_system_open_fd_count()
            self.assert_true(open_count >= 0)
            self.assert_true(open_count < sys_limit)
            max_proc_fd = widget.get_max_process_fd_count()
            self.assert_true(max_proc_fd >= 0)
            self.assert_true(max_proc_fd < proc_limit)
            usage_ratio = widget.get_max_process_fd_usage_ratio()
            self.assert_true(usage_ratio >= 0.0)
            self.assert_true(usage_ratio < 0.5)

            # ===== 执行「系统稳定性」分项检测并校验文件描述符结论 =====
            self.assert_true(widget.get_detection_cards_view_showing())
            self.assert_true(widget.run_detection_item("系统稳定性", timeout=300))
            log("期望: " + ("系统稳定性分项中缺少「文件描述符检测」检测项"))
            self.assert_true(widget.get_detection_item_present("系统稳定性", "文件描述符检测"))
            ok, detail = widget.get_detection_item_verdict("fd_usage")
            log("期望: " + (f"fd_usage 预期通过(低占用进程), 实际 {ok}: {detail}"))
            self.assert_true(ok is True)
            self.assert_true(widget.get_detection_page_showing())

            sleep(1)
            low_fd_count_after = widget.get_process_fd_count(low_fd_pid)
            self.assert_true(low_fd_count_after >= 0)
            self.assert_true(low_fd_count_after <= 3)
        finally:
            widget.stop_low_fd_process()
            widget.kill_pc_manager()

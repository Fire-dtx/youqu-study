#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log


class TestMyCase(BaseCase):

    def test_mycase_329(self):
        """文件描述符检测-正常系统：系统文件描述符参数在正常范围内，
        执行「系统稳定性」分项检测，文件描述符检测项结论应为通过"""
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        self.assert_true(widget.get_detection_functional_modules_showing())

        # ===== 系统级/进程级上限与占用读取 =====
        sys_limit = widget.get_system_file_descriptor_limit()
        self.assert_true(sys_limit > 0)
        proc_limit = widget.get_process_file_descriptor_limit()
        self.assert_true(proc_limit > 0)
        open_count = widget.get_system_open_fd_count()
        self.assert_true(open_count >= 0)
        self.assert_true(open_count < sys_limit)
        max_proc_fd = widget.get_max_process_fd_count()
        self.assert_true(max_proc_fd >= 0)
        self.assert_true(max_proc_fd < proc_limit)

        # ===== 执行「系统稳定性」分项检测并校验文件描述符结论 =====
        self.assert_true(widget.get_detection_cards_view_showing())
        self.assert_true(widget.run_detection_item("系统稳定性", timeout=300))
        log("期望: " + ("系统稳定性分项中缺少「文件描述符检测」检测项"))
        self.assert_true(widget.get_detection_item_present("系统稳定性", "文件描述符检测"))
        ok, detail = widget.get_detection_item_verdict("fd_usage")
        log("期望: " + (f"fd_usage 预期通过(正常系统), 实际 {ok}: {detail}"))
        self.assert_true(ok is True)

        self.assert_true(widget.get_detection_page_showing())

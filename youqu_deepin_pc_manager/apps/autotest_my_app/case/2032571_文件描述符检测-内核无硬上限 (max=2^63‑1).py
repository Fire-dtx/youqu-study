#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import sleep

# 2^63 - 1, 即 64 位有符号长整型最大值(LONG_MAX), 内核 fs.file-max 的理论上限
KERNEL_FD_MAX = 9223372036854775807


class TestMyCase(BaseCase):

    def test_mycase_360(self):
        """文件描述符检测-内核无硬上限 (max=2^63-1)：当 /proc/sys/fs/file-max
        处于内核最大值时，执行「系统稳定性」分项检测，文件描述符检测项结论应为通过"""
        widget = MyAppWidget(check_start=False)

        # ===== 前置: 读取原始 file-max 并确保为内核最大值 2^63-1 =====
        orig_limit = widget.get_system_file_descriptor_limit()
        self.assert_true(orig_limit > 0)

        need_restore = orig_limit != KERNEL_FD_MAX
        try:
            if need_restore:
                _, set_code = widget.sudo_run_cmd(
                    f"echo {KERNEL_FD_MAX} > /proc/sys/fs/file-max",
                    timeout=5,
                    out_debug_flag=False,
                    return_code=True,
                )
                self.assert_true(set_code == 0)
                sleep(1)

            cur_limit = widget.get_system_file_descriptor_limit()
            self.assert_true(cur_limit == KERNEL_FD_MAX)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.get_detection_functional_modules_showing())

            sys_limit = widget.get_system_file_descriptor_limit()
            self.assert_true(sys_limit == KERNEL_FD_MAX)
            proc_limit = widget.get_process_file_descriptor_limit()
            self.assert_true(proc_limit > 0)
            open_count = widget.get_system_open_fd_count()
            self.assert_true(open_count >= 0)
            self.assert_true(open_count < sys_limit)
            max_proc_fd = widget.get_max_process_fd_count()
            self.assert_true(max_proc_fd >= 0)
            self.assert_true(max_proc_fd < proc_limit)

            # ===== 执行「系统稳定性」分项检测并校验文件描述符结论 =====
            since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            self.assert_true(widget.get_detection_cards_view_showing())
            self.assert_true(widget.run_detection_item("系统稳定性", timeout=300))
            log("期望: " + ("系统稳定性分项中缺少「文件描述符检测」检测项"))
            self.assert_true(widget.get_detection_item_present("系统稳定性", "文件描述符检测"))
            ok, detail = widget.get_detection_item_verdict("fd_usage")
            log("期望: " + (f"fd_usage 预期通过(内核无硬上限), 实际 {ok}: {detail}"))
            self.assert_true(ok is True)
            fd_logs = widget.sudo_run_cmd(
                f"journalctl -u deepin-pc-manager-daemon --since '{since}' "
                "| grep -a 'detectFdUsage'",
                timeout=30, out_debug_flag=False,
            )
            log(f"[2032571] 守护日志: {fd_logs.strip()[-160:]!r}")
            self.assert_true("detectFdUsage: done, global% 0" in fd_logs)
            self.assert_true(widget.get_detection_page_showing())
        finally:
            # ===== 清理: 恢复原始 file-max =====
            if need_restore and orig_limit > 0:
                widget.sudo_run_cmd(
                    f"echo {orig_limit} > /proc/sys/fs/file-max",
                    timeout=5,
                    out_debug_flag=False,
                )

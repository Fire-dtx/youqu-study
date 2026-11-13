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

    def _daemon_pid(self):
        return self.widget.run_cmd(
            "pgrep -f '/usr/lib/deepin-daemon/deepin-pc-manager-daemon' | head -1",
            timeout=10, out_debug_flag=False,
        ).strip()

    def _start_detection_only(self):
        """点击分项卡片并等待出现检测进度(不等待完成)"""
        self.assert_true(self.widget.click_detection_card("系统环境检测"))
        for _ in range(30):
            if self.widget._detection_progress_running():
                return True
            sleep(1)
        return False

    def test_mycase_123(self):
        """系统完整性检测-检测过程取消/中断：任务终止且不残留异常状态

        步骤: 1. 启动系统环境检测;
        2. 检测进行中终止检测进程(用例中杀掉执行检测的守护进程, 模拟用户中断)。
        预期: 检测任务终止 -- 守护进程按服务策略重启, 界面/数据无残留卡死状态;
        中断后重新发起检测可正常完成并给出各分项结论。
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

            pid_before = self._daemon_pid()
            logger.info(f"[2032499] daemon_pid_before={pid_before}")
            self.assert_true(pid_before.isdigit())

            self.assert_true(self._start_detection_only())
            logger.info("[2032499] detection started, interrupt daemon")
            self.assert_true(
                widget.sudo_run_cmd(
                    "kill -9 $(pgrep -f '/usr/lib/deepin-daemon/deepin-pc-manager-daemon' | head -1)",
                    timeout=15, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            stopped = False
            for _ in range(20):
                active = widget.run_cmd(
                    "systemctl is-active deepin-pc-manager-daemon 2>/dev/null",
                    timeout=10, out_debug_flag=False,
                ).strip()
                if active != "active":
                    stopped = True
                    break
                sleep(1)
            logger.info(f"[2032499] daemon stopped={stopped} active={active!r}")
            self.assert_true(stopped or active != "active")

            pid_after = ""
            for _ in range(60):
                pid_after = self._daemon_pid()
                if pid_after.isdigit() and pid_after != pid_before:
                    break
                sleep(1)
            logger.info(f"[2032499] daemon_pid_after={pid_after}")
            self.assert_true(pid_after.isdigit())
            self.assert_true(pid_after != pid_before)
            self.assert_true(widget.get_pc_manager_process_status())

            # 中断后重新检测: 无残留卡死, 可正常完成
            widget.reconnect_dogtail()
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            state = widget.get_detection_group_state("系统环境检测")
            logger.info(f"[2032499] rerun group_state={state}")
            self.assert_true(state["total"] > 0)
            self.assert_true(state["checked"] == state["total"])
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032499] core_packages verdict={ok} detail={detail}")
            self.assert_true(ok is True)
        finally:
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

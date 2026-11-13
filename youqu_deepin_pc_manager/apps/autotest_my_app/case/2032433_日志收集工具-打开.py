#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    PROC = r"^/usr/bin/deepin-log-viewer( |$)"
    TITLE = "日志收集工具"

    def _pids(self, widget):
        return [
            x.strip()
            for x in widget.run_cmd(
                f"pgrep -f '{self.PROC}'", timeout=5, out_debug_flag=False
            ).splitlines()
            if x.strip()
        ]

    def _window_titles(self, widget, pid):
        return widget.run_cmd(
            "export DISPLAY=:0; "
            f"for w in $(xdotool search --onlyvisible --pid {pid} "
            "2>/dev/null); do xdotool getwindowname $w; done",
            timeout=10,
            out_debug_flag=False,
        ).strip()

    def test_mycase_265(self):
        """日志收集工具-打开：点击卡片后 deepin-log-viewer 进程与窗口真实启动

        说明: 旧的 pgrep -f deepin-log-viewer 会被执行命令的 shell 自身
        误匹配, 这里改为精确匹配 /usr/bin/deepin-log-viewer 并校验可见窗口。

        回退: 关闭日志收集工具与电脑管家, 校验无进程/窗口残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.run_cmd(
            "killall -TERM deepin-log-viewer 2>/dev/null; true",
            timeout=5, out_debug_flag=False,
        )
        sleep(1)
        try:
            self.assert_true(widget.is_log_viewer_installed())
            self.assert_false(bool(self._pids(widget)))
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())
            widget.click_utility_card_by_name("日志收集工具")

            pid = ""
            titles = ""
            for _ in range(40):
                pids = self._pids(widget)
                if pids:
                    pid = pids[0]
                    titles = self._window_titles(widget, pid)
                    if self.TITLE in titles:
                        break
                sleep(0.5)
            logger.info(f"[2032433] pid={pid!r} titles={titles!r}")
            self.assert_true(bool(pid))
            self.assert_true(self.TITLE in titles)
            self.assert_true(widget.get_utility_page_showing())
        finally:
            widget.run_cmd(
                "killall -TERM deepin-log-viewer 2>/dev/null; true",
                timeout=5, out_debug_flag=False,
            )
            sleep(1)
            if self._pids(widget):
                widget.run_cmd(
                    "killall -KILL deepin-log-viewer 2>/dev/null; true",
                    timeout=5, out_debug_flag=False,
                )
                sleep(1)
            widget.kill_pc_manager()
            left = self._pids(widget)
            logger.info(f"[2032433] teardown procs={left}")
            self.assert_false(bool(left))

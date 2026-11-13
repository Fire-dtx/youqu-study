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

    def _window_info(self, widget, pid):
        return widget.run_cmd(
            "export DISPLAY=:0; "
            f"for w in $(xdotool search --onlyvisible --pid {pid} "
            "2>/dev/null); do xdotool getwindowname $w; done",
            timeout=10,
            out_debug_flag=False,
        ).strip()

    def _cleanup_viewer(self, widget):
        widget.run_cmd(
            "killall -TERM deepin-log-viewer 2>/dev/null; true",
            timeout=5, out_debug_flag=False,
        )
        for _ in range(10):
            if not self._pids(widget):
                break
            sleep(0.5)
        if self._pids(widget):
            widget.run_cmd(
                "killall -KILL deepin-log-viewer 2>/dev/null; true",
                timeout=5, out_debug_flag=False,
            )
            sleep(1)

    def test_mycase_264(self):
        """实用工具-日志工具：单击「日志收集工具」卡片，工具正常打开

        断言:
            1) 日志收集工具已安装、测试前无 deepin-log-viewer 进程;
            2) 实用工具页显示「日志收集工具」卡片;
            3) 单击卡片后真实拉起 /usr/bin/deepin-log-viewer, 出现标题为
               「日志收集工具」的可见窗口, 电脑管家仍停留在实用工具页;
            4) 回退: 关闭日志收集工具与电脑管家, 无进程/窗口残留,
               清理运行期新生成的用户配置目录。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        self._cleanup_viewer(widget)

        installed_before = False
        dirs_before = {}
        try:
            installed_before = widget.is_log_viewer_installed()
            self.assert_true(installed_before)
            self.assert_false(bool(self._pids(widget)))
            home = widget.run_cmd(
                "echo $HOME", timeout=5, out_debug_flag=False
            ).strip()
            for rel in (
                ".config/deepin-log-viewer",
                ".cache/deepin-log-viewer",
                ".local/share/deepin-log-viewer",
                ".config/deepin/deepin-log-viewer",
                ".cache/deepin/deepin-log-viewer",
            ):
                path = f"{home}/{rel}"
                dirs_before[path] = bool(
                    widget.run_cmd(
                        f"test -e {path} && echo yes || echo no",
                        timeout=5, out_debug_flag=False,
                    ).strip().endswith("yes")
                )

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())

            card = widget.dog.find_element_by_attr(
                "$//utility_sectionsContainer//日志收集工具"
            )
            self.assert_true(card.showing)
            self.assert_true(widget._atspi_do_action(card))

            pid = ""
            titles = ""
            for _ in range(40):
                pids = self._pids(widget)
                if pids:
                    pid = pids[0]
                    titles = self._window_info(widget, pid)
                    if self.TITLE in titles:
                        break
                sleep(0.5)
            logger.info(
                f"[2032431] viewer pid={pid!r} titles={titles!r}"
            )
            self.assert_true(bool(pid))
            self.assert_true(self.TITLE in titles)
            self.assert_true(widget.get_utility_page_showing())
        finally:
            self._cleanup_viewer(widget)
            widget.kill_pc_manager()
            left = self._pids(widget)
            cfg_left = []
            for path, existed in dirs_before.items():
                still = bool(
                    widget.run_cmd(
                        f"test -e {path} && echo yes || echo no",
                        timeout=5, out_debug_flag=False,
                    ).strip().endswith("yes")
                )
                if still and not existed:
                    widget.run_cmd(
                        f"rm -rf {path}", timeout=10, out_debug_flag=False
                    )
                    cfg_left.append(path)
            logger.info(
                f"[2032431] teardown procs={left} removed_dirs={cfg_left}"
            )
            self.assert_false(bool(left))
            for path, existed in dirs_before.items():
                still = bool(
                    widget.run_cmd(
                        f"test -e {path} && echo yes || echo no",
                        timeout=5, out_debug_flag=False,
                    ).strip().endswith("yes")
                )
                self.assert_true(still == existed)

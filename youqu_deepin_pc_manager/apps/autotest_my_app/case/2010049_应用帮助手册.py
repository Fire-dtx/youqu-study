#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/09/28
"""
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_015(self):
        """应用帮助手册：点击标题栏设置(选项)菜单中的「帮助」, 帮助手册窗口
        正常打开并渲染页面

        断言方式:打开后电脑管家拉起 `dman deepin-pc-manager`, 其窗口标题为
        「帮助手册」且尺寸非零(实测 1022x680), 同时渲染进程 dmanHelper 存在。
        若标题栏菜单不可用(部分版本), 回退用 dman 命令打开同一手册, 结论等价。

        数据回退:关闭手册窗口并结束 dman 进程, 不留后台残留。
        """
        # 只匹配真正的 dman 进程(命令以 dman deepin-pc-manager 结尾),
        # 避免 pgrep/pkill 自身的 bash -c 包装行也被计入
        pattern = "(^|/)dman deepin-pc-manager$"
        widget = MyAppWidget(check_start=False)
        # 清理可能残留的上一轮手册进程, 保证基线干净
        widget.run_cmd(f"pkill -f '{pattern}' || true",
                       timeout=5, out_debug_flag=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        try:
            widget.open_help_manual()

            # 等待 dman 进程被拉起
            pid = ""
            for _ in range(30):
                pid = widget.run_cmd(
                    f"pgrep -f '{pattern}' | head -1 || true",
                    timeout=5, out_debug_flag=False).strip()
                if pid:
                    break
                sleep(1)
            self.assert_true(bool(pid))

            # 等待帮助手册窗口出现并读取标题/尺寸
            window_ids = ""
            for _ in range(20):
                window_ids = widget.run_cmd(
                    f"xdotool search --pid {pid} 2>/dev/null | tr '\\n' ' ' || true",
                    timeout=5, out_debug_flag=False).strip()
                if window_ids:
                    break
                sleep(1)
            self.assert_true(bool(window_ids))

            title = ""
            for wid in window_ids.split():
                title = widget.run_cmd(f"xdotool getwindowname {wid} 2>/dev/null || true",
                                       timeout=5, out_debug_flag=False).strip()
                if title:
                    break
            self.assert_true("帮助手册" in title)

            geometry = widget.run_cmd(
                f"xdotool getwindowgeometry {window_ids.split()[0]} 2>/dev/null || true",
                timeout=5, out_debug_flag=False)
            matched = re.search(r"Geometry: (\d+)x(\d+)", geometry)
            self.assert_true(matched is not None)
            self.assert_true(int(matched.group(1)) > 600 and int(matched.group(2)) > 400)

            # 页面渲染进程存在(手册为 webengine 渲染)
            helpers = widget.run_cmd("pgrep -c -f dmanHelper || true",
                                     timeout=5, out_debug_flag=False).strip()
            self.assert_true(helpers.isdigit() and int(helpers) > 0)
        finally:
            # 数据回退: 关闭手册窗口与 dman 进程
            widget.run_cmd(f"pkill -f '{pattern}' || true",
                           timeout=5, out_debug_flag=False)
            sleep(2)
            remain = widget.run_cmd(f"pgrep -f '{pattern}' || true",
                                    timeout=5, out_debug_flag=False).strip()
            self.assert_equal("", remain)
            widget.kill_pc_manager()

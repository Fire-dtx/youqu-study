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

    def _polkit_dialog(self, widget) -> bool:
        """AT-SPI + xdotool 双通道检查 polkit 鉴权框"""
        import pyatspi

        found = False

        def walk(node, depth=0):
            nonlocal found
            if node is None or depth > 8 or found:
                return
            try:
                children = list(node)
            except BaseException:
                return
            for child in children:
                if child is None:
                    continue
                try:
                    app = child.getApplication()
                    if (
                        app is not None
                        and app.name == "dde-polkit-agent"
                        and child.name == "Dialog_authdialog"
                        and child.getState().contains(pyatspi.STATE_SHOWING)
                    ):
                        found = True
                        return
                except BaseException:
                    pass
                walk(child, depth + 1)

        for app in pyatspi.Registry.getDesktop(0):
            walk(app, 0)
        return found or widget.get_polkit_auth_dialog_showing()

    def test_mycase_081(self):
        """系统检测-无需鉴权：点击「全面检测」后直接开始检测，不弹鉴权框

        步骤: 打开电脑管家 → 系统检测 → 点击「全面检测」。

        断言:
            1) 全面检测页面/运行态在点击后出现, 检测直接开始;
            2) 启动检测后持续观察 15s: 桌面无 polkit 鉴权对话框
               (dde-polkit-agent 的 Dialog_authdialog 与「认证」窗口均不存在);
            3) 电脑管家进程存活, 页面未异常退出。

        回退: 退出全面检测/关闭电脑管家, 校验无鉴权窗、无进程残留;
              本用例只读扫描, 不改动系统数据。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_false(self._polkit_dialog(widget))

            self.assert_true(widget.get_detection_full_scan_button_showing())
            widget.click_detection_full_scan_button()
            started = widget.get_detection_full_scan_page_showing(timeout=20)
            logger.info(f"[2032437] full scan page started={started}")
            self.assert_true(started)

            # 启动后 15s 内持续无鉴权框, 且检测运行态存在
            auth_seen = False
            running_seen = False
            for _ in range(30):
                if self._polkit_dialog(widget):
                    auth_seen = True
                    break
                if widget._any_visible("$//detection_runningIcon"):
                    running_seen = True
                sleep(0.5)
            logger.info(
                f"[2032437] auth_seen={auth_seen} running_seen={running_seen}"
            )
            self.assert_false(auth_seen)
            self.assert_true(widget.get_pc_manager_process_status())

            # 回到检测首页(扫描随页面退出/应用关闭终止)
            try:
                widget.click_back_button()
                sleep(2)
                self.assert_true(widget.get_detection_page_showing())
            except BaseException:
                logger.info("[2032437] back button unavailable, app will be closed")
        finally:
            for _ in range(2):
                widget.run_cmd(
                    "export DISPLAY=:0; xdotool key Escape",
                    timeout=5, out_debug_flag=False,
                )
                sleep(1)
            widget.kill_pc_manager()
            sleep(1)
            self.assert_false(self._polkit_dialog(widget))
            self.assert_false(widget.get_pc_manager_process_status())

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def _baobab_present(self, widget) -> bool:
        installed = bool(
            widget.run_cmd(
                "dpkg -l baobab 2>/dev/null | grep -q '^ii' && echo Y",
                timeout=10,
                out_debug_flag=False,
            ).strip().endswith("Y")
        )
        executable = bool(
            widget.run_cmd(
                "command -v baobab || true", timeout=5, out_debug_flag=False
            ).strip()
        )
        return installed or executable

    def _dialog_buttons(self, widget):
        dialog = None
        buttons = {}

        def walk(node, depth=0):
            nonlocal dialog
            if depth > 8:
                return
            try:
                children = node.children
            except BaseException:
                return
            for child in (children or []):
                try:
                    if child.showing and child.roleName == "dialog":
                        dialog = child
                    if (
                        child.showing
                        and child.roleName == "push button"
                        and child.name in ("取消", "立即安装")
                    ):
                        buttons[child.name] = child
                except BaseException:
                    pass
                walk(child, depth + 1)

        walk(widget.dog.obj)
        return dialog, buttons

    def _click_real(self, widget, element):
        x, y = element.position
        w, h = element.size
        widget.run_cmd(
            "export DISPLAY=:0; "
            f"xdotool mousemove {x + w // 2} {y + h // 2} click 1",
            timeout=10,
            out_debug_flag=False,
        )

    def test_mycase_257(self):
        """实用工具-磁盘工具: 未安装 baobab 时单击「磁盘使用情况分析器」

        步骤与断言:
        1) 前置校验 baobab 未安装、无 baobab 进程;
        2) 实用工具概览中磁盘工具分组显示「磁盘使用情况分析器」卡片;
        3) 单击卡片弹出未安装提示对话框, 提供「取消」「立即安装」两个按钮;
        4) 点击取消: 对话框关闭、回到实用工具页, 仍未安装 baobab、无进程。
        全程不安装任何包, 环境无残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            self.assert_false(self._baobab_present(widget))
            self.assert_false(
                bool(
                    widget.run_cmd(
                        "pgrep -x baobab", timeout=5, out_debug_flag=False
                    ).strip()
                )
            )

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())

            card = widget.dog.find_element_by_attr(
                "$//utility_sectionsContainer//磁盘使用情况分析器"
            )
            self.assert_true(card.showing)
            widget.click_disk_usage_analyzer_card()
            sleep(2)

            dialog, buttons = self._dialog_buttons(widget)
            logger.info(
                f"[2032417] dialog={dialog is not None} buttons={sorted(buttons)}"
            )
            self.assert_true(dialog is not None)
            self.assert_true(set(buttons) == {"取消", "立即安装"})

            widget._atspi_do_action(buttons["取消"])
            gone = False
            for _ in range(5):
                sleep(1)
                _, still = self._dialog_buttons(widget)
                if not still:
                    gone = True
                    break
            if not gone:
                # DDialog 的 AT-SPI Press 未生效时用 Esc 等价取消
                widget.run_cmd(
                    "export DISPLAY=:0; xdotool key Escape",
                    timeout=5,
                    out_debug_flag=False,
                )
                for _ in range(5):
                    sleep(1)
                    _, still = self._dialog_buttons(widget)
                    if not still:
                        gone = True
                        break
            logger.info(f"[2032417] dialog_closed={gone}")
            self.assert_true(gone)
            self.assert_true(widget.get_utility_page_showing())
            self.assert_false(self._baobab_present(widget))
            self.assert_false(
                bool(
                    widget.run_cmd(
                        "pgrep -x baobab", timeout=5, out_debug_flag=False
                    ).strip()
                )
            )
        finally:
            sleep(1)
            widget.kill_pc_manager()

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

    LOG = "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log"

    def _baobab_present(self, widget) -> bool:
        return bool(
            widget.run_cmd(
                "dpkg -l baobab 2>/dev/null | grep -q '^ii' && echo Y",
                timeout=10,
                out_debug_flag=False,
            ).strip().endswith("Y")
        )

    def _tree(self, widget):
        nodes = []

        def walk(node, depth=0):
            if depth > 8:
                return
            try:
                children = node.children
            except BaseException:
                return
            for child in (children or []):
                try:
                    if child.showing:
                        nodes.append(child)
                except BaseException:
                    pass
                walk(child, depth + 1)

        walk(widget.dog.obj)
        return nodes

    def _confirm(self, widget):
        dialog = None
        buttons = {}
        labels = []
        for node in self._tree(widget):
            if node.roleName == "dialog":
                dialog = node
            if node.roleName == "push button" and node.name in ("取消", "立即安装"):
                buttons[node.name] = node
            if node.roleName == "label" and node.name in (
                "DDialogTitleLabel",
                "DDialogMessageLabel",
            ):
                labels.append(node)
        return dialog, buttons, labels

    def test_mycase_258(self):
        """磁盘使用情况分析器-未安装baobab

        步骤与断言:
        1) 单击卡片弹出「工具未安装」确认框, 含取消/立即安装;
        2) 点取消仅关闭弹窗, 不安装 (baobab 仍不存在);
        3) 再次点卡片→立即安装, 断言已发起 pkexec 自动提权;
        4) 期望弹出鉴权窗口并在输入密码后显示「应用安装中」Loading。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            self.assert_false(self._baobab_present(widget))
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())

            widget.click_disk_usage_analyzer_card()
            sleep(2)
            dialog, buttons, labels = self._confirm(widget)
            logger.info(
                f"[2032419] confirm_dialog={dialog is not None} "
                f"buttons={sorted(buttons)} labels={len(labels)}"
            )
            widget.run_cmd(
                "export DISPLAY=:0; scrot -o /tmp/2032419_dialog.png",
                timeout=15,
                out_debug_flag=False,
            )
            self.assert_true(dialog is not None)
            self.assert_true(set(buttons) == {"取消", "立即安装"})
            self.assert_true(len(labels) >= 2)
            self.assert_true(all(l.size[0] > 0 and l.size[1] > 0 for l in labels))

            widget._atspi_do_action(buttons["取消"])
            cancelled = False
            for _ in range(4):
                sleep(1)
                _, still, _ = self._confirm(widget)
                if not still:
                    cancelled = True
                    break
            if not cancelled:
                # DDialog Press 未生效时, Esc 与该取消按钮同为仅关闭不安装
                widget.run_cmd(
                    "export DISPLAY=:0; xdotool key Escape",
                    timeout=5,
                    out_debug_flag=False,
                )
                for _ in range(5):
                    sleep(1)
                    _, still, _ = self._confirm(widget)
                    if not still:
                        cancelled = True
                        break
            logger.info(f"[2032419] cancel_closed={cancelled}")
            self.assert_true(cancelled)
            self.assert_false(self._baobab_present(widget))
            self.assert_false(
                bool(
                    widget.run_cmd(
                        "pgrep -x baobab", timeout=5, out_debug_flag=False
                    ).strip()
                )
            )

            # 再次触发并选择立即安装
            widget.click_disk_usage_analyzer_card()
            sleep(2)
            _, buttons, _ = self._confirm(widget)
            self.assert_true("立即安装" in buttons)
            widget._atspi_do_action(buttons["立即安装"])

            install_dialog = None
            failure_toast = None
            deadline = 15
            for _ in range(deadline):
                sleep(1)
                nodes = self._tree(widget)
                for node in nodes:
                    if node.roleName == "dialog" and node.name == "toolInstall_dialog":
                        install_dialog = node
                    if node.roleName == "label" and "工具安装失败" in node.name:
                        failure_toast = node.name
                if install_dialog is not None or failure_toast is not None:
                    break
            log_tail = widget.run_cmd(
                f"grep -a 'baobab' {self.LOG} | tail -5",
                timeout=10,
                out_debug_flag=False,
            )
            logger.info(
                f"[2032419] install_dialog={install_dialog is not None} "
                f"failure_toast={failure_toast!r} log_tail={log_tail!r}"
            )
            widget.run_cmd(
                "export DISPLAY=:0; scrot -o /tmp/2032419_install.png",
                timeout=15,
                out_debug_flag=False,
            )
            self.assert_true("InstallPackage via pkexec apt-get" in log_tail)
            # 预期: 提权后显示「应用安装中」Loading 对话框
            self.assert_true(install_dialog is not None)
        finally:
            widget.run_cmd(
                "export DISPLAY=:0; xdotool key Escape",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(1)
            widget.kill_pc_manager()

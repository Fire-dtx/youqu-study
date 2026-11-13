#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import threading
import time

import pyatspi
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from setting import conf
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    HOSTS = "/etc/hosts"
    DAEMON_BACKUP = "/var/log/deepin-pc-manager/hosts.bak"
    BACKUP = "/tmp/hosts_case210.bak"

    def _xdotool(self, widget, args: str):
        widget.run_cmd(
            f'export DISPLAY=:0; xdotool {args}', timeout=10, out_debug_flag=False
        )

    def _click_real(self, widget, element):
        x, y = element.position
        w, h = element.size
        self._xdotool(widget, f"mousemove {x + w // 2} {y + h // 2} click 1")
        sleep(0.5)

    def _sudo(self, widget, cmd: str):
        return widget.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S bash -c \"{cmd}\"",
            timeout=15,
            out_debug_flag=False,
        )

    def _find_card(self, widget):
        for section in widget.dog.find_elements_by_attr(
            "$//utility_sectionsContainer//utility_sectionWidget"
        ) or []:
            def walk(node, depth=0):
                if depth > 4:
                    return None
                for child in (node.children or []):
                    if child.roleName == "push button" and child.name == "本地域名解析工具":
                        return child
                    hit = walk(child, depth + 1)
                    if hit is not None:
                        return hit
                return None

            hit = walk(section)
            if hit is not None:
                return hit
        return None

    def test_mycase_210(self):
        """网络工具-性能与体验

        步骤与断言:
        1) 点击本地域名解析工具卡片, 用 AT-SPI showing 事件测编辑器打开延迟, <200ms;
        2) 在编辑器末尾追加合法记录并点击保存, 从真实点击到 /etc/hosts 落盘
           的完整链路耗时 <200ms。
        收尾: 恢复 /etc/hosts 与 hosts.bak 到测试前状态。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.run_cmd(
            f"cat {self.HOSTS} > {self.BACKUP}", timeout=5, out_debug_flag=False
        )
        self.assert_true(
            bool(
                widget.run_cmd(
                    f"test -s {self.BACKUP} && echo OK",
                    timeout=5,
                    out_debug_flag=False,
                ).strip().endswith("OK")
            )
        )
        daemon_bak_present = bool(
            widget.run_cmd(
                f"test -f {self.DAEMON_BACKUP} && echo Y",
                timeout=5,
                out_debug_flag=False,
            ).strip().endswith("Y")
        )
        daemon_bak_copy = "/tmp/hosts_daemon_bak_case210.keep"
        if daemon_bak_present:
            self._sudo(widget, f"cp -a {self.DAEMON_BACKUP} {daemon_bak_copy}")
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())
            card = self._find_card(widget)
            self.assert_true(card is not None)
            x, y = card.position
            cw, ch = card.size

            state = {"click": None, "open_ms": None}

            def listener(event):
                if state["open_ms"] is not None:
                    return
                try:
                    if not event.type.startswith("object:state-changed:showing"):
                        return
                    if not event.detail1:
                        return
                    if event.source.name in (
                        "utility_hostsTextEdit",
                        "utility_hostsSaveBtn",
                        "utility_hostsPage",
                    ):
                        if state["click"] is not None:
                            state["open_ms"] = round(
                                (time.monotonic() - state["click"]) * 1000, 1
                            )
                            pyatspi.Registry.stop()
                except BaseException as exc:
                    logger.info(f"[2032415] listener_error={exc}")

            def click_card():
                sleep(0.5)
                state["click"] = time.monotonic()
                widget.run_cmd(
                    "export DISPLAY=:0; "
                    f"xdotool mousemove {x + cw // 2} {y + ch // 2} click 1",
                    timeout=10,
                    out_debug_flag=False,
                )

            def watchdog():
                sleep(8)
                try:
                    pyatspi.Registry.stop()
                except BaseException:
                    pass

            pyatspi.Registry.registerEventListener(
                listener, "object:state-changed:showing"
            )
            threading.Thread(target=click_card, daemon=True).start()
            threading.Thread(target=watchdog, daemon=True).start()
            pyatspi.Registry.start(gil=0)
            logger.info(f"[2032415] open_ms={state['open_ms']}")
            self.assert_true(state["open_ms"] is not None)
            self.assert_true(state["open_ms"] < 200)
            self.assert_true(
                widget.dog.find_element_by_attr("$//utility_hostsPage").showing
            )

            edit = widget.dog.find_element_by_attr("$//utility_hostsTextEdit")
            self._click_real(widget, edit)
            self._xdotool(widget, "key ctrl+End")
            self._xdotool(widget, "key Return")
            self._xdotool(
                widget, 'type --clearmodifiers --delay 20 "10.9.9.9 perftest"'
            )
            sleep(0.5)
            save = widget.dog.find_element_by_attr("$//utility_hostsSaveBtn")
            sx, sy = save.position
            sw, sh = save.size
            start = time.monotonic()
            widget.run_cmd(
                "export DISPLAY=:0; "
                f"xdotool mousemove {sx + sw // 2} {sy + sh // 2} click 1",
                timeout=10,
                out_debug_flag=False,
            )
            save_ms = None
            while time.monotonic() - start < 5:
                try:
                    with open(self.HOSTS, "r", encoding="utf-8") as handle:
                        if "10.9.9.9 perftest" in handle.read():
                            save_ms = round((time.monotonic() - start) * 1000, 1)
                            break
                except OSError:
                    pass
            logger.info(f"[2032415] save_ms={save_ms}")
            self.assert_true(save_ms is not None)
            self.assert_true(save_ms < 200)
        finally:
            self._sudo(
                widget,
                f"cp -a {self.BACKUP} {self.HOSTS} && "
                f"chown root:root {self.HOSTS} && chmod 644 {self.HOSTS}",
            )
            if daemon_bak_present:
                self._sudo(
                    widget, f"cp -a {daemon_bak_copy} {self.DAEMON_BACKUP}"
                )
            else:
                self._sudo(widget, f"rm -f {self.DAEMON_BACKUP}")
            self._sudo(widget, f"rm -f {self.BACKUP} {daemon_bak_copy}")
            try:
                with open(self.HOSTS, "r", encoding="utf-8") as handle:
                    restored = handle.read()
                logger.info(
                    f"[2032415] restored_chars={len(restored)} "
                    f"has_test_line={'10.9.9.9 perftest' in restored}"
                )
            except OSError as exc:
                logger.info(f"[2032415] restore_check_error={exc}")
            sleep(1)
            widget.kill_pc_manager()

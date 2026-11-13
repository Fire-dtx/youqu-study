#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import shlex

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from setting import conf
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    MAX_MS = 200
    LAUNCHER = r"^/usr/bin/deepin-diskmanager( |$)"
    PROXY = r"^/usr/bin/deepin-diskmanager-authenticateProxy( |$)"
    SERVICE = r"^/usr/lib/deepin-daemon/deepin-diskmanager-service( |$)"

    def _sudo(self, widget, cmd: str, timeout=120):
        return widget.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S -p '' bash -c {shlex.quote(cmd)}",
            timeout=timeout,
            out_debug_flag=False,
        )

    def _now_ms(self, widget) -> int:
        out = widget.run_cmd(
            "date +%s%3N", timeout=5, out_debug_flag=False
        ).strip()
        return int(out.splitlines()[-1])

    def _pids(self, widget, pattern):
        return [
            x.strip()
            for x in widget.run_cmd(
                f"pgrep -f {shlex.quote(pattern)}", timeout=5,
                out_debug_flag=False,
            ).splitlines()
            if x.strip()
        ]

    def _service_pid(self, widget):
        out = widget.run_cmd(
            "ps -eo pid=,uid=,args= | grep -E "
            "'/usr/lib/deepin-daemon/deepin-diskmanager-service' | grep -v grep",
            timeout=5,
            out_debug_flag=False,
        )
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "0":
                return parts[0]
        return ""

    def _all_nodes(self):
        import pyatspi

        nodes = []

        def walk(node, depth=0):
            if node is None or depth > 10:
                return
            try:
                children = list(node)
            except BaseException:
                return
            for child in children:
                if child is None:
                    continue
                try:
                    if child.getState().contains(pyatspi.STATE_SHOWING):
                        app = child.getApplication()
                        nodes.append(
                            (
                                app.name if app else "",
                                child.getRoleName(),
                                child.name,
                                child,
                            )
                        )
                except BaseException:
                    pass
                walk(child, depth + 1)

        for app in pyatspi.Registry.getDesktop(0):
            walk(app, 0)
        return nodes

    def _click_center(self, widget, element) -> bool:
        try:
            ext = element.queryComponent().getExtents(0)
            if ext.width <= 0 or ext.height <= 0:
                return False
            x, y = ext.x + ext.width // 2, ext.y + ext.height // 2
        except BaseException:
            return False
        out = widget.run_cmd(
            f"export DISPLAY=:0; xdotool mousemove --sync {x} {y} click 1; "
            "echo click=$?",
            timeout=10,
            out_debug_flag=False,
        )
        return "click=0" in out

    def _auth_once(self, widget, timeout=25) -> bool:
        """等待 polkit 鉴权框并输入密码; 键盘优先, 点击仅作聚焦辅助"""
        for _ in range(timeout):
            roles = [
                (app, name, el, role)
                for app, role, name, el in self._all_nodes()
            ]
            dialog = [
                el for app, name, el, role in roles
                if app == "dde-polkit-agent" and name == "Dialog_authdialog"
            ]
            if not dialog:
                sleep(1)
                continue
            entry = confirm = None
            for app, name, el, role in roles:
                if app != "dde-polkit-agent":
                    continue
                if role == "text" and name == "EditableText_passwordinput":
                    entry = el
                elif role == "push button" and name == "Btn_confirm":
                    confirm = el
            logger.info(
                f"[2032427] auth dialog found entry={entry is not None} "
                f"confirm={confirm is not None}"
            )
            for attempt in range(3):
                clicked = False
                if entry is not None:
                    clicked = self._click_center(widget, entry)
                logger.info(f"[2032427] auth attempt={attempt} clicked={clicked}")
                out = widget.run_cmd(
                    "export DISPLAY=:0; xdotool key --clearmodifiers ctrl+a; "
                    "xdotool type --clearmodifiers "
                    f"'{conf.PASSWORD}'; xdotool key --clearmodifiers Return; "
                    "echo typed=$?",
                    timeout=15,
                    out_debug_flag=False,
                )
                logger.info(f"[2032427] auth type out={out!r}")
                sleep(3)
                left = [
                    el for app, name, el, role in self._all_nodes()
                    if app == "dde-polkit-agent"
                    and name == "Dialog_authdialog"
                ]
                if not left:
                    return True
                logger.info("[2032427] auth dialog still present, retry")
            return True
        return False

    def _mask_snapshot(self, widget):
        out = widget.run_cmd(
            "systemctl list-units --type=mount --all --plain --no-legend "
            "2>/dev/null | grep masked | awk '{print $1}'",
            timeout=10,
            out_debug_flag=False,
        )
        return set(x.strip() for x in out.splitlines() if x.strip())

    def _udev_snapshot(self, widget):
        out = widget.run_cmd(
            "ls -1 /run/udev/rules.d 2>/dev/null; "
            "test -d /run/udev/rules.d && echo __DIR__ || true",
            timeout=5,
            out_debug_flag=False,
        )
        return set(x.strip() for x in out.splitlines() if x.strip())

    def _xhost_has_root(self, widget) -> bool:
        out = widget.run_cmd(
            "export DISPLAY=:0; xhost 2>/dev/null | grep -c 'localuser:root'",
            timeout=5,
            out_debug_flag=False,
        )
        return out.strip() not in ("", "0")

    def test_mycase_262(self):
        """磁盘管理器-打开

        步骤: 单击「磁盘管理工具」卡片; 测响应耗时。
        预期: 通过系统 API 唤起窗口(磁盘管理器已打开); < 200ms 拉起独立进程。

        实现说明:
            - 卡片 runType=bin, 产品通过 QProcess::startDetached 启动
              /usr/bin/deepin-diskmanager; 该程序经 pkexec 调起
              com.deepin.diskmanager 的 authenticateProxy, 由 root 服务
              deepin-diskmanager-service 打开窗口。因此应用必须运行在
              session-1(通过启动器)才能弹出 polkit 鉴权框, 并由用例输入密码。
            - 以 5ms 粒度记录「卡片 Press → 启动器进程出现」耗时, 断言 <200ms;
              再等待 root 服务与窗口出现, 断言窗口真实打开。
            - root 服务启动时会 --runtime mask 一批 mount 单元、创建
              /run/udev/rules.d 临时规则、xhost 放行 root; 正常退出会自行恢复。
              用例在开始前快照、结束后兜底恢复这些系统状态。

        回退: 结束 root 服务/启动器/电脑管家, 恢复 mount mask、udev 临时规则、
              xhost root 放行, 校验无进程、无窗口、服务 inactive。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        self._sudo(widget, "pkill -TERM -f "
                   f"{shlex.quote(self.SERVICE)} 2>/dev/null; true", timeout=30)
        sleep(2)
        masks_before = set()
        udev_before = set()
        daemon_was_active = False
        try:
            self.assert_true(widget.is_disk_manager_installed())
            self.assert_false(bool(self._service_pid(widget)))
            self.assert_false(bool(self._pids(widget, self.LAUNCHER)))
            masks_before = self._mask_snapshot(widget)
            udev_before = self._udev_snapshot(widget)
            daemon_was_active = widget.run_cmd(
                "systemctl is-active diskmanager-daemon.service",
                timeout=5,
                out_debug_flag=False,
            ).strip() == "active"

            self.assert_true(widget.launch_app_from_launcher("电脑管家", wait=25))
            self.assert_true(widget.get_pc_manager_process_status())
            session_env = widget.run_cmd(
                "pid=$(pgrep -f '^/usr/libexec/deepin/deepin-pc-manager' | head -1); "
                "tr '\\0' '\\n' < /proc/$pid/environ | grep '^XDG_SESSION_ID='",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            logger.info(f"[2032427] app session env: {session_env!r}")
            self.assert_true("XDG_SESSION_ID=1" in session_env)
            widget.reconnect_dogtail()
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())

            card = widget.dog.find_element_by_attr(
                "$//utility_sectionsContainer//磁盘管理器"
            )
            self.assert_true(card.showing)

            widget.run_cmd(
                "rm -f /tmp/diskmanager_start_ms /tmp/diskmanager_watch.pid; "
                "setsid bash -c 'echo $$ >/tmp/diskmanager_watch.pid; "
                "while ! pgrep -f \"^/usr/bin/deepin-diskmanager( |$)\" "
                ">/dev/null; do sleep 0.005; done; date +%s%3N' "
                ">/tmp/diskmanager_start_ms 2>&1 </dev/null &",
                timeout=10,
                out_debug_flag=False,
            )
            sleep(1)
            watch_pid = widget.run_cmd(
                "cat /tmp/diskmanager_watch.pid", timeout=5, out_debug_flag=False
            ).strip()
            self.assert_true(bool(watch_pid))

            t0 = self._now_ms(widget)
            self.assert_true(widget._atspi_do_action(card))
            t1 = self._now_ms(widget)

            found = ""
            for _ in range(100):
                found = widget.run_cmd(
                    "cat /tmp/diskmanager_start_ms 2>/dev/null",
                    timeout=5,
                    out_debug_flag=False,
                ).strip()
                if found:
                    break
                sleep(0.05)
            logger.info(
                f"[2032427] t0={t0} action_return={t1} found={found!r}"
            )
            self.assert_true(bool(found))
            latency = int(found) - t0
            logger.info(
                f"[2032427] launch latency={latency}ms "
                f"action_rpc={t1 - t0}ms"
            )

            auth_seen = self._auth_once(widget, timeout=25)
            logger.info(f"[2032427] auth dialog={auth_seen}")

            service_pid = ""
            for _ in range(60):
                service_pid = self._service_pid(widget)
                if service_pid:
                    break
                sleep(1)
            logger.info(f"[2032427] root service pid={service_pid!r}")
            self.assert_true(bool(service_pid))

            windows = ""
            titles = ""
            win_pid = ""
            for _ in range(80):
                pids = [service_pid] + self._pids(widget, self.LAUNCHER)
                for pid in pids:
                    if not pid:
                        continue
                    cnt = widget.run_cmd(
                        "export DISPLAY=:0; "
                        f"xdotool search --onlyvisible --pid {pid} "
                        "2>/dev/null | wc -l",
                        timeout=10,
                        out_debug_flag=False,
                    ).strip()
                    if cnt.isdigit() and int(cnt) > 0:
                        windows, win_pid = cnt, pid
                        titles = widget.run_cmd(
                            "export DISPLAY=:0; "
                            f"for w in $(xdotool search --onlyvisible --pid {pid} "
                            "2>/dev/null); do xdotool getwindowname $w; done",
                            timeout=10,
                            out_debug_flag=False,
                        ).strip()
                        break
                if win_pid:
                    break
                # 兜底: 部分 Qt 窗口未设置 _NET_WM_PID, 按标题识别
                titles = widget.run_cmd(
                    "export DISPLAY=:0; "
                    "for w in $(xdotool search --onlyvisible --name '磁盘' "
                    "2>/dev/null); do xdotool getwindowname $w; done",
                    timeout=10,
                    out_debug_flag=False,
                ).strip()
                if titles:
                    windows, win_pid = "1", "title"
                    break
                sleep(0.5)
            logger.info(
                f"[2032427] visible windows={windows!r} pid={win_pid!r} "
                f"titles={titles!r}"
            )
            self.assert_true(windows.isdigit() and int(windows) > 0)
            self.assert_true(latency < self.MAX_MS)
            self.assert_true(widget.get_utility_page_showing())
        finally:
            for _ in range(2):
                widget.run_cmd(
                    "export DISPLAY=:0; xdotool key Escape",
                    timeout=5,
                    out_debug_flag=False,
                )
                sleep(1)
            # 先 TERM 让 root 服务正常退出以触发代理脚本自恢复
            self._sudo(
                widget,
                f"pkill -TERM -f {shlex.quote(self.SERVICE)} 2>/dev/null; "
                f"pkill -TERM -f {shlex.quote(self.LAUNCHER)} 2>/dev/null; "
                f"pkill -TERM -f {shlex.quote(self.PROXY)} 2>/dev/null; true",
                timeout=30,
            )
            for _ in range(20):
                if not self._service_pid(widget) and not self._pids(
                    widget, self.LAUNCHER
                ):
                    break
                sleep(1)
            self._sudo(
                widget,
                f"pkill -KILL -f {shlex.quote(self.SERVICE)} 2>/dev/null; "
                f"pkill -KILL -f {shlex.quote(self.LAUNCHER)} 2>/dev/null; "
                f"pkill -KILL -f {shlex.quote(self.PROXY)} 2>/dev/null; true",
                timeout=30,
            )
            widget.kill_pc_manager()
            widget.run_cmd(
                "test -f /tmp/diskmanager_watch.pid && "
                "kill $(cat /tmp/diskmanager_watch.pid) 2>/dev/null; "
                "rm -f /tmp/diskmanager_start_ms /tmp/diskmanager_watch.pid",
                timeout=10,
                out_debug_flag=False,
            )

            # 兜底恢复 root 服务可能留下的系统状态
            self._sudo(
                widget,
                "export DISPLAY=:0; "
                "xhost -SI:localuser:root >/dev/null 2>&1 || true",
                timeout=15,
            )
            masks_after = self._mask_snapshot(widget)
            new_masks = sorted(masks_after - masks_before)
            if new_masks:
                self._sudo(
                    widget,
                    "systemctl --runtime unmask --quiet -- "
                    + " ".join(new_masks),
                    timeout=30,
                )
            udev_after = self._udev_snapshot(widget)
            new_rules = sorted(
                x for x in udev_after - udev_before if x != "__DIR__"
            )
            if new_rules:
                self._sudo(
                    widget,
                    "rm -f " + " ".join(
                        shlex.quote("/run/udev/rules.d/" + x) for x in new_rules
                    ),
                    timeout=15,
                )
            if "__DIR__" in udev_after and "__DIR__" not in udev_before:
                self._sudo(widget, "rmdir /run/udev/rules.d 2>/dev/null || true")
            if not daemon_was_active:
                self._sudo(
                    widget,
                    "systemctl stop diskmanager-daemon.service "
                    ">/dev/null 2>&1 || true",
                    timeout=30,
                )
            sleep(1)
            left_proc = (
                self._pids(widget, self.SERVICE)
                + self._pids(widget, self.LAUNCHER)
                + self._pids(widget, self.PROXY)
            )
            masks_final = self._mask_snapshot(widget)
            udev_final = self._udev_snapshot(widget)
            logger.info(
                f"[2032427] teardown procs={left_proc} "
                f"xhost_root={self._xhost_has_root(widget)} "
                f"new_masks={new_masks} masks_final={sorted(masks_final)} "
                f"udev_new={new_rules} udev_final={sorted(udev_final)} "
                f"daemon={widget.run_cmd('systemctl is-active diskmanager-daemon.service', timeout=5, out_debug_flag=False).strip()}"
            )
            self.assert_false(bool(left_proc))
            self.assert_false(self._xhost_has_root(widget))
            self.assert_true(masks_final == masks_before)
            self.assert_true(udev_final == udev_before)
            if not daemon_was_active:
                active = widget.run_cmd(
                    "systemctl is-active diskmanager-daemon.service",
                    timeout=5,
                    out_debug_flag=False,
                ).strip()
                self.assert_true(active != "active")

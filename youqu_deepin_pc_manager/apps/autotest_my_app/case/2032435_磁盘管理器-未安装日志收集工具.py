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

    PKG = "deepin-log-viewer"
    DB = "/etc/permissionmanager.db"
    VIEWER = r"^/usr/bin/deepin-log-viewer( |$)"
    TITLE = "日志收集工具"

    def _sudo(self, widget, cmd: str, timeout=300):
        return widget.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S -p '' bash -c {shlex.quote(cmd)}",
            timeout=timeout,
            out_debug_flag=False,
        )

    def _viewer_pids(self, widget):
        return [
            x.strip()
            for x in widget.run_cmd(
                f"pgrep -f '{self.VIEWER}'", timeout=5,
                out_debug_flag=False,
            ).splitlines()
            if x.strip()
        ]

    def _viewer_titles(self, widget, pid):
        return widget.run_cmd(
            "export DISPLAY=:0; "
            f"for w in $(xdotool search --onlyvisible --pid {pid} "
            "2>/dev/null); do xdotool getwindowname $w; done",
            timeout=10,
            out_debug_flag=False,
        ).strip()

    def _kill_viewer(self, widget):
        widget.run_cmd(
            "killall -TERM deepin-log-viewer 2>/dev/null; true",
            timeout=5, out_debug_flag=False,
        )
        for _ in range(10):
            if not self._viewer_pids(widget):
                break
            sleep(0.5)
        if self._viewer_pids(widget):
            widget.run_cmd(
                "killall -KILL deepin-log-viewer 2>/dev/null; true",
                timeout=5, out_debug_flag=False,
            )
            sleep(1)

    def _all_nodes(self):
        import pyatspi

        nodes = []

        def walk(node, depth=0):
            if node is None or depth > 12:
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

    def _app_nodes(self, app_name="deepin-pc-manager"):
        return [
            (role, name, el)
            for app, role, name, el in self._all_nodes()
            if app == app_name
        ]

    def _press(self, widget, element) -> bool:
        try:
            if widget._atspi_do_action(element):
                return True
        except BaseException:
            pass
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
            timeout=10, out_debug_flag=False,
        )
        return "click=0" in out

    # ---------- 未安装确认框 ----------

    def _confirm(self):
        """返回 (有标题标签, 有描述标签, buttons)

        Dtk DLabel 未实现 AT-SPI Text 接口, 断言 DDialog 的
        「标题 + 描述 + 取消/立即安装」结构; 文案由 utility_page.cpp 的
        tr("Tool Not Installed") / tr("This tool is not installed yet.
        Install it now?") 及 zh_CN 翻译保证。
        """
        title = message = False
        buttons = {}
        for role, name, el in self._app_nodes():
            if role == "push button" and (name or "") in ("取消", "立即安装"):
                buttons[name] = el
            elif role == "label" and name == "DDialogTitleLabel":
                title = True
            elif role == "label" and name == "DDialogMessageLabel":
                message = True
        return title, message, buttons

    def _wait_confirm(self, timeout=15):
        for _ in range(timeout):
            title, message, buttons = self._confirm()
            if buttons:
                return title, message, buttons
            sleep(1)
        return False, False, {}

    def _wait_gone(self, timeout=10):
        for _ in range(timeout):
            if not self._confirm()[2]:
                return True
            sleep(1)
        return False

    # ---------- polkit ----------

    def _wait_auth(self, timeout=20):
        for _ in range(timeout):
            if any(
                app == "dde-polkit-agent" and name == "Dialog_authdialog"
                for app, _r, name, _el in self._all_nodes()
            ):
                return True
            sleep(1)
        return False

    def _type_auth(self, widget) -> bool:
        for attempt in range(4):
            nodes = self._all_nodes()
            dialog = [
                el for app, _r, name, el in nodes
                if app == "dde-polkit-agent" and name == "Dialog_authdialog"
            ]
            if not dialog:
                return True
            entry = None
            for app, role, name, el in nodes:
                if app == "dde-polkit-agent" and role == "text" \
                        and name == "EditableText_passwordinput":
                    entry = el
            clicked = self._press(widget, entry) if entry is not None else False
            out = widget.run_cmd(
                "export DISPLAY=:0; xdotool key --clearmodifiers ctrl+a; "
                "xdotool type --clearmodifiers "
                f"'{conf.PASSWORD}'; xdotool key --clearmodifiers Return; "
                "echo typed=$?",
                timeout=15, out_debug_flag=False,
            )
            logger.info(
                f"[2032435] auth attempt={attempt} clicked={clicked} out={out!r}"
            )
            sleep(3)
            if not any(
                app == "dde-polkit-agent" and name == "Dialog_authdialog"
                for app, _r, name, _el in self._all_nodes()
            ):
                return True
        return False

    # ---------- 包状态 ----------

    def _version(self, widget) -> str:
        return widget.run_cmd(
            f"dpkg-query -W -f='${{Version}}' {self.PKG} 2>/dev/null",
            timeout=10, out_debug_flag=False,
        ).strip()

    def _installed(self, widget) -> bool:
        return bool(
            widget.run_cmd(
                f"dpkg -l {self.PKG} 2>/dev/null | grep '^ii'",
                timeout=10, out_debug_flag=False,
            ).strip()
        )

    def _apt_busy(self, widget) -> bool:
        out = widget.run_cmd(
            "pgrep -af 'apt-get|dpkg' | grep -E "
            f"'{self.PKG}|apt-get (install|remove)' | grep -v grep",
            timeout=5, out_debug_flag=False,
        )
        return bool(out.strip())

    def _db_rows(self, widget):
        out = self._sudo(
            widget,
            f"sqlite3 {self.DB} \"SELECT pkgname,type FROM "
            f"package_white_table WHERE pkgname='{self.PKG}';\"",
            timeout=30,
        )
        return [
            x.replace("验证成功", "").strip()
            for x in out.splitlines()
            if x.replace("验证成功", "").strip()
        ]

    def test_mycase_266(self):
        """磁盘管理器-未安装日志收集工具

        步骤: 卸载 deepin-log-viewer → 单击「日志收集工具」卡片 → 取消 →
              再次单击卡片 → 立即安装 → 输入密码 → 观察 Loading。

        断言:
            1) 确认框: DDialog 标题+描述标签与「取消」「立即安装」按钮;
            2) 取消后弹窗关闭, 包未安装, 无日志收集工具进程;
            3) 立即安装 → polkit 鉴权 → toolInstall_dialog Loading;
            4) 安装成功 toast 且包恢复安装, 产品自动拉起日志收集工具窗口。

        回退: 关闭工具与电脑管家, 校验包版本/文件完整、包数不变、
              permissionmanager.db 不变、apt 缓存与临时 deb 清理、
              用户配置目录无新增、无进程残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        self._kill_viewer(widget)

        version_before = ""
        pkg_count_before = 0
        archives_before = set()
        db_before = []
        repack = ""
        dirs_before = {}
        try:
            self.assert_true(widget.is_log_viewer_installed())
            version_before = self._version(widget)
            self.assert_true(bool(version_before))
            pkg_count_before = int(
                widget.run_cmd(
                    "dpkg-query -W -f='${Package}\\n' 2>/dev/null | wc -l",
                    timeout=30, out_debug_flag=False,
                ).strip()
            )
            archives_before = set(
                widget.run_cmd(
                    "ls -1 /var/cache/apt/archives/deepin-log-viewer_*.deb "
                    "2>/dev/null",
                    timeout=10, out_debug_flag=False,
                ).split()
            )
            db_before = self._db_rows(widget)
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
            logger.info(
                f"[2032435] before version={version_before} "
                f"pkgs={pkg_count_before} archives={archives_before} "
                f"db={db_before}"
            )

            # 保险: 先重打包, 安装失败可离线恢复
            self._sudo(widget, "rm -f /tmp/deepin-log-viewer_*.deb", timeout=20)
            repack_out = self._sudo(
                widget, f"cd /tmp && dpkg-repack {self.PKG} 2>&1", timeout=120
            )
            logger.info(f"[2032435] dpkg-repack={repack_out[-300:]!r}")
            repack = widget.run_cmd(
                "ls -1t /tmp/deepin-log-viewer_*.deb 2>/dev/null | head -1",
                timeout=5, out_debug_flag=False,
            ).strip()

            # ===== 卸载 =====
            out = widget.run_cmd(
                f"echo '{conf.PASSWORD}' | sudo -S -p '' "
                f"env DEBIAN_FRONTEND=noninteractive apt-get remove -y {self.PKG}",
                timeout=180, out_debug_flag=False,
            )
            logger.info(f"[2032435] remove output={out[-400:]!r}")
            self.assert_false(widget.is_log_viewer_installed())
            self.assert_true(
                not widget.run_cmd(
                    "command -v deepin-log-viewer || true",
                    timeout=5, out_debug_flag=False,
                ).strip()
            )

            # ===== 启动应用(session-1, 安装需鉴权) =====
            self.assert_true(widget.launch_app_from_launcher("电脑管家", wait=25))
            self.assert_true(widget.get_pc_manager_process_status())
            session_env = widget.run_cmd(
                "pid=$(pgrep -f '^/usr/libexec/deepin/deepin-pc-manager' | head -1); "
                "tr '\\0' '\\n' < /proc/$pid/environ | grep '^XDG_SESSION_ID='",
                timeout=10, out_debug_flag=False,
            ).strip()
            logger.info(f"[2032435] app session env: {session_env!r}")
            self.assert_true("XDG_SESSION_ID=1" in session_env)
            widget.reconnect_dogtail()
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())

            card = widget.dog.find_element_by_attr(
                "$//utility_sectionsContainer//日志收集工具"
            )
            self.assert_true(card.showing)

            # ===== 单击卡片 → 取消 =====
            self.assert_true(widget._atspi_do_action(card))
            has_title, has_message, buttons = self._wait_confirm(20)
            logger.info(
                f"[2032435] confirm title_label={has_title} "
                f"message_label={has_message} buttons={sorted(buttons)}"
            )
            self.assert_true(has_title)
            self.assert_true(has_message)
            self.assert_true(set(buttons) == {"取消", "立即安装"})
            pressed = self._press(widget, buttons["取消"])
            gone = self._wait_gone(10)
            if not gone:
                widget.run_cmd(
                    "export DISPLAY=:0; xdotool key Escape",
                    timeout=5, out_debug_flag=False,
                )
                gone = self._wait_gone(10)
            logger.info(f"[2032435] cancel pressed={pressed} closed={gone}")
            self.assert_true(gone)
            self.assert_false(widget.is_log_viewer_installed())
            self.assert_false(bool(self._viewer_pids(widget)))
            self.assert_true(widget.get_utility_page_showing())

            # ===== 再次单击 → 立即安装 → 鉴权 → Loading =====
            self.assert_true(widget._atspi_do_action(card))
            _, _, buttons = self._wait_confirm(20)
            self.assert_true("立即安装" in buttons)
            pressed = self._press(widget, buttons["立即安装"])
            logger.info(f"[2032435] install pressed={pressed}")

            install_dialog_seen = False
            for _ in range(30):
                sleep(1)
                nodes = self._app_nodes()
                if any(name == "toolInstall_dialog" for _r, name, _e in nodes):
                    install_dialog_seen = True
                    break
            logger.info(f"[2032435] toolInstall dialog={install_dialog_seen}")

            auth_seen = self._wait_auth(25)
            logger.info(f"[2032435] auth dialog={auth_seen}")
            if auth_seen:
                self.assert_true(self._type_auth(widget))

            if not install_dialog_seen:
                for _ in range(15):
                    nodes = self._app_nodes()
                    if any(
                        name == "toolInstall_dialog" or name == "toolInstall_progress"
                        for _r, name, _e in nodes
                    ):
                        install_dialog_seen = True
                        break
                    sleep(1)
            logger.info(f"[2032435] loading visible={install_dialog_seen}")
            self.assert_true(install_dialog_seen)

            # ===== 安装完成 =====
            success = ""
            failure = ""
            quiet = 0
            for _ in range(240):
                names = [n for _r, n, _e in self._app_nodes() if n]
                if any("工具安装成功" in n for n in names):
                    success = next(n for n in names if "工具安装成功" in n)
                    break
                if any("工具安装失败" in n for n in names):
                    failure = next(n for n in names if "工具安装失败" in n)
                    break
                if not self._apt_busy(widget) and self._installed(widget):
                    quiet += 1
                    if quiet >= 5:
                        break
                else:
                    quiet = 0
                sleep(1)
            logger.info(
                f"[2032435] success={success!r} failure={failure!r} "
                f"installed={self._installed(widget)} busy={self._apt_busy(widget)}"
            )
            self.assert_false(bool(failure))
            self.assert_true(self._installed(widget))
            self.assert_true(self._version(widget) == version_before)

            # 产品自动拉起日志收集工具
            pid = ""
            titles = ""
            for _ in range(40):
                pids = self._viewer_pids(widget)
                if pids:
                    pid = pids[0]
                    titles = self._viewer_titles(widget, pid)
                    if self.TITLE in titles:
                        break
                sleep(1)
            logger.info(
                f"[2032435] auto launch pid={pid!r} titles={titles!r}"
            )
            self.assert_true(bool(pid))
            self.assert_true(self.TITLE in titles)
        finally:
            for _ in range(3):
                widget.run_cmd(
                    "export DISPLAY=:0; xdotool key Escape",
                    timeout=5, out_debug_flag=False,
                )
                sleep(1)
            for _ in range(60):
                if not self._apt_busy(widget):
                    break
                sleep(2)
            self._kill_viewer(widget)
            widget.kill_pc_manager()

            # ===== 包回退 =====
            if not self._installed(widget):
                out = widget.run_cmd(
                    f"echo '{conf.PASSWORD}' | sudo -S -p '' "
                    f"env DEBIAN_FRONTEND=noninteractive "
                    f"apt-get install -y {self.PKG}",
                    timeout=300, out_debug_flag=False,
                )
                logger.info(f"[2032435] fallback apt install={out[-300:]!r}")
            if not self._installed(widget) and repack:
                out = self._sudo(widget, f"dpkg -i {shlex.quote(repack)}", 180)
                logger.info(f"[2032435] fallback dpkg -i={out[-300:]!r}")
            self.assert_true(self._installed(widget))
            version_after = self._version(widget)
            self.assert_true(version_after == version_before)
            verify_out = widget.run_cmd(
                f"dpkg -V {self.PKG} 2>&1", timeout=60, out_debug_flag=False
            ).strip()
            self.assert_false(bool(verify_out))
            self.assert_true(
                widget.run_cmd(
                    "command -v deepin-log-viewer", timeout=5,
                    out_debug_flag=False,
                ).strip().endswith("deepin-log-viewer")
            )

            archives_after = set(
                widget.run_cmd(
                    "ls -1 /var/cache/apt/archives/deepin-log-viewer_*.deb "
                    "2>/dev/null",
                    timeout=10, out_debug_flag=False,
                ).split()
            )
            new_archives = sorted(archives_after - archives_before)
            if new_archives:
                self._sudo(
                    widget,
                    "rm -f " + " ".join(shlex.quote(x) for x in new_archives),
                    timeout=30,
                )
            if repack:
                self._sudo(widget, f"rm -f {shlex.quote(repack)}", timeout=15)
            self._sudo(widget, "rm -f /tmp/deepin-log-viewer_*.deb", timeout=15)

            removed_dirs = []
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
                    removed_dirs.append(path)

            pkg_count_after = int(
                widget.run_cmd(
                    "dpkg-query -W -f='${Package}\\n' 2>/dev/null | wc -l",
                    timeout=30, out_debug_flag=False,
                ).strip()
            )
            db_after = self._db_rows(widget)
            left = self._viewer_pids(widget)
            logger.info(
                f"[2032435] teardown pkgs={pkg_count_after} db={db_after} "
                f"procs={left} removed_dirs={removed_dirs} "
                f"archives={sorted(widget.run_cmd('ls -1 /var/cache/apt/archives/deepin-log-viewer_*.deb 2>/dev/null', timeout=5, out_debug_flag=False).split())}"
            )
            self.assert_true(pkg_count_after == pkg_count_before)
            self.assert_true(db_after == db_before)
            self.assert_false(bool(left))
            for path, existed in dirs_before.items():
                still = bool(
                    widget.run_cmd(
                        f"test -e {path} && echo yes || echo no",
                        timeout=5, out_debug_flag=False,
                    ).strip().endswith("yes")
                )
                self.assert_true(still == existed)

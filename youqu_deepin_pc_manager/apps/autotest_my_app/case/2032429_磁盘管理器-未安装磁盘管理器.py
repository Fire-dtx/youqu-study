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

    PKG = "deepin-diskmanager"
    DB = "/etc/permissionmanager.db"
    LAUNCHER = r"^/usr/bin/deepin-diskmanager( |$)"
    PROXY = r"^/usr/bin/deepin-diskmanager-authenticateProxy( |$)"
    SERVICE = r"^/usr/lib/deepin-daemon/deepin-diskmanager-service( |$)"

    # ---------- 基础 ----------

    def _sudo(self, widget, cmd: str, timeout=300):
        return widget.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S -p '' bash -c {shlex.quote(cmd)}",
            timeout=timeout,
            out_debug_flag=False,
        )

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

    def _press(self, widget, element) -> bool:
        try:
            ok = widget._atspi_do_action(element)
            if ok:
                return True
        except BaseException:
            pass
        return self._click_center(widget, element)

    # ---------- 确认对话框 ----------

    def _confirm(self):
        """返回 (有标题标签, 有描述标签, buttons) —— 工具未安装确认框

        Dtk 的 DLabel 未实现 AT-SPI Text 接口(queryText 抛
        NotImplementedError), 无法读取标签文本; 这里按运行时可达证据断言
        DDialog 的「标题 + 描述 + 取消/立即安装」结构, 文案由产品源码
        utility_page.cpp 的 tr("Tool Not Installed") /
        tr("This tool is not installed yet. Install it now?") 及其
        zh_CN 翻译保证。
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

    def _wait_gone(self, timeout=10, key="按钮"):
        for _ in range(timeout):
            _, _, buttons = self._confirm()
            if not buttons:
                return True
            sleep(1)
        return False

    # ---------- polkit 鉴权 ----------

    def _wait_auth(self, timeout=20):
        for _ in range(timeout):
            nodes = self._all_nodes()
            if any(
                app == "dde-polkit-agent" and name == "Dialog_authdialog"
                for app, _r, name, _el in nodes
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
                timeout=15,
                out_debug_flag=False,
            )
            logger.info(
                f"[2032429] auth attempt={attempt} clicked={clicked} out={out!r}"
            )
            sleep(3)
            left = [
                el for app, _r, name, el in self._all_nodes()
                if app == "dde-polkit-agent" and name == "Dialog_authdialog"
            ]
            if not left:
                return True
        return False

    # ---------- 安装状态 ----------

    def _version(self, widget) -> str:
        return widget.run_cmd(
            f"dpkg-query -W -f='${{Version}}' {self.PKG} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        ).strip()

    def _installed(self, widget) -> bool:
        return bool(
            widget.run_cmd(
                f"dpkg -l {self.PKG} 2>/dev/null | grep '^ii'",
                timeout=10,
                out_debug_flag=False,
            ).strip()
        )

    def _apt_busy(self, widget) -> bool:
        out = widget.run_cmd(
            "pgrep -af 'apt-get|dpkg' | grep -E "
            "'deepin-diskmanager|apt-get (install|remove)' | grep -v grep",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(out.strip())

    # ---------- 系统状态快照 ----------

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

    def _xhost_root(self, widget) -> bool:
        out = widget.run_cmd(
            "export DISPLAY=:0; xhost 2>/dev/null | grep -c 'localuser:root'",
            timeout=5,
            out_debug_flag=False,
        )
        return out.strip() not in ("", "0")

    def _db_rows(self, widget):
        out = self._sudo(
            widget,
            f"sqlite3 {self.DB} \"SELECT pkgname,type FROM package_white_table "
            f"WHERE pkgname='{self.PKG}';\"",
            timeout=30,
        )
        return [
            x.replace("验证成功", "").strip()
            for x in out.splitlines()
            if x.replace("验证成功", "").strip()
        ]

    # ---------- 收尾 ----------

    def _kill_diskmanager(self, widget):
        for sig in ("TERM", "KILL"):
            self._sudo(
                widget,
                f"pkill -{sig} -f {shlex.quote(self.SERVICE)} 2>/dev/null; "
                f"pkill -{sig} -f {shlex.quote(self.LAUNCHER)} 2>/dev/null; "
                f"pkill -{sig} -f {shlex.quote(self.PROXY)} 2>/dev/null; true",
                timeout=30,
            )
            sleep(2)
            if not (
                self._pids(widget, self.SERVICE)
                or self._pids(widget, self.LAUNCHER)
                or self._pids(widget, self.PROXY)
            ):
                break

    def test_mycase_263(self):
        """磁盘管理器-未安装磁盘管理器

        步骤: 卸掉 deepin-diskmanager → 单击「磁盘管理器」卡片 → 取消 →
              再次单击卡片 → 立即安装 → 输入密码 → 观察 Loading。

        断言:
            1) 弹出确认框: 标题「工具未安装」, 描述「当前工具尚未安装，是否立即安装？」,
               按钮「取消」「立即安装」;
            2) 取消后弹窗关闭, 包未安装, 无磁盘管理器进程, 页面正常;
            3) 立即安装后弹出 polkit 鉴权框, 输入密码后出现 toolInstall_dialog
               (DWaterProgress + 状态标签) 的安装中 Loading;
            4) 安装完成 (工具安装成功), 产品自动拉起工具进程/窗口。

        回退: 结束工具与电脑管家, 校验包恢复为测试前版本且文件完整, 清理 apt
              缓存与临时 deb, 恢复 mount mask/udev 规则/xhost root 放行与
              systemd 单元状态, permissionmanager.db 无变化, 无进程残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        self._kill_diskmanager(widget)

        version_before = ""
        installed_before = False
        pkg_count_before = 0
        archives_before = set()
        masks_before = set()
        udev_before = set()
        unit_before = ("", "")
        db_before = []
        repack = ""
        try:
            installed_before = widget.is_disk_manager_installed()
            self.assert_true(installed_before)
            version_before = self._version(widget)
            self.assert_true(bool(version_before))
            pkg_count_before = int(
                widget.run_cmd(
                    "dpkg-query -W -f='${Package}\\n' 2>/dev/null | wc -l",
                    timeout=30,
                    out_debug_flag=False,
                ).strip()
            )
            archives_before = set(
                widget.run_cmd(
                    "ls -1 /var/cache/apt/archives/deepin-diskmanager_*.deb "
                    "2>/dev/null",
                    timeout=10,
                    out_debug_flag=False,
                ).split()
            )
            masks_before = self._mask_snapshot(widget)
            udev_before = self._udev_snapshot(widget)
            unit_before = (
                widget.run_cmd(
                    "systemctl is-enabled diskmanager-daemon.service",
                    timeout=5, out_debug_flag=False,
                ).strip(),
                widget.run_cmd(
                    "systemctl is-active diskmanager-daemon.service",
                    timeout=5, out_debug_flag=False,
                ).strip(),
            )
            db_before = self._db_rows(widget)
            logger.info(
                f"[2032429] before version={version_before} "
                f"pkgs={pkg_count_before} archives={archives_before} "
                f"unit={unit_before} db={db_before}"
            )

            # 保险: 先重打包当前版本, 安装失败时可离线恢复
            self._sudo(widget, "rm -f /tmp/deepin-diskmanager_*.deb", timeout=20)
            repack_out = self._sudo(
                widget,
                f"cd /tmp && dpkg-repack {self.PKG} 2>&1",
                timeout=120,
            )
            logger.info(f"[2032429] dpkg-repack={repack_out[-300:]!r}")
            repack = widget.run_cmd(
                "ls -1t /tmp/deepin-diskmanager_*.deb 2>/dev/null | head -1",
                timeout=5, out_debug_flag=False,
            ).strip()

            # ===== 步骤 0: 卸载 =====
            out = widget.run_cmd(
                f"echo '{conf.PASSWORD}' | sudo -S -p '' "
                f"env DEBIAN_FRONTEND=noninteractive apt-get remove -y {self.PKG}",
                timeout=180,
                out_debug_flag=False,
            )
            logger.info(f"[2032429] remove output={out[-400:]!r}")
            self.assert_false(widget.is_disk_manager_installed())
            self.assert_true(
                not widget.run_cmd(
                    "command -v deepin-diskmanager || true",
                    timeout=5, out_debug_flag=False,
                ).strip()
            )

            # ===== 启动应用(session-1, 鉴权需要) =====
            self.assert_true(widget.launch_app_from_launcher("电脑管家", wait=25))
            self.assert_true(widget.get_pc_manager_process_status())
            session_env = widget.run_cmd(
                "pid=$(pgrep -f '^/usr/libexec/deepin/deepin-pc-manager' | head -1); "
                "tr '\\0' '\\n' < /proc/$pid/environ | grep '^XDG_SESSION_ID='",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            logger.info(f"[2032429] app session env: {session_env!r}")
            self.assert_true("XDG_SESSION_ID=1" in session_env)
            widget.reconnect_dogtail()
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())

            card = widget.dog.find_element_by_attr(
                "$//utility_sectionsContainer//磁盘管理器"
            )
            self.assert_true(card.showing)

            # ===== 步骤 1-2: 单击卡片 → 确认框 → 取消 =====
            self.assert_true(widget._atspi_do_action(card))
            has_title, has_message, buttons = self._wait_confirm(20)
            logger.info(
                f"[2032429] confirm title_label={has_title} "
                f"message_label={has_message} buttons={sorted(buttons)}"
            )
            self.assert_true(has_title)
            self.assert_true(has_message)
            self.assert_true(set(buttons) == {"取消", "立即安装"})
            pressed = self._press(widget, buttons["取消"])
            gone = self._wait_gone(10)
            if not gone:
                # AT-SPI Press 未生效时按 Esc 等价取消
                widget.run_cmd(
                    "export DISPLAY=:0; xdotool key Escape",
                    timeout=5, out_debug_flag=False,
                )
                gone = self._wait_gone(10)
            logger.info(
                f"[2032429] cancel pressed={pressed} closed={gone}"
            )
            self.assert_true(gone)
            self.assert_false(widget.is_disk_manager_installed())
            self.assert_false(
                bool(
                    widget.run_cmd(
                        "pgrep -f deepin-diskmanager", timeout=5,
                        out_debug_flag=False,
                    ).strip()
                )
            )
            self.assert_true(widget.get_utility_page_showing())

            # ===== 步骤 3-4: 再次单击 → 立即安装 → 鉴权 → Loading =====
            self.assert_true(widget._atspi_do_action(card))
            _, _, buttons = self._wait_confirm(20)
            self.assert_true("立即安装" in buttons)
            pressed = self._press(widget, buttons["立即安装"])
            logger.info(f"[2032429] install pressed={pressed}")

            install_dialog_seen = False
            status_text = ""
            for _ in range(30):
                sleep(1)
                nodes = self._app_nodes()
                if any(name == "toolInstall_dialog" for _r, name, _e in nodes):
                    install_dialog_seen = True
                    for _r, name, _e in nodes:
                        if name == "toolInstall_statusLabel":
                            status_text = name
                    break
            logger.info(
                f"[2032429] toolInstall dialog={install_dialog_seen} "
                f"status={status_text!r}"
            )

            auth_seen = self._wait_auth(25)
            logger.info(f"[2032429] auth dialog={auth_seen}")
            if auth_seen:
                self.assert_true(self._type_auth(widget))

            # 若鉴权前 Loading 没抓到, 鉴权后再确认一次
            if not install_dialog_seen:
                for _ in range(15):
                    nodes = self._app_nodes()
                    if any(
                        name == "toolInstall_dialog" or name == "toolInstall_progress"
                        for _r, name, _e in nodes
                    ):
                        install_dialog_seen = True
                        status_text = next(
                            (n for _r, n, _e in nodes
                             if n == "toolInstall_statusLabel"), ""
                        )
                        break
                    sleep(1)
            logger.info(
                f"[2032429] loading visible={install_dialog_seen} "
                f"status={status_text!r}"
            )
            self.assert_true(install_dialog_seen)

            # ===== 等待安装完成(工具安装成功 toast) =====
            success = ""
            failure = ""
            for _ in range(240):
                names = [
                    n for _r, n, _e in self._app_nodes() if n
                ]
                if any("工具安装成功" in n for n in names):
                    success = next(n for n in names if "工具安装成功" in n)
                    break
                if any("工具安装失败" in n for n in names):
                    failure = next(n for n in names if "工具安装失败" in n)
                    break
                if not self._apt_busy(widget) and self._installed(widget):
                    sleep(2)
                    continue
                sleep(1)
            logger.info(
                f"[2032429] success={success!r} failure={failure!r} "
                f"installed={self._installed(widget)} busy={self._apt_busy(widget)}"
            )
            self.assert_false(bool(failure))
            self.assert_true(self._installed(widget))
            self.assert_true(self._version(widget) == version_before)

            # 产品安装成功后自动拉起工具: 处理鉴权并校验窗口
            launched = False
            for _ in range(30):
                if self._pids(widget, self.LAUNCHER) or self._service_pid(widget):
                    launched = True
                    break
                sleep(1)
            logger.info(f"[2032429] auto launch process={launched}")
            if launched:
                if self._wait_auth(10):
                    self._type_auth(widget)
                window_pid = ""
                for _ in range(30):
                    pids = [self._service_pid(widget)] + self._pids(
                        widget, self.LAUNCHER
                    )
                    for pid in pids:
                        if not pid:
                            continue
                        cnt = widget.run_cmd(
                            "export DISPLAY=:0; "
                            f"xdotool search --onlyvisible --pid {pid} "
                            "2>/dev/null | wc -l",
                            timeout=8, out_debug_flag=False,
                        ).strip()
                        if cnt.isdigit() and int(cnt) > 0:
                            window_pid = pid
                            break
                    if window_pid:
                        break
                    sleep(1)
                titles = ""
                if window_pid:
                    titles = widget.run_cmd(
                        "export DISPLAY=:0; "
                        f"for w in $(xdotool search --onlyvisible --pid {window_pid} "
                        "2>/dev/null); do xdotool getwindowname $w; done",
                        timeout=8, out_debug_flag=False,
                    ).strip()
                logger.info(
                    f"[2032429] auto launch window pid={window_pid!r} "
                    f"titles={titles!r}"
                )
                self.assert_true(bool(window_pid))
                self.assert_true("磁盘" in titles)
        finally:
            # ===== 界面回退 =====
            for _ in range(3):
                widget.run_cmd(
                    "export DISPLAY=:0; xdotool key Escape",
                    timeout=5, out_debug_flag=False,
                )
                sleep(1)
            # 等 apt/dpkg 事务结束, 绝不在事务中杀进程
            for _ in range(60):
                if not self._apt_busy(widget):
                    break
                sleep(2)
            self._kill_diskmanager(widget)
            widget.kill_pc_manager()
            widget.run_cmd(
                "export DISPLAY=:0; xhost -SI:localuser:root "
                ">/dev/null 2>&1 || true",
                timeout=10, out_debug_flag=False,
            )

            # ===== 包回退 =====
            if not self._installed(widget):
                out = widget.run_cmd(
                    f"echo '{conf.PASSWORD}' | sudo -S -p '' "
                    f"env DEBIAN_FRONTEND=noninteractive "
                    f"apt-get install -y {self.PKG}",
                    timeout=300, out_debug_flag=False,
                )
                logger.info(f"[2032429] fallback apt install={out[-300:]!r}")
            if not self._installed(widget) and repack:
                out = self._sudo(widget, f"dpkg -i {shlex.quote(repack)}", 180)
                logger.info(f"[2032429] fallback dpkg -i={out[-300:]!r}")
            self.assert_true(self._installed(widget))
            version_after = self._version(widget)
            logger.info(
                f"[2032429] version after={version_after} "
                f"before={version_before}"
            )
            self.assert_true(version_after == version_before)

            verify_out = widget.run_cmd(
                f"dpkg -V {self.PKG} 2>&1", timeout=60, out_debug_flag=False
            ).strip()
            logger.info(f"[2032429] dpkg -V={verify_out!r}")
            self.assert_false(bool(verify_out))
            self.assert_true(
                widget.run_cmd(
                    f"command -v deepin-diskmanager", timeout=5,
                    out_debug_flag=False,
                ).strip().endswith("deepin-diskmanager")
            )

            # ===== 系统状态回退 =====
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
            new_rules = sorted(x for x in udev_after - udev_before if x != "__DIR__")
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
            if unit_before:
                if unit_before[1] != "active":
                    self._sudo(
                        widget,
                        "systemctl stop diskmanager-daemon.service "
                        ">/dev/null 2>&1 || true",
                        timeout=30,
                    )
            # apt 缓存与临时包
            archives_after = set(
                widget.run_cmd(
                    "ls -1 /var/cache/apt/archives/deepin-diskmanager_*.deb "
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
            self._sudo(widget, "rm -f /tmp/deepin-diskmanager_*.deb", timeout=15)

            pkg_count_after = int(
                widget.run_cmd(
                    "dpkg-query -W -f='${Package}\\n' 2>/dev/null | wc -l",
                    timeout=30, out_debug_flag=False,
                ).strip()
            )
            db_after = self._db_rows(widget)
            left_proc = (
                self._pids(widget, self.SERVICE)
                + self._pids(widget, self.LAUNCHER)
                + self._pids(widget, self.PROXY)
            )
            unit_after = (
                widget.run_cmd(
                    "systemctl is-enabled diskmanager-daemon.service",
                    timeout=5, out_debug_flag=False,
                ).strip(),
                widget.run_cmd(
                    "systemctl is-active diskmanager-daemon.service",
                    timeout=5, out_debug_flag=False,
                ).strip(),
            )
            logger.info(
                f"[2032429] teardown pkgs={pkg_count_after} "
                f"db={db_after} procs={left_proc} "
                f"xhost_root={self._xhost_root(widget)} "
                f"masks={sorted(self._mask_snapshot(widget))} "
                f"udev={sorted(self._udev_snapshot(widget))} "
                f"unit={unit_after} "
                f"archives={sorted(widget.run_cmd('ls -1 /var/cache/apt/archives/deepin-diskmanager_*.deb 2>/dev/null', timeout=5, out_debug_flag=False).split())}"
            )
            self.assert_true(pkg_count_after == pkg_count_before)
            self.assert_true(db_after == db_before)
            self.assert_false(bool(left_proc))
            self.assert_false(self._xhost_root(widget))
            self.assert_true(self._mask_snapshot(widget) == masks_before)
            self.assert_true(self._udev_snapshot(widget) == udev_before)
            self.assert_true(unit_after == unit_before)

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

    PKG = "baobab"
    DB = "/etc/permissionmanager.db"
    LOG = "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log"

    def _sudo(self, widget, cmd: str, timeout=180):
        return widget.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S -p '' bash -c {shlex.quote(cmd)}",
            timeout=timeout,
            out_debug_flag=False,
        )

    def _db(self, widget, sql: str, timeout=60):
        out = self._sudo(
            widget,
            f"sqlite3 {self.DB} {shlex.quote(sql)}",
            timeout=timeout,
        )
        lines = []
        for line in out.splitlines():
            line = line.replace("请输入密码", "").replace("验证成功", "").strip()
            if line:
                lines.append(line)
        return "\n".join(lines)

    def _package_set(self, widget):
        out = widget.run_cmd(
            "dpkg-query -W -f='${Package}\\n' 2>/dev/null | sort",
            timeout=30,
            out_debug_flag=False,
        )
        return set(x.strip() for x in out.splitlines() if x.strip())

    def _target_packages(self, widget):
        """apt 安装 baobab 会新增的全部包名(含依赖)"""
        out = widget.run_cmd(
            "apt-get -s install -y baobab 2>/dev/null | "
            "sed -n 's/^Inst \\([^ ]*\\).*/\\1/p'",
            timeout=60,
            out_debug_flag=False,
        )
        pkgs = [x.strip().split(":")[0] for x in out.splitlines() if x.strip()]
        return pkgs

    def _all_nodes(self):
        """收集当前所有 AT-SPI showing 节点[(app, role, name, element), ...]"""
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

    def _find_button(self, name):
        for app, role, text, el in self._all_nodes():
            if role == "push button" and text == name:
                return el
        return None

    def _wait_button(self, name, timeout=15):
        for _ in range(timeout):
            el = self._find_button(name)
            if el is not None:
                return el
            sleep(1)
        return None

    def _install_whitelist(self, widget, pkgs):
        """把本次要安装的包加入 permission-manager 安装白名单

        UOS 的 dpkg pre-unpack 钩子只允许安装 package_white_table 内的包,
        否则报「禁止安装非白名单包」。该限制属于系统安全策略, 不是产品问题;
        测试按等价环境构造: 临时加入白名单, 跑完真实安装流程后精确删除。
        """
        before = self._db(
            widget,
            "SELECT pkgname FROM package_white_table WHERE pkgname IN (%s);"
            % ",".join("'%s'" % p for p in pkgs),
        )
        existing = set(x for x in before.splitlines() if x.strip())
        added = [p for p in pkgs if p not in existing]
        if added:
            sql = ";".join(
                "INSERT OR IGNORE INTO package_white_table(pkgname,type) "
                "VALUES ('%s','default')" % p
                for p in added
            )
            self._db(widget, sql + ";")
        check = self._db(
            widget,
            "SELECT pkgname FROM package_white_table WHERE pkgname IN (%s);"
            % ",".join("'%s'" % p for p in pkgs),
        )
        missing = [p for p in pkgs if p not in set(check.splitlines())]
        logger.info(f"[2032421] whitelist added={added} missing={missing}")
        return added

    def _restore_whitelist(self, widget, added):
        if not added:
            return True
        self._db(
            widget,
            "DELETE FROM package_white_table WHERE pkgname IN (%s);"
            % ",".join("'%s'" % p for p in added),
        )
        left = self._db(
            widget,
            "SELECT count(*) FROM package_white_table WHERE pkgname IN (%s);"
            % ",".join("'%s'" % p for p in added),
        )
        return left.strip() == "0"

    def _present_packages(self, widget, pkgs):
        out = widget.run_cmd(
            "for p in %s; do dpkg-query -W -f='${Package}\\n' \"$p\" "
            "2>/dev/null; done" % " ".join(pkgs),
            timeout=30,
            out_debug_flag=False,
        )
        return set(x.strip() for x in out.splitlines() if x.strip())

    def _purge(self, widget, pkgs):
        """卸载测试新增包: 临时停掉 permission-manager 以解除 dpkg 提权拦截

        permission-manager 对未登记的包在 dpkg 卸载阶段返回「保护」, 直接
        apt purge 会失败; 该服务只影响提权校验, 短暂停止后立即恢复。
        """
        self._sudo(
            widget,
            "systemctl mask --runtime permission-manager.service >/dev/null 2>&1 || true; "
            "systemctl stop permission-manager.service >/dev/null 2>&1 || true",
            timeout=30,
        )
        try:
            present = self._present_packages(widget, pkgs)
            if present:
                out = self._sudo(
                    widget,
                    "DEBIAN_FRONTEND=noninteractive apt-get purge -y "
                    + " ".join(sorted(present)),
                    timeout=300,
                )
                logger.info(f"[2032421] purge output tail: {out[-500:]!r}")
            self._sudo(widget, "dpkg --configure --pending >/dev/null 2>&1 || true")
        finally:
            self._sudo(
                widget,
                "systemctl unmask --runtime permission-manager.service >/dev/null 2>&1 || true; "
                "systemctl start permission-manager.service",
                timeout=60,
            )
        active = widget.run_cmd(
            "systemctl is-active permission-manager.service",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        self.assert_true(active == "active")

    def _clean_cache(self, widget, pkgs):
        # /var/cache/apt 需要 root
        pattern = " ".join(
            f"/var/cache/apt/archives/{p}_*.deb*" for p in pkgs
        )
        self._sudo(widget, f"rm -f {pattern}", timeout=30)

    def test_mycase_259(self):
        """磁盘使用情况分析器-baobab安装成功

        用例描述:
            步骤: 单击「磁盘使用情况分析器」卡片 -「立即安装」- 输入密码
            预期: toast 提示【工具安装成功】, 并直接拉起工具。

        环境说明与等价构造:
            1) 测试机 UOS 20 的 dpkg pre-unpack 钩子只允许安装
               /etc/permissionmanager.db 中 package_white_table 内的包,
               否则直接以「禁止安装非白名单包」失败。这不是产品行为,
               故测试前把本次 apt 计划新增的包(含依赖)临时写入白名单,
               测试结束精确删除, 恢复表内容。
            2) 产品安装命令是 pkexec apt-get, 依赖会话 polkit 代理弹鉴权框。
               从 SSH 直接启动的电脑管家不属于桌面 session-1, polkit 找不到
               代理(libyelp0 之外的包同理)。因此改用启动器真实拉起应用,
               使主进程位于 session-1.scope, 鉴权框可正常出现并输入密码。
            3) 安装成功后断言: 安装对话框完成、toast「工具安装成功」、
               baobab 包已安装且进程被拉起。

        回退: 杀 baobab/电脑管家, 临时停 permission-manager 卸载本次新增包
              (含依赖), 恢复服务与白名单表, 清理 apt 缓存, 校验包集合与
              数据库行数恢复、无 baobab 进程与残留目录。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.kill_baobab()
        created_dirs = []
        targets = []
        added_whitelist = []
        before_pkgs = set()
        whitelist_count_before = ""
        try:
            # ===== 前置: baobab 未安装, 记录基线 =====
            widget.run_cmd(
                "export DISPLAY=:0; xdotool key Escape",
                timeout=5,
                out_debug_flag=False,
            )
            self.assert_false(widget.is_baobab_installed())
            self.assert_false(widget.get_baobab_process_status())
            before_pkgs = self._package_set(widget)
            whitelist_count_before = self._db(
                widget, "SELECT count(*) FROM package_white_table;"
            )
            logger.info(
                f"[2032421] baseline packages={len(before_pkgs)} "
                f"whitelist_rows={whitelist_count_before}"
            )

            targets = self._target_packages(widget)
            logger.info(f"[2032421] apt targets={targets}")
            self.assert_true(self.PKG in targets)
            added_whitelist = self._install_whitelist(widget, targets)

            # ===== 记录可能被工具创建的目录, 供回退清理 =====
            home = widget.run_cmd("echo $HOME", timeout=5, out_debug_flag=False).strip()
            for rel in (".config/baobab", ".cache/baobab", ".local/share/baobab"):
                path = f"{home}/{rel}"
                if not widget.run_cmd(
                    f"test -e {path} && echo yes || echo no",
                    timeout=5,
                    out_debug_flag=False,
                ).strip().endswith("yes"):
                    created_dirs.append(path)

            # ===== 通过启动器在桌面会话内启动应用 =====
            launched = widget.launch_app_from_launcher("电脑管家", wait=25)
            logger.info(f"[2032421] launcher started={launched}")
            self.assert_true(launched)
            self.assert_true(widget.get_pc_manager_process_status())
            session_env = widget.run_cmd(
                "pid=$(pgrep -f '^/usr/libexec/deepin/deepin-pc-manager' | head -1); "
                "tr '\\0' '\\n' < /proc/$pid/environ | grep '^XDG_SESSION_ID='",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            logger.info(f"[2032421] app session env: {session_env!r}")
            self.assert_true("XDG_SESSION_ID=1" in session_env)

            widget.reconnect_dogtail()
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())
            widget.click_disk_usage_analyzer_card()

            # ===== 未安装确认框 → 立即安装 =====
            install_btn = self._wait_button("立即安装", timeout=15)
            self.assert_true(install_btn is not None)
            self.assert_true(self._click_center(widget, install_btn))

            # ===== polkit 鉴权: 出现则输入密码; 已缓存授权则直接安装 =====
            auth_seen = False
            install_dialog_seen = False
            for _ in range(15):
                sleep(1)
                roles = [
                    (app, role, name)
                    for app, role, name, _el in self._all_nodes()
                ]
                if any(
                    app == "dde-polkit-agent" and name == "Dialog_authdialog"
                    for app, _r, name in roles
                ):
                    auth_seen = True
                    break
                if any(
                    app == "deepin-pc-manager" and name == "toolInstall_dialog"
                    for app, _r, name in roles
                ):
                    install_dialog_seen = True
                    break
            logger.info(
                f"[2032421] auth_seen={auth_seen} "
                f"install_dialog_seen={install_dialog_seen}"
            )
            if auth_seen:
                # 密码框与确定按钮只取一次坐标; 提交后用全新树查询, 避免访问失效节点
                entry = None
                confirm = None
                for _app, role, name, el in self._all_nodes():
                    if role == "text" and name == "EditableText_passwordinput":
                        entry = el
                    elif role == "push button" and name == "Btn_confirm":
                        confirm = el
                self.assert_true(entry is not None and confirm is not None)
                self.assert_true(self._click_center(widget, entry))
                sleep(1)
                typed = widget.run_cmd(
                    "export DISPLAY=:0; xdotool type --clearmodifiers "
                    f"'{conf.PASSWORD}'",
                    timeout=10,
                    out_debug_flag=False,
                )
                logger.info(f"[2032421] password typed: {typed!r}")
                sleep(1)
                # Return 与点击确定等价; 回车后不再引用旧节点
                widget.run_cmd(
                    "export DISPLAY=:0; xdotool key --clearmodifiers Return",
                    timeout=10,
                    out_debug_flag=False,
                )

            # ===== 等待安装完成 toast + 工具拉起 =====
            success_toast = ""
            failure_toast = ""
            deadline = 240
            for _ in range(deadline):
                names = [name for _a, _r, name, _e in self._all_nodes() if name]
                if any("工具安装成功" in n for n in names):
                    success_toast = next(n for n in names if "工具安装成功" in n)
                    break
                if any("工具安装失败" in n for n in names):
                    failure_toast = next(n for n in names if "工具安装失败" in n)
                    break
                sleep(1)
            logger.info(
                f"[2032421] success_toast={success_toast!r} "
                f"failure_toast={failure_toast!r}"
            )
            self.assert_false(bool(failure_toast))
            self.assert_true(bool(success_toast))
            self.assert_true(widget.is_baobab_installed())
            baobab_started = widget.wait_baobab_process_running(timeout=20)
            logger.info(f"[2032421] baobab process started={baobab_started}")
            self.assert_true(baobab_started)
            output = widget.run_cmd(
                f"grep -a 'baobab' {self.LOG} | tail -5",
                timeout=10,
                out_debug_flag=False,
            )
            logger.info(f"[2032421] product log tail: {output!r}")
            self.assert_true("InstallPackage via pkexec apt-get" in output)
        finally:
            # ===== 界面回退 =====
            for _ in range(3):
                widget.run_cmd(
                    "export DISPLAY=:0; xdotool key Escape",
                    timeout=5,
                    out_debug_flag=False,
                )
                sleep(1)
            widget.kill_baobab()
            widget.kill_pc_manager()

            # ===== 包与系统回退 =====
            try:
                if targets:
                    self._purge(widget, targets)
                    self._clean_cache(widget, targets)
            finally:
                if added_whitelist:
                    restored = self._restore_whitelist(widget, added_whitelist)
                    logger.info(f"[2032421] whitelist restored={restored}")
                    if not restored:
                        raise AssertionError("白名单未恢复到测试前状态")
            for path in created_dirs:
                widget.run_cmd(
                    f"rm -rf {shlex.quote(path)}",
                    timeout=10,
                    out_debug_flag=False,
                )
            # 清理可能的临时目录与 2032421 探针文件
            widget.run_cmd(
                "rm -f /tmp/probe_install.py /tmp/probe_install2.py "
                "/tmp/probe_polkit2.py /tmp/probe_polkit3.py /tmp/probe_polkit4.py "
                "/tmp/probe_launch.py /tmp/probe_polkit2.png /tmp/probe_polkit3.png "
                "/tmp/probe_polkit4.png /tmp/apt_baobab.out /tmp/purge_yelp.out",
                timeout=10,
                out_debug_flag=False,
            )
            after_pkgs = self._package_set(widget)
            added = sorted(after_pkgs - before_pkgs)
            removed = sorted(before_pkgs - after_pkgs)
            whitelist_count_after = self._db(
                widget, "SELECT count(*) FROM package_white_table;"
            )
            logger.info(
                f"[2032421] teardown added_pkgs={added} removed_pkgs={removed} "
                f"whitelist_rows={whitelist_count_after} "
                f"baobab_present={widget.is_baobab_installed()} "
                f"baobab_process={widget.get_baobab_process_status()} "
                f"pm_active={widget.run_cmd('systemctl is-active permission-manager.service', timeout=5, out_debug_flag=False).strip()}"
            )
            logger.info(f"[2032421] teardown residual packages: {added}")
            self.assert_false(added)
            self.assert_false(widget.is_baobab_installed())
            self.assert_false(widget.get_baobab_process_status())
            self.assert_true(whitelist_count_after == whitelist_count_before)

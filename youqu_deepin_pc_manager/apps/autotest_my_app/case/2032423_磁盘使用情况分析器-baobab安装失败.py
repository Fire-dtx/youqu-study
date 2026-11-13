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

    LOG = "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log"
    FAIL_CONF = "/etc/apt/apt.conf.d/99zz-dpm-case-fail"
    PROXY_CONF = "/etc/apt/apt.conf.d/99zz-dpm-case-offline"
    PIN_CONF = "/etc/apt/preferences.d/99zz-dpm-case-no-baobab.pref"
    TARGETS = [
        "baobab",
        "fonts-dejavu",
        "fonts-dejavu-extra",
        "libyelp0",
        "python3-distro",
        "yelp",
        "yelp-xsl",
    ]
    GENERIC = "工具安装失败"
    NETWORK = "网络连接失败，请切换网络后重试"
    UNSUPPORTED = "当前系统版本不支持该工具安装"

    def _sudo(self, widget, cmd: str, timeout=180):
        return widget.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S -p '' bash -c {shlex.quote(cmd)}",
            timeout=timeout,
            out_debug_flag=False,
        )

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

    def _find_button(self, name):
        for _app, role, text, el in self._all_nodes():
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

    def _toast_text(self):
        names = [name for _a, _r, name, _e in self._all_nodes() if name]
        for name in names:
            if self.GENERIC in name or self.NETWORK in name or self.UNSUPPORTED in name:
                return name
        return ""

    def _start_install(self, widget):
        """点击卡片→立即安装→按需输入密码, 返回是否出现鉴权框"""
        widget.click_disk_usage_analyzer_card()
        btn = self._wait_button("立即安装", timeout=15)
        self.assert_true(btn is not None)
        self.assert_true(self._click_center(widget, btn))

        auth_seen = False
        for _ in range(15):
            sleep(1)
            roles = [(app, name) for app, _r, name, _e in self._all_nodes()]
            if any(
                app == "dde-polkit-agent" and name == "Dialog_authdialog"
                for app, name in roles
            ):
                auth_seen = True
                break
            if any(
                app == "deepin-pc-manager" and name == "toolInstall_dialog"
                for app, name in roles
            ):
                break
        logger.info(f"[2032423] auth_seen={auth_seen}")
        if auth_seen:
            entry = confirm = None
            for _app, role, name, el in self._all_nodes():
                if role == "text" and name == "EditableText_passwordinput":
                    entry = el
                elif role == "push button" and name == "Btn_confirm":
                    confirm = el
            self.assert_true(entry is not None and confirm is not None)
            self.assert_true(self._click_center(widget, entry))
            sleep(1)
            widget.run_cmd(
                "export DISPLAY=:0; xdotool type --clearmodifiers "
                f"'{conf.PASSWORD}'",
                timeout=10,
                out_debug_flag=False,
            )
            sleep(1)
            widget.run_cmd(
                "export DISPLAY=:0; xdotool key --clearmodifiers Return",
                timeout=10,
                out_debug_flag=False,
            )
        return auth_seen

    def _wait_toast(self, widget, timeout=120):
        for _ in range(timeout):
            text = self._toast_text()
            if text:
                return text
            sleep(1)
        return ""

    def _package_set(self, widget):
        out = widget.run_cmd(
            "dpkg-query -W -f='${Package}\\n' 2>/dev/null | sort",
            timeout=30,
            out_debug_flag=False,
        )
        return set(x.strip() for x in out.splitlines() if x.strip())

    def _present(self, widget, names):
        out = widget.run_cmd(
            "for p in %s; do dpkg-query -W -f='${Package}\\n' \"$p\" "
            "2>/dev/null; done" % " ".join(names),
            timeout=30,
            out_debug_flag=False,
        )
        return [x.strip() for x in out.splitlines() if x.strip()]

    def _clean_cache(self, widget):
        self._sudo(
            widget,
            "rm -f " + " ".join(
                f"/var/cache/apt/archives/{p}_*.deb*" for p in self.TARGETS
            ) + " /var/cache/apt/archives/partial/*",
            timeout=30,
        )

    def _purge_extra(self, widget, names):
        """卸载测试过程中意外装入的包(如 dpkg 钩子部分执行)

        permission-manager 对未登记包拦截 dpkg 卸载, 临时停服务后清理,
        随后立即恢复, 与 2032421 相同的回退手法。
        """
        if not names:
            return
        self._sudo(
            widget,
            "systemctl mask --runtime permission-manager.service >/dev/null 2>&1 || true; "
            "systemctl stop permission-manager.service >/dev/null 2>&1 || true",
            timeout=30,
        )
        try:
            self._sudo(
                widget,
                "DEBIAN_FRONTEND=noninteractive apt-get purge -y "
                + " ".join(sorted(names)),
                timeout=300,
            )
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

    def _apply_fail_conf(self, widget):
        self._sudo(
            widget,
            "printf '%s\\n' "
            "'DPkg::Pre-Invoke { \"echo E: simulated dpkg failure; false; \"; };' "
            f"> {self.FAIL_CONF}",
            timeout=15,
        )
        ok = widget.run_cmd(
            f"test -s {self.FAIL_CONF} && echo ok || echo missing",
            timeout=5,
            out_debug_flag=False,
        ).strip()
        self.assert_true(ok == "ok")

    def test_mycase_260(self):
        """磁盘使用情况分析器-baobab安装失败

        预期(3 个失败场景, 均不自动拉起工具):
            1. 安装失败: toast【工具安装失败, 请稍后重试或联系…】
            2. 无网络: toast【网络连接失败, 请切换网络后重试】
            3. 版本/架构不支持: toast【当前系统版本不支持该工具安装】

        环境构造(可逆, 不改产品代码):
            1) 安装失败: apt 注入 DPkg::Pre-Invoke 失败脚本, 让真实
               pkexec apt-get 在解包前返回 100, 不落任何包。
            2) 无网络: 不改真实网络(会断 SSH), 向 apt 注入不可达代理
               127.0.0.1:9, 使下载阶段真实失败。
            3) 版本不支持: apt preferences 将 baobab Pin-Priority 置 -1,
               apt 输出「没有可安装候选 / no installation candidate」。
            每个场景均走真实界面与 polkit 鉴权, 记录实际 toast。

        回退: 删除 3 个注入配置、清理 apt 缓存、卸载意外新增包、杀进程,
              校验包集合无变化、无 baobab 包/进程、注入文件不存在。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.kill_baobab()
        before_pkgs = set()
        toasts = {}
        problems = []
        try:
            widget.run_cmd(
                "export DISPLAY=:0; xdotool key Escape",
                timeout=5,
                out_debug_flag=False,
            )
            self.assert_false(widget.is_baobab_installed())
            self.assert_false(widget.get_baobab_process_status())
            before_pkgs = self._package_set(widget)
            for path in (self.FAIL_CONF, self.PROXY_CONF, self.PIN_CONF):
                self._sudo(widget, f"rm -f {path}", timeout=15)
            self._clean_cache(widget)

            self.assert_true(widget.launch_app_from_launcher("电脑管家", wait=25))
            self.assert_true(widget.get_pc_manager_process_status())
            session_env = widget.run_cmd(
                "pid=$(pgrep -f '^/usr/libexec/deepin/deepin-pc-manager' | head -1); "
                "tr '\\0' '\\n' < /proc/$pid/environ | grep '^XDG_SESSION_ID='",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            logger.info(f"[2032423] app session env: {session_env!r}")
            self.assert_true("XDG_SESSION_ID=1" in session_env)
            widget.reconnect_dogtail()
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())

            # ===== 场景1: 安装过程报错 =====
            self._apply_fail_conf(widget)
            self._start_install(widget)
            toasts["install_error"] = self._wait_toast(widget, timeout=120)
            logger.info(f"[2032423] scenario1 toast={toasts['install_error']!r}")
            self._sudo(widget, f"rm -f {self.FAIL_CONF}", timeout=15)
            self._clean_cache(widget)
            sleep(2)
            self.assert_false(widget.is_baobab_installed())
            self.assert_false(widget.get_baobab_process_status())
            log1 = widget.run_cmd(
                f"grep -a 'Install failed for' {self.LOG} | tail -1",
                timeout=10,
                out_debug_flag=False,
            )
            logger.info(f"[2032423] scenario1 log={log1[-300:]!r}")
            self.assert_true("Install failed for" in log1)

            # ===== 场景2: 无网络 =====
            self._sudo(
                widget,
                "printf '%s\\n' "
                "'Acquire::http::Proxy \"http://127.0.0.1:9\";' "
                "'Acquire::https::Proxy \"http://127.0.0.1:9\";' "
                f"> {self.PROXY_CONF}",
                timeout=15,
            )
            ok = widget.run_cmd(
                f"test -s {self.PROXY_CONF} && echo ok || echo missing",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            self.assert_true(ok == "ok")
            self._start_install(widget)
            toasts["network"] = self._wait_toast(widget, timeout=120)
            logger.info(f"[2032423] scenario2 toast={toasts['network']!r}")
            self._sudo(widget, f"rm -f {self.PROXY_CONF}", timeout=15)
            self._clean_cache(widget)
            sleep(2)
            self.assert_false(widget.is_baobab_installed())
            self.assert_false(widget.get_baobab_process_status())
            net_log = widget.run_cmd(
                f"grep -a 'Install failed for' {self.LOG} | tail -1",
                timeout=10,
                out_debug_flag=False,
            )
            logger.info(f"[2032423] scenario2 log={net_log[-300:]!r}")

            # ===== 场景3: 仓库无可用候选(版本/架构不支持)=====
            self._sudo(
                widget,
                "printf '%s\\n' "
                "'Package: baobab' 'Pin: release *' 'Pin-Priority: -1' "
                f"> {self.PIN_CONF}",
                timeout=15,
            )
            sim = widget.run_cmd(
                "apt-get -s install -y baobab 2>&1 | tail -3",
                timeout=60,
                out_debug_flag=False,
            )
            logger.info(f"[2032423] scenario3 pin sim={sim!r}")
            self.assert_true(
                "no installation candidate" in sim or "没有可安装候选" in sim
            )
            self._start_install(widget)
            toasts["unsupported"] = self._wait_toast(widget, timeout=120)
            logger.info(f"[2032423] scenario3 toast={toasts['unsupported']!r}")
            sleep(2)
            self.assert_false(widget.is_baobab_installed())
            self.assert_false(widget.get_baobab_process_status())

            # ===== 汇总断言(三个场景都跑完再判定)=====
            if not toasts.get("install_error", "").startswith(self.GENERIC):
                problems.append(f"场景1 toast={toasts.get('install_error')!r}")
            if toasts.get("network") != self.NETWORK:
                problems.append(f"场景2 toast={toasts.get('network')!r}")
            if toasts.get("unsupported") != self.UNSUPPORTED:
                problems.append(f"场景3 toast={toasts.get('unsupported')!r}")
            logger.info(f"[2032423] toast problems={problems}")
            self.assert_false(bool(problems))
        finally:
            for _ in range(3):
                widget.run_cmd(
                    "export DISPLAY=:0; xdotool key Escape",
                    timeout=5,
                    out_debug_flag=False,
                )
                sleep(1)
            widget.kill_baobab()
            widget.kill_pc_manager()
            self._sudo(
                widget,
                f"rm -f {self.FAIL_CONF} {self.PROXY_CONF} {self.PIN_CONF}",
                timeout=15,
            )
            self._clean_cache(widget)
            after_pkgs = self._package_set(widget)
            extras = [p for p in self.TARGETS if p in after_pkgs and p not in before_pkgs]
            if extras:
                self._purge_extra(widget, extras)
                self._clean_cache(widget)
            after_pkgs = self._package_set(widget)
            added = sorted(after_pkgs - before_pkgs)
            removed = sorted(before_pkgs - after_pkgs)
            left = widget.run_cmd(
                f"test -e {self.FAIL_CONF} && echo fail_left; "
                f"test -e {self.PROXY_CONF} && echo proxy_left; "
                f"test -e {self.PIN_CONF} && echo pin_left; true",
                timeout=10,
                out_debug_flag=False,
            )
            audit = widget.run_cmd(
                "dpkg --audit 2>&1 | tail -3",
                timeout=30,
                out_debug_flag=False,
            )
            logger.info(
                f"[2032423] teardown conf_left={left!r} added={added} "
                f"removed={removed} audit={audit!r} "
                f"baobab_present={widget.is_baobab_installed()} "
                f"baobab_process={widget.get_baobab_process_status()}"
            )
            self.assert_false("left" in left)
            self.assert_false(added)
            self.assert_false(removed)
            self.assert_false(widget.is_baobab_installed())
            self.assert_false(widget.get_baobab_process_status())

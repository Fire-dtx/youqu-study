#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
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
    MAX_MS = 200

    def _sudo(self, widget, cmd: str, timeout=300):
        return widget.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S -p '' bash -c {shlex.quote(cmd)}",
            timeout=timeout,
            out_debug_flag=False,
        )

    def _db(self, widget, sql: str):
        out = self._sudo(widget, f"sqlite3 {self.DB} {shlex.quote(sql)}")
        lines = []
        for line in out.splitlines():
            line = line.replace("请输入密码", "").replace("验证成功", "").strip()
            if line:
                lines.append(line)
        return "\n".join(lines)

    def _now_ms(self, widget) -> int:
        out = widget.run_cmd(
            "date +%s%3N", timeout=5, out_debug_flag=False
        ).strip()
        return int(out.splitlines()[-1])

    def _targets(self, widget):
        out = widget.run_cmd(
            "apt-get -s install -y baobab 2>/dev/null | "
            "sed -n 's/^Inst \\([^ ]*\\).*/\\1/p'",
            timeout=60,
            out_debug_flag=False,
        )
        return [x.strip().split(":")[0] for x in out.splitlines() if x.strip()]

    def _install(self, widget, targets):
        before = set(
            x for x in self._db(
                widget,
                "SELECT pkgname FROM package_white_table WHERE pkgname IN (%s);"
                % ",".join("'%s'" % p for p in targets),
            ).splitlines()
            if x
        )
        added = [p for p in targets if p not in before]
        if added:
            self._db(
                widget,
                ";".join(
                    "INSERT OR IGNORE INTO package_white_table(pkgname,type) "
                    "VALUES ('%s','default')" % p
                    for p in added
                )
                + ";",
            )
        out = self._sudo(
            widget,
            "DEBIAN_FRONTEND=noninteractive apt-get install -y baobab",
        )
        logger.info(f"[2032425] install output tail: {out[-300:]!r}")
        self.assert_true(widget.is_baobab_installed())
        return added

    def _purge(self, widget, names):
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

    def _clean_cache(self, widget, names):
        self._sudo(
            widget,
            "rm -f " + " ".join(
                f"/var/cache/apt/archives/{p}_*.deb*" for p in names
            ) + " /var/cache/apt/archives/partial/*",
            timeout=30,
        )

    def test_mycase_261(self):
        """磁盘使用情况分析器-baobab打开

        步骤: 单击「磁盘使用情况分析器」卡片, 测响应耗时。
        预期: < 200ms 拉起独立进程。

        实现:
            - baobab 未安装时先用 apt 装入(测试数据构造), 结束时精确卸载;
              原本已安装则保持不动。
            - 点击前启动 5ms 粒度的进程监听, 用 AT-SPI Press 触发卡片,
              记录「动作发起→baobab 进程出现」的毫秒差。
            - 额外断言 baobab 是独立进程(PPID 不是电脑管家主进程),
              且实用工具页面保持正常。

        回退: 杀 baobab/电脑管家/监听进程, 删除临时文件; 若本次安装过
              baobab, 临时停 permission-manager 卸载并恢复, 校验包集合
              与白名单行数还原。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.kill_baobab()
        installed_by_case = False
        targets = []
        added_whitelist = []
        before_pkgs = set()
        wl_before = ""
        try:
            before_pkgs = set(
                x.strip()
                for x in widget.run_cmd(
                    "dpkg-query -W -f='${Package}\\n' 2>/dev/null | sort",
                    timeout=30,
                    out_debug_flag=False,
                ).splitlines()
                if x.strip()
            )
            wl_before = self._db(widget, "SELECT count(*) FROM package_white_table;")
            if not widget.is_baobab_installed():
                targets = self._targets(widget)
                logger.info(f"[2032425] install targets={targets}")
                self.assert_true(self.PKG in targets)
                added_whitelist = self._install(widget, targets)
                installed_by_case = True

            self.assert_true(widget.is_baobab_installed())
            self.assert_false(widget.get_baobab_process_status())
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())
            self.assert_true(widget.get_utility_cards_view_showing())

            card = widget.dog.find_element_by_attr(
                "$//utility_sectionsContainer//磁盘使用情况分析器"
            )
            self.assert_true(card.showing)

            # 5ms 粒度监听进程出现时刻
            widget.run_cmd(
                "rm -f /tmp/baobab_start_ms /tmp/baobab_watch.pid; "
                "setsid bash -c 'echo $$ >/tmp/baobab_watch.pid; "
                "while ! pgrep -x baobab >/dev/null; do sleep 0.005; done; "
                "date +%s%3N' >/tmp/baobab_start_ms 2>&1 </dev/null &",
                timeout=10,
                out_debug_flag=False,
            )
            sleep(1)
            watch_pid = widget.run_cmd(
                "cat /tmp/baobab_watch.pid", timeout=5, out_debug_flag=False
            ).strip()
            self.assert_true(bool(watch_pid))

            t0 = self._now_ms(widget)
            self.assert_true(widget._atspi_do_action(card))
            t1 = self._now_ms(widget)

            found = ""
            for _ in range(100):
                found = widget.run_cmd(
                    "cat /tmp/baobab_start_ms 2>/dev/null",
                    timeout=5,
                    out_debug_flag=False,
                ).strip()
                if found:
                    break
                sleep(0.05)
            logger.info(f"[2032425] t0={t0} action_return={t1} found={found!r}")
            self.assert_true(bool(found))
            latency = int(found) - t0
            logger.info(
                f"[2032425] launch latency={latency}ms "
                f"action_rpc={t1 - t0}ms"
            )

            self.assert_true(widget.get_baobab_process_status())
            app_pid = widget.run_cmd(
                "pgrep -f '^/usr/libexec/deepin/deepin-pc-manager' | head -1",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            bb_pid = widget.run_cmd(
                "pgrep -x baobab | head -1", timeout=5, out_debug_flag=False
            ).strip()
            bb_ppid = widget.run_cmd(
                f"ps -o ppid= -p {bb_pid}", timeout=5, out_debug_flag=False
            ).strip()
            bb_exe = widget.run_cmd(
                f"readlink -f /proc/{bb_pid}/exe", timeout=5, out_debug_flag=False
            ).strip()
            logger.info(
                f"[2032425] app_pid={app_pid} baobab_pid={bb_pid} "
                f"ppid={bb_ppid} exe={bb_exe}"
            )
            self.assert_true(bb_ppid != app_pid)
            self.assert_true(bb_exe.endswith("/baobab"))
            self.assert_true(latency < self.MAX_MS)
            self.assert_true(widget.get_utility_page_showing())
        finally:
            widget.kill_baobab()
            widget.kill_pc_manager()
            widget.run_cmd(
                "test -f /tmp/baobab_watch.pid && kill $(cat /tmp/baobab_watch.pid) "
                "2>/dev/null; rm -f /tmp/baobab_start_ms /tmp/baobab_watch.pid",
                timeout=10,
                out_debug_flag=False,
            )
            if installed_by_case and targets:
                self._purge(widget, targets)
                self._clean_cache(widget, targets)
                if added_whitelist:
                    self._db(
                        widget,
                        "DELETE FROM package_white_table WHERE pkgname IN (%s);"
                        % ",".join("'%s'" % p for p in added_whitelist),
                    )
            after_pkgs = set(
                x.strip()
                for x in widget.run_cmd(
                    "dpkg-query -W -f='${Package}\\n' 2>/dev/null | sort",
                    timeout=30,
                    out_debug_flag=False,
                ).splitlines()
                if x.strip()
            )
            wl_after = self._db(widget, "SELECT count(*) FROM package_white_table;")
            added = sorted(after_pkgs - before_pkgs)
            removed = sorted(before_pkgs - after_pkgs)
            logger.info(
                f"[2032425] teardown added={added} removed={removed} "
                f"whitelist={wl_before}->{wl_after} "
                f"baobab_present={widget.is_baobab_installed()} "
                f"baobab_process={widget.get_baobab_process_status()}"
            )
            self.assert_false(added)
            self.assert_false(removed)
            self.assert_true(wl_after == wl_before)
            if installed_by_case:
                self.assert_false(widget.is_baobab_installed())
            self.assert_false(widget.get_baobab_process_status())

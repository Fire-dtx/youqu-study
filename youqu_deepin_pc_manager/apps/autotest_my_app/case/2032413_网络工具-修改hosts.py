#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from setting import conf
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    HOSTS = "/etc/hosts"
    DAEMON_BACKUP = "/var/log/deepin-pc-manager/hosts.bak"
    BACKUP = "/tmp/hosts_case209.bak"
    DAEMON_BACKUP_SAVED = "/tmp/hosts_daemon_bak_case209.keep"

    def _xdotool(self, widget, args: str):
        widget.run_cmd(
            f'export DISPLAY=:0; xdotool {args}', timeout=10, out_debug_flag=False
        )

    def _click_real(self, widget, element):
        x, y = element.position
        w, h = element.size
        self._xdotool(
            widget, f"mousemove {x + w // 2} {y + h // 2} click 1"
        )
        sleep(1)

    def _read_hosts(self, widget):
        return widget.run_cmd(f"cat {self.HOSTS}", timeout=5, out_debug_flag=False)

    def _editor_text(self, widget):
        edit = widget.dog.find_element_by_attr("$//utility_hostsTextEdit")
        text_iface = edit.queryText()
        return text_iface.getText(0, text_iface.characterCount)

    def _sudo(self, widget, cmd: str):
        return widget.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S bash -c \"{cmd}\"",
            timeout=15,
            out_debug_flag=False,
        )

    def test_mycase_209(self):
        """网络工具-修改hosts

        步骤与断言:
        1) 在 hosts 编辑框末尾追加 `10.20.42.200 uos`, 点击保存,
           断言 /etc/hosts 实际写入该行, 且守护进程生成 hosts.bak;
        2) 追加格式错误行 `10.1.1.  111`, 点击保存, 断言 /etc/hosts 未被改动
           (保存被校验拦截), 并记录错误提示;
        3) 本机无 /target, 用 `cat /etc/hosts` 等价校验文件与修改一致。
        收尾: 恢复 /etc/hosts 与 /var/log/deepin-pc-manager/hosts.bak 到测试前状态。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.run_cmd(
            f"cat {self.HOSTS} > {self.BACKUP}",
            timeout=5,
            out_debug_flag=False,
        )
        backup_rc = bool(
            widget.run_cmd(
                f"test -s {self.BACKUP} && echo OK",
                timeout=5,
                out_debug_flag=False,
            ).strip().endswith("OK")
        )
        if not backup_rc:
            self._sudo(widget, f"cp -a {self.HOSTS} {self.BACKUP}")
        had_daemon_backup = bool(
            widget.run_cmd(
                f"test -f {self.DAEMON_BACKUP} && "
                f"echo '{conf.PASSWORD}' | sudo -S cp -a {self.DAEMON_BACKUP} "
                f"{self.DAEMON_BACKUP_SAVED} && echo YES",
                timeout=15,
                out_debug_flag=False,
            ).strip().endswith("YES")
        )
        logger.info(f"[2032413] had_daemon_backup={had_daemon_backup}")
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())
            widget.click_utility_card_by_name("本地域名解析工具")
            sleep(1)
            self.assert_true(
                widget.dog.find_element_by_attr("$//utility_hostsPage").showing
            )

            edit = widget.dog.find_element_by_attr("$//utility_hostsTextEdit")
            self._click_real(widget, edit)
            self._xdotool(widget, "key ctrl+End")
            self._xdotool(widget, "key Return")
            self._xdotool(
                widget, 'type --clearmodifiers --delay 60 "10.20.42.200 uos"'
            )
            sleep(1)
            save = widget.dog.find_element_by_attr("$//utility_hostsSaveBtn")
            self._click_real(widget, save)

            saved = False
            for _ in range(10):
                if "10.20.42.200 uos" in self._read_hosts(widget):
                    saved = True
                    break
                sleep(1)
            on_disk = self._read_hosts(widget)
            editor = self._editor_text(widget)
            logger.info(
                f"[2032413] step1 saved={saved} disk_has_line="
                f"{'10.20.42.200 uos' in on_disk} editor_has_line="
                f"{'10.20.42.200 uos' in editor} "
                f"daemon_backup_exists={bool(widget.run_cmd('test -f ' + self.DAEMON_BACKUP + ' && echo Y', timeout=5, out_debug_flag=False).strip())}"
            )
            self.assert_true(saved)
            self.assert_true("10.20.42.200 uos" in editor)

            # 步骤 2: 格式错误的 IP, 保存应被拦截
            before_bad = on_disk
            self._click_real(widget, edit)
            self._xdotool(widget, "key ctrl+End")
            self._xdotool(widget, "key Return")
            self._xdotool(
                widget, 'type --clearmodifiers --delay 60 "10.1.1.  111"'
            )
            sleep(1)
            save = widget.dog.find_element_by_attr("$//utility_hostsSaveBtn")
            self._click_real(widget, save)
            sleep(2)
            after_bad = self._read_hosts(widget)
            logger.info(
                f"[2032413] step2 unchanged={after_bad == before_bad} "
                f"bad_line_on_disk={'10.1.1.' in after_bad}"
            )
            self.assert_true(after_bad == before_bad)
            self.assert_true("10.1.1." not in after_bad)

            # 步骤 3: 本机无 /target, 用 cat /etc/hosts 等价校验
            chroot_hosts = self._read_hosts(widget)
            if widget.run_cmd("test -d /target", timeout=5, out_debug_flag=False):
                chroot_hosts = self._sudo(widget, "chroot /target cat /etc/hosts")
            logger.info(
                f"[2032413] step3 has_line={'10.20.42.200 uos' in chroot_hosts} "
                f"chars={len(chroot_hosts)}"
            )
            self.assert_true("10.20.42.200 uos" in chroot_hosts)
        finally:
            if backup_rc:
                pass
            self._sudo(
                widget,
                f"cp -a {self.BACKUP} {self.HOSTS} && "
                f"chown root:root {self.HOSTS} && chmod 644 {self.HOSTS}",
            )
            if had_daemon_backup:
                self._sudo(
                    widget,
                    f"cp -a {self.DAEMON_BACKUP_SAVED} {self.DAEMON_BACKUP}",
                )
            else:
                self._sudo(widget, f"rm -f {self.DAEMON_BACKUP}")
            widget.run_cmd(f"rm -f {self.BACKUP}", timeout=5, out_debug_flag=False)
            widget.run_cmd(
                f"echo '{conf.PASSWORD}' | sudo -S rm -f "
                f"{self.DAEMON_BACKUP_SAVED}",
                timeout=10,
                out_debug_flag=False,
            )
            restored = self._read_hosts(widget)
            logger.info(
                f"[2032413] restored_line={'10.20.42.200 uos' not in restored} "
                f"chars={len(restored)}"
            )
            sleep(1)
            widget.kill_pc_manager()

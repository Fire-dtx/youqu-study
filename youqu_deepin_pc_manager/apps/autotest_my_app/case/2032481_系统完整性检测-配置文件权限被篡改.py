#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import re
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    TARGET_FILE = "/usr/bin/systemd"
    REAL_FILE = "/lib/systemd/systemd"

    def _mode_of(self, path):
        return self.widget.run_cmd(
            f"stat -c %a {path} 2>/dev/null", timeout=10, out_debug_flag=False,
        ).strip()

    def _verify_systemd(self):
        return self.widget.run_cmd(
            "dpkg -V systemd 2>/dev/null | grep -a 'systemd/systemd' ; true",
            timeout=20, out_debug_flag=False,
        ).strip()

    def _core_package_logs(self, since):
        return self.widget.sudo_run_cmd(
            f"journalctl -u deepin-pc-manager-daemon --since '{since}' "
            "| grep -a 'detectCorePackages'",
            timeout=30, out_debug_flag=False,
        )

    def test_mycase_114(self):
        """系统完整性检测-配置文件权限被篡改：修改 systemd 可执行文件权限后检测仍 PASS

        步骤: 1. chmod 修改 /usr/bin/systemd(指向 /lib/systemd/systemd)的权限;
        2. 执行系统环境检测(系统完整性检测)。
        预期: 检测项 PASS -- 仅权限变化不构成核心包内容损坏, 产品校验结果为
        缺失 0、损坏 0; 用例结束前恢复原始权限。
        说明: 原文件权限已是 755, 按用例描述 chmod 755 不产生任何变化,
        等价实现改为 700(权限确实被篡改且 dpkg 校验可见差异), 检测后恢复。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        mode_before = self._mode_of(self.REAL_FILE)
        verify_before = self._verify_systemd()
        logger.info(f"[2032481] mode_before={mode_before} verify_before={verify_before[:80]}")
        try:
            self.assert_true(
                widget.sudo_run_cmd(
                    f"chmod 700 {self.TARGET_FILE}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            mode_tampered = self._mode_of(self.REAL_FILE)
            verify_tampered = self._verify_systemd()
            logger.info(
                f"[2032481] mode_tampered={mode_tampered} "
                f"verify_tampered={verify_tampered[:100]}"
            )
            self.assert_true(mode_tampered == "700")
            self.assert_true(self.REAL_FILE in verify_tampered)

            since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            self.assert_true(widget.get_detection_item_present("系统环境检测", "核心包检查"))
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032481] core_packages verdict={ok} detail={detail}")
            self.assert_true(ok is True)

            logs = self._core_package_logs(since)
            self.assert_true(
                re.search(r"verifying\s+(\d+)\s+core packages", logs) is not None
            )
            self.assert_true("completed, missing: 0 corrupted: 0" in logs)
        finally:
            widget.sudo_run_cmd(
                f"chmod {mode_before or '755'} {self.TARGET_FILE}",
                timeout=10, out_debug_flag=False,
            )
            mode_restored = self._mode_of(self.REAL_FILE)
            verify_restored = self._verify_systemd()
            logger.info(
                f"[2032481] mode_restored={mode_restored} "
                f"verify_restored={verify_restored[:100]}"
            )
            self.assert_true(mode_restored == mode_before)
            self.assert_true(verify_restored == verify_before)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

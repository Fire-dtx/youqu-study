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

    CONFIG_FILE = "/etc/lightdm/lightdm.conf"
    BACKUP_FILE = "/tmp/lightdm_conf_backup_2032479"

    def _dpkg_verify_lightdm(self):
        return self.widget.run_cmd(
            "dpkg -V lightdm 2>&1; true", timeout=15, out_debug_flag=False,
        )

    def _config_md5(self):
        return self.widget.run_cmd(
            f"md5sum {self.CONFIG_FILE} 2>/dev/null | awk '{{print $1}}'",
            timeout=10, out_debug_flag=False,
        ).strip()

    def _core_package_logs(self, since):
        return self.widget.sudo_run_cmd(
            f"journalctl -u deepin-pc-manager-daemon --since '{since}' "
            "| grep -a 'detectCorePackages'",
            timeout=30, out_debug_flag=False,
        )

    def test_mycase_113(self):
        """系统完整性检测-配置文件被篡改：篡改 lightdm 配置文件后系统完整性检测仍 PASS

        步骤: 1. 向 /etc/lightdm/lightdm.conf 追加篡改内容(先备份);
        2. 执行系统环境检测(系统完整性检测)。
        预期: 检测项 PASS -- 产品对 conffile(配置文件)内容变更按设计忽略,
        dpkg 校验缺失 0、损坏 0, 核心包检查结论为通过; 用例结束前原样恢复配置。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        verify_before = self._dpkg_verify_lightdm()
        md5_before = self._config_md5()
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            self.assert_true(
                widget.sudo_run_cmd(
                    f"cp {self.CONFIG_FILE} {self.BACKUP_FILE}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            self.assert_true(
                widget.sudo_run_cmd(
                    f"bash -c 'echo \"# TAMPERED_BY_AUTOTEST_2032479\" >> {self.CONFIG_FILE}'",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            # 篡改生效: 配置文件内容 md5 与篡改前不同, 且 dpkg 校验识别为配置文件差异行
            md5_tampered = self._config_md5()
            verify_after = self._dpkg_verify_lightdm()
            logger.info(
                f"[2032479] md5_before={md5_before} md5_tampered={md5_tampered} "
                f"dpkg_verify_tampered={verify_after.strip()[:120]}"
            )
            self.assert_true(md5_before and md5_tampered and md5_before != md5_tampered)
            self.assert_true(self.CONFIG_FILE in verify_after)
            self.assert_true(" c " in verify_after)

            since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            self.assert_true(widget.get_detection_item_present("系统环境检测", "核心包检查"))
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032479] core_packages verdict={ok} detail={detail}")
            self.assert_true(ok is True)

            logs = self._core_package_logs(since)
            matched = re.search(r"verifying\s+(\d+)\s+core packages", logs)
            self.assert_true(matched is not None)
            self.assert_true("completed, missing: 0 corrupted: 0" in logs)
        finally:
            widget.sudo_run_cmd(
                f"cp {self.BACKUP_FILE} {self.CONFIG_FILE}",
                timeout=10, out_debug_flag=False,
            )
            widget.sudo_run_cmd(
                f"rm -f {self.BACKUP_FILE}", timeout=5, out_debug_flag=False,
            )
            widget.remove_test_junk_files()
            widget.kill_pc_manager()
            verify_restored = self._dpkg_verify_lightdm()
            md5_restored = self._config_md5()
            logger.info(
                f"[2032479] dpkg_verify_restored={verify_restored.strip()[:120]} "
                f"md5_restored={md5_restored}"
            )
            self.assert_true(md5_restored == md5_before)
            self.assert_true(verify_restored.strip() == verify_before.strip())


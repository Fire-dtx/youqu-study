#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    TARGET = "/usr/bin/sudoreplay"
    PACKAGE = "sudo"
    BACKUP = "/tmp/sudoreplay_perm_backup_2032491"

    def _md5(self, path):
        return self.widget.run_cmd(
            f"md5sum {path} 2>/dev/null | awk '{{print $1}}'",
            timeout=10, out_debug_flag=False,
        ).strip()

    def _size(self, path):
        return self.widget.run_cmd(
            f"stat -c %s {path} 2>/dev/null", timeout=10, out_debug_flag=False,
        ).strip()

    def _verify_package(self):
        out = self.widget.sudo_run_cmd(
            f"dpkg --verify {self.PACKAGE} 2>/dev/null; true",
            timeout=30, out_debug_flag=False,
        )
        return "\n".join(line for line in out.splitlines() if self.TARGET in line).strip()

    def test_mycase_119(self):
        """系统完整性检测-非配置文件权限被篡改：二进制文件被空文件替换后检测仍通过

        步骤: 1. 备份核心包 sudo 的二进制文件后, 用空文件替换
        /usr/bin/sudoreplay(对应用例中 cp 备份 + touch 覆盖);
        2. 执行系统环境检测(系统完整性检测)。
        预期: 检测通过 -- dpkg 校验虽报该文件 md5 差异, 但内容已不含二进制特征,
        产品按设计跳过非二进制文件(避免 OEM 定制误报), 核心包检查结论仍为通过;
        校验记录"non-binary file skipped", 用例结束前恢复原文件。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        md5_before = self._md5(self.TARGET)
        verify_before = self._verify_package()
        logger.info(f"[2032491] md5_before={md5_before} verify_before={verify_before!r}")
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            self.assert_true(bool(md5_before))
            self.assert_true(verify_before == "")
            self.assert_true(
                widget.sudo_run_cmd(
                    f"cp {self.TARGET} {self.BACKUP}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            self.assert_true(
                widget.sudo_run_cmd(
                    f"bash -c ': > {self.TARGET}'",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            size_after = self._size(self.TARGET)
            verify_tampered = self._verify_package()
            logger.info(
                f"[2032491] size_after={size_after} verify_tampered={verify_tampered!r}"
            )
            self.assert_true(size_after == "0")
            self.assert_true(self.TARGET in verify_tampered)

            since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032491] verdict={ok} detail={detail}")
            self.assert_true(ok is True)

            logs = widget.sudo_run_cmd(
                f"journalctl -u deepin-pc-manager-daemon --since '{since}' "
                "| grep -a 'detectCorePackages'",
                timeout=30, out_debug_flag=False,
            )
            logger.info(f"[2032491] skipped_log={'non-binary file skipped' in logs}")
            self.assert_true("completed, missing: 0 corrupted: 0" in logs)
            self.assert_true(f'non-binary file skipped: "{self.TARGET}"' in logs)
        finally:
            widget.sudo_run_cmd(
                f"[ -f {self.BACKUP} ] && cp {self.BACKUP} {self.TARGET} "
                f"&& chmod 755 {self.TARGET}; rm -f {self.BACKUP}",
                timeout=15, out_debug_flag=False,
            )
            md5_restored = self._md5(self.TARGET)
            verify_restored = self._verify_package()
            logger.info(
                f"[2032491] md5_restored={md5_restored} verify_restored={verify_restored!r}"
            )
            self.assert_true(md5_restored == md5_before)
            self.assert_true(verify_restored == "")
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

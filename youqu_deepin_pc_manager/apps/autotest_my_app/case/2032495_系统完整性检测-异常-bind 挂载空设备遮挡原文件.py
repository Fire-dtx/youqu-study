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

    def _md5(self, path):
        return self.widget.run_cmd(
            f"md5sum {path} 2>/dev/null | awk '{{print $1}}'",
            timeout=10, out_debug_flag=False,
        ).strip()

    def _verify_package(self):
        out = self.widget.sudo_run_cmd(
            f"dpkg --verify {self.PACKAGE} 2>/dev/null; true",
            timeout=30, out_debug_flag=False,
        )
        return "\n".join(line for line in out.splitlines() if self.TARGET in line).strip()

    def _is_mounted(self):
        rc = self.widget.run_cmd(
            f"mountpoint -q {self.TARGET} && echo mounted || echo clean",
            timeout=10, out_debug_flag=False,
        ).strip()
        return rc == "mounted"

    def test_mycase_121(self):
        """系统完整性检测-bind 挂载空设备遮挡原文件：检测仍通过

        步骤: 1. 用 sudo mount --bind /dev/null 遮挡核心包 sudo 的文件
        /usr/bin/sudoreplay(对应用例中 bind /dev/null /etc/profile),
        再用 dpkg --verify 确认校验异常;
        2. 执行系统环境检测(系统完整性检测)。
        预期: 检测通过 -- 被遮挡后文件内容为空, 不具备二进制特征,
        产品按设计跳过非二进制文件, 核心包检查结论仍为通过;
        用例结束前卸载挂载并确认文件内容复原。
        说明: 用例脚本使用 /etc/profile(不属于产品核心包清单), 等价改用清单内
        核心包 sudo 的二进制文件, 使其真正参与本次检测。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        md5_before = self._md5(self.TARGET)
        verify_before = self._verify_package()
        logger.info(f"[2032495] md5_before={md5_before} verify_before={verify_before!r}")
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            self.assert_true(bool(md5_before))
            self.assert_true(verify_before == "")
            rc = widget.sudo_run_cmd(
                f"mount --bind /dev/null {self.TARGET}",
                timeout=15, out_debug_flag=False, return_code=True,
            )[1]
            self.assert_true(rc == 0)
            time.sleep(1)
            self.assert_true(self._is_mounted())
            md5_masked = self._md5(self.TARGET)
            verify_masked = self._verify_package()
            logger.info(f"[2032495] md5_masked={md5_masked!r} verify_masked={verify_masked!r}")
            self.assert_true(md5_masked != md5_before)
            self.assert_true(self.TARGET in verify_masked)

            since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032495] verdict={ok} detail={detail}")
            self.assert_true(ok is True)
            logs = widget.sudo_run_cmd(
                f"journalctl -u deepin-pc-manager-daemon --since '{since}' "
                "| grep -a 'detectCorePackages'",
                timeout=30, out_debug_flag=False,
            )
            logger.info(f"[2032495] skipped_log={'non-binary file skipped' in logs}")
            self.assert_true(f'non-binary file skipped: "{self.TARGET}"' in logs)
        finally:
            if self._is_mounted():
                widget.sudo_run_cmd(
                    f"umount {self.TARGET} || umount -l {self.TARGET}",
                    timeout=20, out_debug_flag=False,
                )
            self.assert_true(not self._is_mounted())
            md5_restored = self._md5(self.TARGET)
            verify_restored = self._verify_package()
            logger.info(
                f"[2032495] md5_restored={md5_restored} verify_restored={verify_restored!r}"
            )
            self.assert_true(md5_restored == md5_before)
            self.assert_true(verify_restored == "")
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

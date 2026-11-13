#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    TARGET = "/etc/systemd/journald.conf"
    PACKAGE = "systemd"
    BACKUP = "/tmp/journald_conf_backup_2032493"

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
        return "\n".join(
            line for line in out.splitlines() if "journald.conf" in line
        ).strip()

    def test_mycase_120(self):
        """系统完整性检测-损坏悬空软链接替换原文件：检测仍通过

        步骤: 1. 备份核心包 systemd 的配置文件后, 用无效软链接替换
        /etc/systemd/journald.conf(对应用例中 cp 备份 + ln -sf /nonexistfile);
        2. 执行系统环境检测(系统完整性检测)。
        预期: 检测通过 -- dpkg 校验将该文件判定为 conffile(输出含 c 标记),
        产品按设计忽略配置文件差异, 核心包检查结论仍为通过;
        用例结束前删除软链接并恢复原文件。
        说明: 用例脚本以 /etc/profile 为例(不属于产品核心包清单), 等价改用
        核心包清单内 systemd 的配置文件, 使其真正参与本次检测。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        verify_baseline = self._verify_package()
        md5_before = self._md5(self.TARGET)
        logger.info(
            f"[2032493] md5_before={md5_before} verify_baseline={verify_baseline!r}"
        )
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            self.assert_true(bool(md5_before))
            self.assert_true(
                widget.sudo_run_cmd(
                    f"cp {self.TARGET} {self.BACKUP}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            rc = widget.sudo_run_cmd(
                f"bash -c 'rm -f {self.TARGET} && ln -s /nonexistfile_2032493 {self.TARGET}'",
                timeout=10, out_debug_flag=False, return_code=True,
            )[1]
            self.assert_true(rc == 0)
            link_target = widget.run_cmd(
                f"readlink {self.TARGET} 2>/dev/null", timeout=10, out_debug_flag=False,
            ).strip()
            verify_tampered = self._verify_package()
            logger.info(
                f"[2032493] link_target={link_target} verify_tampered={verify_tampered!r}"
            )
            self.assert_true(link_target == "/nonexistfile_2032493")
            self.assert_true(self.TARGET in verify_tampered)
            self.assert_true(" c " in verify_tampered)

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032493] verdict={ok} detail={detail}")
            self.assert_true(ok is True)
        finally:
            widget.sudo_run_cmd(
                f"bash -c 'rm -f {self.TARGET} && [ -f {self.BACKUP} ] && "
                f"cp {self.BACKUP} {self.TARGET}; rm -f {self.BACKUP}'",
                timeout=15, out_debug_flag=False,
            )
            md5_restored = self._md5(self.TARGET)
            verify_restored = self._verify_package()
            logger.info(
                f"[2032493] md5_restored={md5_restored} verify_restored={verify_restored!r}"
            )
            self.assert_true(md5_restored == md5_before)
            self.assert_true(verify_restored == verify_baseline)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

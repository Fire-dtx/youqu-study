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

    TARGET = "/usr/bin/sudoreplay"
    PACKAGE = "sudo"
    BACKUP = "/tmp/sudoreplay_backup_2032487"

    def _md5(self, path):
        return self.widget.run_cmd(
            f"md5sum {path} 2>/dev/null | awk '{{print $1}}'",
            timeout=10, out_debug_flag=False,
        ).strip()

    def _verify_package(self):
        """以 root 执行 dpkg --verify, 返回与篡改目标文件相关的行"""
        out = self.widget.sudo_run_cmd(
            f"dpkg --verify {self.PACKAGE} 2>/dev/null; true",
            timeout=30, out_debug_flag=False,
        )
        return "\n".join(
            line for line in out.splitlines() if self.TARGET in line
        ).strip()

    def test_mycase_117(self):
        """系统完整性检测-非配置文件内容被 dd 篡改：检测失败并给出具体篡改信息

        步骤: 1. 对核心包 sudo 的非配置文件 /usr/bin/sudoreplay 执行
        dd 篡改前 20 字节(先备份原文件);
        2. 执行系统环境检测(系统完整性检测)。
        预期: 检测失败 -- dpkg --verify 报 md5 校验失败(无 c 标记, 非配置文件),
        核心包检查项输出包名 sudo 与文件路径 /usr/bin/sudoreplay;
        用例结束前恢复原文件并确认再次检测通过。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        md5_before = self._md5(self.TARGET)
        verify_before = self._verify_package()
        logger.info(f"[2032487] md5_before={md5_before} verify_before={verify_before[:80]!r}")
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
                    f"dd if=/dev/zero of={self.TARGET} bs=1 count=20 conv=notrunc",
                    timeout=15, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            md5_tampered = self._md5(self.TARGET)
            verify_tampered = self._verify_package()
            logger.info(
                f"[2032487] md5_tampered={md5_tampered} verify_tampered={verify_tampered!r}"
            )
            self.assert_true(md5_tampered != md5_before)
            self.assert_true(self.TARGET in verify_tampered)
            self.assert_true(" c " not in verify_tampered)

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            state = widget.get_detection_group_state("系统环境检测")
            logger.info(f"[2032487] group_state={state}")
            self.assert_true(state["issues"] >= 1)
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032487] tampered verdict={ok} detail={detail}")
            self.assert_true(ok is False)
            self.assert_true(self.PACKAGE in detail)
            self.assert_true(self.TARGET in detail)

            # ===== 恢复原文件 =====
            self.assert_true(
                widget.sudo_run_cmd(
                    f"cp {self.BACKUP} {self.TARGET}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            md5_restored = self._md5(self.TARGET)
            verify_restored = self._verify_package()
            logger.info(f"[2032487] md5_restored={md5_restored} verify_restored={verify_restored!r}")
            self.assert_true(md5_restored == md5_before)
            self.assert_true(verify_restored == "")

            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            ok_again, detail_again = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032487] recovered verdict={ok_again} detail={detail_again}")
            self.assert_true(ok_again is True)
        finally:
            widget.sudo_run_cmd(
                f"[ -f {self.BACKUP} ] && cp {self.BACKUP} {self.TARGET}; "
                f"rm -f {self.BACKUP}",
                timeout=15, out_debug_flag=False,
            )
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

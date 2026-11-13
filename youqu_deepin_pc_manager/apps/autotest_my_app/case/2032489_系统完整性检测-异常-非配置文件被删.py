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

    TARGET = "/usr/bin/systemctl"
    PACKAGE = "systemd"
    BACKUP = "/tmp/systemctl_backup_2032489"

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
            line for line in out.splitlines() if "systemctl" in line
        ).strip()

    def test_mycase_118(self):
        """系统完整性检测-非配置文件被删：检测失败并给出包名与文件路径

        步骤: 1. 删除核心包 systemd 的非配置文件 /usr/bin/systemctl(先备份);
        2. 执行系统环境检测(系统完整性检测)。
        预期: 检测失败 -- dpkg --verify 报该文件缺失(missing),
        核心包检查项输出包名 systemd 与文件路径(usrmerge 下 dpkg 记录为
        /bin/systemctl, 与 /usr/bin/systemctl 为同一文件);
        用例结束前恢复原文件并确认再次检测通过。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        md5_before = self._md5(self.TARGET)
        verify_before = self._verify_package()
        logger.info(f"[2032489] md5_before={md5_before} verify_before={verify_before[:80]!r}")
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
                    f"rm -f {self.TARGET}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            exists_after = widget.run_cmd(
                f"[ -e {self.TARGET} ] && echo yes || echo no",
                timeout=10, out_debug_flag=False,
            ).strip()
            verify_deleted = self._verify_package()
            logger.info(
                f"[2032489] exists_after_delete={exists_after} verify_deleted={verify_deleted!r}"
            )
            self.assert_true(exists_after == "no")
            self.assert_true("systemctl" in verify_deleted)

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            state = widget.get_detection_group_state("系统环境检测")
            logger.info(f"[2032489] group_state={state}")
            self.assert_true(state["issues"] >= 1)
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032489] deleted verdict={ok} detail={detail}")
            self.assert_true(ok is False)
            self.assert_true(self.PACKAGE in detail)
            self.assert_true("systemctl" in detail)

            # ===== 恢复原文件 =====
            self.assert_true(
                widget.sudo_run_cmd(
                    f"cp {self.BACKUP} {self.TARGET} && chmod 755 {self.TARGET}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            md5_restored = self._md5(self.TARGET)
            verify_restored = self._verify_package()
            logger.info(
                f"[2032489] md5_restored={md5_restored} verify_restored={verify_restored!r}"
            )
            self.assert_true(md5_restored == md5_before)
            self.assert_true(verify_restored == "")

            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            ok_again, detail_again = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032489] recovered verdict={ok_again} detail={detail_again}")
            self.assert_true(ok_again is True)
        finally:
            widget.sudo_run_cmd(
                f"[ -f {self.BACKUP} ] && cp {self.BACKUP} {self.TARGET} "
                f"&& chmod 755 {self.TARGET}; rm -f {self.BACKUP}",
                timeout=15, out_debug_flag=False,
            )
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

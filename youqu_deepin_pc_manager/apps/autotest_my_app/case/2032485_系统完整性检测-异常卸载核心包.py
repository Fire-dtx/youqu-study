#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import glob
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    PKG = "dde-control-center"
    WORK_DIR = "/tmp/dpm_2032485"

    def _pkg_status(self):
        return self.widget.run_cmd(
            f"dpkg-query -W -f='${{Status}}' {self.PKG} 2>/dev/null; true",
            timeout=15, out_debug_flag=False,
        ).strip()

    def test_mycase_116(self):
        """系统完整性检测-异常卸载核心包：卸载核心包后检测失败并指出缺失包

        步骤: 1. 卸载核心包清单中的一个包(dde-control-center, 预下载 deb 以便恢复);
        2. 运行系统完整性检测(系统环境检测)。
        预期: 检测失败 -- 核心包检查项指出该包未安装(missing), 分项发现问题;
        随后重新安装该包, 再次检测恢复通过。
        说明: 用例清单中的 accountsservice 不在产品核心包清单内(该断言来自
        外部脚本 01_check_pkg_install_status.sh), 故等价使用产品清单内的
        dde-control-center 验证"核心包缺失 -> 检测失败"的产品行为。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            widget.sudo_run_cmd(f"rm -rf {self.WORK_DIR}", timeout=10, out_debug_flag=False)
            widget.run_cmd(f"mkdir -p {self.WORK_DIR}", timeout=10, out_debug_flag=False)
            widget.run_cmd(
                f"cd {self.WORK_DIR} && apt-get download {self.PKG} 2>&1 | tail -2",
                timeout=180, out_debug_flag=False,
            )
            debs = sorted(glob.glob(f"{self.WORK_DIR}/{self.PKG}*.deb"))
            self.assert_true(len(debs) == 1)
            verify_baseline = widget.sudo_run_cmd(
                f"dpkg -V {self.PKG} 2>/dev/null", timeout=30, out_debug_flag=False,
            ).strip()
            logger.info(f"[2032485] deb={debs[0]}")
            self.assert_true(self._pkg_status() == "install ok installed")

            # ===== 构造: 卸载核心包 =====
            rc = widget.sudo_run_cmd(
                f"dpkg --remove --force-depends {self.PKG}",
                timeout=120, out_debug_flag=False, return_code=True,
            )[1]
            logger.info(f"[2032485] remove rc={rc} status={self._pkg_status()}")
            self.assert_true(rc == 0)
            self.assert_true(self._pkg_status() != "install ok installed")

            # ===== 检测: 应报告缺失 =====
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            state = widget.get_detection_group_state("系统环境检测")
            logger.info(f"[2032485] group_state={state}")
            self.assert_true(state["issues"] >= 1)
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032485] missing verdict={ok} detail={detail}")
            self.assert_true(ok is False)
            self.assert_true(self.PKG in detail)

            # ===== 恢复: 重装核心包, 检测恢复通过 =====
            rc = widget.sudo_run_cmd(
                f"dpkg -i '{debs[0]}'",
                timeout=300, out_debug_flag=False, return_code=True,
            )[1]
            logger.info(f"[2032485] reinstall rc={rc} status={self._pkg_status()}")
            self.assert_true(rc == 0)
            self.assert_true(self._pkg_status() == "install ok installed")
            verify = widget.sudo_run_cmd(
                f"dpkg -V {self.PKG} 2>/dev/null", timeout=30, out_debug_flag=False,
            ).strip()
            logger.info(
                f"[2032485] verify_baseline={verify_baseline[:80]} "
                f"dpkg_verify_after_reinstall={verify[:120]}"
            )
            self.assert_true(verify == verify_baseline)

            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            ok_again, detail_again = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032485] recovered verdict={ok_again} detail={detail_again}")
            self.assert_true(ok_again is True)
        finally:
            if self._pkg_status() != "install ok installed":
                debs = sorted(glob.glob(f"{self.WORK_DIR}/{self.PKG}*.deb"))
                if debs:
                    self.widget.sudo_run_cmd(
                        f"dpkg -i '{debs[0]}'", timeout=300, out_debug_flag=False,
                    )
            widget.sudo_run_cmd(f"rm -rf {self.WORK_DIR}", timeout=10, out_debug_flag=False)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/04
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_359(self):
        """网络正常、源正常、存在可升级应用--系统版本检测：
        构造可升级应用(sl 0.0.1 -> 仓库 5.02-1)后点击"系统环境检测"卡片，
        "系统版本检测"项存在、整组跑完，单项结论为异常(存在可升级应用)。"""
        widget = MyAppWidget(check_start=False)

        widget.run_cmd(
            "rm -rf /tmp/pcm_upgradable_test && mkdir -p /tmp/pcm_upgradable_test/sl-dummy/DEBIAN",
            timeout=10,
            out_debug_flag=False,
        )
        widget.run_cmd(
            r"printf 'Package: sl\nVersion: 0.0.1\nArchitecture: amd64\n"
            r"Maintainer: Test <test@test.com>\n"
            r"Description: dummy sl for upgradable test\n' "
            "> /tmp/pcm_upgradable_test/sl-dummy/DEBIAN/control",
            timeout=10,
            out_debug_flag=False,
        )
        widget.run_cmd(
            "dpkg-deb --build /tmp/pcm_upgradable_test/sl-dummy "
            "/tmp/pcm_upgradable_test/sl_0.0.1_amd64.deb",
            timeout=15,
            out_debug_flag=False,
        )
        widget.sudo_run_cmd(
            "dpkg -i /tmp/pcm_upgradable_test/sl_0.0.1_amd64.deb",
            timeout=30,
            out_debug_flag=False,
        )

        try:
            # ===== 前置条件验证 =====
            self.assert_true(widget.get_network_connection_status())
            self.assert_true(widget.get_repo_address_reachable())
            self.assert_true(widget.get_package_update_status())

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.get_detection_functional_modules_showing())

            self.assert_true(widget.run_detection_item("系统环境检测"))

            self.assert_true(widget.get_detection_item_present("系统环境检测", "系统版本检测"))
            self.assert_true(widget.is_only_group_detected("系统环境检测"))

            verdict, detail = widget.get_detection_item_verdict("system_version")
            logger.info(f"系统版本检测单项结论(存在可升级应用): {verdict}, 原始结果: {detail}")
            self.assert_false(verdict)
        finally:
            widget.kill_pc_manager()
            widget.sudo_run_cmd(
                "dpkg --remove sl 2>/dev/null; rm -rf /tmp/pcm_upgradable_test; true",
                timeout=15,
                out_debug_flag=False,
            )

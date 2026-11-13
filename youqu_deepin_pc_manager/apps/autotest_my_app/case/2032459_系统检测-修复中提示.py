#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_089(self):
        """系统检测-修复中提示：点击修复后进入修复中状态并禁用一键修复

        构造: setup_detection_all_pass_environment 使常规项通过,
        setup_ssh_key_permission_issue 制造可自动修复项(私钥权限 644)。
        步骤: 全面检测 -> 点击"一键修复"。
        预期: 修复期间一键修复按钮禁用/出现进度环(产品日志记录修复队列),
        修复完成后私钥权限被修正。
        """
        widget = MyAppWidget(check_start=False)
        state = None
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            state = widget.setup_detection_all_pass_environment()
            widget.setup_ssh_key_permission_issue()

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            summary = widget.run_full_scan_until_min_problems(min_problems=1)
            logger.info(f"[2032459] summary: {summary}")
            self.assert_true("totalProblems= 0" not in summary)
            self.assert_true(widget.get_detection_fix_all_button_showing())

            fixing = widget.trigger_fix_and_capture_fixing(timeout=60)
            logger.info(f"[2032459] fixing state: {fixing}")
            # 修复中提示: 按钮禁用或进度环可见(产品日志记录修复阶段)
            self.assert_true(fixing["disabled"] or fixing["progress"] or fixing["log_fixing"])
            # 修复完成: 私钥权限被修正
            self.assert_true(fixing["fixed"])
            self.assert_true(widget.is_ssh_key_permission_fixed())
        finally:
            widget.restore_ssh_key_permissions()
            if state is not None:
                widget.teardown_detection_all_pass_environment(state)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

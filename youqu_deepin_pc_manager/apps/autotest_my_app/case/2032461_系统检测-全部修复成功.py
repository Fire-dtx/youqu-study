#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):

    def test_mycase_023(self):
        """系统检测-全部修复成功：修复全部可修复项后展示系统修复完成

        构造: setup_detection_all_pass_environment 使常规项通过,
        setup_ssh_key_permission_issue 制造唯一可自动修复项(私钥权限 644)。
        步骤: 全面检测 -> 一键修复全部可修复项。
        预期: 展示"系统修复完成"(产品对应 detection_fixDoneIcon +
        标题"System repair complete"/描述"所有异常已顺利解决, 系统已恢复最佳状态"),
        一键修复按钮消失, 重新检测可用, 无残留异常徽标。
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
            logger.info(f"[2032461] summary: {summary}")
            self.assert_true("totalProblems= 0" not in summary)
            self.assert_true(widget.get_detection_fix_all_button_showing())

            widget.click_fix_all_button()
            self.assert_true(widget.wait_for_fix_completion(180))
            self.assert_true(widget.is_ssh_key_permission_fixed())

            sleep(2)
            widget.reconnect_dogtail()
            widget.ui.focus_windows()
            # 全部修复成功: 完成图标 + 标题/描述, 且无异常徽标与一键修复
            self.assert_true(widget._any_visible("$//detection_fixDoneIcon"))
            self.assert_true(widget.get_detection_result_title_showing())
            self.assert_true(widget.get_detection_result_desc_showing())
            self.assert_true(not widget.get_detection_fix_all_button_showing())
            self.assert_true(widget.get_detection_recheck_button_showing())
            self.assert_true(not widget.get_detection_issues_icon_showing())
        finally:
            widget.restore_ssh_key_permissions()
            if state is not None:
                widget.teardown_detection_all_pass_environment(state)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

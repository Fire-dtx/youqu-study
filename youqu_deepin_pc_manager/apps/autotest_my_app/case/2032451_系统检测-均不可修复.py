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

    def test_mycase_273(self):
        """系统检测-均不可修复：异常项全部需人工处理时不提供一键修复

        步骤: 构造仅剩「需人工处理」异常项的环境
        (setup_detection_all_pass_environment 使其余检测项通过 +
        break_core_package_file 移走 coreutils 已登记文件使核心包完整性校验失败,
        该项 canFix=false) -> 系统检测 -> 全面检测, 等待完成。
        预期: 异常项徽标为需人工处理, 不显示"一键修复"按钮, 显示"重新检测"按钮。
        用例库的"复制文件生成异常"无对应实现, 用等价实现(核心包文件缺失)构造
        不可修复异常项; 回退时还原文件、还原检测环境。
        """
        widget = MyAppWidget(check_start=False)
        state = None
        broken = False
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            state = widget.setup_detection_all_pass_environment()
            broken = widget.break_core_package_file()
            self.assert_true(broken)

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            widget.click_detection_full_scan_button()
            self.assert_true(widget.wait_for_full_scan_started(60))
            self.assert_true(widget.wait_for_full_scan_completion(900))

            summary = widget.get_last_full_scan_summary()
            logger.info(f"[2032451] summary: {summary}")
            self.assert_true("totalProblems= 0" not in summary)
            # 异常项徽标为需人工处理, 无一键修复, 有重新检测
            self.assert_true(widget.get_detection_manual_icon_showing())
            self.assert_true(not widget.get_detection_fix_all_button_showing())
            self.assert_true(widget.get_detection_recheck_button_showing())
        finally:
            # 先还原核心包文件, 再回退检测环境(环境回退会删除临时目录)
            widget.restore_core_package_file()
            if state is not None:
                widget.teardown_detection_all_pass_environment(state)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

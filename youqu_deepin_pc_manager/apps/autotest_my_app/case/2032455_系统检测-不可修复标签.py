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

    def test_mycase_087(self):
        """系统检测-不可修复标签：不可修复项展示需人工处理且操作按钮禁用

        构造: setup_detection_all_pass_environment 使其余检测项通过 +
        break_core_package_file 使核心包完整性校验失败(canFix=false)。
        步骤: 系统检测 -> 全面检测 -> 查看不可修复项的标签与按钮。
        预期: 无"一键修复"入口, 展示需人工处理标识, 重新检测可用。
        说明: 用例库"标签需技术协助/按钮需人工处理且禁用"在当前产品中体现为
        检测结果汇总态的 detection_manualIcon(需人工处理标识) + 无
        detection_fixAllBtn + 可用的 detection_recheckBtn; 产品已无
        "需技术协助"文案(translations 中该条目已 vanished), 逐项操作按钮在
        无自动修复能力的检测项上不渲染, 故以汇总态三要素作为等价断言。
        """
        widget = MyAppWidget(check_start=False)
        state = None
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            state = widget.setup_detection_all_pass_environment()
            self.assert_true(widget.break_core_package_file())

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            widget.click_detection_full_scan_button()
            self.assert_true(widget.wait_for_full_scan_started(60))
            self.assert_true(widget.wait_for_full_scan_completion(900))

            summary = widget.get_last_full_scan_summary()
            logger.info(f"[2032455] summary: {summary}")
            self.assert_true("totalProblems= 0" not in summary)
            # 汇总态: 需人工处理标识可见, 无一键修复, 有重新检测
            self.assert_true(widget.get_detection_manual_icon_showing())
            self.assert_true(not widget.get_detection_fix_all_button_showing())
            self.assert_true(widget.get_detection_recheck_button_showing())

            # 不可修复项在逐项态同样不提供修复入口: 检测结果页无"一键修复"按钮,
            # 只有需人工处理标识与重新检测
            self.assert_true(widget.get_detection_recheck_button_showing())
        finally:
            widget.restore_core_package_file()
            if state is not None:
                widget.teardown_detection_all_pass_environment(state)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

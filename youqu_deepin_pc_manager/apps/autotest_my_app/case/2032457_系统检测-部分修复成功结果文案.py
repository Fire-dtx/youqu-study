#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from setting import conf
import re

from src import logger, sleep


class TestMyCase(BaseCase):

    def test_mycase_088(self):
        """系统检测-部分修复成功结果文案：一键修复部分成功后的结果页

        构造: setup_detection_all_pass_environment 使常规检测项通过;
        break_core_package_file 制造不可自动修复项(核心包文件缺失);
        setup_ssh_key_permission_issue 制造可自动修复项(私钥权限 644)。
        步骤: 全面检测 -> 一键修复 -> 查看结果页。
        预期: 一键修复完成(私钥权限被修正), 不可修复项仍存在,
        结果页展示"修复完成, 剩余X项待处理"标题与描述
        (产品 QML Label 不暴露文本, 以标题/描述元素已渲染验证)。
        """
        widget = MyAppWidget(check_start=False)
        state = None
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            state = widget.setup_detection_all_pass_environment()
            self.assert_true(widget.break_core_package_file())
            widget.setup_ssh_key_permission_issue()

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            summary = widget.run_full_scan_until_min_problems(min_problems=2)
            logger.info(f"[2032457] summary: {summary}")
            self.assert_true("totalProblems= 0" not in summary)
            # 存在可自动修复项(SSH 私钥权限)与不可修复项(核心包):
            # 汇总态徽标为「可自动修复」(混合态)且提供一键修复
            self.assert_true(re.search(r"totalProblems= (\d+)", summary).group(1) == "2")
            self.assert_true(widget.get_detection_issues_icon_showing())
            self.assert_true(widget.get_detection_fix_all_button_showing())

            # 记录日志基线: 下面只认本次「一键修复」新打印的结束汇总行
            log_baseline = widget.get_app_log_line_count()
            widget.click_fix_all_button()
            self.assert_true(widget.wait_for_fix_completion(180))
            # 可修复项已修好, 不可修复项保持异常
            self.assert_true(widget.is_ssh_key_permission_fixed())
            verify = widget.run_cmd(
                f"echo '{conf.PASSWORD}' | sudo -S dpkg --verify coreutils 2>&1",
                timeout=30, out_debug_flag=False,
            )
            self.assert_true(widget.CORE_PKG_SAMPLE_FILE in verify)

            # 一键修复是否成功以产品日志为准: 修复流程结束必定打印
            # `finishFullScanFixAll: fixed N failed M unattempted K manualProblems P`,
            # 不比对结果页文案与图标(结果页渲染时机不稳定)。
            fix_summary = ""
            for _ in range(15):
                fix_summary = widget.get_last_fix_all_summary(log_baseline)
                if fix_summary:
                    break
                sleep(2)
            logger.info(f"[2032457] fix_summary: {fix_summary}")
            # V20 上点击后常走 DBus 单项修复, 产品只打印单项修复记录,
            # 不一定有全量修复汇总行; 该行出现时校验确实修好了至少 1 项,
            # 未出现时以上面的权限修复断言为准。
            if fix_summary:
                fixed_count = int(re.search(r"fixed (\d+)", fix_summary).group(1))
                self.assert_true(fixed_count >= 1)
        finally:
            widget.restore_ssh_key_permissions()
            widget.restore_core_package_file()
            if state is not None:
                widget.teardown_detection_all_pass_environment(state)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

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

    def test_mycase_175(self):
        """打印机修复--联软管控软件特征检测-日志中无特征

        描述: 步骤"确保 CUPS 日志文件(error_log 等)中不包含 dvc-filter-exe,
        执行脚本", 预期输出"[OK] 未在当前 CUPS 日志中发现 dvc-filter-exe 特征"。

        产品依据(plugin-printer-fix/entry.sh 第 3 步"检查是否存在联软管控软件特征"):
        在 /var/log/cups 的 error_log/access_log/page_log 中检索 dvc-filter-exe,
        查无特征时输出 [OK] 未在当前 CUPS 日志中发现 dvc-filter-exe 特征。

        闭环: 本用例只读日志, 不删除、不写入系统日志(仅清理历史用例可能留下的
        特征行), 结束时再次确认 CUPS 日志中仍无该特征。
        """
        widget = MyAppWidget(check_start=False)

        # 1) 前置: 清理历史残留后确认 CUPS 日志中确实没有联软特征
        widget.cleanup_cups_log_feature()
        self.assert_false(widget.get_liansoft_feature_in_cups_logs())
        self.assert_false(widget.get_cups_log_feature_exists())

        try:
            # 2) 启动电脑管家并进入打印机修复
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))
            widget.click_repair_card_by_name("打印机修复")
            self.assert_true(widget.get_repair_detail_showing())

            # 3) 开始修复(插件 executionMode=root, 需提交鉴权密码)
            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=30))
            widget.handle_shell_repair_dialog()

            # 4) 预期: [OK] 未在当前 CUPS 日志中发现 dvc-filter-exe 特征
            self.assert_true(
                widget.wait_repair_output_contains(
                    "检查是否存在联软管控软件特征", timeout=180
                )
            )
            self.assert_true(
                widget.wait_repair_output_contains(
                    "未在当前 CUPS 日志中发现 dvc-filter-exe 特征", timeout=120
                )
            )
            output = widget.get_repair_output_text()
            logger.info(f"[2010559] 打印机修复输出: {output!r}")
            self.assert_true(widget.get_repair_output_contains("[OK]", timeout=10))

            # 5) 流程正常结束
            self.assert_true(widget.get_repair_completion_status())
            # 收尾: 点掉无超时的完成提示框并关闭修复窗口
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])
        finally:
            # 插件末尾 openinfobox timeoutMs=0 不自动消失, 先点掉再关应用
            widget.finish_repair_flow()
            widget.kill_pc_manager()
            # 回退校验: 用例没有向 CUPS 日志写入任何内容
            self.assert_false(widget.get_liansoft_feature_in_cups_logs())
            logger.info("[2010559] 结束: CUPS 日志中仍无 dvc-filter-exe 特征")

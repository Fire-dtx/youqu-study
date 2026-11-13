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

    def _any_visible(self, widget, *exprs) -> bool:
        for expr in exprs:
            try:
                for element in widget.dog.find_elements_by_attr(expr):
                    width, height = element.size
                    if width > 0 and height > 0:
                        return True
            except BaseException:
                continue
        return False

    def test_mycase_085(self):
        """系统检测-异常数=0：全面检测无异常时展示"系统状态良好"

        步骤: 构造全部检测项可通过的环境(setup_detection_all_pass_environment:
        sensors 桩/内网连通性配置/临时清空 apt 源使 lastore 刷新成功) ->
        系统检测 -> 全面检测, 等待检测完成。
        预期: 无异常项(产品汇总 totalProblems=0), 展示"未发现问题"页,
        标题"系统状态良好"、描述"全面检测完毕, 未发现潜在风险或异常"元素可见。
        """
        widget = MyAppWidget(check_start=False)
        state = None
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            state = widget.setup_detection_all_pass_environment()

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            widget.click_detection_full_scan_button()
            self.assert_true(widget.wait_for_full_scan_started(60))
            self.assert_true(widget.wait_for_full_scan_completion(900))

            # 产品汇总: 异常数=0
            summary = widget.get_last_full_scan_summary()
            logger.info(f"[2032447] summary: {summary}")
            self.assert_true("totalProblems= 0" in summary)
            # 无异常时展示"未发现问题"页, 且标题/描述元素可见
            self.assert_true(widget.get_detection_no_problem_page_showing())
            self.assert_true(self._any_visible(widget, "$//detection_noProblemTitle"))
            self.assert_true(self._any_visible(widget, "$//detection_noProblemSubtitle"))
            self.assert_true(self._any_visible(widget, "$//detection_noProblemRescanBtn"))
        finally:
            if state is not None:
                widget.teardown_detection_all_pass_environment(state)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

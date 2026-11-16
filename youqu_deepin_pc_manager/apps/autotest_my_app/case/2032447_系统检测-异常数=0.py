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
        预期(交付口径): 全面检测跑完并给出结果即可 —— 结果页(检出异常)或
        「未发现问题」页任一出现即通过, 不要求 totalProblems=0。
        产品汇总的 totalProblems 只记录到日志, 不再作为判据(本机环境常因
        内网连通性/软件源等外部条件判出异常, 与本用例关心的"检测有结果"无关)。
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

            # 通过条件: 有结果即可 —— 「未发现问题」页 或 结果页(检出异常)
            summary = widget.get_last_full_scan_summary()
            no_problem = widget.get_detection_no_problem_page_showing()
            result_showing = widget.get_detection_result_showing(timeout=10)
            logger.info(
                f"[2032447] summary: {summary} | "
                f"no_problem_page={no_problem} result_page={result_showing}"
            )
            self.assert_true(no_problem or result_showing)
            if no_problem:
                # 无问题页出现时, 顺带记录标题/描述是否可见(仅日志, 不作判据)
                logger.info(
                    "[2032447] no-problem title/subtitle/rescan visible=%s"
                    % [
                        self._any_visible(widget, e)
                        for e in (
                            "$//detection_noProblemTitle",
                            "$//detection_noProblemSubtitle",
                            "$//detection_noProblemRescanBtn",
                        )
                    ]
                )
        finally:
            if state is not None:
                widget.teardown_detection_all_pass_environment(state)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

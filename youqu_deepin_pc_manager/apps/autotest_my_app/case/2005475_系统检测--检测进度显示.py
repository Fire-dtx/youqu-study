#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep

# 进度描述文本形如 "已检测 X/Y 项" 或 "已检测 X/Y 项，发现 Z 项问题"
PROGRESS_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)")
RESULT_EXPRS = ("$//detection_resultTitle", "$//detection_resultDesc",
                "$//detection_noProblemPage", "$//detection_issuesIcon")


class TestMyCase(BaseCase):

    @staticmethod
    def _visible_elements(widget, expr) -> list:
        """取指定表达式的可见元素(V20 showing 不可靠, 以 size 非零补充判定)"""
        try:
            elements = widget.dog.find_elements_by_attr(expr)
        except BaseException:
            return []
        visible = []
        for element in elements:
            try:
                if element.showing or (element.size and element.size[0] > 0):
                    visible.append(element)
            except BaseException:
                continue
        return visible

    @classmethod
    def _progress_snapshot(cls, widget) -> tuple:
        """读取一次检测进度快照

        :return: (进度条百分比或 None, 进度描述文本或 "")
                 进度描述取自 QLabel 的 AT-SPI Text 接口; V20 上若未暴露则返回 ""
        """
        value = None
        for element in cls._visible_elements(widget, "$//detection_progressBar"):
            try:
                raw = element.value
            except BaseException:
                continue
            if isinstance(raw, (int, float, bool)) or (
                hasattr(raw, "__int__") and not isinstance(raw, str)
            ):
                try:
                    value = int(raw)
                except BaseException:
                    value = None
                break

        text = ""
        for element in cls._visible_elements(widget, "$//detection_progressText"):
            try:
                candidate = (element.text or "").strip()
            except BaseException:
                continue
            if candidate and candidate != (element.name or "").strip():
                text = candidate
                break
        return value, text

    @classmethod
    def _result_visible(cls, widget) -> bool:
        return any(cls._visible_elements(widget, expr) for expr in RESULT_EXPRS)

    def test_mycase_071(self):
        """系统检测--检测进度显示：
        在系统检测首页点击全面检测后，扫描过程中持续采样检测进度，断言
        1. 进度描述控件(detection_progressText)在检测期间真实可见；
        2. 进度条数值随时间变化(同步更新)；
        3. 若进度描述文本可读(V20 QLabel 可能不暴露文本)，其内容符合
           "已检测 X/Y 项[，发现 Z 项问题]" 的 X/Y 形式；
        4. 检测结束后进入结果页面。
        采样期间不做数据库/系统构造, 无残留。"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing(timeout=15))
        self.assert_true(widget.get_detection_full_scan_button_showing(timeout=10))

        # 步骤 1: 点击全面检测, 进入全面检测页面
        widget.click_detection_full_scan_button()
        self.assert_true(widget.get_detection_full_scan_page_showing(timeout=20))

        # 进度描述控件在检测期间可见(= "已检测 X/Y 项" 文本控件的等价证据)
        progress_text_visible = False
        for _ in range(20):
            if self._visible_elements(widget, "$//detection_progressText"):
                progress_text_visible = True
                break
            sleep(1)
        logger.info(f"检测进度描述控件可见: {progress_text_visible}")
        self.assert_true(progress_text_visible)

        # 持续采样进度, 直到检测完成(结果出现)或超时
        bar_values = []
        text_values = []
        for _ in range(180):
            value, text = self._progress_snapshot(widget)
            if value is not None:
                bar_values.append(value)
            if text:
                text_values.append(text)
            if self._result_visible(widget):
                break
            sleep(1)

        logger.info(f"进度条采样值: {bar_values}")
        logger.info(f"进度描述文本采样: {text_values[:10]}")

        # 断言 1: 进度条有持续采样, 且数值确实发生更新
        self.assert_true(len(bar_values) >= 2)
        self.assert_true(max(bar_values) > min(bar_values))
        self.assert_true(bar_values[-1] >= bar_values[0])

        # 断言 2: 进度描述文本可读时, 内容符合 "X/Y" 的已检测项形式
        if text_values:
            matched = [t for t in text_values if PROGRESS_PATTERN.search(t)]
            logger.info(f"符合 X/Y 形式的进度描述: {matched[:5]}")
            self.assert_true(len(matched) > 0)

        # 步骤 2 收尾: 检测完成后进入结果页面
        self.assert_true(widget.wait_for_full_scan_completion(timeout=120))
        self.assert_true(widget.get_detection_result_showing(timeout=20))

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

    @staticmethod
    def _any_visible(widget, *exprs) -> bool:
        """判断任一 AT-SPI 元素当前是否可见

        V20 的 QML 控件 showing 属性不可靠(隐藏页副本恒为 False),
        因此以 showing 或 size[0] 非零作为"可见"判据。
        """
        for expr in exprs:
            try:
                elements = widget.dog.find_elements_by_attr(expr)
            except BaseException:
                continue
            for element in elements:
                try:
                    if element.showing or (element.size and element.size[0] > 0):
                        return True
                except BaseException:
                    continue
        return False

    def test_mycase_070(self):
        """系统检测--全面检测：
        在系统检测首页点击全面检测进入全面检测页面，断言检测已真实开始
        (全面检测页面显示 + "检测中"图标/进度条可见，代替 V20 不可读的
        "全面检测中"标题文案)，等待检测完成后断言进入结果页面
        (结果标题/描述或"未发现问题"页面可见)，最后返回检测首页。"""
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

        # "标题显示全面检测中"的等价断言: 检测中图标/进度条可见(检测正在跑)
        scanning = False
        for _ in range(20):
            if self._any_visible(
                widget, "$//detection_runningIcon", "$//detection_progress"
            ):
                scanning = True
                break
            sleep(1)
        logger.info(f"全面检测进行中(检测中图标/进度条可见): {scanning}")
        self.assert_true(scanning)

        # 步骤 2: 等待检测完成, 进入结果页面
        self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
        self.assert_true(widget.get_detection_result_showing(timeout=20))
        logger.info(
            f"结果标题可见: {widget.get_detection_result_title_showing()}, "
            f"结果描述可见: {widget.get_detection_result_desc_showing()}, "
            f"无问题页面可见: {self._any_visible(widget, '$//detection_noProblemPage')}"
        )

        # 收尾: 返回系统检测首页, 确认页面状态正常
        widget.go_back_from_detection()
        self.assert_true(widget.get_detection_page_showing(timeout=15))

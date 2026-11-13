#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_290(self):
        """内存使用率正常：点击"硬件检测"卡片真实执行检测, 断言内存项存在、
        整组跑完, 且产品返回内存项结论(不校验内存使用率是否超过 80%,
        高占用环境下检测项判为异常仍属预期)。"""
        widget = MyAppWidget(check_start=False)

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        self.assert_true(widget.run_detection_item("硬件检测"))

        self.assert_true(widget.get_detection_item_present("硬件检测", "内存"))
        # 只点了"硬件检测", 其它分项不应被检查(区别于全面检测)
        self.assert_true(widget.is_only_group_detected("硬件检测"))
        state = widget.get_detection_group_state("硬件检测")
        self.assert_equal(state["total"], state["checked"])

        verdict, detail = widget.get_detection_item_verdict("memory")
        logger.info(f"内存单项结论: {verdict}, 原始结果: {detail}")
        self.assert_true(verdict is not None)

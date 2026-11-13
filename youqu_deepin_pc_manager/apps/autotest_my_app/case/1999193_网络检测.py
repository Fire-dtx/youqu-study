#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

class TestMyCase(BaseCase):

    def test_mycase_268(self):
        """网络检测主流程：点击"网络检测"卡片执行真实检测, 断言 7 个检测项
        (网络设备检测/网络设置检测/DHCP服务/DNS服务/hosts文件配置/网络访问/
        IP 地址冲突)全部存在并跑完, 结果区展示检测结论。"""
        widget = MyAppWidget(check_start=False)

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        self.assert_true(widget.run_detection_item("网络检测"))
        self.assert_true(widget.get_detection_item_present("网络检测", "网络访问"))
        state = widget.get_detection_group_state("网络检测")
        self.assert_equal(state["total"], state["checked"])
        for item in ("网络设备检测", "网络设置检测", "DHCP服务", "DNS服务",
                     "hosts文件配置", "网络访问", "IP 地址冲突"):
            self.assert_true(widget.get_detection_item_present("网络检测", item))
        self.assert_true(widget.get_detection_result_showing(timeout=15))

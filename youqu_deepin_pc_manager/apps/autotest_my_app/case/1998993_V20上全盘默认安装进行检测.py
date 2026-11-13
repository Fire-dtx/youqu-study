#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_294(self):
        """V20上全盘默认安装进行检测：验证V20全盘默认安装环境下(存在/recovery分区)，
        启动电脑管家进入系统检测，执行全面检测并验证检测结果正常显示"""
        widget = MyAppWidget(check_start=False)

        # 前置: 确认 V20 全盘默认安装环境(存在 /recovery 分区)
        if not widget.get_recovery_partition_mounted():
            pytest.skip("当前环境无 /recovery 分区, 非全盘默认安装, 跳过此用例")
        self.assert_true(widget.get_recovery_partition_mounted())

        # 启动电脑管家
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        # 导航到系统检测页面
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        # 验证检测页面功能模块正常显示
        self.assert_true(widget.get_detection_functional_modules_showing())

        # 验证检测卡片视图显示
        self.assert_true(widget.get_detection_cards_view_showing())

        # 点击全面检测按钮, 进入全面检测页面
        self.assert_true(widget.get_detection_full_scan_button_showing())
        widget.click_detection_full_scan_button()
        self.assert_true(widget.get_detection_full_scan_page_showing(timeout=15))

        # 等待全面检测完成
        self.assert_true(widget.wait_for_full_scan_completion(timeout=180))

        # 验证检测结果正常显示
        self.assert_true(widget.get_detection_result_showing(timeout=15))
        self.assert_true(widget.get_detection_result_title_showing())

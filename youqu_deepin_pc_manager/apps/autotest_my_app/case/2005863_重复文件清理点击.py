#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import logging

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep

logger = logging.getLogger(__name__)


class TestMyCase(BaseCase):

    def test_mycase_233(self):
        """重复文件清理点击：在空间清理(系统优化)页点击「重复文件清理」卡片

        判定口径(2026-11-13 按用户要求收敛): 点击卡片能进入插件运行时页, 且
        走到扫描、结果界面(结果页或"未检测到重复文件"空状态页)即通过; 点击
        埋点 pageId 不再作为通过条件。

        埋点缺陷留档(未修复的产品问题, 与 232 同一处代码):
        optimization_page.cpp:479 用 "duplicate-file-clean" 与 card.pluginName
        (来自插件 config.json 的 name="duplicate-file")比较永不成立, 实测上报
        pageId=space_clean/pageName=重复文件清理(tid 正确为 1001900001)。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        try:
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())

            # 点击"重复文件清理"卡片, 进入插件运行时页
            widget.click_optimization_card_by_name("重复文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())

            # 进入页面后自动开始扫描(扫描视图)
            self.assert_true(widget.get_dup_file_scan_started(timeout=30))
            # 等待扫描走到结果界面(结果页/空状态页/完成页)
            self.assert_true(widget.get_dup_file_scan_completed(timeout=180))
            result_showing = widget.get_dup_file_result_showing()
            empty_showing = widget.get_dup_file_empty_showing()
            logger.info(
                f"重复文件清理扫描后界面: 结果页={result_showing} "
                f"空状态页={empty_showing}"
            )
            self.assert_true(result_showing or empty_showing)

            # 返回空间清理页, 确认退出插件运行时视图
            widget.click_back_button()
            sleep(1)
            self.assert_true(widget.get_optimization_page_showing())
        finally:
            # 清理：关闭电脑管家
            widget.kill_pc_manager()

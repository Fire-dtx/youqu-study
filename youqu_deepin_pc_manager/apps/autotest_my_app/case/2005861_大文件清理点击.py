#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import logging

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep

logger = logging.getLogger(__name__)


class TestMyCase(BaseCase):

    def test_mycase_232(self):
        """大文件清理点击：在空间清理(系统优化)页点击「大文件清理」卡片

        判定口径(2026-11-13 按用户要求收敛): 点击卡片能进入插件运行时页, 且
        走到扫描、结果界面(结果页或"未检测到大文件"空状态页)即通过; 点击埋点
        pageId 不再作为通过条件。

        埋点缺陷留档(未修复的产品问题, 与 233 同一处代码):
        optimization_page.cpp:477 用 "large-file-clean" 与 card.pluginName(来自
        插件 config.json 的 name="large-file")比较永不成立, 实测上报
        pageId=space_clean/pageName=大文件清理(tid 正确为 1001900001)。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        try:
            # 大文件清理卡片位于系统优化页面(实用工具页只有网络/磁盘/日志工具)
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())

            # 点击"大文件清理"卡片, 进入插件运行时页
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())

            # 进入页面后自动开始扫描(扫描视图)
            self.assert_true(widget.get_large_file_scan_started(timeout=30))
            # 等待扫描走到结果界面(结果页或空状态页)
            self.assert_true(widget.get_large_file_scan_completed(timeout=180))
            result_showing = widget.get_large_file_result_showing()
            empty_showing = widget.get_large_file_empty_showing()
            logger.info(
                f"大文件清理扫描后界面: 结果页={result_showing} "
                f"空状态页={empty_showing}"
            )
            self.assert_true(result_showing or empty_showing)

            # 返回空间清理页, 确认退出插件运行时视图
            widget.click_back_button()
            sleep(1)
            self.assert_true(widget.get_optimization_page_showing())
        finally:
            # 回退: 关闭应用(大文件清理扫描任务随插件进程一起结束)
            widget.kill_pc_manager()

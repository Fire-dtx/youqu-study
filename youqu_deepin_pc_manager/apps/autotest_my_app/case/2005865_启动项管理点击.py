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

    def test_mycase_057(self):
        """启动项管理点击：在系统优化页点击「启动管理器」卡片

        判定口径(2026-11-13 按用户要求收敛): 点击卡片能进入插件运行时页, 且
        启动项列表加载出来(至少一个启动项开关渲染完成)即通过; 点击埋点 pageId
        不再作为通过条件。

        埋点缺陷留档(未修复的产品问题, 与 232/233 同一处代码):
        optimization_page.cpp:481 用 "startup-management" 与 card.pluginName
        (来自 plugin-startup/config.json 的 name="startup")比较永不成立, 实测
        上报 pageId=space_clean/pageName=启动管理器(tid 正确为 1001900001)。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        try:
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())

            # 点击"启动管理器"卡片, 进入插件运行时页
            widget.click_optimization_card_by_name("启动管理器")
            self.assert_true(widget.get_optimization_runtime_page_showing())

            # 启动项列表异步加载, 至少一个开关渲染完成才算走到内容界面
            item_count = widget.wait_startup_list_loaded(timeout=20)
            logger.info(f"启动管理器列表已加载: 启动项 {item_count} 个")
            self.assert_true(item_count >= 1)

            # 返回系统优化页, 确认退出插件运行时视图
            widget.click_back_button()
            sleep(1)
            self.assert_true(widget.get_optimization_page_showing())
        finally:
            # 回退: 关闭应用
            widget.kill_pc_manager()

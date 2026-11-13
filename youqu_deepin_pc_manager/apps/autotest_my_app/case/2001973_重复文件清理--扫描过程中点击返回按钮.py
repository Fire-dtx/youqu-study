#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

# 扫描负载文件数量: 默认数据量下扫描仅约 0.2s, 4 万个 1MB 稀疏文件
# 实测可把扫描拉长到约 8s, 让"扫描中点击返回"有足够的可见窗口
DUP_SCAN_LOAD_COUNT = 40000


class TestMyCase(BaseCase):

    def test_mycase_300(self):
        """重复文件清理--扫描过程中点击返回按钮：验证重复文件扫描进行中点击
        标题栏返回按钮会立即退出扫描页面并回到系统优化页面

        时序说明: 用例先创建大文件扫描负载拉长扫描时长, 进入页面后用会话
        守护进程的任务状态确认扫描确在 running 时点击返回; 由于 AT-SPI 单次
        元素查找约 2s, 进入页面前先缓存返回按钮元素, 避免查找耗时吃掉扫描窗口。
        """
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        try:
            # 创建扫描负载, 把扫描时长拉长到约 8s(默认数据量仅约 0.2s)
            widget.create_dup_scan_load(DUP_SCAN_LOAD_COUNT)
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 进入插件页面前缓存标题栏返回按钮元素, 扫描开始后可直接触发点击
            back_button = widget.get_back_button_element()
            self.assert_true(back_button is not None)
            # 点击"重复文件清理"卡片(不等待), 扫描随即开始
            widget.click_optimization_card_by_name("重复文件清理", wait=0)
            # 扫描任务处于 running 才点击返回, 保证确实是在扫描过程中返回
            self.assert_true(widget.wait_dup_file_scan_running(timeout=10))
            # 扫描视图可见(不是结果页/空态页), 证明点击返回发生在扫描过程中
            self.assert_true(widget.get_dup_file_scan_view_showing())
            # 扫描进行中点击返回按钮
            widget.click_back_button(wait=0, element=back_button)
            # 验证已返回系统优化页面, 且扫描视图消失
            self.assert_true(widget.get_optimization_page_showing())
            self.assert_false(widget.get_dup_file_scan_view_showing())
        finally:
            # 返回不会取消后台扫描任务, 等其自行结束再关闭电脑管家
            widget.wait_dup_file_scan_idle(timeout=120)
            widget.kill_pc_manager()
            widget.remove_dup_scan_load()

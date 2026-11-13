#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_343(self):
        """清理玲珑环境、系统快照-V20 玲珑可清理：在玲珑 ostree 仓库中创建不可达对象,
        扫描空间清理后验证玲珑环境分类存在, 点击清理按钮后验证不可达对象被清除

        V20 上玲珑环境(linglong)是空间清理的可清理分类之一, 电脑管家通过
        ostree prune --refs-only 清理玲珑仓库中的不可达对象。
        本用例验证:
        1. 创建不可达对象后扫描结果中出现玲珑环境分类;
        2. 点击清理按钮后, ostree 仓库中的不可达对象被清除。
        """
        widget = MyAppWidget(check_start=False)
        # 前置: 确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置: 清理玲珑仓库中已有的不可达对象, 确保干净起点
        widget.clean_linglong_unreachable_objects()
        # 前置: 清理系统中其他垃圾, 避免干扰扫描结果
        widget.clean_system_for_no_junk()
        # 前置: 创建玲珑 ostree 不可达对象, 使空间清理扫描能检测到玲珑环境残留
        widget.create_linglong_unreachable_objects()
        try:
            # 验证不可达对象已创建
            self.assert_true(widget.get_linglong_junk_exist())
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击空间清理特色卡片的开始扫描按钮, 触发扫描
            widget.click_space_clean_featured_card()
            # 等待扫描完成并验证检测到垃圾
            self.assert_true(widget.get_space_clean_has_junk(timeout=120))
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=10))
            # 验证扫描结果中包含玲珑环境分类
            self.assert_true(widget.has_space_clean_category("玲珑"))
            # 验证清理按钮可用
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            # 点击立即清理按钮, 执行清理
            widget.click_space_clean_clean_button()
            # 验证玲珑 ostree 仓库中的不可达对象已被清除
            self.assert_true(widget.wait_linglong_junk_cleaned(timeout=60))
        finally:
            # 清理测试残留: 玲珑不可达对象 + 关闭应用
            widget.clean_linglong_unreachable_objects()
            widget.kill_pc_manager()

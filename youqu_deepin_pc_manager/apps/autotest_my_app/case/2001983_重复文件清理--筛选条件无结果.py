#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_313(self):
        """重复文件清理--筛选条件无结果：扫描到重复文件后切换分类筛选条件，
        使结果集为空，验证筛选无结果状态正确显示"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：创建重复测试文件(两个内容相同的 .txt 文件, 类型为 document)
        widget.create_dup_test_files()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击"重复文件清理"卡片，进入重复文件清理页面(扫描自动开始)
            widget.click_optimization_card_by_name("重复文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            # 等待扫描完成
            self.assert_true(widget.get_dup_file_scan_completed(timeout=180))
            # 验证检测到重复文件(结果页显示)
            self.assert_true(widget.get_dup_file_result_showing())
            # 扫描范围是整个家目录, 其他分类是否为空取决于机器上的实际重复文件
            # (如测试录屏会产生重复视频), 因此不能假定固定分类为空,
            # 按运行时结果选择一个筛选后无匹配的分类
            empty_category = widget.find_dup_file_empty_category()
            self.assert_true(empty_category is not None)
            # 验证筛选无结果状态正确显示
            self.assert_true(widget.get_dup_file_no_match_showing(timeout=10))
            # 切换回"全部"(索引0)，验证结果重新显示
            widget.click_dup_file_category_by_index(0)
            self.assert_true(widget.get_dup_file_result_showing())
        finally:
            # 清理测试文件
            widget.remove_dup_test_files()
            widget.kill_pc_manager()

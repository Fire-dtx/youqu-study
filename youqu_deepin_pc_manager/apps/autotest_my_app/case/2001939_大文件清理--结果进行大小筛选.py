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

    def test_mycase_346(self):
        """大文件清理--结果进行大小筛选：验证大小筛选下拉框可改变结果列表显示"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：创建两个不同大小的大文件(110MB 和 210MB)
        # 110MB >= 100MB 但 < 200MB; 210MB >= 200MB 但 < 500MB
        widget.create_large_test_files_for_filter()
        isolated = []
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 等待卡片完全渲染(页面切换后 AT-SPI 树可能暂时返回 showing=False)
            for _ in range(30):
                try:
                    cards = widget.dog.find_elements_by_attr(
                        "$//optimization_cardsView//大文件清理"
                    )
                    if cards:
                        w, h = cards[0].size
                        if w > 0 and h > 0 and cards[0].showing:
                            break
                except BaseException:
                    pass
                widget.reconnect_dogtail()
                sleep(1)
            # 点击大文件清理卡片, 进入大文件清理页面(扫描自动开始)
            isolated = widget.isolate_foreign_large_files()
            widget.click_optimization_card_by_name("大文件清理", timeout=30)
            self.assert_true(widget.get_optimization_runtime_page_showing(timeout=30))
            # 等待扫描完成
            self.assert_true(widget.get_large_file_scan_completed(timeout=180))
            # 验证检测到大文件(结果页而非空状态页)
            self.assert_true(widget.get_large_file_result_showing())
            # 默认筛选 >=100MB, 应至少显示 2 个文件(110MB + 210MB)
            sleep(2)
            count_100mb = widget.get_large_file_table_row_count()
            self.assert_true(count_100mb >= 2)
            # 切换筛选到 >=200MB, 显示的文件数应减少(210MB 仍可见, 110MB 被过滤)
            widget.click_large_file_size_filter_option(1)
            sleep(2)
            count_200mb = widget.get_large_file_table_row_count()
            self.assert_true(count_200mb < count_100mb)
            self.assert_true(count_200mb >= 1)
            # 切换筛选到 >=500MB, 应无匹配文件
            widget.click_large_file_size_filter_option(2)
            sleep(2)
            self.assert_true(widget.get_large_file_no_match_showing())
            # 切换回 >=100MB, 应再次显示与初始筛选相同的文件数
            widget.click_large_file_size_filter_option(0)
            sleep(2)
            count_back = widget.get_large_file_table_row_count()
            self.assert_true(count_back >= 2)
            self.assert_true(count_back == count_100mb)
        finally:
            widget.restore_foreign_large_files(isolated)
            # 清理测试大文件
            widget.remove_large_test_files_for_filter()

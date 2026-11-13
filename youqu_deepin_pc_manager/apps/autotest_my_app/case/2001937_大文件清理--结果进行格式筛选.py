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

    def test_mycase_338(self):
        """大文件清理--结果进行格式筛选：验证大文件清理结果页可按文件格式分类筛选，
        点击不同分类按钮后表格仅显示对应格式的大文件，
        切换到无匹配文件的分类时显示"无匹配"提示"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理其他测试用例可能遗留的大文件, 避免干扰计数
        widget.remove_large_test_file()
        # 前置：创建不同格式的大文件(视频/归档/其他, 各100MB)
        widget.create_typed_large_test_files()
        isolated = []
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击大文件清理卡片, 进入大文件清理页面(扫描自动开始)
            isolated = widget.isolate_foreign_large_files()
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            # 等待扫描完成并验证结果页显示(检测到大文件)
            self.assert_true(widget.get_large_file_result_page_showing(timeout=180))
            self.assert_true(widget.get_large_file_has_results(timeout=15))

            # 记录"全部"分类下的行数作为基准
            self.assert_true(widget.get_large_file_category_button_checked("all"))
            all_count = widget.get_large_file_table_row_count()
            self.assert_true(all_count >= 3)

            # 点击"视频"分类, 验证仅显示视频格式文件
            self.assert_true(widget.click_large_file_category_button("video"))
            self.assert_true(widget.get_large_file_category_button_checked("video"))
            sleep(1)
            video_count = widget.get_large_file_table_row_count()
            self.assert_true(video_count == 1)

            # 点击"归档"分类, 验证仅显示归档格式文件
            self.assert_true(widget.click_large_file_category_button("archive"))
            self.assert_true(widget.get_large_file_category_button_checked("archive"))
            sleep(1)
            archive_count = widget.get_large_file_table_row_count()
            self.assert_true(archive_count == 1)

            # 点击"其他"分类, 验证仅显示其他格式文件
            self.assert_true(widget.click_large_file_category_button("other"))
            self.assert_true(widget.get_large_file_category_button_checked("other"))
            sleep(1)
            other_count = widget.get_large_file_table_row_count()
            self.assert_true(other_count == 1)

            # 点击"文档"分类(无匹配文件), 验证显示"无匹配"提示
            self.assert_true(widget.click_large_file_category_button("document"))
            self.assert_true(widget.get_large_file_category_button_checked("document"))
            sleep(1)
            self.assert_true(widget.get_large_file_no_match_showing())

            # 切换回"全部"分类, 验证所有文件恢复显示
            self.assert_true(widget.click_large_file_category_button("all"))
            self.assert_true(widget.get_large_file_category_button_checked("all"))
            sleep(1)
            final_count = widget.get_large_file_table_row_count()
            self.assert_true(final_count == all_count)
            self.assert_true(not widget.get_large_file_no_match_showing())
        finally:
            widget.restore_foreign_large_files(isolated)
            # 清理测试大文件
            widget.remove_typed_large_test_files()

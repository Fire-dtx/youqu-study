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

    def test_mycase_340(self):
        """大文件清理--彻底删除确认对话框：选中大文件后选择"彻底删除"操作，
        点击执行按钮时弹出确认对话框，验证对话框正确显示并可取消"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：创建测试用大文件(110MB, 满足大文件清理>=100MB阈值)
        widget.create_large_test_file()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 刷新 AT-SPI 树(页面切换后旧引用可能失效)
            widget.reconnect_dogtail()
            # 点击大文件清理卡片, 进入大文件清理页面(插件自动开始扫描)
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            # 等待扫描完成并验证结果页面显示
            self.assert_true(widget.get_large_file_result_page_showing(timeout=180))
            # 验证检测到大文件(结果页而非空状态页)
            self.assert_true(widget.get_large_file_has_results(timeout=15))
            # 选中第一行大文件
            widget.click_large_file_table_checkbox(0)
            # 验证执行按钮可用(选中文件后按钮应启用)
            self.assert_true(widget.get_large_file_execute_button_enabled())
            # 将操作下拉框切换为"彻底删除"
            widget.select_large_file_action("彻底删除")
            sleep(1)
            # 点击执行按钮, 触发彻底删除确认对话框
            widget.click_large_file_execute_button()
            sleep(2)
            # 验证彻底删除确认对话框弹出
            self.assert_true(widget.get_large_file_delete_confirm_dialog_showing(timeout=10))
            # 点击"取消"按钮关闭对话框, 不实际删除文件
            self.assert_true(
                widget.click_large_file_delete_confirm_dialog_button("取消", timeout=10)
            )
            sleep(1)
            # 验证对话框已关闭(不再可见)
            self.assert_false(widget.get_large_file_delete_confirm_dialog_showing(timeout=3))
        finally:
            # 清理测试大文件
            widget.remove_large_test_file()

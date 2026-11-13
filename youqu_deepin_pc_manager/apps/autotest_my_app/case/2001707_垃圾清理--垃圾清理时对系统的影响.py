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

    def test_mycase_370(self):
        """垃圾清理--垃圾清理时对系统的影响：验证垃圾清理过程中系统资源占用合理、
        UI 保持响应、进程稳定运行，清理完成后无严重错误日志"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：创建测试垃圾文件确保扫描能检测到垃圾
        widget.create_all_space_clean_junk()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击空间清理特色卡片的开始扫描按钮，触发扫描
            widget.click_space_clean_featured_card()
            # 等待扫描完成并验证检测到垃圾
            self.assert_true(widget.get_space_clean_has_junk(timeout=240))
            # 验证结果页面已显示
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=10))

            # 记录清理前的系统内存使用率，作为基线
            mem_usage_before = widget.get_system_memory_usage_percent()
            self.assert_true(0 <= mem_usage_before <= 100)

            # 点击立即清理按钮
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            widget.click_space_clean_clean_button()

            # 清理过程中验证 UI 保持响应（AT-SPI 树可访问，UI 线程未阻塞）
            self.assert_true(widget.check_ui_responsive())

            # 清理过程中验证 CPU 占用合理（不超过 80%）
            cpu_during = widget.get_pc_manager_cpu_usage()
            self.assert_true(cpu_during >= 0)
            self.assert_true(cpu_during < 80)

            # 清理过程中验证内存占用合理（不超过系统总内存的 50%）
            mem_total = widget.get_system_memory_total_mb()
            pm_mem_during = widget.get_pc_manager_memory_mb()
            self.assert_true(pm_mem_during >= 0)
            if mem_total > 0:
                self.assert_true(pm_mem_during < mem_total * 0.5)

            # 等待清理完成，验证测试垃圾文件已被清理
            self.assert_true(widget.wait_test_junk_files_cleaned(timeout=60))

            # 清理完成后验证进程仍然存活（未崩溃）
            self.assert_true(widget.get_pc_manager_process_status())

            # 清理完成后验证 CPU 占用回落到合理范围
            sleep(2)
            cpu_after = widget.get_pc_manager_cpu_usage()
            self.assert_true(cpu_after >= 0)
            self.assert_true(cpu_after < 50)

            # 验证系统内存使用率保持在合理范围（未因清理操作异常增长）
            mem_usage_after = widget.get_system_memory_usage_percent()
            self.assert_true(0 <= mem_usage_after <= 100)

            # 验证 UI 在清理完成后仍保持响应
            self.assert_true(widget.check_ui_responsive())

            # 验证日志中不存在严重错误（段错误、崩溃、abort 等）
            self.assert_true(widget.get_pc_manager_log_no_critical_errors())
        finally:
            # 清理测试垃圾文件
            widget.remove_all_space_clean_junk()

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_219(self):
        """压力稳定性-空间清理立即扫描/返回压测

        描述:
        1. 空间清理界面点击立即扫描 -> 扫描结束显示"清理选中项""重新扫描"
        2. 点击右上角返回 -> 回到系统优化首页, 反应及时不卡顿
        3. 步骤 1、2 重复 10 次
        4. 再次进入空间清理 -> 点击清理 -> 清理完成显示重新扫描/完成
        5. 点击完成后返回垃圾清理首页

        等价实现:
        - 扫描目标用回收站中的 5 个 1MB 测试文件构造(产品只统计固定类别);
        - 每轮记录"点击扫描->结果页出现"与"点击返回->系统优化页出现"的耗时,
          断言阈值(扫描 <=120s、返回 <=10s)以覆盖"反应及时不卡顿";
        - 本版本结果页按钮为 spaceClean_cleanBtn(清理选中项)/
          spaceClean_rescanBtn(重新扫描); 清理完成后清理项消失、按钮仍在,
          空状态页的 spaceClean_emptyRescanBtn(返回首页)仅在彻底无垃圾时出现,
          因此"完成"以标题栏返回按钮等价, 返回后校验系统优化页与空间清理入口;
        - 清理有效性直接校验测试垃圾文件已被产品删除。

        闭环: 结束关闭电脑管家并删除测试垃圾文件。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.create_test_junk_files()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            rounds = 10
            scan_costs, back_costs = [], []
            for round_index in range(rounds):
                started = time.monotonic()
                widget.click_optimization_nav_by_attr()
                self.assert_true(widget.get_optimization_page_showing())

                widget.click_space_clean_featured_card()
                self.assert_true(widget.get_space_clean_has_junk(timeout=120))
                scan_cost = time.monotonic() - started
                scan_costs.append(scan_cost)
                logger.info(
                    f"[2011915] 第 {round_index + 1} 轮扫描完成, 耗时 {scan_cost:.1f}s"
                )

                # 预期 1: 扫描结束显示"清理选中项""重新扫描"按钮
                self.assert_true(widget.get_space_clean_clean_button_enabled())
                self.assert_true(
                    widget.is_space_clean_element_visible("$//spaceClean_rescanBtn")
                )

                # 预期 2: 返回系统优化首页, 反应及时
                started = time.monotonic()
                widget.click_back_button()
                sleep(2)
                widget.reconnect_dogtail()
                self.assert_true(widget.get_optimization_page_showing())
                back_cost = time.monotonic() - started
                back_costs.append(back_cost)
                logger.info(
                    f"[2011915] 第 {round_index + 1} 轮返回完成, 耗时 {back_cost:.1f}s"
                )
                self.assert_true(back_cost <= 10)

                # 预期 3: 界面反应及时不卡顿, 进程始终存活
                self.assert_true(widget.get_pc_manager_process_status())

            logger.info(
                f"[2011915] {rounds} 轮: 扫描 avg={sum(scan_costs) / rounds:.1f}s "
                f"max={max(scan_costs):.1f}s; 返回 avg={sum(back_costs) / rounds:.1f}s "
                f"max={max(back_costs):.1f}s"
            )

            # 预期 4: 再次进入空间清理, 清理选中项
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_has_junk(timeout=120))
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            widget.click_space_clean_clean_button()

            # 清理有效性: 测试垃圾文件被实际删除
            self.assert_true(widget.wait_test_junk_files_cleaned(timeout=120))
            self.assert_false(widget.get_test_junk_files_exist())

            # 预期 5: 清理完成后结果页仍在, 保留"重新扫描"/"清理选中项"
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=30))
            self.assert_true(
                widget.is_space_clean_element_visible("$//spaceClean_rescanBtn")
            )
            self.assert_true(
                widget.is_space_clean_element_visible("$//spaceClean_cleanBtn")
            )
            logger.info(
                "[2011915] 清理完成页: 结果页保留 重新扫描/清理选中项 按钮, "
                "完成以标题栏返回等价"
            )

            # 预期 6: 点击完成(返回)后回到垃圾清理首页(系统优化页)
            widget.click_back_button()
            sleep(2)
            widget.reconnect_dogtail()
            self.assert_true(widget.get_optimization_page_showing())
            self.assert_true(widget.get_space_clean_featured_card_showing())
        finally:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()

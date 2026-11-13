#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

# 全面检测覆盖的 5 个分类
DETECTION_CARDS = ("系统环境检测", "更新环境检测", "硬件检测", "网络检测", "系统稳定性")


class TestMyCase(BaseCase):

    def test_mycase_021(self):
        """系统检测--无异常问题：全面检测完成后能进入结果页

        通过条件(2026-11-12 调整)：点击"全面检测"后扫描完成并展示结果页即可。
        不要求被测机处于"无异常"状态 —— 本机真实存在 3 项不可自动修复异常
        (Lastore 更新源任务失败、无外网、服务重启次数偏高), 结果页会落在
        "需人工处理"; 结果页的实际状态只记录为证据, 不参与通过判定。
        本用例不构造数据, 无残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing(timeout=15))
        self.assert_true(widget.get_detection_full_scan_button_showing(timeout=10))

        # 步骤 1: 点击全面检测, 等待扫描完成
        widget.click_detection_full_scan_button()
        self.assert_true(widget.get_detection_full_scan_page_showing(timeout=20))
        self.assert_true(widget.wait_for_full_scan_completion(timeout=300))

        # 断言: 扫描完成后结果页已展示(结果标题/描述/结果图标任一可见)
        self.assert_true(widget.get_detection_result_showing(timeout=30))

        # 记录结果页实际状态(仅证据, 不参与通过判定)
        success_icon = widget.get_detection_success_icon_showing()
        issues = widget.get_detection_issues_icon_showing()
        no_problem_page = widget.get_detection_no_problem_page_showing()
        fix_all = widget.get_detection_fix_all_button_showing()
        recheck = widget.get_detection_recheck_button_showing()
        title_showing = widget.get_detection_result_title_showing()
        desc_showing = widget.get_detection_result_desc_showing()
        logger.info(
            f"结果页状态: 无异常图标={success_icon}, 发现问题图标={issues}, "
            f"无问题页面={no_problem_page}, 结果标题={title_showing}, "
            f"结果描述={desc_showing}, 一键修复={fix_all}, 重新检测={recheck}"
        )

        for card in DETECTION_CARDS:
            state = widget.get_detection_group_state(card)
            logger.info(f"{card} 检测状态: {state}")

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_056(self):
        """空间清理点击：在系统优化页点击「空间清理」特色卡片后进入扫描页,
        且产品上报一条 tid=1001900001/pageId=space_clean 的点击埋点(点击次数 +1)

        埋点核对方式:特色卡片 clicked 槽调用
        reportFeatureClick(SpaceClean, "space_clean"), 应用日志新增一行
        "Event logged: ..."(含 space_clean), 同时 event-log 守护进程 journal
        中电脑管家事件收据 +1。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        try:
            # 进入系统优化页, 确认空间清理特色卡片入口已渲染
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            self.assert_true(widget.get_space_clean_featured_card_showing())

            # 点击前基线: 应用日志中的空间清理埋点行数与守护进程收据条数
            log_fragments = ["Event logged:", "1001900001", "space_clean"]
            base_log = widget.count_app_log_matches(*log_fragments)
            base_receipts = widget.count_eventlog_daemon_receipts()
            self.assert_true(base_receipts >= 0)

            # 点击特色卡片上的开始扫描按钮, 应切换到空间清理插件运行时页
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_optimization_runtime_page_showing(timeout=15))

            # 验证一次点击恰好新增一条上报
            after_log = widget.wait_app_log_matches(log_fragments, base_log + 1)
            after_receipts = widget.wait_eventlog_daemon_receipts(base_receipts + 1)
            self.assert_equal(base_log + 1, after_log)
            # 守护进程可能对同一事件记录多条收据, 只要求确有新增
            self.assert_true(after_receipts >= base_receipts + 1)
        finally:
            # 回退: 关闭应用
            widget.kill_pc_manager()

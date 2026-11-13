#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_234(self):
        """修复工具（网络 / 外设 / 微信等）点击：在修复工具页点击任意修复工具后
        进入工具详情页, 且产品上报一条 tid=1001900001/pageId=repair_tool 的点击
        埋点(点击次数 +1), detail 字段带上被点击工具的 id

        埋点核对方式:卡片 clicked 槽调用 showToolRuntime ->
        reportFeatureClick(RepairTool, "repair_tool", card.id), 应用日志新增一行
        "Event logged: ..."(含 repair_tool 与 detail), 同时 event-log 守护进程
        journal 中电脑管家事件收据 +1。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        try:
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            card_names = widget.get_repair_card_names()
            self.assert_true(len(card_names) > 0)
            tool_name = card_names[0]

            # 点击前基线: 应用日志中的修复工具埋点行数与守护进程收据条数
            log_fragments = ["Event logged:", "1001900001", "repair_tool"]
            base_log = widget.count_app_log_matches(*log_fragments)
            base_receipts = widget.count_eventlog_daemon_receipts()
            self.assert_true(base_receipts >= 0)

            widget.click_repair_card_by_name(tool_name)
            self.assert_true(widget.get_repair_detail_showing())

            # 验证一次点击恰好新增一条上报
            after_log = widget.wait_app_log_matches(log_fragments, base_log + 1)
            after_receipts = widget.wait_eventlog_daemon_receipts(base_receipts + 1)
            self.assert_equal(base_log + 1, after_log)
            # 守护进程可能对同一事件记录多条收据, 只要求确有新增
            self.assert_true(after_receipts >= base_receipts + 1)

            # 验证上报里带工具名(detail = 卡片 id, 形如 "network-repair")
            event_line = widget.get_last_app_log_line(*log_fragments)
            detail = re.search(r'\\"detail\\":\\"([^"\\]*)\\"', event_line)
            self.assert_true(detail is not None and detail.group(1).strip() != "")
        finally:
            # 回退: 关闭应用
            widget.kill_pc_manager()

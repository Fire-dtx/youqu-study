#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):
    def test_mycase_230(self):
        """系统检测 - 全面检测点击:点击全面检测按钮后进入全面检测页面,
        且产品上报一条 tid=1001900001/pageId=detection_full 的点击埋点

        埋点核对方式:产品 TelemetryService 在按钮 clicked 槽里调用
        reportFeatureClick(DetectionFull, "detection_full"), 经
        libdeepin-event-log.so 发到 system 总线
        org.deepin.EventLog1.ReportEventLog(packagename, eventinfo)。
        证据分两段:
        1) 应用日志新增一行 "Event logged: ...", 内容含 tid=1001900001 与
           pageId/pageName=detection_full, 证明事件内容与产品定义一致;
        2) event-log 守护进程 journal 中电脑管家事件收据 +1, 证明事件确实
           被 system 总线服务接收(对应用例的"点击次数 + 1")。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        try:
            # 导航到系统检测页面
            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            # 验证全面检测按钮可见且可点击
            self.assert_true(widget.get_detection_full_scan_button_showing())

            # 点击前基线: 应用日志中的点击埋点行数与守护进程收据条数
            log_fragments = ("Event logged:", "1001900001", "detection_full")
            base_log = widget.count_app_log_matches(*log_fragments)
            base_receipts = widget.count_eventlog_daemon_receipts()
            self.assert_true(base_receipts >= 0)

            # 点击全面检测按钮, 验证进入全面检测页面
            widget.click_detection_full_scan_button()
            self.assert_true(widget.get_detection_full_scan_page_showing(timeout=15))

            # 验证一次点击恰好新增一条上报
            after_log = widget.wait_app_log_matches(log_fragments, base_log + 1)
            after_receipts = widget.wait_eventlog_daemon_receipts(base_receipts + 1)
            self.assert_equal(base_log + 1, after_log)
            # 守护进程可能对同一事件记录多条收据, 只要求确有新增
            self.assert_true(after_receipts >= base_receipts + 1)
        finally:
            # 回退: 关闭应用
            widget.kill_pc_manager()

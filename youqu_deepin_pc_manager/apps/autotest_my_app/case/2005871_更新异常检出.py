#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_236(self):
        """更新异常检出：给 /etc/apt/sources.list 加不可变属性(chattr +i,
        模拟文件权限被篡改)后执行「更新环境检测」, 检测结果上报一条
        tid=1001900002 的检出埋点, abnormalItems 中含仓库权限类异常项

        埋点核对方式:分项检测完成时 detection_page.cpp 调用
        reportDetectionResult(level, normal, abnormal, titles, reasons),
        应用日志新增一行 "Event logged: ..."(含 tid 1001900002), 同时
        event-log 守护进程 journal 中电脑管家事件收据新增。
        """
        sources = "/etc/apt/sources.list"
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        immutable_set = False
        try:
            # 数据构造: 给软件源配置文件加不可变属性
            def attr_flags() -> str:
                out = widget.sudo_run_cmd(f"lsattr {sources}", timeout=10,
                                          out_debug_flag=False) or ""
                fields = out.split()
                return fields[0] if fields else ""

            if "i" not in attr_flags():
                widget.sudo_run_cmd(f"chattr +i {sources}", timeout=10,
                                    out_debug_flag=False)
                immutable_set = True
            self.assert_true("i" in attr_flags())

            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            log_fragments = ["Event logged:", "1001900002"]
            base_log = widget.count_app_log_matches(*log_fragments)
            base_receipts = widget.count_eventlog_daemon_receipts()
            self.assert_true(base_receipts >= 0)

            # 执行「更新环境检测」并等待该分项检测完成
            self.assert_true(widget.run_detection_item("更新环境检测", timeout=240))

            after_log = widget.wait_app_log_matches(log_fragments, base_log + 1, timeout=30)
            after_receipts = widget.wait_eventlog_daemon_receipts(base_receipts + 1)
            self.assert_equal(base_log + 1, after_log)
            # 守护进程可能对同一事件记录多条收据, 只要求确有新增
            self.assert_true(after_receipts >= base_receipts + 1)

            # 检出的异常项应指向软件源权限被篡改
            event_line = widget.get_last_app_log_line(*log_fragments)
            abnormal = re.search(r'\\"abnormalCount\\":(\d+)', event_line)
            items = re.findall(r'\\"(?:title|reason)\\":\\"(.*?)\\"', event_line)
            if abnormal is None or int(abnormal.group(1)) == 0:
                logger.warning(f"检出埋点未包含异常项: {event_line}")
            self.assert_true(abnormal is not None and int(abnormal.group(1)) > 0)
            if not any(("权限" in item or "只读" in item) for item in items):
                logger.warning(f"异常项中未出现权限/只读关键字: {items}")
            self.assert_true(any(("权限" in item or "只读" in item) for item in items))

            self.assert_true(widget.leave_detection_runtime_page())
        finally:
            # 数据回退: 去掉不可变属性, 恢复软件源可写
            if immutable_set:
                widget.sudo_run_cmd(f"chattr -i {sources}", timeout=10,
                                    out_debug_flag=False)
            widget.kill_pc_manager()

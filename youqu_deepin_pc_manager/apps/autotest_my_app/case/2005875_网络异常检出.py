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

# 阻断到公网 80/443 的规则(出方向)。管理链路是同网段, 不受影响, 不会把自己踢掉。
# 用完整规则串做 -C/-D, 避免按行号删除误伤机器上已有规则。
IPTABLES_RULE = (
    "-p tcp -m multiport --dports 80,443 -d 0.0.0.0/0 "
    "-m addrtype ! --dst-type LOCAL -j DROP"
)


class TestMyCase(BaseCase):

    def test_mycase_238(self):
        """网络异常检出：在"网络访问不通"的现场执行「网络检测」,
        检测结果上报一条 tid=1001900002 的检出埋点, abnormalItems 中含
        网络访问项, 原因为网络连接错误

        埋点核对方式:分项检测完成时 detection_page.cpp 调用
        reportDetectionResult(level, normal, abnormal, titles, reasons),
        应用日志新增一行 "Event logged: ..."(含 tid 1001900002), 同时
        event-log 守护进程 journal 中电脑管家事件收据新增。

        数据构造: iptables 出方向丢弃到公网的 80/443(公网访问不通, 同网段
        管理链路不受影响), 用例结束按完整规则串删除该条规则并校验无残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        rule_added = False

        def rule_exists() -> bool:
            out = widget.sudo_run_cmd(
                f"iptables -C OUTPUT {IPTABLES_RULE} 2>/dev/null && echo yes || true",
                timeout=10,
                out_debug_flag=False,
            )
            return "yes" in (out or "")

        try:
            # ---- 构造: 公网访问异常 ----
            if not rule_exists():
                widget.sudo_run_cmd(
                    f"iptables -I OUTPUT 1 {IPTABLES_RULE}",
                    timeout=20,
                    out_debug_flag=False,
                )
                rule_added = True
            self.assert_true(rule_exists())

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            log_fragments = ["Event logged:", "1001900002"]
            base_log = widget.count_app_log_matches(*log_fragments)
            base_receipts = widget.count_eventlog_daemon_receipts()
            self.assert_true(base_receipts >= 0)

            # 执行「网络检测」并等待该分项检测完成
            self.assert_true(widget.run_detection_item("网络检测", timeout=180))

            after_log = widget.wait_app_log_matches(log_fragments, base_log + 1, timeout=30)
            after_receipts = widget.wait_eventlog_daemon_receipts(base_receipts + 1)
            self.assert_equal(base_log + 1, after_log)
            # 守护进程可能对同一事件记录多条收据, 只要求确有新增
            self.assert_true(after_receipts >= base_receipts + 1)

            # 检出的异常项应是网络访问(公网访问不通)
            event_line = widget.get_last_app_log_line(*log_fragments)
            abnormal = re.search(r'\\"abnormalCount\\":(\d+)', event_line)
            items = re.findall(r'\\"(?:title|reason)\\":\\"(.*?)\\"', event_line)
            if abnormal is None or int(abnormal.group(1)) == 0:
                logger.warning(f"检出埋点未包含异常项: {event_line}")
            self.assert_true(abnormal is not None and int(abnormal.group(1)) > 0)
            logger.info(f"网络检测异常项: {items}")
            if not any("网络访问" in item for item in items):
                logger.warning(f"异常项中未出现网络访问: {items}")
            self.assert_true(any("网络访问" in item for item in items))

            self.assert_true(widget.leave_detection_runtime_page())
        finally:
            # 回退: 删除本用例新增的 iptables 规则并校验无残留, 再关闭应用
            if rule_added:
                widget.sudo_run_cmd(
                    f"iptables -D OUTPUT {IPTABLES_RULE}",
                    timeout=20,
                    out_debug_flag=False,
                )
            self.assert_false(rule_exists())
            widget.kill_pc_manager()

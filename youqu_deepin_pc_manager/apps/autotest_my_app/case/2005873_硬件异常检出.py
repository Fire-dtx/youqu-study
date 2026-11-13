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

    def test_mycase_237(self):
        """硬件异常检出：在 CPU 温度检测工具(lm-sensors)缺失的环境下执行
        「硬件检测」, 检测结果上报一条 tid=1001900002 的检出埋点, abnormalItems
        中含 CPU 温度项, 原因为温度检测包缺失

        埋点核对方式:分项检测完成时 detection_page.cpp 调用
        reportDetectionResult(level, normal, abnormal, titles, reasons),
        应用日志新增一行 "Event logged: ..."(含 tid 1001900002), 同时
        event-log 守护进程 journal 中电脑管家事件收据新增。

        数据构造: 场景要求 lm-sensors 缺失。与 `1999123 test_mycase_324` 同一
        构造方式 —— 把 `sensors` 二进制临时移走(`/usr/bin/sensors.autotest_bak`),
        等价于未安装, 用例结束移回并校验可执行。不卸载包、不改 dpkg 状态,
        因此不会被其它用例的依赖预检(如 288 会 apt 安装 lm-sensors)破坏。
        """
        widget = MyAppWidget(check_start=False)
        sensors_bak = "/usr/bin/sensors.autotest_bak"
        sensors_moved = False
        # ---- 构造前置: sensors 命令不存在 ----
        sensors_path = widget.run_cmd(
            "command -v sensors 2>/dev/null || true", timeout=5, out_debug_flag=False
        ).strip()
        if sensors_path:
            logger.warning(f"环境存在 sensors({sensors_path}), 临时移走以构造缺失场景")
            widget.sudo_run_cmd(
                f"rm -f {sensors_bak}; mv {sensors_path} {sensors_bak}",
                timeout=10,
                out_debug_flag=False,
            )
            sensors_moved = True
        self.assert_equal(
            "",
            widget.run_cmd(
                "command -v sensors 2>/dev/null || true", timeout=5, out_debug_flag=False
            ).strip(),
        )

        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        try:
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            log_fragments = ["Event logged:", "1001900002"]
            base_log = widget.count_app_log_matches(*log_fragments)
            base_receipts = widget.count_eventlog_daemon_receipts()
            self.assert_true(base_receipts >= 0)

            # 执行「硬件检测」并等待该分项检测完成
            self.assert_true(widget.run_detection_item("硬件检测", timeout=240))

            after_log = widget.wait_app_log_matches(log_fragments, base_log + 1, timeout=30)
            after_receipts = widget.wait_eventlog_daemon_receipts(base_receipts + 1)
            self.assert_equal(base_log + 1, after_log)
            # 守护进程可能对同一事件记录多条收据, 只要求确有新增
            self.assert_true(after_receipts >= base_receipts + 1)

            # 检出的异常项应是 CPU 温度检测, 原因为 lm-sensors 缺失
            event_line = widget.get_last_app_log_line(*log_fragments)
            abnormal = re.search(r'\\"abnormalCount\\":(\d+)', event_line)
            items = re.findall(r'\\"(?:title|reason)\\":\\"(.*?)\\"', event_line)
            if abnormal is None or int(abnormal.group(1)) == 0:
                logger.warning(f"检出埋点未包含异常项: {event_line}")
            self.assert_true(abnormal is not None and int(abnormal.group(1)) > 0)
            if not any("lm-sensors" in item for item in items):
                logger.warning(f"异常项中未出现 lm-sensors 原因: {items}")
            self.assert_true(any("lm-sensors" in item for item in items))

            self.assert_true(widget.leave_detection_runtime_page())
        finally:
            # 回退: 恢复 sensors 二进制(必须校验, 否则测试机失去温度检测能力)
            if sensors_moved:
                widget.sudo_run_cmd(
                    f"mv {sensors_bak} /usr/bin/sensors", timeout=10, out_debug_flag=False
                )
            self.assert_true(bool(
                widget.run_cmd(
                    "command -v sensors 2>/dev/null", timeout=5, out_debug_flag=False
                ).strip()
            ))
            widget.kill_pc_manager()

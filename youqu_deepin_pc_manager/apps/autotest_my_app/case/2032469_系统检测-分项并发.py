#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    CARD = "网络检测"
    APP_LOG = "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log"
    START_PATTERN = 'startTask "Detect" key "networkcheck.'

    def _count_start_tasks(self) -> int:
        out = self.widget.run_cmd(
            f"grep -ac '{self.START_PATTERN}' {self.APP_LOG} 2>/dev/null; true",
            timeout=10, out_debug_flag=False,
        )
        numbers = re.findall(r"(\d+)", out)
        return int(numbers[-1]) if numbers else 0

    def _new_start_timestamps(self, before: int) -> list:
        """取本次点击后新增的网络检测任务启动时间(秒, 含毫秒小数)"""
        out = self.widget.run_cmd(
            f"grep -a '{self.START_PATTERN}' {self.APP_LOG} 2>/dev/null | "
            f"tail -n +{before + 1}",
            timeout=10, out_debug_flag=False,
        )
        stamps = []
        for line in out.splitlines():
            matched = re.search(r"\d{4}-\d{2}-\d{2}, (\d{2}):(\d{2}):(\d{2})\.(\d{3})", line)
            if not matched:
                continue
            hour, minute, second, milli = (int(g) for g in matched.groups())
            stamps.append(hour * 3600 + minute * 60 + second + milli / 1000.0)
        return stamps

    def test_mycase_091(self):
        """系统检测-分项并发：同一分类下全部检测项同时开始并发执行

        步骤: 进入系统检测 -> 点击"网络检测"分类(该分类共 7 个检测项)。
        预期: 7 个检测项同时进行。应用按调度器 8 槽位并发下发检测任务,
        实测 7 个检测项的 startTask 下发时间落在同一时刻(毫秒级间隔),
        且分组进度最终满额(7/7)。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            item_count = len(widget.get_detection_item_names(self.CARD))
            logger.info(f"[2032469] {self.CARD} item_count={item_count}")
            self.assert_true(item_count >= 5)

            before = self._count_start_tasks()
            self.assert_true(widget.click_detection_card(self.CARD))
            self.assert_true(widget.wait_detection_group_completion(self.CARD, timeout=180))
            stamps = self._new_start_timestamps(before)
            span_ms = round((max(stamps) - min(stamps)) * 1000, 3) if len(stamps) > 1 else None
            state = widget.get_detection_group_state(self.CARD)
            logger.info(
                f"[2032469] start_count={len(stamps)} span_ms={span_ms} state={state}"
            )
            # 分类内全部检测项均被下发, 且同时开始(下发时间跨度 < 1 秒)
            self.assert_true(len(stamps) == item_count)
            self.assert_true(span_ms is not None and span_ms < 1000)
            self.assert_true(state["checked"] == item_count)
        finally:
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

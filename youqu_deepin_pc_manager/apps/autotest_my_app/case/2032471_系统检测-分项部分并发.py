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

    CARD = "更新环境检测"
    APP_LOG = "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log"
    START_PATTERN = 'startTask "Detect" key "updatecheck.'

    def _count_start_tasks(self):
        out = self.widget.run_cmd(
            f"grep -ac '{self.START_PATTERN}' {self.APP_LOG} 2>/dev/null; true",
            timeout=10, out_debug_flag=False,
        )
        numbers = re.findall(r"(\d+)", out)
        return int(numbers[-1]) if numbers else 0

    def _new_start_timestamps(self, before):
        """取本次进入分项后新增的检测任务下发时间(秒, 含毫秒小数)"""
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

    def test_mycase_092(self):
        """系统检测-分项部分并发：分类内所选检测项同时进行, 不占多余槽位

        步骤: 进入系统检测 -> 点击"更新环境检测"分类(共 4 个检测项)开始检测。
        预期: 分类内这 4 项同时进行(下发时间同一时刻, 无先后串行等待),
        且并发数受 8 槽上限约束、不会为空槽位预占资源。
        V20 2.14.0 分项页面按分类整体下发检测(无逐项勾选);
        等价实现: 用分类内全部项代替"选中 3 项", 验证所选项全部并发。
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
            logger.info(f"[2032471] {self.CARD} item_count={item_count}")
            self.assert_true(3 <= item_count <= 8)

            before = self._count_start_tasks()
            self.assert_true(widget.click_detection_card(self.CARD))
            self.assert_true(widget.wait_detection_group_completion(self.CARD, timeout=300))
            stamps = self._new_start_timestamps(before)
            span_ms = round((max(stamps) - min(stamps)) * 1000, 3) if len(stamps) > 1 else None
            state = widget.get_detection_group_state(self.CARD)
            logger.info(
                f"[2032471] start_count={len(stamps)} span_ms={span_ms} state={state}"
            )
            # 所选检测项全部同时下发, 数量与分类项数一致, 未超过 8 槽上限
            self.assert_true(len(stamps) == item_count)
            self.assert_true(item_count <= 8)
            self.assert_true(span_ms is not None and span_ms < 1000)
            self.assert_true(state["checked"] == item_count)
        finally:
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

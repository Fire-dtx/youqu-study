#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep

# 系统检测首页的 5 个分项分类(全面检测按分类依次/并行执行)
GROUPS = ("系统环境检测", "更新环境检测", "硬件检测", "网络检测", "系统稳定性")

# 折叠态 DetectionGroupWidget 固定高度 40, 展开态含检测项列表, 高度明显更大
COLLAPSED_HEIGHT = 40
EXPANDED_THRESHOLD = 60

RESULT_EXPRS = ("$//detection_resultTitle", "$//detection_resultDesc",
                "$//detection_noProblemPage", "$//detection_issuesIcon")


class TestMyCase(BaseCase):

    @staticmethod
    def _group_snapshot(widget, name):
        """读取一个检测分类的当前状态

        被测应用 DetectionGroupWidget: 折叠时 setFixedHeight(40),
        展开时高度恢复正常(含检测项列表), 因此以元素高度区分展开/收起;
        accessibleDescription 形如
        "Detection group: 系统环境检测, 已检查 2/6 项，发现 0 项问题",
        从中解析已检查项数与总项数。

        :return: (高度, checked, total, description) 或 None(分类不存在)
        """
        try:
            elements = widget.dog.find_elements_by_attr(f"$//detectionGroup_{name}")
        except BaseException:
            return None
        best = None
        for element in elements:
            try:
                width, height = element.size
            except BaseException:
                continue
            if width <= 0 and height <= 0:
                continue
            description = (element.description or "").strip()
            matched = re.search(r"(\d+)\s*/\s*(\d+)", description)
            checked, total = (
                (int(matched.group(1)), int(matched.group(2))) if matched else (-1, -1)
            )
            candidate = (int(height), checked, total, description)
            if best is None or candidate[0] > best[0]:
                best = candidate
        return best

    @classmethod
    def _any_visible(cls, widget, *exprs) -> bool:
        for expr in exprs:
            try:
                elements = widget.dog.find_elements_by_attr(expr)
            except BaseException:
                continue
            for element in elements:
                try:
                    if element.showing or (element.size and element.size[0] > 0):
                        return True
                except BaseException:
                    continue
        return False

    def test_mycase_020(self):
        """系统检测--分类自动展开收起：
        点击全面检测后持续采样 5 个检测分类的展开状态(以分类控件高度区分,
        折叠态固定 40px), 验证:
        1. 检测过程中当前正在检测的分类自动展开(检测项列表可见);
        2. 不同分类先后自动展开(下一分类继续展开);
        3. 分类检测完成后自动收起, 且完成后不会一直保持展开;
        4. 检测完成后进入结果页面。
        本用例仅观察 UI 状态, 不构造任何数据。"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing(timeout=15))
        self.assert_true(widget.get_detection_full_scan_button_showing(timeout=10))

        widget.click_detection_full_scan_button()
        self.assert_true(widget.get_detection_full_scan_page_showing(timeout=20))

        # 采样各分类的展开状态与检测进度
        samples = []
        for _ in range(150):
            snapshot = {name: self._group_snapshot(widget, name) for name in GROUPS}
            samples.append(snapshot)
            if self._any_visible(widget, *RESULT_EXPRS):
                break
            sleep(1)

        for index, snapshot in enumerate(samples):
            pretty = {}
            for name, value in snapshot.items():
                if value is None:
                    pretty[name] = None
                else:
                    height, checked, total, _ = value
                    pretty[name] = {
                        "h": height,
                        "expanded": height > EXPANDED_THRESHOLD,
                        "checked": checked,
                        "total": total,
                    }
            logger.info(f"采样{index}: {pretty}")

        # 断言 1: 检测过程中至少有一个分类自动展开
        expanded_names = set()
        any_expanded_sample = False
        for snapshot in samples:
            for name, value in snapshot.items():
                if value is not None and value[0] > EXPANDED_THRESHOLD:
                    expanded_names.add(name)
                    any_expanded_sample = True
        logger.info(f"检测期间自动展开过的分类: {sorted(expanded_names)}")
        self.assert_true(any_expanded_sample)
        self.assert_true(len(expanded_names) >= 2)

        # 断言 2: 已检测完成(checked == total > 0)的分类自动收起;
        # 允许一个采样点的瞬时过渡, 但连续两个采样点仍展开即判失败
        violations = []
        for index in range(len(samples) - 1):
            for name in GROUPS:
                current = samples[index].get(name)
                nxt = samples[index + 1].get(name)
                if current is None or nxt is None:
                    continue
                height, checked, total, _ = current
                if total <= 0 or checked != total:
                    continue
                if height > EXPANDED_THRESHOLD and nxt[0] > EXPANDED_THRESHOLD:
                    violations.append((index, name, height, nxt[0]))
        logger.info(f"完成后仍保持展开的异常样本: {violations[:10]}")
        self.assert_true(len(violations) == 0)

        # 断言 3: 检测完成后进入结果页面
        self.assert_true(widget.wait_for_full_scan_completion(timeout=120))
        self.assert_true(widget.get_detection_result_showing(timeout=20))

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from time import sleep

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


def normalize(text):
    """归一化修复项文案(产品按钮存在空格差异, 如 "USB 设备修复")"""
    return "".join(str(text).split()).lower()


class TestMyCase(BaseCase):

    def _wait_card_names(self, widget, timeout=15):
        """等待修复列表刷新稳定(连续两次读取一致)后返回可见修复项名称

        搜索框输入后列表是异步刷新的, 直接读取可能拿到刷新前的旧数据,
        因此连续两次读取结果一致才认为刷新完成。
        """
        previous = None
        current = []
        for _ in range(timeout):
            current = widget.get_repair_visible_card_names()
            signature = tuple(sorted(normalize(name) for name in current))
            if signature == previous:
                return current
            previous = signature
            sleep(1)
        return current

    def _wait_cards_matching(self, widget, predicate, timeout=15):
        """轮询等待可见修复项满足条件后返回当前列表

        :param predicate: 接收可见修复项名称列表, 返回是否满足预期
        """
        current = []
        for _ in range(timeout):
            current = widget.get_repair_visible_card_names()
            if predicate(current):
                return current
            sleep(1)
        return current

    def test_mycase_029(self):
        """修复工具--搜索功能：验证搜索框按关键词过滤、清空恢复及空结果提示"""
        widget = MyAppWidget(check_start=False)
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            # 验证搜索框可见
            self.assert_true(widget.get_repair_search_edit_showing())

            # 前置条件: 存在“网络修复”、“输入法”工具(输入法相关工具名为“重启输入法”)
            baseline = self._wait_card_names(widget)
            baseline_set = {normalize(name) for name in baseline}
            print("DIAG baseline=%r" % baseline)
            self.assert_true(len(baseline_set) > 0)
            self.assert_true("网络修复" in baseline_set)
            self.assert_true(any("输入法" in name for name in baseline_set))
            # 列表中确有多个工具, 搜索才有过滤空间
            self.assert_true(len(baseline_set) >= 2)
            # 初始状态不应出现“未找到”空状态
            self.assert_false(widget.get_repair_empty_state_showing())

            # ---- 步骤1: 输入“网络”, 列表仅显示“网络修复” ----
            widget.input_repair_search("网络")
            net_cards = self._wait_cards_matching(
                widget,
                lambda names: {normalize(name) for name in names} == {"网络修复"},
            )
            net_set = {normalize(name) for name in net_cards}
            print("DIAG 网络=%r" % net_cards)
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(net_set == {"网络修复"})
            self.assert_true(len(net_cards) == 1)
            # 其余工具被过滤掉(取基线中一个与“网络”无关的工具反向断言)
            other_tool = next(name for name in baseline_set if "网络" not in name)
            self.assert_true(other_tool not in net_set)
            self.assert_false(widget.get_repair_empty_state_showing())

            # ---- 步骤2: 输入“输入法”, 列表仅显示输入法相关工具 ----
            widget.input_repair_search("输入法")
            ime_cards = self._wait_cards_matching(
                widget,
                lambda names: len(names) == 1 and "输入法" in normalize(names[0]),
            )
            print("DIAG 输入法=%r" % ime_cards)
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(len(ime_cards) == 1)
            self.assert_true("输入法" in normalize(ime_cards[0]))
            self.assert_false(widget.get_repair_empty_state_showing())

            # ---- 步骤3: 清空搜索框, 列表恢复显示所有工具 ----
            widget.clear_repair_search()
            restored = self._wait_cards_matching(
                widget,
                lambda names: {normalize(name) for name in names} == baseline_set,
            )
            restored_set = {normalize(name) for name in restored}
            print("DIAG restored=%r" % restored)
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(restored_set == baseline_set)
            self.assert_true(len(restored) == len(baseline))
            self.assert_false(widget.get_repair_empty_state_showing())

            # ---- 步骤4: 输入不存在的关键词, 列表区域显示“未找到匹配的修复工具” ----
            widget.input_repair_search("不存在的工具")
            empty_cards = self._wait_cards_matching(widget, lambda names: len(names) == 0)
            labels = {
                label["name"]: label
                for label in widget.get_repair_empty_state_labels()
            }
            print("DIAG 不存在的工具 cards=%r labels=%r" % (empty_cards, labels))
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(len(empty_cards) == 0)
            # 产品把空状态标题/副标题的 accessible name 固定为 objectName,
            # AT-SPI 读不到“未找到匹配的修复工具”“请尝试其他关键词”文案,
            # 以标题 + 副标题标签实际渲染(size 非零)作为等价断言。
            self.assert_true(widget.get_repair_empty_state_showing())
            for label_name in ("repair_emptyTitle", "repair_emptyText"):
                self.assert_true(label_name in labels)
                self.assert_true(labels[label_name]["width"] > 0)
                self.assert_true(labels[label_name]["height"] > 0)

            # 回退筛选状态, 列表恢复
            widget.clear_repair_search()
            final_cards = self._wait_cards_matching(
                widget, lambda names: len(names) == len(baseline)
            )
            self.assert_true(len(final_cards) == len(baseline))
            self.assert_false(widget.get_repair_empty_state_showing())
        finally:
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

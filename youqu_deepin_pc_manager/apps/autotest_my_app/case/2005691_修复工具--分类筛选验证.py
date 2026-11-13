#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from time import sleep

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


def normalize(text):
    """归一化修复项文案: 产品按钮存在空格差异(如 "USB 设备修复")"""
    return "".join(str(text).split()).lower()


class TestMyCase(BaseCase):

    def _visible_sections(self, widget):
        """读取当前真正可见的分区(产品把未选中分类的分区缩成 0x0)"""
        return widget.get_repair_visible_sections_detail()

    def _wait_visible_sections(self, widget, timeout=15):
        """等待筛选结果稳定(连续两次读取一致)后返回可见分区明细"""
        previous = None
        current = []
        for _ in range(timeout):
            current = self._visible_sections(widget)
            signature = (
                len(current),
                tuple(
                    frozenset(normalize(card) for card in section["cards"])
                    for section in current
                ),
            )
            if current and signature == previous:
                return current
            previous = signature
            sleep(1)
        return current

    @staticmethod
    def _section_sets(sections):
        return [frozenset(normalize(card) for card in s["cards"]) for s in sections]

    def test_mycase_028(self):
        """修复工具--分类筛选验证：验证分类标签能正确筛选修复工具列表"""
        widget = MyAppWidget(check_start=False)
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_cards_view_showing())

            # ---- 基准数据: "全部"视图下各分类分区的修复项 ----
            baseline = self._wait_visible_sections(widget)
            baseline_sets = self._section_sets(baseline)
            print(
                "DIAG baseline=%r"
                % [(s["title"], s["cards"]) for s in baseline]
            )
            # 前置条件: 列表中存在至少两个不同分类的工具
            self.assert_true(len(baseline) >= 2)
            for section in baseline:
                self.assert_true(len(section["cards"]) > 0)
            # 每个修复项只能归属一个分类(分类不串位)
            owner = {}
            for index, card_set in enumerate(baseline_sets):
                for card in card_set:
                    self.assert_true(card not in owner)
                    owner[card] = index

            # ---- 分类标签 ----
            tab_count = widget.get_repair_category_tab_count()
            print("DIAG tab_count=%s sections=%s" % (tab_count, len(baseline)))
            # 一个"全部"标签 + 每个分类一个标签
            self.assert_true(tab_count == len(baseline) + 1)

            # ---- 逐个点击标签, 记录筛选后实际可见的分区 ----
            results = {}
            for tab_index in range(tab_count):
                self.assert_true(widget.click_repair_category_tab_by_index(tab_index))
                self.assert_true(widget.get_repair_page_showing())
                visible = self._wait_visible_sections(widget)
                visible_sets = self._section_sets(visible)
                results[tab_index] = visible_sets
                print(
                    "DIAG tab=%s -> %r"
                    % (tab_index, [sorted(s) for s in visible_sets])
                )

            # ---- 步骤3 的基准: 只有一个标签显示全部分类(即"全部"标签) ----
            all_tabs = [
                index
                for index, sets in results.items()
                if set(sets) == set(baseline_sets) and len(sets) == len(baseline_sets)
            ]
            print("DIAG all_tabs=%r" % all_tabs)
            self.assert_true(len(all_tabs) == 1)
            all_tab = all_tabs[0]

            # ---- 步骤1/2: 其余标签各自只显示一个分类, 且分类不重复 ----
            filtered = {}
            for index, sets in results.items():
                if index == all_tab:
                    continue
                self.assert_true(len(sets) == 1)
                category = sets[0]
                self.assert_true(category in baseline_sets)
                self.assert_true(category not in filtered.values())
                filtered[index] = category
            print("DIAG filtered=%r" % {k: sorted(v) for k, v in filtered.items()})
            # 每个分类都有对应的筛选标签, 且都只显示本分类的工具
            self.assert_true(set(filtered.values()) == set(baseline_sets))

            # 显式覆盖描述中的"系统修复"/"桌面修复"两个标签:
            # 标签文案在 V20 上不可读, 以该分类独有的修复项反查其标签
            def tab_of(card):
                key = normalize(card)
                section = owner[key]
                for index, category in filtered.items():
                    if category == baseline_sets[section]:
                        return index
                return None

            system_tab = tab_of("网络修复")
            desktop_tab = tab_of("密钥环修复")
            print("DIAG system_tab=%r desktop_tab=%r" % (system_tab, desktop_tab))
            self.assert_true(system_tab is not None)
            self.assert_true(desktop_tab is not None)
            self.assert_true(system_tab != desktop_tab)
            # 系统修复标签: 只显示系统修复分类的工具
            self.assert_true(
                results[system_tab] == [baseline_sets[owner[normalize("网络修复")]]]
            )
            # 桌面修复标签: 只显示桌面修复分类的工具(不含系统修复项)
            self.assert_true(
                results[desktop_tab] == [baseline_sets[owner[normalize("密钥环修复")]]]
            )
            self.assert_true(
                normalize("网络修复") not in results[desktop_tab][0]
            )

            # ---- 步骤3: 点击"全部", 列表恢复显示所有分类的工具 ----
            self.assert_true(widget.click_repair_category_tab_by_index(all_tab))
            restored = self._wait_visible_sections(widget)
            restored_sets = self._section_sets(restored)
            print("DIAG restored=%r" % [sorted(s) for s in restored_sets])
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_cards_view_showing())
            self.assert_true(len(restored_sets) == len(baseline_sets))
            self.assert_true(set(restored_sets) == set(baseline_sets))
            self.assert_true(
                {normalize(card) for cards in restored_sets for card in cards}
                == {normalize(card) for cards in baseline_sets for card in cards}
            )
        finally:
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

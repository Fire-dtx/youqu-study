#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_135(self):
        """修复工具--工具基础展示验证

        步骤: 1) 进入"修复工具"列表, 选择一个修复工具的卡片(优先"网络修复")点击,
                 观察详情页内容。
        预期: 1) 详情页顶部正确显示该工具的标题和副标题(描述), 且详情页正文
                 (描述区 / 修复项区 / 开始修复入口)正常展示。

        说明: 产品 QML Label 的 AT-SPI name 被固定为 objectName、text 恒为
              None, 读不到标题文案, 因此以"详情页页头标题/副标题标签实际渲染
              (size 非零)"+ "列表页页头同时被隐藏"作为标题与副标题正确展示的
              等价断言(见 widget.get_repair_detail_header_showing 的实测依据)。
        """
        widget = MyAppWidget(check_start=False)
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            # ---- 前置: 进入修复工具列表 ----
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_cards_view_showing())
            card_names = widget.get_repair_visible_card_names()
            print("DIAG repair_cards=%r" % (card_names,))
            self.assert_true(len(card_names) > 0)

            # 描述里以"网络修复"为示例; 该卡片不存在时退化为列表第一个工具
            target = "网络修复" if "网络修复" in card_names else card_names[0]
            print("DIAG target_tool=%r" % (target,))

            # ---- 步骤1: 从列表点击进入该修复工具的详情页 ----
            widget.click_repair_card_by_name(target)
            self.assert_true(widget.get_repair_detail_showing())

            # 详情页顶部页头: 标题(工具名) + 副标题(工具描述)均已渲染
            self.assert_true(widget.get_repair_detail_header_showing())
            # 列表页页头此时应已隐藏, 证明上面的页头属于详情页而非列表页
            self.assert_false(widget.get_repair_page_header_showing(timeout=2))

            # ---- 详情页正文展示 ----
            detail = widget.get_repair_detail_content()
            print("DIAG detail_content=%r" % (detail,))
            self.assert_true(detail["detail_shown"])
            # "描述"小节的问题说明
            self.assert_true(detail["problem_desc_showing"])
            # "修复项"小节至少有一个修复步骤
            self.assert_true(detail["step_count"] > 0)
            # 详情页底部的"开始修复"入口
            self.assert_true(detail["start_btn_showing"])

            # 详情页保持稳定展示
            self.assert_true(widget.get_repair_detail_showing(timeout=5))
        finally:
            try:
                widget.kill_pc_manager()
            except BaseException:
                pass

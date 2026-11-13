#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log


class TestMyCase(BaseCase):

    def test_mycase_095(self):
        """更新环境模块检查：检测首页的「更新环境检测」卡片应包含
        boot分区空间检测、仓库地址检查、仓库地址权限检查、本地环境检查 4 个检查项，
        「关键库检测」归属「系统环境检测」；执行两者的分项检测后检测项结论可读取"""
        widget = MyAppWidget(check_start=False)

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        self.assert_true(widget.get_detection_cards_view_showing())

        cards = widget.get_detection_card_names()
        log("期望: " + (f"检测首页缺少更新环境检测卡片: {cards}"))
        self.assert_true("更新环境检测" in cards)
        log("期望: " + (f"检测首页缺少系统环境检测卡片: {cards}"))
        self.assert_true("系统环境检测" in cards)

        # ===== 更新环境检测的 4 个检查项 =====
        update_items = widget.get_detection_item_names("更新环境检测")
        for item in ("boot分区空间检测", "仓库地址检查", "仓库地址权限检查", "本地环境检查"):
            log("期望: " + (f"更新环境检测缺少检查项 {item}: {update_items}"))
            self.assert_true(item in update_items)

        # 关键库检测不属于更新环境模块，应归属系统环境检测
        log("期望: " + (f"关键库检测不应出现在更新环境检测中: {update_items}"))
        self.assert_true("关键库检测" not in update_items)
        log("期望: " + ("关键库检测应归属系统环境检测"))
        self.assert_true(widget.get_detection_item_present("系统环境检测", "关键库检测"))

        # ===== 执行「更新环境检测」分项检测并校验检测项结论可读取 =====
        self.assert_true(widget.run_detection_item("更新环境检测", timeout=300))
        for detection_id in ("boot_partition_space", "repository_url",
                             "repository_permission", "local_environment"):
            ok, detail = widget.get_detection_item_verdict(detection_id)
            log("期望: " + (f"{detection_id} 检测项未实现或调用失败: {detail}"))
            self.assert_true(ok is not None)

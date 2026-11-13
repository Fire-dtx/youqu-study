#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_131(self):
        """修复工具--修复工具模块分类：验证修复工具按系统/桌面/外设/应用四类分区展示"""
        widget = MyAppWidget(check_start=False)
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 进入左侧导航"修复工具"
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_cards_view_showing())

            # 页面存在分类标签(全部/系统/桌面/外设/应用等)
            tab_count = widget.get_repair_category_tab_count()
            self.assert_true(tab_count > 0)

            # 模块分区: 描述要求修复工具按 4 个模块分类展示
            sections = widget.get_repair_sections_detail()
            self.assert_true(len(sections) >= 4)
            # 每个模块分区下都必须有修复项, 不允许出现空分区
            for section in sections:
                self.assert_true(len(section["cards"]) > 0)

            # 描述中的模块 -> 修复项映射
            expect_groups = [
                ("系统修复", ["网络修复", "依赖关系修复", "长文件名支持修复"]),
                ("桌面修复", ["密钥环修复", "重启输入法"]),
                ("外设修复", ["打印机修复", "USB设备修复"]),
                ("应用修复", ["微信修复", "企业微信修复", "QQ修复", "WPS双击打开修复"]),
            ]

            def normalize(text):
                # 产品按钮文案存在空格差异(如 "USB 设备修复"), 比较时忽略空白与大小写
                return "".join(str(text).split()).lower()

            section_card_sets = [
                {normalize(card) for card in section["cards"]} for section in sections
            ]
            all_cards = set()
            for card_set in section_card_sets:
                all_cards |= card_set

            for group_name, tools in expect_groups:
                expect_names = {normalize(tool) for tool in tools}
                # 1) 该分类下的修复项都应出现在修复列表中
                missing = expect_names - all_cards
                print("DIAG group=%s missing=%r" % (group_name, sorted(missing)))
                self.assert_true(not missing)
                # 2) 同一分类下的修复项必须归属同一个分区(分类不串位)
                same_section = any(
                    expect_names.issubset(card_set) for card_set in section_card_sets
                )
                print(
                    "DIAG group=%s same_section=%s" % (group_name, same_section)
                )
                self.assert_true(same_section)

            print(
                "DIAG section_cards=%r"
                % ([(section["title"], section["cards"]) for section in sections],)
            )
            # 分类展示完成后页面仍正常显示
            self.assert_true(widget.get_repair_page_showing())
        finally:
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_207(self):
        """实用工具-网络工具

        步骤与断言:
        1) 进入实用工具, 概览页显示 网络工具/磁盘工具/日志工具 三个分组;
        2) 网络工具分组下显示「本地域名解析工具」卡片;
        3) 点击卡片进入本地域名解析工具页面(标题/副标题、hosts 编辑框、
           取消/保存按钮可见), 概览页隐藏。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())

            def section_cards():
                result = []
                for sec in widget.dog.find_elements_by_attr(
                    "$//utility_sectionsContainer//utility_sectionWidget"
                ) or []:
                    if not sec.showing:
                        continue
                    cards = []

                    def collect(node, depth=0):
                        if depth > 4:
                            return
                        try:
                            children = node.children
                        except BaseException:
                            return
                        for child in children:
                            try:
                                if child.roleName == "push button" and child.name:
                                    cards.append(child.name)
                                    continue
                            except BaseException:
                                pass
                            collect(child, depth + 1)

                    collect(sec)
                    result.append(cards)
                return result

            groups = section_cards()
            logger.info(f"[2032409] groups={groups}")
            self.assert_true(len(groups) == 3)
            self.assert_true(groups[0] == ["本地域名解析工具"])

            overview = widget.dog.find_element_by_attr("$//utility_overview")
            self.assert_true(overview.showing)

            # 200ms 级性能不在此用例断言; 点击卡片进入运行时页面
            widget.click_utility_card_by_name("本地域名解析工具")
            sleep(1)

            runtime = widget.dog.find_element_by_attr("$//utility_runtime")
            self.assert_true(runtime.showing)
            self.assert_false(overview.showing)
            hosts_page = widget.dog.find_element_by_attr("$//utility_hostsPage")
            self.assert_true(hosts_page.showing)
            for expr in (
                "$//utility_hostsTextEdit",
                "$//utility_hostsCancelBtn",
                "$//utility_hostsSaveBtn",
            ):
                elems = widget.dog.find_elements_by_attr(expr) or []
                self.assert_true(bool(elems) and elems[0].showing)

            labels = {}
            for child in (runtime.children or []):
                if child.name == "pageHeader" and child.showing:
                    for label in (child.children or []):
                        if label.showing:
                            labels[label.name] = label
            logger.info(f"[2032409] runtime_header={sorted(labels)}")
            for name in ("pageHeader_titleLabel", "pageHeader_subtitleLabel"):
                self.assert_true(name in labels)
                w, h = labels[name].size
                self.assert_true(w > 0 and h > 0)

        finally:
            sleep(1)
            widget.kill_pc_manager()

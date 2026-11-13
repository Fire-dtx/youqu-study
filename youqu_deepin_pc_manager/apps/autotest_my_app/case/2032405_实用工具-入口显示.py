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

    def test_mycase_206(self):
        """实用工具-入口显示

        断言:
        1) 左侧导航依次为 系统检测/系统优化/修复工具/实用工具;
        2) 进入实用工具后大标题与副标题标签可见(截图已确认文案为
           「实用工具」「通过图形化工具管理你的系统」);
        3) 分类标签共 4 个, 默认仅「全部」选中;
        4) 分组顺序为 网络工具/磁盘工具/日志工具, 各组卡片数 1/2/1,
           卡片名称与预期一致。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            nav = widget.dog.find_element_by_attr("$//mainWindow_navList")
            nav_items = [
                (c.name, c.description) for c in (nav.children or [])
            ]
            logger.info(f"[2032405] nav={nav_items}")
            self.assert_true([n for n, _ in nav_items] == [
                "系统检测", "系统优化", "修复工具", "实用工具",
            ])
            self.assert_true([
                d for _, d in nav_items
            ] == [
                "切换到系统检测模块", "切换到系统优化模块",
                "切换到修复工具模块", "切换到实用工具模块",
            ])

            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())

            overview = widget.dog.find_element_by_attr("$//utility_overview")
            header = None
            for c in (overview.children or []):
                if c.name == "pageHeader" and c.showing:
                    header = c
                    break
            self.assert_true(header is not None)
            labels = {
                c.name: c for c in (header.children or []) if c.showing
            }
            logger.info(f"[2032405] header_labels={sorted(labels)}")
            self.assert_true("pageHeader_titleLabel" in labels)
            self.assert_true("pageHeader_subtitleLabel" in labels)
            for label in labels.values():
                w, h = label.size
                self.assert_true(w > 0 and h > 0)

            tabs = widget.dog.find_elements_by_attr(
                "$//utility_categoryTabs//utility_catBtn"
            ) or []
            tab_state = [bool(t.checked) for t in tabs]
            logger.info(f"[2032405] tabs={len(tabs)} checked={tab_state}")
            self.assert_true(len(tabs) == 4)
            self.assert_true(tab_state == [True, False, False, False])

            sections = []
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
                sections.append(cards)
            logger.info(f"[2032405] sections={sections}")
            self.assert_true(sections == [
                ["本地域名解析工具"],
                ["磁盘管理器", "磁盘使用情况分析器"],
                ["日志收集工具"],
            ])
        finally:
            sleep(1)
            widget.kill_pc_manager()

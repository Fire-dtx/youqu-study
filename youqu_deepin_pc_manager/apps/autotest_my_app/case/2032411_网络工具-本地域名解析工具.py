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

    def test_mycase_208(self):
        """网络工具-本地域名解析工具

        步骤与断言:
        1) 单击本地域名解析工具卡片进入二级页;
        2) 二级页标题/副标题标签可见(截图已确认文案为
           「本地域名解析工具」「图形化修改hosts文件」);
        3) 编辑框默认内容与 /etc/hosts 完全一致;
        4) 取消/保存按钮可见。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())

            widget.click_utility_card_by_name("本地域名解析工具")
            sleep(1)
            self.assert_true(
                widget.dog.find_element_by_attr("$//utility_runtime").showing
            )
            self.assert_false(
                widget.dog.find_element_by_attr("$//utility_overview").showing
            )
            self.assert_true(
                widget.dog.find_element_by_attr("$//utility_hostsPage").showing
            )

            edit = widget.dog.find_element_by_attr("$//utility_hostsTextEdit")
            self.assert_true(edit.showing)
            text_iface = edit.queryText()
            shown = text_iface.getText(0, text_iface.characterCount)
            on_disk = widget.run_cmd(
                "cat /etc/hosts", timeout=5, out_debug_flag=False
            )
            logger.info(
                f"[2032411] editor_chars={len(shown)} disk_chars={len(on_disk)}"
            )
            self.assert_true(shown.rstrip("\n") == on_disk.rstrip("\n"))

            for expr in (
                "$//utility_hostsCancelBtn",
                "$//utility_hostsSaveBtn",
            ):
                elems = widget.dog.find_elements_by_attr(expr) or []
                self.assert_true(bool(elems) and elems[0].showing)

            runtime = widget.dog.find_element_by_attr("$//utility_runtime")
            labels = {}
            for child in (runtime.children or []):
                if child.name == "pageHeader" and child.showing:
                    for label in (child.children or []):
                        if label.showing:
                            labels[label.name] = label
            logger.info(f"[2032411] header={sorted(labels)}")
            for name in ("pageHeader_titleLabel", "pageHeader_subtitleLabel"):
                self.assert_true(name in labels)
                w, h = labels[name].size
                self.assert_true(w > 0 and h > 0)
        finally:
            sleep(1)
            widget.kill_pc_manager()

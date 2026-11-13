#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):
    def test_mycase_046(self):
        """实用工具-Tab和搜索联动

        步骤与预期:
        1) 搜索「磁盘」: 显示 2 张卡片(磁盘使用情况分析器、磁盘管理器);
        2) 切到「日志工具」: 显示 1 张卡片(日志收集工具);
        3) 切回「全部」并清空搜索词: 恢复 4 张卡片。
        分类 Tab 使用真实鼠标点击(xdotool); AT-SPI Action/raw click 只改选中态
        不触发 DButtonBox::buttonClicked, 不能用于本用例的联动验证。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_utility_nav()
            self.assert_true(widget.get_utility_page_showing())
            self.assert_true(widget.get_utility_search_edit_showing())

            def tabs():
                return widget.dog.find_elements_by_attr(
                    "$//utility_categoryTabs//utility_catBtn"
                ) or []

            def click_tab_real(index):
                tab = tabs()[index]
                pos, size = tab.position, tab.size
                cx = int(pos[0] + size[0] / 2)
                cy = int(pos[1] + size[1] / 2)
                widget.run_cmd(
                    f"xdotool mousemove {cx} {cy} click 1",
                    timeout=5, out_debug_flag=False,
                )
                sleep(2)

            def visible_names():
                return widget.get_visible_utility_tool_names()

            # 1. 搜索「磁盘」
            widget.input_utility_search("磁盘")
            sleep(2)
            step1 = visible_names()
            logger.info(f"[2032407] step1 search=磁盘 cards={step1}")
            self.assert_true(len(step1) == 2)
            self.assert_true(set(step1) == {"磁盘管理器", "磁盘使用情况分析器"})
            self.assert_true(bool(tabs()[0].checked))

            # 2. 切到「日志工具」, 搜索词保留
            click_tab_real(3)
            checked = [bool(t.checked) for t in tabs()]
            step2 = visible_names()
            logger.info(
                f"[2032407] step2 tab=日志工具 checked={checked} "
                f"cards={step2} empty={widget.get_utility_empty_state_showing()}"
            )
            widget.run_cmd(
                "scrot /tmp/2032407_step2.png",
                timeout=10, out_debug_flag=False,
            )
            self.assert_true(checked == [False, False, False, True])
            step2_ok = (
                len(step2) == 1 and step2[0] == "日志收集工具"
            )

            # 3. 切回「全部」并清空搜索词
            click_tab_real(0)
            self.assert_true(bool(tabs()[0].checked))
            widget.clear_utility_search()
            sleep(2)
            step3 = visible_names()
            logger.info(f"[2032407] step3 all+cleared cards={step3}")
            self.assert_true(len(step3) == 4)
            self.assert_true(set(step3) == {
                "本地域名解析工具", "磁盘管理器",
                "磁盘使用情况分析器", "日志收集工具",
            })

            # 步骤 2 的预期单独断言, 保证步骤 3 的闭环验证先完成
            self.assert_true(step2_ok)
        finally:
            sleep(1)
            widget.kill_pc_manager()

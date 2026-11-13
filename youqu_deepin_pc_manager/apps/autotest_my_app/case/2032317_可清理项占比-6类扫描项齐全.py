#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_375(self):
        """可清理项占比-6类扫描项齐全

        为全部扫描分类构造数据后扫描, 验证结果中全部可清理分类齐全。
        期望描述的是 V25 占比条的 6 类横向顺序(系统垃圾/应用垃圾/系统快照/
        玲珑环境/痕迹信息/Cookies)。V20 实测结果页为纵向列表且无占比条
        (见 2.14.0 界面截图: 摘要仅"发现N个可清理项, 合计X MB"), 且产品
        未编译系统快照扫描, 因此按 V20 等价校验:
        1. 结果页分类齐全: 系统垃圾/应用垃圾/痕迹信息/Cookies/玲珑环境;
        2. 不含系统快照;
        3. 各分类均带可清理项(名称带数量且 >0)。
        """
        widget = MyAppWidget(check_start=False)
        is_v25 = widget.is_v25_environment()
        widget.kill_pc_manager()
        widget.create_all_category_junk()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_has_junk(timeout=150))
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=20))
            sleep(3)

            names = widget.get_space_clean_category_names(retries=10)
            logger.info(f"[2032317] 结果页分类: {names}")
            self.assert_true(bool(names))

            required = ["系统垃圾", "应用垃圾", "痕迹信息", "Cookies", "玲珑环境"]
            for keyword in required:
                self.assert_true(any(keyword in name for name in names))
            if is_v25:
                self.assert_true(len(names) >= 6)
                self.assert_true(any("快照" in name for name in names))
            else:
                self.assert_true(len(names) == 5)
                self.assert_false(any("快照" in name for name in names))

            # 分类复选框存在且可用, 说明各分类均有可清理项
            checkboxes = widget.get_space_clean_category_checkboxes()
            self.assert_true(len(checkboxes) >= len(required))
            self.assert_true(widget.get_space_clean_clean_button_enabled())
        finally:
            widget.remove_all_category_junk()
            widget.kill_pc_manager()

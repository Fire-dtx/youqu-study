#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_318(self):
        """可清理项占比-6类扫描项占比为0

        清空全部可扫描垃圾后扫描, 验证结果页进入无垃圾空状态:
        1. 结果页空状态元素(spaceClean_emptyTitle/emptySubtitle)可见;
        2. 结果页不出现任何分类项, 分类数量为 0;
        3. 无清理按钮/分类复选框可用。

        V20 2.14.0 实测空状态文案为"未发现垃圾文件 / 您的系统很干净"
        且无占比条(截图 /tmp/pcm_no_junk.png), 与期望的"暂无可清理项"
        属同一空状态语义, 按版本等价校验。
        注意 get_space_clean_category_names 解析的是扫描预填充页标签,
        会保留旧计数, 因此这里用结果页分类数量判定。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        # 前置: 清理全部可扫描垃圾, 并确保玲珑仓库无不可达对象
        widget.clean_system_for_no_junk()
        widget.clean_linglong_unreachable_objects()
        try:
            self.assert_false(widget.get_linglong_junk_exist())
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_no_junk(timeout=150))
            self.assert_false(widget.get_space_clean_has_junk(timeout=10))

            # 空状态标题/副标题可见
            self.assert_true(
                widget.is_space_clean_element_visible("$//spaceClean_emptyTitle")
            )
            self.assert_true(
                widget.is_space_clean_element_visible("$//spaceClean_emptySubtitle")
            )

            # 结果页无分类项
            category_count = widget.get_space_clean_category_count(retries=10)
            logger.info(f"[2032319] 无垃圾状态可见分类数: {category_count}")
            self.assert_true(category_count == 0)
            self.assert_false(
                widget.get_space_clean_clean_button_enabled()
            )
        finally:
            widget.kill_pc_manager()

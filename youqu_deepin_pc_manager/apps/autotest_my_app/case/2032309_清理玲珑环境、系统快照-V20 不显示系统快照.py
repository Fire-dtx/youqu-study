#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_316(self):
        """清理玲珑环境、系统快照-V20 不显示系统快照

        为全部扫描分类构造测试数据后进入空间清理扫描结果页:
        V20 结果页分类为 5 类(系统垃圾/应用垃圾/痕迹信息/Cookies/玲珑环境),
        不显示系统快照; V25 为 6 类(额外包含系统快照)。

        判定使用 get_space_clean_category_names 返回的分类名称列表,
        避免 get_space_clean_category_count(仅统计结果页可见同步元素)
        在结果页刚渲染时数量不足导致误判。
        """
        widget = MyAppWidget(check_start=False)
        is_v25 = widget.is_v25_environment()

        # 前置: 关闭应用, 为全部扫描分类构造测试数据(含玲珑不可达对象)
        widget.kill_pc_manager()
        widget.create_all_category_junk()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())

            # 扫描
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_has_junk(timeout=150))
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=20))
            sleep(3)

            names = widget.get_space_clean_category_names(retries=10)
            logger.info(f"[2032309] 结果页分类: {names}")
            self.assert_true(bool(names))

            if is_v25:
                # V25: 结果页包含系统快照分类, 分类数量为 6
                self.assert_true(len(names) >= 6)
                self.assert_true(any("快照" in name for name in names))
            else:
                # V20: 守护进程不扫描快照, 结果页为 5 类且不含系统快照
                self.assert_true(len(names) == 5)
                self.assert_false(any("快照" in name for name in names))
                for keyword in ("系统垃圾", "应用垃圾", "痕迹信息", "Cookies", "玲珑环境"):
                    self.assert_true(any(keyword in name for name in names))

            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            widget.remove_all_category_junk()
            widget.kill_pc_manager()

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

    def test_mycase_280(self):
        """清理玲珑环境、系统快照-扫描入口：空间清理扫描结果包含全部大类

        步骤: 系统优化 -> 空间清理 -> 扫描。
        预期: 扫描列表包含系统垃圾、应用垃圾、系统快照、玲珑环境、痕迹信息、
        Cookies 六大类。V20 产品不扫描系统快照(守护进程无快照能力),
        结果页固定为 5 类(系统垃圾/应用垃圾/痕迹信息/Cookies/玲珑环境);
        V25 额外包含系统快照共 6 类。用例先为各分类构造真实数据
        (回收站、应用残留、痕迹、Cookie、玲珑仓库不可达对象), 扫描后
        按版本校验分类数量与名称, 最后清理全部构造数据并关闭应用。
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

            # 步骤: 空间清理 -> 扫描
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_scan_started(timeout=30))
            self.assert_true(widget.get_space_clean_has_junk(timeout=150))
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=20))
            sleep(3)

            names = widget.get_space_clean_category_names(retries=10)
            count = widget.get_space_clean_category_count(retries=10)
            logger.info(f"[2032299] 结果页分类: {names}, 可见分类数: {count}")
            self.assert_true(bool(names))
            self.assert_true(count > 0)

            # 1. 分类数量: V20 为 5 类(无系统快照), V25 为 6 类(含系统快照)
            if is_v25:
                self.assert_true(count >= 6)
            else:
                self.assert_true(count == 5)

            # 2. 分类名称: 逐类校验(名称形如 "系统垃圾 (6)")
            for keyword in ("系统垃圾", "应用垃圾", "痕迹信息", "Cookies", "玲珑环境"):
                self.assert_true(any(keyword in name for name in names))
            if is_v25:
                self.assert_true(any("快照" in name for name in names))
            else:
                # V20 结果页不应出现系统快照分类
                self.assert_false(any("快照" in name for name in names))

            # 3. 玲珑环境分类确实被扫描到可清理数据(构造的 ostree 不可达对象)
            self.assert_true(widget.get_linglong_junk_exist())
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            # 闭环: 清理全部构造的垃圾数据(含玲珑不可达对象)并关闭应用
            widget.remove_all_category_junk()
            widget.kill_pc_manager()

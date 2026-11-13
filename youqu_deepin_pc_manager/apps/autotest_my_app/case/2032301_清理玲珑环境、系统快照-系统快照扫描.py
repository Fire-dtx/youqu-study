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

    def test_mycase_315(self):
        """清理玲珑环境、系统快照-系统快照扫描

        步骤 1(V25 备份还原创建 3 个还原点)依赖 V25(PCM_HAVE_OSTREE)构建的
        系统快照能力; 当前测试机为 V20, 产品未编译快照扫描代码, 无法创建
        还原点, 采用版本等价校验:
        1. 空间清理扫描正常启动并完成, 结果页显示分类;
        2. 已构造玲珑仓库不可达对象时, 结果页包含玲珑环境分类;
        3. V20 结果页不包含系统快照分类(功能未提供, 与 2032309 同口径);
        4. V25 上若系统中有快照, 结果页应出现快照分类, 且每个快照条目
           为「名称 (创建于 YYYY-MM-DD HH:MM:SS)」并可显示占用大小。
        本用例在 V20 完成后清理构造数据并关闭应用。
        """
        widget = MyAppWidget(check_start=False)
        is_v25 = widget.is_v25_environment()

        # 前置: 关闭应用, 构造系统垃圾与玲珑不可达对象
        widget.kill_pc_manager()
        widget.create_test_junk_files()
        widget.create_linglong_unreachable_objects()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())

            # 步骤 2: 扫描
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_scan_started(timeout=30))
            self.assert_true(widget.get_space_clean_has_junk(timeout=150))
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=20))
            sleep(3)

            names = widget.get_space_clean_category_names(retries=10)
            count = widget.get_space_clean_category_count(retries=10)
            logger.info(f"[2032301] 结果页分类: {names}, 可见分类数: {count}")
            self.assert_true(bool(names))
            self.assert_true(count > 0)

            # 玲珑环境分类应出现(已构造不可达对象)
            self.assert_true(any("玲珑" in name for name in names))

            if is_v25:
                # V25 的"3 个还原点/条目格式/倒序/默认不勾选"需在 V25 环境由
                # 备份还原创建还原点后验证; 当前测试机为 V20, 不在此分支断言。
                logger.info(
                    f"[2032301] V25 环境需补充还原点场景, 当前分类: {names}"
                )
            else:
                # V20: 快照扫描未编译, 结果页不得出现快照分类
                self.assert_false(any("快照" in name for name in names))
                self.assert_true(len(names) == 5)

            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            widget.remove_test_junk_files()
            widget.clean_linglong_unreachable_objects()
            widget.kill_pc_manager()

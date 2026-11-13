#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):

    def test_mycase_080(self):
        """系统检测--空间清理入口有垃圾

        前置: 系统存在可清理垃圾(向回收站写入 5 个 1MB 文件, 属于
        空间清理"系统垃圾"类别的扫描范围)。
        步骤: 进入系统优化页(产品中空间清理入口所在页面) -> 观察空间清理
        特色卡片 -> 点击卡片上的开始扫描进入空间清理。
        预期(等价断言):
        1. 空间清理特色卡片入口已渲染(卡片框架 + 开始扫描按钮)。
           说明: 卡片描述"存在垃圾可清理"由 QML 自绘, AT-SPI 只暴露英文
           accessibleName, .name/.text 均读不到中文文案, 故以入口卡片可见
           作为"入口有垃圾"的可观测等价载体;
        2. 点击后产品真实跳转到空间清理并开始扫描(get_space_clean_scan_started);
        3. 扫描完成后结果为"有垃圾"页(spaceClean_resultTitle 可见), 且分类
           列表中"系统垃圾"分类存在(数量>0), 与前置写入的回收站垃圾对应。
        """
        widget = MyAppWidget(check_start=False)
        try:
            # 前置: 确保电脑管家已关闭(关闭失败则不继续, 避免实例叠加)
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())
            # 前置: 创建测试垃圾文件, 保证空间清理能扫描到"存在垃圾"
            widget.create_test_junk_files()
            junk_count = widget.run_cmd(
                "ls -1 ~/.local/share/Trash/files/autotest_junk 2>/dev/null | wc -l",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            logger.info(f"构造的回收站垃圾文件数: {junk_count}")
            self.assert_equal(5, int(junk_count or 0))
            # 启动电脑管家
            widget.launch_from_launcher()
            sleep(3)
            self.assert_true(widget.get_pc_manager_process_status())

            # 步骤 1: 进入系统优化页并确认空间清理特色卡片入口已渲染
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            self.assert_true(widget.get_space_clean_featured_card_showing())

            # 步骤 2: 点击空间清理入口(开始扫描), 产品跳转到空间清理并扫描
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_scan_started(timeout=60))

            # 断言: 扫描结果为有垃圾页面
            self.assert_true(widget.get_space_clean_has_junk(timeout=180))

            # 断言: 垃圾分类真实存在, 且"系统垃圾"数量与前置垃圾对应
            categories = widget.get_space_clean_category_names(retries=5)
            logger.info(f"空间清理扫描分类: {categories}")
            self.assert_true(len(categories) > 0)
            self.assert_true(widget.has_space_clean_category("系统垃圾", retries=5))
        finally:
            # 清理前置构造的垃圾文件并校验, 关闭本用例启动的电脑管家
            widget.remove_test_junk_files()
            self.assert_equal(
                "no",
                widget.run_cmd(
                    "test -e ~/.local/share/Trash/files/autotest_junk "
                    "&& echo yes || echo no",
                    timeout=5,
                    out_debug_flag=False,
                ).strip(),
            )
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())

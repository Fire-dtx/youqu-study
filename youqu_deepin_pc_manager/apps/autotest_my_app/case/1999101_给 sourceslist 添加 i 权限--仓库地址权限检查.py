#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep, logger


class TestMyCase(BaseCase):

    def test_mycase_350(self):
        """给 sources.list 添加 i 权限--仓库地址权限检查：
        为 /etc/apt/sources.list 添加 immutable (i) 属性(异常状态)，
        启动电脑管家进入系统检测，验证检测页面功能正常显示且更新环境检测正常执行，
        最后确保环境恢复到测试前状态(移除 immutable 属性)"""
        widget = MyAppWidget(check_start=False)

        # ===== 前置准备: 记录 sources.list 原始状态, 确保 sources.list 不带 immutable 属性 =====
        had_immutable = widget.get_source_file_immutable_status()
        if had_immutable:
            widget.remove_source_file_immutable()

        # 验证 sources.list 可读且当前不带 immutable 属性
        self.assert_true(widget.get_source_file_readable())
        self.assert_false(widget.get_source_file_immutable_status())

        # 为 sources.list 添加 immutable (i) 属性, 构造异常权限场景
        widget.add_source_file_immutable()

        # 验证 immutable 属性已成功添加
        self.assert_true(widget.get_source_file_immutable_status())

        try:
            # ===== 启动电脑管家并进入系统检测 =====
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            # 导航到系统检测页面
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            # 点击"更新环境检测"卡片, 真实触发该分项检测
            self.assert_true(widget.run_detection_item("更新环境检测"))

            # sources.list 被 chattr +i 篡改后, 该分项应检出问题
            self.assert_true(widget.get_detection_item_present("更新环境检测", "仓库地址权限检查"))
            # 只点了"更新环境检测", 其它分项不应被检查(区别于全面检测)
            self.assert_true(widget.is_only_group_detected("更新环境检测"))
            state = widget.get_detection_group_state("更新环境检测")
            self.assert_true(state["total"] > 0)
            self.assert_true(state["issues"] > 0)

            verdict, detail = widget.get_detection_item_verdict("repository_permission")
            logger.info(f"仓库地址权限检查单项结论(带 i 权限): {verdict}, 原始结果: {detail}")
            self.assert_false(verdict)

            sleep(2)
        finally:
            # ===== 清理: 移除 sources.list 的 immutable 属性 =====
            widget.remove_source_file_immutable()

            # 如果测试前 sources.list 本身就带 immutable 属性则恢复
            if had_immutable:
                widget.add_source_file_immutable()

            # 关闭电脑管家，清理进程
            widget.kill_pc_manager()

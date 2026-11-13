#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/04
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep, logger


class TestMyCase(BaseCase):

    def test_mycase_352(self):
        """删除 /usr/local/lib 目录 -进行更新环境检测：删除 /usr/local/lib 后点击
        "更新环境检测"卡片，仅该分项执行检测，"本地环境检查"项存在、
        整组跑完且无问题，电脑管家进程未崩溃。"""
        widget = MyAppWidget(check_start=False)

        # ===== 前置准备: 清理可能残留的冲突 .so 文件, 保证基线无冲突 =====
        widget.clean_conflict_library()
        if not widget.get_local_lib_directory_exists():
            widget.run_cmd("mkdir -p /usr/local/lib 2>/dev/null", timeout=5, out_debug_flag=False)

        # ===== 构造场景: 删除 /usr/local/lib 目录(备份后移除) =====
        widget.remove_local_lib_directory()
        sleep(1)
        self.assert_true(not widget.get_local_lib_directory_exists())

        try:
            widget.kill_pc_manager()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            # 点击"更新环境检测"卡片, 真实触发该分项检测
            self.assert_true(widget.run_detection_item("更新环境检测"))

            # /usr/local/lib 缺失不应导致本地环境检查误报
            self.assert_true(widget.get_detection_item_present("更新环境检测", "本地环境检查"))
            self.assert_true(widget.is_only_group_detected("更新环境检测"))

            state = widget.get_detection_group_state("更新环境检测")
            self.assert_true(state["total"] > 0)
            self.assert_equal(0, state["issues"])

            verdict, detail = widget.get_detection_item_verdict("local_environment")
            logger.info(f"本地环境检查单项结论(/usr/local/lib 缺失): {verdict}, 原始结果: {detail}")
            self.assert_true(verdict)

            # 电脑管家主进程未因 /usr/local/lib 缺失而崩溃
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            widget.restore_local_lib_directory()
            widget.kill_pc_manager()

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):

    def test_mycase_314(self):
        """存在冲突文件-进行更新环境检测：/usr/local/lib/ 和 /usr/lib 或 /usr/lib/*均存在同名文件：
        在 /usr/local/lib 下创建与系统包管理库(/usr/lib/x86_64-linux-gnu/libz.so.1)同名的
        但内容不同的 .so 文件, 点击检测卡片执行真实检测, 该检测项应检出问题。

        说明: xlsx 将该检测项归在"更新环境检测", 被测程序 1.1.7 把关键库冲突
        (critical_libraries) 归在"系统环境检测", 因此点击"系统环境检测"卡片,
        并从产品 D-Bus 检测通道读取 critical_libraries 结论一并校验。
        最后清理测试创建的冲突文件。
        """
        widget = MyAppWidget(check_start=False)

        # ===== 前置准备: 确保 /usr/local/lib 无残留冲突文件 =====
        widget.clean_conflict_library()

        # ===== 构造冲突: 在 /usr/local/lib 创建与系统包管理库同名的 .so 文件 =====
        widget.create_conflict_library()
        sleep(1)

        # 验证冲突文件已创建, 且内容与系统库不同
        self.assert_true(widget.get_conflict_library_exists())
        local_sha = widget.run_cmd(
            "sha256sum /usr/local/lib/libz.so.1 | cut -d' ' -f1", timeout=10, out_debug_flag=False
        ).strip()
        sys_sha = widget.run_cmd(
            "sha256sum /usr/lib/x86_64-linux-gnu/libz.so.1 | cut -d' ' -f1",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        self.assert_true(local_sha != sys_sha)

        try:
            # ===== 启动电脑管家并进入系统检测 =====
            widget.kill_pc_manager()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            # 点击"系统环境检测"卡片, 真实触发关键库检测
            self.assert_true(widget.run_detection_item("系统环境检测"))
            self.assert_true(widget.get_detection_item_present("系统环境检测", "关键库检测"))

            state = widget.get_detection_group_state("系统环境检测")
            self.assert_true(state["total"] > 0)
            self.assert_true(state["issues"] > 0)

            # 产品 D-Bus 检测通道: 关键库冲突应给出失败结论
            verdict, detail = widget.get_detection_item_verdict("critical_libraries")
            logger.info(f"关键库检测结论: {verdict}, 原始结果: {detail}")
            self.assert_true(verdict is False)

            # 检出问题后结果区提供一键修复/重新扫描入口
            self.assert_true(widget.get_detection_result_actions_showing())
        finally:
            # ===== 清理: 删除测试创建的冲突 .so 文件 =====
            widget.clean_conflict_library()

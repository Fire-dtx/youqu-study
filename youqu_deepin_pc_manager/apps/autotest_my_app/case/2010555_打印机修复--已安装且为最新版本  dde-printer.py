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

    def test_mycase_173(self):
        """打印机修复--已安装且为最新版本 dde-printer

        描述: 步骤"执行脚本", 预期输出"[OK] dde-printer 已是最新版本"。

        产品依据(plugin-printer-fix/config.json + entry.sh):
        - 修复步骤第 2 条"检查并安装或升级 dde-printer";
        - 已安装且 apt 无更高候选版本时输出 [OK] dde-printer 已是最新版本,
          不执行任何安装/升级动作。

        闭环要求: 用例不卸载、不降级系统包; 结束前再次确认 dde-printer 仍已安装
        且版本未变(修复流程没有擅自升级/删除)。
        """
        widget = MyAppWidget(check_start=False)

        # 1) 前置: dde-printer 已安装且为 apt 候选版本(没有可升级版本)
        if not widget.is_dde_printer_installed():
            widget.install_dde_printer()
        self.assert_true(widget.is_dde_printer_installed())
        if not widget.is_dde_printer_latest():
            widget.install_dde_printer()
            sleep(2)
        installed, candidate = widget.get_dde_printer_versions()
        logger.info(f"[2010555] dde-printer 版本: installed={installed!r} candidate={candidate!r}")
        self.assert_true(widget.is_dde_printer_latest())

        try:
            # 2) 启动电脑管家并进入打印机修复
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))
            self.assert_true(widget.get_repair_cards_view_showing())
            widget.click_repair_card_by_name("打印机修复")
            self.assert_true(widget.get_repair_detail_showing())

            # 3) 开始修复(插件 executionMode=root, 需提交鉴权密码)
            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=30))
            widget.handle_shell_repair_dialog()

            # 4) 预期: 输出 [OK] dde-printer 已是最新版本
            self.assert_true(
                widget.wait_repair_output_contains("检查 dde-printer 状态", timeout=180)
            )
            self.assert_true(
                widget.wait_repair_output_contains(
                    "dde-printer 已是最新版本", timeout=120
                )
            )
            self.assert_true(widget.get_repair_output_contains("[OK]", timeout=10))

            output = widget.get_repair_output_text()
            logger.info(f"[2010555] 打印机修复输出: {output!r}")

            # 5) 该分支不应触发安装/升级动作
            for keyword in ("正在安装 dde-printer", "正在升级 dde-printer"):
                if keyword in output:
                    logger.error(f"已是最新版本分支仍出现 {keyword!r}")
                self.assert_false(keyword in output)

            # 6) 流程正常结束
            self.assert_true(widget.get_repair_completion_status())
            # 收尾: 点掉无超时的完成提示框并关闭修复窗口
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])
        finally:
            # 插件末尾 openinfobox timeoutMs=0 不自动消失, 先点掉再关应用
            widget.finish_repair_flow()
            widget.kill_pc_manager()
            # 回退校验: 包仍在且版本未变
            after_installed, after_candidate = widget.get_dde_printer_versions()
            logger.info(
                f"[2010555] 结束状态: dde-printer={after_installed!r} "
                f"candidate={after_candidate!r}"
            )
            self.assert_true(widget.is_dde_printer_installed())
            self.assert_equal(installed, after_installed)

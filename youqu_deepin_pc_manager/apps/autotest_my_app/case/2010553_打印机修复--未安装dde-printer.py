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

    def test_mycase_038(self):
        """打印机修复--未安装 dde-printer

        描述: 步骤"卸载 dde-printer(apt remove dde-printer), 执行脚本",
        预期输出"[WARN] 系统未安装 dde-printer"。

        产品依据(plugin-printer-fix/config.json + entry.sh):
        - 修复步骤第 2 条"检查并安装或升级 dde-printer";
        - 未安装时脚本给出 [WARN] 系统未安装 dde-printer 的结论行。

        闭环要求: 本用例会卸载系统包, 结束时必须装回 dde-printer 并断言
        已恢复安装, 测试机不留缺包状态。
        """
        widget = MyAppWidget(check_start=False)

        try:
            # 1) 前置: 先确保处于"已安装"状态, 使卸载动作有确定起点
            if not widget.is_dde_printer_installed():
                widget.install_dde_printer()
            self.assert_true(widget.is_dde_printer_installed())

            # 2) 描述步骤: 卸载 dde-printer 并确认卸载生效
            widget.uninstall_dde_printer()
            self.assert_false(widget.is_dde_printer_installed())
            logger.info("[2010553] dde-printer 已卸载, 开始执行打印机修复脚本")

            # 3) 启动电脑管家并进入打印机修复
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))
            self.assert_true(widget.get_repair_cards_view_showing())
            widget.click_repair_card_by_name("打印机修复")
            self.assert_true(widget.get_repair_detail_showing())

            # 4) 开始修复(插件 executionMode=root, 需提交鉴权密码)
            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=30))
            widget.handle_shell_repair_dialog()

            # 5) 预期: 输出 [WARN] 系统未安装 dde-printer
            self.assert_true(
                widget.wait_repair_output_contains("未安装 dde-printer", timeout=180)
            )
            self.assert_true(widget.get_repair_output_contains("[WARN]", timeout=10))

            output = widget.get_repair_output_text()
            logger.info(f"[2010553] 打印机修复输出: {output!r}")

            # 6) 流程正常结束, 且此分支不产生"已是最新版本"之类的错误结论
            self.assert_true(widget.get_repair_completion_status())
            # 收尾: 点掉无超时的完成提示框并关闭修复窗口
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])
        finally:
            # 回退: 关对话框/应用 -> 装回 dde-printer 并确认
            # 插件末尾 openinfobox timeoutMs=0 不自动消失, 先点掉再关应用
            widget.finish_repair_flow()
            widget.kill_pc_manager()
            if not widget.is_dde_printer_installed():
                widget.install_dde_printer()
                sleep(2)
            restored = widget.is_dde_printer_installed()
            logger.info(f"[2010553] 回退后 dde-printer 已安装: {restored}")
            self.assert_true(restored)

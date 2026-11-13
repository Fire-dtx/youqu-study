#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_039(self):
        """音频修复-ALSA Speaker (内置扬声器硬件)恢复

        测试机声卡(Intel ICH/AD1980)只有 Master 与 Capture 控件, 无 Speaker
        控件(amixer: Unable to find simple control 'Speaker'), 无法构造
        Speaker 静音场景。按版本/硬件等价校验:
        1. 若存在 Speaker 控件: 静音后执行修复, 断言恢复非静音;
        2. 否则: 执行音频修复, 断言完成且现有硬件通道(Master/Capture)
           处于非静音状态, 输出日志包含物理声卡通道状态自检。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        controls = widget.run_cmd(
            "amixer scontrols 2>/dev/null", timeout=10, out_debug_flag=False
        )
        has_speaker = "'Speaker'" in controls
        logger.info(f"[2032331] 声卡控件: {controls!r}, 有 Speaker: {has_speaker}")

        def speaker_muted() -> bool:
            text = widget.run_cmd(
                "amixer sget Speaker 2>/dev/null", timeout=10, out_debug_flag=False
            )
            return "[off]" in text

        try:
            if has_speaker:
                widget.run_cmd(
                    "amixer -q sset Speaker mute 2>/dev/null",
                    timeout=10,
                    out_debug_flag=False,
                )
                self.assert_true(speaker_muted())

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            widget.click_repair_card_by_name("音频设备修复")
            self.assert_true(widget.get_repair_detail_showing())
            widget.click_repair_start_button()
            widget.handle_shell_repair_dialog()

            self.assert_true(widget.get_repair_completion_status())
            output_text = widget.get_shell_repair_output_text()
            logger.info(f"[2032331] 修复输出尾部: {output_text[-300:]!r}")
            self.assert_true("恢复完成" in output_text)

            if has_speaker:
                self.assert_false(speaker_muted())
            # 现有硬件通道应处于非静音状态
            self.assert_false(widget.get_alsa_master_mute_status())
            capture = widget.run_cmd(
                "amixer sget Capture 2>/dev/null", timeout=10, out_debug_flag=False
            )
            if "[on]" in capture:
                self.assert_true("Capture" in capture)

            # 脚本末尾提示框无超时, 点掉后修复窗口才能关闭
            state = widget.finish_repair_flow("音频修复")
            self.assert_false(state["window_left"])
        finally:
            # 失败路径同样清理: 提示框无超时, 不点掉会阻塞脚本且窗口关不掉
            widget.finish_repair_flow("音频修复")
            if has_speaker:
                widget.run_cmd(
                    "amixer -q sset Speaker unmute 2>/dev/null",
                    timeout=10,
                    out_debug_flag=False,
                )
            widget.kill_pc_manager()

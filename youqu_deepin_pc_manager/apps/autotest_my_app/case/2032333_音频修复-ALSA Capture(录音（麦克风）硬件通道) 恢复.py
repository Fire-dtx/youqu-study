#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_181(self):
        """音频修复-ALSA Capture(录音/麦克风硬件通道) 恢复

        前置将 ALSA Capture 通道静音, 执行音频设备修复后校验:
        1. 修复完成, 输出日志包含"恢复完成";
        2. Capture 通道恢复为非静音, 音量被重设为 50%(取整容差)。
        若测试机无 Capture 控件则跳过静音构造, 仅验证修复自检完成。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        controls = widget.run_cmd(
            "amixer scontrols 2>/dev/null", timeout=10, out_debug_flag=False
        )
        has_capture = "'Capture'" in controls
        logger.info(f"[2032333] 声卡控件: {controls!r}, 有 Capture: {has_capture}")

        def capture_text() -> str:
            return str(
                widget.run_cmd(
                    "amixer sget Capture 2>/dev/null",
                    timeout=10,
                    out_debug_flag=False,
                )
            )

        try:
            if has_capture:
                widget.run_cmd(
                    "amixer -q sset Capture nocap 2>/dev/null",
                    timeout=10,
                    out_debug_flag=False,
                )
                self.assert_true("[off]" in capture_text())

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
            logger.info(f"[2032333] 修复输出尾部: {output_text[-300:]!r}")
            self.assert_true("恢复完成" in output_text)

            if has_capture:
                text_after = capture_text()
                logger.info(f"[2032333] Capture 状态: {text_after!r}")
                self.assert_false("[off]" in text_after)
                self.assert_true("50%" in text_after or "50 %" in text_after)

            # 脚本末尾提示框无超时, 点掉后修复窗口才能关闭
            state = widget.finish_repair_flow("音频修复")
            self.assert_false(state["window_left"])
        finally:
            # 失败路径同样清理: 提示框无超时, 不点掉会阻塞脚本且窗口关不掉
            widget.finish_repair_flow("音频修复")
            if has_capture:
                widget.run_cmd(
                    "amixer -q sset Capture cap 2>/dev/null",
                    timeout=10,
                    out_debug_flag=False,
                )
            widget.kill_pc_manager()

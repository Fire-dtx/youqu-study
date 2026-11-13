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

    def test_mycase_177(self):
        """音频修复-正常音频

        默认音频正常, 执行音频设备修复后验证检测/自检通过。
        产品音频修复插件(plugin-audio-fix/entry.sh)没有独立"检测"按钮:
        点击开始修复即执行恢复脚本, 脚本末尾输出"恢复完成, 当前音频状态验证"
        并弹出"修复完成"提示框。此处以脚本自检通过 + 音频状态正常作为
        "检测通过"的等价断言:
        1. 输出日志出现"恢复完成"/"修复完成";
        2. 默认 Sink 与默认 Source 均未静音(音频配置正常)。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            widget.click_repair_card_by_name("音频设备修复")
            self.assert_true(widget.get_repair_detail_showing())

            widget.click_repair_start_button()
            widget.handle_shell_repair_dialog()

            keyword = widget.wait_repair_output_keywords(
                ["恢复完成", "修复完成"], timeout=180
            )
            logger.info(f"[2032323] 音频修复输出命中: {keyword}")
            self.assert_true(bool(keyword))
            self.assert_true(widget.get_repair_completion_status(timeout=60))

            # 音频状态正常: 默认输出/输入设备未静音
            self.assert_false(widget.get_sink_mute_status())
            source_name = widget.get_default_source_name()
            self.assert_true(bool(source_name))
            self.assert_false(widget.get_source_mute_status(source_name))

            # 脚本末尾 openinfobox 无超时, 必须先点【确定】才能关掉修复窗口
            state = widget.finish_repair_flow("音频修复")
            self.assert_false(state["window_left"])
        finally:
            # 失败路径同样清理: 提示框无超时, 不点掉会阻塞脚本且窗口关不掉
            widget.finish_repair_flow("音频修复")
            widget.kill_pc_manager()

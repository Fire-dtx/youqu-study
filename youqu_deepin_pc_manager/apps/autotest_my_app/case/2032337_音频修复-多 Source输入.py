#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_183(self):
        """音频修复-多 Source输入

        前置(按用例库描述): 系统存在多个 Source, 将非 monitor 的 Source 静音
        构造异常, 作为"检测失败"的等价证据。
        修复: 执行音频设备修复, 断言完成, 且当前存在的全部 Source
        (排除 *.monitor) 取消静音并统一为 50% 音量。
        注意: 修复脚本会 pulseaudio -k 重启音频服务, 运行时加载的虚拟
        Source 会被卸载, 故修复后按"当前存在的 Source"校验; 结束后兜底
        卸载虚拟模块并关闭应用。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        def parse_sources():
            text = str(
                widget.run_cmd(
                    "LC_ALL=C pactl list sources 2>/dev/null",
                    timeout=10,
                    out_debug_flag=False,
                )
            )
            sources = {}
            for block in re.split(r"\n(?=Source #)", text):
                name = re.search(r"Name:\s*(\S+)", block)
                if not name or name.group(1).endswith(".monitor"):
                    continue
                mute = re.search(r"(?:Mute|静音)\s*[:：]\s*(\S+)", block)
                volume = re.search(r"(\d+)%", block)
                sources[name.group(1)] = {
                    "muted": bool(mute and mute.group(1) in ("yes", "是")),
                    "volume": int(volume.group(1)) if volume else -1,
                }
            return sources

        module_id = widget.create_virtual_audio_source()
        self.assert_true(module_id > 0)
        self.assert_true(widget.check_audio_source_exists("virtual_test_sink.monitor"))
        try:
            sources_before = parse_sources()
            logger.info(f"[2032337] 修复前 Source: {sources_before}")
            self.assert_true(bool(sources_before))
            for source_name in sources_before:
                widget.run_cmd(
                    f"pactl set-source-mute {source_name} 1 2>/dev/null",
                    timeout=5,
                    out_debug_flag=False,
                )
            sleep(1)
            for source_name, info in parse_sources().items():
                self.assert_true(info["muted"])

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
            logger.info(f"[2032337] 修复输出尾部: {output_text[-300:]!r}")
            self.assert_true("恢复完成" in output_text)

            sources_after = parse_sources()
            logger.info(f"[2032337] 修复后 Source: {sources_after}")
            self.assert_true(bool(sources_after))
            for source_name, info in sources_after.items():
                self.assert_false(info["muted"])
                self.assert_true(info["volume"] == 50)

            # 脚本末尾提示框无超时, 点掉后修复窗口才能关闭
            state = widget.finish_repair_flow("音频修复")
            self.assert_false(state["window_left"])
        finally:
            # 失败路径同样清理: 提示框无超时, 不点掉会阻塞脚本且窗口关不掉
            widget.finish_repair_flow("音频修复")
            widget.cleanup_virtual_audio_source(module_id)
            self.assert_false(
                widget.check_audio_source_exists("virtual_test_sink.monitor")
            )
            widget.kill_pc_manager()

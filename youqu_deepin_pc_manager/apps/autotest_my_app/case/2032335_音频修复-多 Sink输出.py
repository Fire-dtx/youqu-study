#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_182(self):
        """音频修复-多 Sink输出

        前置(按用例库描述): 系统存在多个 Sink, 并对新增 Sink 静音构造异常。
        1. 检测: 产品无独立检测按钮, 以"存在静音 Sink"的异常状态作为检测
           失败等价证据(修复前断言 Sink 处于静音);
        2. 修复: 执行音频设备修复, 断言修复完成, 且全部 Sink 均取消静音并
           统一为 50% 音量。
        注意: 修复脚本会 pulseaudio -k 重启音频服务, 运行时 load-module
        加载的 null-sink 会被卸载(实测修复后仅剩物理 Sink), 因此修复后按
       "当前存在的全部 Sink"校验; 测试用 Sink 若仍存在也一并校验。
        结束后卸载测试用 null-sink 模块, 恢复原始 Sink 列表。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        def parse_sinks():
            text = str(
                widget.run_cmd(
                    "LC_ALL=C pactl list sinks 2>/dev/null",
                    timeout=10,
                    out_debug_flag=False,
                )
            )
            sinks = {}
            for block in re.split(r"\n(?=Sink #)", text):
                name = re.search(r"Name:\s*(\S+)", block)
                if not name:
                    continue
                mute = re.search(r"(?:Mute|静音)\s*[:：]\s*(\S+)", block)
                volume = re.search(r"(\d+)%", block)
                sinks[name.group(1)] = {
                    "muted": bool(mute and mute.group(1) in ("yes", "是")),
                    "volume": int(volume.group(1)) if volume else -1,
                }
            return sinks

        module_ids = []
        for sink_name in ("autotest_sink_a", "autotest_sink_b"):
            out = widget.run_cmd(
                "pactl load-module module-null-sink "
                f"sink_name={sink_name} "
                f"sink_properties=device.description={sink_name} 2>/dev/null",
                timeout=10,
                out_debug_flag=False,
            )
            module_id = str(out).strip()
            logger.info(f"[2032335] 加载 {sink_name} -> module {module_id!r}")
            if module_id.isdigit():
                module_ids.append(module_id)
        try:
            self.assert_true(len(module_ids) == 2)
            sinks_before = parse_sinks()
            logger.info(f"[2032335] 修复前 Sink: {sinks_before}")
            self.assert_true("autotest_sink_a" in sinks_before)
            self.assert_true("autotest_sink_b" in sinks_before)

            # 异常场景: 静音两个测试 Sink(等价检测失败证据)
            for sink_name in ("autotest_sink_a", "autotest_sink_b"):
                widget.run_cmd(
                    f"pactl set-sink-mute {sink_name} 1 2>/dev/null",
                    timeout=5,
                    out_debug_flag=False,
                )
            sleep(1)
            sinks_muted = parse_sinks()
            self.assert_true(sinks_muted["autotest_sink_a"]["muted"])
            self.assert_true(sinks_muted["autotest_sink_b"]["muted"])

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
            logger.info(f"[2032335] 修复输出尾部: {output_text[-300:]!r}")
            self.assert_true("恢复完成" in output_text)

            # 修复成功: 全部 Sink unmute 且音量 50%
            sinks_after = parse_sinks()
            logger.info(f"[2032335] 修复后 Sink: {sinks_after}")
            self.assert_true(bool(sinks_after))
            for sink_name, info in sinks_after.items():
                self.assert_false(info["muted"])
                self.assert_true(info["volume"] == 50)

            # 脚本末尾提示框无超时, 点掉后修复窗口才能关闭
            state = widget.finish_repair_flow("音频修复")
            self.assert_false(state["window_left"])
        finally:
            # 失败路径同样清理: 提示框无超时, 不点掉会阻塞脚本且窗口关不掉
            widget.finish_repair_flow("音频修复")
            for module_id in module_ids:
                widget.run_cmd(
                    f"pactl unload-module {module_id} 2>/dev/null",
                    timeout=10,
                    out_debug_flag=False,
                )
            widget.kill_pc_manager()

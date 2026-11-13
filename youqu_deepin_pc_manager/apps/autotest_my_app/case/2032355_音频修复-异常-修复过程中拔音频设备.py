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

    def test_mycase_188(self):
        """音频修复-异常-修复过程中拔音频设备

        前置(按用例库描述): 修复中拔掉 USB 耳机。测试机为虚拟机, 无可用
        USB 声卡, 等价实现为: 修复前挂载一块虚拟音频设备(null-sink),
        修复执行过程中将其卸载(拔出), 单设备消失不应阻断其余设备的修复。

        断言: 弹拔后应用不崩溃、页面可响应; 修复流程仍完成, 输出含
        "恢复完成", 且当前仍存在的全部 Sink 均 unmute 且音量 50%
        (单设备失败不阻断其他设备)。结束后卸载虚拟设备并关闭应用。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        if not widget.get_audio_service_status():
            widget.start_audio_service()

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

        module_id = widget.create_virtual_audio_source()
        self.assert_true(module_id > 0)
        try:
            self.assert_true(widget.check_audio_source_exists("virtual_test_sink.monitor"))
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            widget.click_repair_card_by_name("音频设备修复")
            self.assert_true(widget.get_repair_detail_showing())

            widget.click_repair_start_button()
            widget.handle_shell_repair_dialog()
            # 修复进行中拔出虚拟音频设备
            sleep(3)
            widget.cleanup_virtual_audio_source(module_id)
            module_id = 0
            sleep(2)
            self.assert_false(
                widget.check_audio_source_exists("virtual_test_sink.monitor")
            )

            # 应用不崩溃, 页面可响应
            self.assert_true(widget.get_pc_manager_process_status())
            widget._focus_windows_safe()
            self.assert_true(
                widget.get_repair_page_showing(timeout=10)
                or widget.get_repair_detail_showing(timeout=5)
            )

            # 单设备拔出不阻断修复: 流程仍完成, 剩余设备全部恢复
            self.assert_true(widget.get_repair_completion_status())
            output_text = widget.get_shell_repair_output_text()
            logger.info(f"[2032355] 详情页输出尾部: {output_text[-400:]!r}")
            self.assert_true("恢复完成" in output_text)
            sinks_after = parse_sinks()
            logger.info(f"[2032355] 修复后 Sink: {sinks_after}")
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
            if module_id > 0:
                widget.cleanup_virtual_audio_source(module_id)
            widget.kill_pc_manager()
            sleep(2)
            widget.start_audio_service()
            self.assert_true(widget.get_audio_service_status())

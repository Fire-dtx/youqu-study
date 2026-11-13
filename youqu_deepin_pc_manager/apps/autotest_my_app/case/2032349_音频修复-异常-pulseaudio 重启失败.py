#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_187(self):
        """音频修复-异常-pulseaudio 重启失败

        前置(按用例库描述, 附件脚本使 PulseAudio 无法重启)。等价实现:
        以 systemctl --user mask 屏蔽 pulseaudio.service/pulseaudio.socket
        并杀掉当前脉冲音频进程, 使修复脚本中的 `pulseaudio -k` 与后续
        `pactl` 调用无法恢复音频服务(重启失败), 修复结束后 unmask 并
        重新启动服务校验恢复。

        断言: 详情页输出出现 "正在重启 PulseAudio 音频服务以重载配置",
        修复流程仍能走到结束、应用不崩溃; 清理后音频服务恢复 active。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        self.assert_true(widget.get_audio_service_status())
        masked = False
        try:
            result = widget.run_cmd(
                "systemctl --user mask pulseaudio.service pulseaudio.socket "
                "2>&1; echo RC=$?",
                timeout=10,
                out_debug_flag=False,
            )
            logger.info(f"[2032349] mask 结果: {str(result)!r}")
            masked = "RC=0" in str(result)
            if not masked:
                # 兼容未使用 systemd 管理 pulseaudio 的镜像: 退化为仅杀进程
                logger.info("[2032349] mask 不可用, 退化为仅终止进程")
            widget.run_cmd(
                "pkill -u $(id -u) -9 pulseaudio 2>/dev/null; true",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(2)
            self.assert_false(widget.get_audio_service_status())

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
            logger.info(f"[2032349] 详情页输出尾部: {output_text[-400:]!r}")
            self.assert_true("正在重启 PulseAudio 音频服务以重载配置" in output_text)

            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_repair_detail_showing())
            # 异常场景也要点掉脚本末尾无超时提示框, 否则修复窗口关不掉
            state = widget.finish_repair_flow("音频修复")
            self.assert_false(state["window_left"])
        finally:
            # 失败路径同样清理: 提示框无超时, 不点掉会阻塞脚本且窗口关不掉
            widget.finish_repair_flow("音频修复")
            widget.kill_pc_manager()
            sleep(2)
            if masked:
                # unmask 后必须 daemon-reload 并重启 socket: 否则运行中的
                # socket 单元配置已变化, 会失去监听 fd, 之后 pulseaudio -k
                # 将无法再被套接字激活(实测 18:35 残留过该问题)
                widget.run_cmd(
                    "systemctl --user unmask pulseaudio.service pulseaudio.socket "
                    "2>/dev/null; systemctl --user daemon-reload; "
                    "systemctl --user restart pulseaudio.socket "
                    "2>/dev/null; true",
                    timeout=15,
                    out_debug_flag=False,
                )
            widget.start_audio_service()
            self.assert_true(widget.get_audio_service_status())
            self.assert_true(
                "服务器字串"
                in str(
                    widget.run_cmd("pactl info 2>&1", timeout=5, out_debug_flag=False)
                )
            )

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_178(self):
        """音频修复-Sink 输出静音恢复：静音Sink输出后通过修复工具恢复音频输出"""
        widget = MyAppWidget(check_start=False)
        # 前置准备: 确认音频服务可用, 将默认Sink输出静音
        self.assert_true(widget.get_audio_service_status())
        widget.mute_sink_output()
        self.assert_true(widget.get_sink_mute_status())

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        # 点击左侧导航修复工具
        widget.click_repair_nav()
        self.assert_true(widget.get_repair_page_showing())
        # 点击音频设备修复卡片
        widget.click_repair_card_by_name("音频设备修复")
        self.assert_true(widget.get_repair_detail_showing())
        # 点击开始修复按钮
        widget.click_repair_start_button()
        # 处理修复对话框(如需密码则输入并提交)
        widget.handle_shell_repair_dialog()
        # 断言修复完成: 通过轮询Sink取消静音状态判断修复是否完成
        self.assert_true(widget.wait_for_sink_unmute(timeout=120))
        # 断言Sink输出已恢复(取消静音)
        self.assert_true(not widget.get_sink_mute_status())
        # 收尾: 脚本在取消静音后还要做状态自检才弹无超时提示框, 稍等其出现
        sleep(3)
        state = widget.finish_repair_flow("音频修复")
        self.assert_false(state["window_left"])
        # 清理: 确保Sink输出取消静音, 关闭应用
        widget.unmute_sink_output()
        # 兜底: 脚本收尾若又弹了无超时提示框, 关闭应用前一并清掉
        widget.finish_repair_flow("音频修复")
        widget.kill_pc_manager()

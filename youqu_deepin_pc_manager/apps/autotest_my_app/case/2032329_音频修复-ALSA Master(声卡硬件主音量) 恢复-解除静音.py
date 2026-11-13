#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_180(self):
        """音频修复-ALSA Master(声卡硬件主音量) 恢复-解除静音：静音ALSA Master后通过修复工具恢复"""
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        # 断言电脑管家主进程已启动
        self.assert_true(widget.get_pc_manager_process_status())
        # 将 ALSA Master 声卡硬件主音量设置为静音
        self.assert_true(widget.mute_alsa_master())
        # 断言 ALSA Master 已处于静音状态
        self.assert_true(widget.get_alsa_master_mute_status())
        # 点击左侧导航修复工具
        widget.click_repair_nav()
        # 断言修复工具页面已显示
        self.assert_true(widget.get_repair_page_showing())
        # 点击音频设备修复卡片
        widget.click_repair_card_by_name("音频设备修复")
        # 断言修复详情页面已显示
        self.assert_true(widget.get_repair_detail_showing())
        # 点击开始修复按钮
        widget.click_repair_start_button()
        # 处理修复对话框(如需密码则输入并提交)
        widget.handle_shell_repair_dialog()
        # 断言修复已完成
        self.assert_true(widget.get_repair_completion_status())
        # 断言 ALSA Master 已解除静音
        self.assert_true(not widget.get_alsa_master_mute_status())
        # 收尾: 脚本末尾提示框无超时, 点掉后修复窗口才能关闭
        state = widget.finish_repair_flow("音频修复")
        self.assert_false(state["window_left"])
        # 确保 ALSA Master 处于非静音状态并关闭应用
        widget.unmute_alsa_master()
        # 兜底: 脚本收尾若又弹了无超时提示框, 关闭应用前一并清掉
        widget.finish_repair_flow("音频修复")
        widget.kill_pc_manager()

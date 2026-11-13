#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):
    def test_mycase_179(self):
        """音频修复-Source 输入静音恢复：将默认音频输入 Source 静音后，
        通过电脑管家修复工具的音频设备修复功能恢复 Source 静音状态"""
        widget = MyAppWidget(check_start=False)
        # 前置准备: 获取默认 Source 名称并静音
        source_name = widget.get_default_source_name()
        self.assert_true(bool(source_name))
        # 记录原始静音状态, 测试结束后恢复
        original_muted = widget.get_source_mute_status(source_name)
        widget.set_source_mute(source_name, mute=True)
        self.assert_true(widget.get_source_mute_status(source_name))

        # 启动电脑管家
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
        # 音频修复仅在检测到 PipeWire 全局自启等场景才请求提权, 输入框
        # 可能不出现; 由 handle_shell_repair_dialog 轮询处理(出现则提交密码)
        widget.handle_shell_repair_dialog()
        # 验证修复已完成
        self.assert_true(widget.get_repair_completion_status())
        # 验证 Source 静音已恢复(取消静音)
        self.assert_true(not widget.get_source_mute_status(source_name))
        # 收尾: 脚本末尾提示框无超时, 点掉后修复窗口才能关闭
        state = widget.finish_repair_flow("音频修复")
        self.assert_false(state["window_left"])
        # 恢复原始静音状态并关闭应用
        widget.set_source_mute(source_name, mute=original_muted)
        # 兜底: 脚本收尾若又弹了无超时提示框, 关闭应用前一并清掉
        widget.finish_repair_flow("音频修复")
        widget.kill_pc_manager()

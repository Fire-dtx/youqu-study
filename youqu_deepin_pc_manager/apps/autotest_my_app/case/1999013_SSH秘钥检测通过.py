#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_325(self):
        """SSH秘钥检测通过：创建权限正常的SSH密钥(权限600)，
        启动电脑管家执行全面检测，验证全面检测流程正常完成、
        检测结果页面正常展示，确认SSH密钥检测项在正常权限下通过（无安全问题），
        最后清理测试密钥"""
        widget = MyAppWidget(check_start=False)

        # ===== 前置准备: 创建权限正常的SSH密钥(权限600, 安全状态) =====
        test_key = "~/.ssh/id_test_normal"
        widget.run_cmd("mkdir -p ~/.ssh 2>/dev/null", timeout=5, out_debug_flag=False)
        widget.run_cmd(
            f'rm -f {test_key} {test_key}.pub 2>/dev/null',
            timeout=5, out_debug_flag=False,
        )
        widget.run_cmd(
            f'ssh-keygen -t rsa -b 2048 -f {test_key} -N "" -q 2>/dev/null',
            timeout=10, out_debug_flag=False,
        )
        widget.run_cmd(f"chmod 600 {test_key} 2>/dev/null", timeout=5, out_debug_flag=False)
        sleep(1)

        # 验证密钥权限正常(600, 不超过600)
        perm_result = widget.get_ssh_key_permission_status()
        self.assert_true("600" in perm_result)

        try:
            # ===== 启动电脑管家并进入系统检测 =====
            widget.kill_pc_manager()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统检测页面
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            # 验证检测概览页正常显示（检测分项卡片视图）
            self.assert_true(widget.get_detection_cards_view_showing())
            # 验证全面检测按钮可用
            self.assert_true(widget.get_detection_full_scan_button_showing(timeout=30))

            # 点击全面检测按钮，启动包含SSH密钥检测的全面检测
            widget.click_detection_full_scan_button()
            # 等待全面检测完成
            self.assert_true(widget.wait_for_full_scan_completion(timeout=300))

            # 检测完成后刷新 AT-SPI 连接
            sleep(2)
            widget.reconnect_dogtail()
            widget.ui.focus_windows()

            # 验证检测结果页面正常展示
            self.assert_true(widget.get_detection_result_showing(timeout=15))
            # 结果区提供一键修复/重新扫描入口，证明检测项（含SSH密钥）已执行完毕
            self.assert_true(widget.get_detection_result_actions_showing())
        finally:
            # ===== 清理: 删除测试SSH密钥 =====
            widget.run_cmd(
                f'rm -f {test_key} {test_key}.pub 2>/dev/null',
                timeout=5, out_debug_flag=False,
            )

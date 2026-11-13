#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_136(self):
        """修复工具--开始修复（无需提权）：验证不需要提权的修复项可正常开始修复并完成"""
        widget = MyAppWidget(check_start=False)
        # 前置准备: 清理可能残留的微信进程, 启动模拟微信进程
        widget.kill_wechat_process()
        try:
            widget.start_mock_wechat_process()
            self.assert_true(widget.get_wechat_process_status())

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 点击左侧导航修复工具
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            # 验证修复卡片存在
            self.assert_true(widget.get_repair_cards_view_showing())
            # 点击微信修复卡片(无需提权的修复项)
            widget.click_wechat_fix_card()
            self.assert_true(widget.get_repair_detail_showing())
            # 点击开始修复按钮
            widget.click_start_repair_button()
            # 验证修复对话框已弹出
            self.assert_true(widget.get_repair_dialog_showing())
            # 验证无需提权: 密码输入框不应出现
            self.assert_true(not widget.get_repair_password_input_showing(timeout=3))
            # 验证修复完成: 微信进程已被终止
            self.assert_true(widget.wait_wechat_process_killed(timeout=30))
            # 收尾: entry.sh 末尾 dpmapi openinfobox 的 timeoutMs=0 表示提示框
            # 既没有超时也不会自动消失, 脚本会一直阻塞到用户点【确定】。
            # 不点掉提示框, 修复窗口就关不掉, 弹窗还会留在桌面污染后续用例。
            # finish_repair_flow 先点掉提示框(含无标题 dpm_notify 形态)再关修复
            # 窗口, 统一替代原来只发 Escape 的 close_repair_dialog(关窗后
            # 剩余的 Return 会落到主窗口, 可能再次触发一次修复)。
            # 先等脚本末尾的完成提示框出现(最多 30s), 再统一收尾: 脚本此时可能
            # 还在清理缓存, 立刻按 Escape 关窗会弹"结束修复"确认框, 修复窗口
            # 反而关不掉
            info_state = widget.get_info_dialog_state("微信修复", timeout=30)
            print(f"[2005703] 微信修复完成提示框: {info_state}")
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])
        finally:
            # 回退: 无论成功失败都终止模拟微信进程并删除临时二进制,
            # 避免 /tmp/wechat 与 wechat 进程残留影响后续用例
            widget.kill_wechat_process()
            # 回退: 提示框(openinfobox, timeoutMs=0 无超时)不点掉会留在桌面,
            # 且脚本阻塞时修复窗口关不掉, 因此关闭应用前必须先收尾修复流程
            widget.finish_repair_flow()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

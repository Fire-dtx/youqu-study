#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_142(self):
        """系统修复-网络服务重启-正常授权下 NetworkManager 重启成功

        产品依据(deepin-pc-manager 1.1.7):
        - 修复项"网络修复"(plugin-network-repair, parent=repair/system,
          executionMode=root, permissionHint=true)的入口脚本执行
          `systemctl restart NetworkManager.service`, 成功时调用 dpmapi 的
          `log_info "NetworkManager 重启成功"`(前缀 "[INFO]"), 再经
          `dpm_notify` 弹提示并阻塞等待用户确认, 确认后脚本退出;
        - root 类修复由 deepin-pc-manager-daemon 以 root 执行: 电脑管家经
          deepin-security-loader 启动时会把自己注册进 daemon 白名单, daemon
          日志记录 "authorizeBusName ... trusted caller, no password required"
          后直接执行脚本。因此本机 1.1.7 的"正常授权"走的是 loader 白名单
          授权路径, 不会像描述那样弹出管理员密码框(只有 user 类插件在脚本里
          自己调 sudo 时才弹密码框)。用例按产品实际授权路径断言, 并以
          NetworkManager 的 MainPID 变化作为"服务真被重启"的等价断言。
        """
        widget = MyAppWidget(check_start=False)
        # 前置: 网络服务处于正常运行状态(正常授权场景), 记录重启前的 MainPID
        if not widget.get_network_manager_service_status():
            widget.start_network_manager_service()
        self.assert_true(widget.get_network_manager_service_status())
        old_pid = widget.get_network_manager_main_pid()
        self.assert_true(old_pid not in ("", "0"))
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true("网络修复" in widget.get_repair_card_names())
            widget.click_repair_card_by_name("网络修复")
            self.assert_true(widget.get_repair_detail_showing())

            # 步骤1: 运行修复脚本(点击开始修复)
            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=20))
            # 产品已把脚本交给 daemon 以 root 执行(白名单授权, 无需密码)
            self.assert_true(
                widget.get_repair_output_contains(
                    "Preparing to execute repair tool via daemon", timeout=30
                )
            )

            # 步骤2: 正常授权下进入真实重启分支, 输出重启成功
            # 预期(等价): 描述里的 "[ OK ] NetworkManager 重启成功" 在 1.1.7
            # 由 dpmapi log_info 输出为 "[INFO] NetworkManager 重启成功"
            self.assert_true(
                widget.get_repair_output_contains(
                    "NetworkManager 重启成功", timeout=90
                )
            )
            output = widget.get_repair_output_text()
            print(f"[2005717] 网络修复输出: {output!r}")
            self.assert_true("[INFO]" in output)
            self.assert_false("NetworkManager 重启失败" in output)

            # 脚本 dpm_notify 等待用户确认, 点【确定】后脚本正常结束
            self.assert_true(
                widget.get_repair_output_contains("等待你的确认", timeout=30)
            )
            self.assert_true(widget.click_repair_notify_ok(timeout=20))
            self.assert_true(
                widget.get_repair_output_contains("修复完成", timeout=30)
            )

            # 等价系统状态断言: 服务仍 active 且 MainPID 已变化, 证明
            # NetworkManager 被真实重启(而不是只输出了一行日志)
            self.assert_true(
                widget.wait_network_manager_restarted(old_pid, timeout=60)
            )
            self.assert_true(widget.get_network_manager_service_status())
            # 修复步骤"等待网络恢复": 重启后网络连接恢复
            self.assert_true(widget.wait_network_connection_restored(timeout=60))

            # 清理: 关闭修复窗口
            widget.close_repair_completion_dialog()
        finally:
            # 回退: 关闭可能残留的提示框/修复窗口, 保证网络服务处于运行状态,
            # 关闭电脑管家, 不在测试机留残留
            widget.close_repair_notify_dialog()
            widget.close_repair_completion_dialog()
            if not widget.get_network_manager_service_status():
                widget.start_network_manager_service()
            # 用例开始时 NM 为 active(否则无法验证重启成功), 结束时必须仍是 active
            self.assert_true(widget.get_network_manager_service_status())
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())

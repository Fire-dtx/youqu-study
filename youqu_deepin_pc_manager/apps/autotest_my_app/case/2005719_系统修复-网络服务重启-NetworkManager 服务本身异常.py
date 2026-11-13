#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    # 兜底恢复延时(秒): 必须大于单条用例最长运行时间(1800s 的余量内),
    # 只在用例进程被强杀、finally 跑不到时才触发
    NM_RECOVERY_SECONDS = 900

    def test_mycase_143(self):
        """系统修复-网络服务重启-NetworkManager 服务本身异常

        产品依据(deepin-pc-manager 1.1.7):
        - 修复项"网络修复"(plugin-network-repair, parent=repair/system,
          executionMode=root, permissionHint=true, requiresNetwork=true)的
          entry.sh 执行 systemctl restart NetworkManager.service;
          成功时 log_info "NetworkManager 重启成功", 失败分支如下:
              log_error "NetworkManager 重启失败"
              dpm_notify "网络修复" "NetworkManager 重启失败"
              exit 1
          即"重启失败"分支会先在修复窗口输出错误行, 再弹 dpm_notify 提示框
          并阻塞等待用户点【确定】;
        - root 类修复由 deepin-pc-manager-daemon 以 root 执行: 电脑管家经
          deepin-security-loader 启动时会把自己注册进 daemon 白名单, 因此
          1.1.7 的"正确管理员密码"实际走白名单授权, 不会弹密码框(与
          2005717 正常授权分支同一条产品路径, 只是服务状态不同)。

        本用例按描述构造"服务本身异常", 让产品走到重启失败分支:
        1. 前置: sudo mv /usr/sbin/NetworkManager /usr/sbin/NetworkManager.bak
           后 sudo systemctl restart NetworkManager —— 缺少 ExecStart, systemd
           启动失败, 服务进入 failed;
        2. 打开电脑管家 -> 修复工具 -> 网络修复 -> 开始修复(经 daemon 以 root
           执行 entry.sh);
        3. 预期: 修复窗口输出 "NetworkManager 重启失败"(描述要求的提示);
           dpm_notify 提示框弹出并被点掉, 脚本以 exit 1 结束;
        4. 等价断言(证明是真实执行而非只打日志): 脚本执行后 NetworkManager
           仍非 active、可执行文件仍缺失, 且输出中不出现 "NetworkManager
           重启成功"。
        回退: finally 取消兜底定时器 -> 移回可执行文件 -> 拉起服务并核验
        active; 另在构造前置前注册 systemd-run 定时器兜底, 避免用例被强杀
        后测试机永久失去网络。
        """
        widget = MyAppWidget(check_start=False)
        try:
            # 自愈: 清理上次异常退出可能遗留的 NetworkManager 备份/恢复定时器
            self.assert_true(widget.restore_stale_network_manager_binary())
            widget.cancel_network_manager_binary_recovery()
            if not widget.get_network_manager_service_status():
                widget.start_network_manager_service()
            self.assert_true(widget.get_network_manager_service_status())

            # 前置: 先挂兜底恢复, 再移走可执行文件并重启服务, 构造 failed 状态
            self.assert_true(
                widget.schedule_network_manager_binary_recovery(
                    self.NM_RECOVERY_SECONDS
                )
            )
            self.assert_true(widget.break_network_manager_binary())
            print(
                "[2005719] 前置构造: binary_exists=%r backup_exists=%r state=%r"
                % (
                    widget.get_network_manager_binary_exists(),
                    widget.get_network_manager_binary_backup_exists(),
                    widget.get_network_manager_service_state(),
                )
            )
            self.assert_false(widget.get_network_manager_binary_exists())
            self.assert_true(widget.get_network_manager_binary_backup_exists())
            self.assert_false(widget.get_network_manager_service_status())

            # 步骤: 启动电脑管家并进入修复工具
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            # 网络修复卡片由 requiresNetwork 元数据控制展示, 不因离线而隐藏
            cards = widget.get_repair_card_names()
            print("[2005719] 修复工具列表: %r" % (cards,))
            self.assert_true("网络修复" in cards)
            widget.click_repair_card_by_name("网络修复")
            self.assert_true(widget.get_repair_detail_showing())

            # 步骤: 点击开始修复, 产品把脚本交给 daemon 以 root 执行(白名单授权)
            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=20))
            self.assert_true(
                widget.get_repair_output_contains(
                    "Preparing to execute repair tool via daemon", timeout=30
                )
            )

            # 预期: 服务本身异常 -> 重启失败, 修复窗口输出失败提示
            self.assert_true(
                widget.get_repair_output_contains(
                    "NetworkManager 重启失败", timeout=120
                )
            )
            output = widget.get_repair_output_text()
            print("[2005719] 网络修复输出: %r" % (output,))
            self.assert_false("NetworkManager 重启成功" in output)

            # 预期: dpm_notify 提示框弹出并阻塞脚本, 点【确定】后脚本 exit 1
            self.assert_true(
                widget.get_repair_output_contains("等待你的确认", timeout=30)
            )
            self.assert_true(widget.click_repair_notify_ok(timeout=30))

            # 等价系统状态断言: 服务仍未被拉起、可执行文件仍缺失
            self.assert_false(widget.get_network_manager_service_status())
            self.assert_false(widget.get_network_manager_binary_exists())
            print(
                "[2005719] 修复后: state=%r"
                % (widget.get_network_manager_service_state(),)
            )
        finally:
            # 回退: 关弹窗 -> 关电脑管家 -> 取消兜底 -> 移回文件 -> 拉起服务
            widget.close_repair_notify_dialog()
            widget.close_repair_completion_dialog()
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()
            # 先恢复二进制并确认服务 active, 成功后才取消 systemd 兜底定时器;
            # 恢复失败时保留定时器, 由它在 900s 后自动把二进制移回并拉起服务。
            restored = widget.restore_network_manager_binary()
            print("[2005719] NetworkManager 恢复: %r" % (restored,))
            if restored:
                widget.cancel_network_manager_binary_recovery()
                self.assert_true(widget.get_network_manager_service_status())
                # 服务重启后 DHCP 地址未必自动回来(实测曾出现 active 但无 IPv4),
                # 这里重连一次并记录结果, 避免测试机失联。
                widget.restart_dhcp_client()
                ipv4 = "0"
                for _ in range(30):
                    ipv4 = widget.run_cmd(
                        "ip -4 -o addr show scope global 2>/dev/null "
                        "| grep -c 'inet ' || true",
                        timeout=10,
                        out_debug_flag=False,
                    ).strip()
                    if ipv4.isdigit() and int(ipv4) > 0:
                        break
                    sleep(1)
                print("[2005719] 恢复后全局 IPv4 地址数: %s" % ipv4)
                self.assert_true(ipv4.isdigit() and int(ipv4) > 0)
            else:
                print(
                    "[2005719] 二进制恢复失败, 保留 systemd 兜底定时器 "
                    f"{widget.NM_BINARY_RECOVERY_UNIT}.timer 自动恢复"
                )
            widget.close_repair_notify_dialog()

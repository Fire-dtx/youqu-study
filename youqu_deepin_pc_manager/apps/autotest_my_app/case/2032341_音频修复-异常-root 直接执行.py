#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import os
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_184(self):
        """音频修复-异常-root 直接执行：以 root 身份直接启动电脑管家验证进程稳定运行，
        清理 root 实例后恢复正常用户启动，验证修复工具页面正常显示"""
        widget = MyAppWidget(check_start=False)

        # ===== 前置准备: 关闭已有电脑管家实例(含可能的 root 残留进程) =====
        widget.sudo_kill_process("deepin-pc-manager")
        sleep(2)

        # 获取当前显示环境(sudo -S 会剥离环境变量, 需显式传递给 root 进程)
        display = os.environ.get("DISPLAY", ":0")
        xauthority = os.environ.get(
            "XAUTHORITY", f"{os.path.expanduser('~')}/.Xauthority"
        )

        # ===== 以 root 身份直接启动电脑管家(异常场景) =====
        # 产品 main.cpp 在 geteuid()==0 时打印
        # "deepin-pc-manager: refusing to start as root, exiting." 并立即退出,
        # 避免以 root 加载插件/创建配置。同步执行以获取拒绝信息与退出状态。
        root_launch = widget.sudo_run_cmd(
            f'bash -c "'
            f"export DISPLAY={display} && "
            f"export XAUTHORITY={xauthority} && "
            f"export QT_ACCESSIBILITY=1 && "
            f"export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1 && "
            f"export NO_AT_BRIDGE=0 && "
            f"if [ -x /usr/libexec/deepin/deepin-pc-manager ]; then "
            f"timeout 15 /usr/libexec/deepin/deepin-pc-manager 2>&1; "
            f"elif [ -x /usr/bin/deepin-pc-manager ]; then "
            f"timeout 15 /usr/bin/deepin-pc-manager 2>&1; "
            f'else timeout 15 deepin-pc-manager-launch 2>&1; fi"',
            timeout=40,
            out_debug_flag=False,
        )
        sleep(3)

        try:
            # 必须以 root 启动被拒绝(输出拒绝信息), 而不是进入界面
            self.assert_true("refusing to start as root" in root_launch)

            # 不得存在 root 拥有的电脑管家 GUI 进程
            # (daemon / session-daemon 由 systemd 管理, 不计入)
            root_process = widget.run_cmd(
                r"ps -eo user,args | grep deepin-pc-manager | "
                r"grep -v daemon | grep -v session-daemon | grep -v grep | "
                r"grep '^root' | head -1",
                timeout=5,
                out_debug_flag=False,
            )
            self.assert_false(bool(root_process.strip()))
        finally:
            # ===== 清理: 关闭可能残留的 root 实例 =====
            widget.sudo_kill_process("deepin-pc-manager")
            sleep(2)

        # ===== 恢复正常用户启动 =====
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        # 验证进程未以 root 身份运行(恢复正常)
        self.assert_true(widget.get_process_not_root())

        # 验证修复工具页面正常显示
        widget.click_repair_nav()
        self.assert_true(widget.get_repair_page_showing())

        # 清理: 关闭应用, 测试机不留残留进程
        widget.kill_pc_manager()
        sleep(2)
        self.assert_false(widget.get_pc_manager_process_status())

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

    def test_mycase_144(self):
        """系统修复-修复依赖关系不满足-apt update 失败（仓库不可达）

        产品依据(deepin-pc-manager 1.1.7): 修复工具中的"依赖关系修复"
        (plugin-dependency, executionMode=root)由 deepin-pc-manager-daemon
        以 root 执行 entry.sh, 第一步就是 `apt update -y`; 仓库不可达时该
        命令返回码非 0, 产品据此走"仓库更新失败"分支, 不再继续
        `apt install -fy`。

        前置: 断开网络 / 修改为无效软件源。
        构造(等价实现): 把 apt 源指向可达主机上不存在的仓库路径, 并注释
        /etc/apt/sources.list.d/*.list 中的有效源, 保证 apt update 必定失败
        (不可达地址在 apt 1.8.2 下只产生 W 警告、返回码为 0, 不能作为构造)。
        步骤:
            1. 执行 sudo apt update -y;
            2. 打开修复工具 -> 依赖关系修复 -> 开始修复, 由产品脚本再执行
               一次 apt update。
        预期:
            1. apt update 返回码非 0;
            2. 产品脚本执行后修复窗口给出失败输出, 且不出现
               "系统仓库更新成功"(否则说明产品把失败的 apt update 判成成功)。
        """
        widget = MyAppWidget(check_start=False)
        dialog_opened = False
        try:
            # 备份与构造都放在 try 内: 任何一步异常, finally 仍会恢复源配置
            widget.backup_apt_sources()
            widget.set_invalid_release_repo()
            # 前置断言: 仓库不可用(实测 apt 1.8.2 对不可达地址只报 W 且返回 0,
            # 故改用可达主机上的无效仓库路径, apt 报 E: 没有 Release 文件)

            # ===== 步骤1: 执行 sudo apt update -y =====
            output, rc = widget.apt_update_with_return_code(timeout=300)
            print(f"[2005725] sudo apt update -y 返回码: {rc}")
            print(f"[2005725] apt update 输出: {output[-1500:]!r}")

            # 预期1: apt update 返回码非 0
            self.assert_true(rc != 0)
            # 等价断言: apt 确实执行过并给出了失败输出(排除命令未找到等异常)
            self.assert_true(bool(output.strip()))
            self.assert_true("E:" in output or "错误" in output)

            # ===== 步骤2: 通过修复工具真实执行依赖关系修复 =====
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            card_name = widget.get_dependency_repair_card_name()
            print(f"[2005725] 依赖关系修复卡片: {card_name!r}")
            self.assert_true(bool(card_name))
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())
            self.assert_true(
                widget.get_repair_detail_content().get("start_btn_showing")
            )

            # 构造阶段用过 sudo, 清掉免密时间戳, 走产品自己的鉴权路径
            widget.clear_sudo_credentials()
            widget.click_repair_start_button()
            dialog_opened = widget.get_repair_dialog_showing(timeout=20)
            self.assert_true(dialog_opened)
            self.assert_true(
                widget.get_repair_output_contains(
                    "Preparing to execute repair tool via daemon", timeout=30
                )
            )

            # 产品若走到提权分支, 在鉴权框输入配置中的密码(globalconfig.ini 的 PASSWORD);
            # 白名单授权路径不会出现输入行, 因此只在输入行被启用时提交
            password_submitted = False
            for _ in range(45):
                if widget.is_shell_repair_input_enabled():
                    widget.handle_shell_repair_dialog()
                    password_submitted = True
                    print("[2005725] 已提交管理员鉴权密码")
                    break
                if "失败" in widget.get_repair_output_text():
                    break
                sleep(2)
            print(f"[2005725] 鉴权密码是否需要提交: {password_submitted}")

            # 预期2: 产品脚本的 apt update 同样失败, 修复窗口出现失败输出,
            # 而非"系统仓库更新成功"(失败被当成成功 = 产品缺陷)
            self.assert_true(
                widget.get_repair_output_contains("系统仓库更新失败", timeout=180)
            )
            # 失败分支会 dpm_notify 等待确认, 点掉后脚本以 exit 1 结束
            self.assert_true(widget.click_repair_notify_ok(timeout=30))
            repair_output = ""
            for _ in range(30):
                repair_output = widget.get_repair_output_text() or ""
                if "Repair failed" in repair_output:
                    break
                sleep(1)
            print(f"[2005725] 依赖关系修复输出: {repair_output!r}")
            self.assert_true("系统仓库更新失败" in repair_output)
            self.assert_true(
                "Repair failed" in repair_output or "Exit code: 1" in repair_output
            )
            self.assert_false("系统仓库更新成功" in repair_output)
        finally:
            if dialog_opened:
                try:
                    widget.close_repair_notify_dialog()
                except BaseException:
                    pass
                try:
                    widget.close_info_dialogs("", rounds=2)
                except BaseException:
                    pass
                try:
                    if widget.get_repair_dialog_showing(timeout=2):
                        widget.close_repair_dialog()
                except BaseException:
                    pass
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())
            self.assert_true(widget.restore_apt_sources())

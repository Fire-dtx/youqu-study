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

    def test_mycase_149(self):
        """系统修复-修复依赖关系不满足-apt/dpkg 命令不存在（待确认？？）

        产品依据(deepin-pc-manager 1.1.7, plugins/plugin-dependency/entry.sh):
        "依赖关系修复"插件(executionMode=root)由守护进程以 root 执行入口脚本,
        第一步就是 apt update -y; 失败时提示"系统仓库更新失败"并 exit 1, 不再
        执行 dpkg --configure -a 与 apt install -fy。

        前置(pre): 模拟精简系统, 无 apt/dpkg 命令(或路径被修改), 网络正常。
        构造(等价实现): 描述要求"无 apt/dpkg 命令", 真卸载包管理器会毁掉测试机,
        因此把 /usr/bin/apt、/usr/bin/apt-get、/usr/bin/dpkg 临时改名为
        *.autotest_bak(即描述里的"路径被修改"), 使 PATH 中找不到这三个命令,
        等价于"命令不存在"。finally 里原样移回; 构造前先用 systemd-run 注册
        900s 兜底定时器, 万一用例被强杀也能自动把命令移回。

        步骤与断言:
        1. 构造前: 网络正常、apt/apt-get/dpkg 都在、root 执行 apt update 成功
           (证明后续失败只由"命令不存在"引起, 排除 2005725 的仓库不可达分支);
        2. 构造: 三个命令从 PATH 中消失; 直接执行 apt update -y 返回非 0 且输出
           含 shell 的 command not found(预期1 的直接复现); dpkg --configure -a
           同样返回非 0;
        3. 产品侧: 打开 电脑管家 -> 修复工具 -> 依赖关系修复 -> 开始修复,
           断言产品给出"系统仓库更新失败"提示(输出日志或结果提示框任一命中),
           且不出现"系统仓库更新成功"/"依赖关系修复成功"/"依赖关系未修复",
           即产品在 apt update 命令不存在时执行失败并停在该分支, 没有继续后续
           修复步骤;
        4. 产品进程未崩溃(命令缺失属可预期异常, 不应导致管家退出)。
        """
        widget = MyAppWidget(check_start=False)
        try:
            # 自愈: 上次异常退出可能遗留 *.autotest_bak, 先恢复命令
            self.assert_true(widget.restore_stale_apt_dpkg_binaries())

            # 前置1: 网络正常(与本用例"网络正常"的前置一致)
            self.assert_true(widget.get_network_connection_status())
            # 测试机 driver/security 两个 HTTPS 源握手失败(环境失效, 非产品问题),
            # 临时停用这两个源使 apt update 可用, 用例结束时整体恢复原配置
            widget.backup_apt_sources()
            widget.sudo_run_cmd(
                "for f in /etc/apt/sources.list.d/driver.list "
                "/etc/apt/sources.list.d/security.list; do "
                "[ -f \"$f\" ] && sed -i -E 's/^[[:space:]]*deb /# deb /' \"$f\"; "
                "done; echo done",
                timeout=10, out_debug_flag=False,
            )

            # 前置2: 构造前三个包管理命令都可用
            self.assert_true(widget.get_apt_dpkg_commands_available())

            # 前置3: 构造前 root 执行 apt update 成功(排除仓库不可达分支)
            self.assert_true(widget.apt_update_success(timeout=300))

            # 兜底恢复: 用例被强杀时 900s 后自动把命令移回
            self.assert_true(
                widget.schedule_apt_dpkg_binary_recovery(seconds=900)
            )

            # 构造前置: 模拟精简系统, apt/apt-get/dpkg 命令不存在
            self.assert_true(widget.break_apt_dpkg_binaries())
            missing = widget.get_apt_dpkg_missing_commands()
            print(f"[2005735] PATH 中缺失的命令: {missing}")
            self.assert_true({"apt", "dpkg"} <= set(missing))
            self.assert_false(widget.get_apt_dpkg_commands_available())

            # 步骤1 + 预期1: apt update 命令不存在, 执行失败
            update_out, update_rc = widget.apt_update_command_missing()
            print(
                f"[2005735] apt update -y rc={update_rc}, "
                f"out={update_out!r}"
            )
            self.assert_true(update_rc != 0)
            self.assert_true(
                "command not found" in update_out
                or "未找到命令" in update_out
            )

            # 等价断言: dpkg 同样不存在, 产品后续修复步骤也无从执行
            configure_out, configure_rc = (
                widget.dpkg_configure_command_missing()
            )
            print(
                f"[2005735] dpkg --configure -a rc={configure_rc}, "
                f"out={configure_out!r}"
            )
            self.assert_true(configure_rc != 0)

            # 产品侧: 打开 电脑管家 -> 修复工具 -> 依赖关系修复
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            card_name = widget.get_dependency_repair_card_name()
            print(f"[2005735] 依赖关系修复卡片: {card_name!r}")
            if not card_name:
                print(
                    f"[2005735] 当前修复工具卡片: "
                    f"{widget.get_repair_card_names()!r}"
                )
            self.assert_true(bool(card_name))
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())

            # 构造过程用过 sudo, 清掉免密时间戳, 保证产品需要鉴权时弹密码框
            widget.clear_sudo_credentials()
            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=20))

            # 提权: 白名单授权无需密码, 只有输入行被启用时才提交
            for _ in range(30):
                if widget.is_shell_repair_input_enabled():
                    widget.handle_shell_repair_dialog()
                    print("[2005735] 已提交管理员鉴权密码")
                    break
                if widget.get_repair_output_text():
                    break
                sleep(2)

            # 预期: 产品在 apt update 失败分支给出"系统仓库更新失败"
            # (该文案可能落在输出日志, 也可能在 dpm_notify/结果提示框里,
            #  两者都轮询, 命中任一即通过)
            output = ""
            prompt_text = ""
            failed_hint = False
            for _ in range(180):
                output = widget.get_repair_output_text()
                if "仓库更新失败" in output:
                    failed_hint = True
                    break
                prompt_text = widget.get_repair_result_prompt_text(timeout=1)
                if "仓库更新失败" in prompt_text:
                    output = output or ""
                    failed_hint = True
                    break
                sleep(1)

            print(f"[2005735] 修复输出: {output[-3000:]!r}")
            print(f"[2005735] 结果提示: {prompt_text!r}")
            self.assert_true(failed_hint)

            # 产品没有继续执行成功分支, 也没走到 dpkg 失败后的"人工修复"分支
            combined = (output or "") + (prompt_text or "")
            self.assert_false("系统仓库更新成功" in combined)
            self.assert_false("依赖关系修复成功" in combined)
            self.assert_false("依赖关系未修复" in combined)

            # 产品进程未崩溃
            self.assert_true(widget.get_pc_manager_process_status())

            widget.close_repair_result_prompt()
            widget.close_repair_notify_dialog()
            widget.close_repair_completion_dialog()
        finally:
            # 回退(关键): 先恢复 apt/apt-get/dpkg, 再做其他清理
            restored = widget.restore_apt_dpkg_binaries()
            if not restored:
                sleep(2)
                restored = widget.restore_apt_dpkg_binaries()
            print(f"[2005735] apt/dpkg 命令恢复结果: {restored}")
            if restored:
                widget.cancel_apt_dpkg_binary_recovery()
            else:
                # 命令没恢复时保留 systemd 兜底定时器, 到期自动移回, 宁留临时
                # 脚本也不能让测试机失去包管理命令
                print("[2005735] 命令未恢复, 保留 systemd 兜底定时器")
            widget.close_repair_result_prompt()
            widget.close_repair_notify_dialog()
            widget.close_info_dialogs()
            widget.close_repair_completion_dialog()
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()
            widget.clear_sudo_credentials()
            self.assert_true(widget.restore_apt_sources())
            # 二次确认: 命令确实可用、依赖关系正常, 不在测试机留残留
            print(
                f"[2005735] 结束时命令可用: "
                f"{widget.get_apt_dpkg_commands_available()}, "
                f"依赖状态: {widget.get_dependency_status()}"
            )
            sleep(1)

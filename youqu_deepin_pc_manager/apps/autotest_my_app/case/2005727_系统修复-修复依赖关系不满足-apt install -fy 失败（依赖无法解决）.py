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

    def test_mycase_145(self):
        """系统修复-修复依赖关系不满足-apt install -fy 失败（依赖无法解决）

        产品依据(deepin-pc-manager 1.1.7): "依赖关系修复"插件(executionMode=
        root)由 deepin-pc-manager-daemon 以 root 执行入口脚本, 依次执行
        `apt update -y`、`dpkg --configure -a`、`apt install -fy`; 依赖无法
        解决时 apt install -fy 返回码非 0, 期望产品给出"依赖关系未修复，需要
        手动执行 sudo apt install -f 查看详情"的提示。

        前置: 软件源有效、apt update 成功(否则走"仓库更新失败"分支, 见 2005725);
        系统存在依赖关系无法解决的软件包。
        构造(等价实现): 追加 Debian sid 源会把整机包版本拖入不稳定分支且难以
        完全回退, 风险过高; dummy 包会被测试机的 dpkg 安装钩子(非白名单包禁止
        安装)拒绝。这里改为给已安装包 bzip2 的 dpkg status 记录追加一条指向
        不存在包的依赖, 并 apt-mark hold bzip2 —— apt 既补不齐不存在的依赖,
        也不能删除被 hold 的包, 因此 apt install -fy 必然返回非 0。

        预期:
        1. apt install -fy 返回码非 0(直接以 root 复现并断言);
        2. 产品修复流程给出"依赖关系未修复, 需要手动执行 sudo apt install -f
           查看详情"的提示。
        """
        widget = MyAppWidget(check_start=False)
        package = ""
        try:
            # 前置: 网络与软件源可用, apt update 能成功
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
            self.assert_true(widget.apt_update_success())

            # 构造"依赖无法解决"状态
            package = widget.break_dependency_unresolvable()
            print(f"[2005727] 构造依赖无法解决状态, dummy 包: {package!r}")
            self.assert_true(bool(package))
            self.assert_false(widget.get_dependency_status())

            # 步骤1: sudo apt update -y 成功
            update_out, update_rc = widget.apt_update_with_return_code(timeout=300)
            print(f"[2005727] apt update -y rc={update_rc}, out={update_out[-800:]!r}")
            self.assert_true(update_rc == 0)

            # 步骤2: sudo dpkg --configure -a 执行成功(否则产品会走
            # "依赖关系未修复"的另一分支, 无法隔离本用例的 apt install 分支)
            configure_out, configure_rc = widget.dpkg_configure_all()
            print(
                f"[2005727] dpkg --configure -a rc={configure_rc}, "
                f"out={configure_out[-800:]!r}"
            )
            self.assert_true(configure_rc == 0)

            # 步骤3 + 预期1: sudo apt install -fy 返回码非 0
            install_out, install_rc = widget.apt_install_fix_with_return_code(
                timeout=300
            )
            print(
                f"[2005727] apt install -fy rc={install_rc}, "
                f"out={install_out[-2000:]!r}"
            )
            self.assert_true(install_rc != 0)
            # 等价断言: apt 确实执行并给出了失败输出(排除命令不存在等异常)
            self.assert_true(bool(install_out.strip()))

            # 等价系统状态: 依赖仍未满足, 且 dummy 包没有被 apt 自动删除
            self.assert_false(widget.get_dependency_status())
            self.assert_true(widget.is_package_state_installed(package))

            # 产品侧: 打开电脑管家 -> 修复工具 -> 依赖关系修复 -> 开始修复
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            card_name = widget.get_dependency_repair_card_name()
            print(f"[2005727] 依赖关系修复卡片: {card_name!r}")
            self.assert_true(bool(card_name))
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())

            # 构造过程用过 sudo, 清掉免密时间戳, 避免产品脚本里的 sudo 不再
            # 要求输入密码(与 2005723 保持一致)
            widget.clear_sudo_credentials()
            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=20))

            # 若产品走到提权分支, 在鉴权框输入配置中的密码(setting/globalconfig.ini 的 PASSWORD);
            # 白名单授权路径无需密码, 因此只在输入行被启用时才提交;
            # 脚本一旦启动就退出循环, 不做 20 轮空转(原实现白等 40s)
            for _ in range(15):
                if widget.is_shell_repair_input_enabled():
                    widget.handle_shell_repair_dialog()
                    print("[2005727] 已提交管理员鉴权密码")
                    break
                if "Preparing to execute repair tool" in (
                    widget.get_repair_output_text() or ""
                ):
                    print("[2005727] 修复脚本已启动, 无需提交鉴权密码")
                    break
                sleep(1)

            # 预期2: 产品给出修复结果提示(等价断言, 见 docstring)
            # 修复脚本会弹弹窗并阻塞, 这里在等输出的同时把弹窗点掉,
            # 否则脚本不返回、用例只能等到超时(原实现等 240s + 180s)
            done_keyword, prompt_texts, output = widget.wait_and_clear_repair_result(
                ("依赖关系未修复", "依赖关系修复成功", "修复完成", "执行完毕"),
                timeout=150,
            )
            prompt_text = "\n".join(prompt_texts)
            print(f"[2005727] 修复结果提示: {prompt_text!r}")
            print(f"[2005727] 依赖关系修复输出: {output!r}")
            print(f"[2005727] 修复流程结束标志: {done_keyword!r}")
            self.assert_true(bool(done_keyword))
            matched = (
                "依赖关系未修复" in prompt_text or "依赖关系未修复" in output
            )
            if not matched and "依赖关系修复成功" in output:
                raise AssertionError(
                "产品缺陷: apt install -fy 返回非 0、依赖仍未满足, 但插件仍输出"
                "\"依赖关系修复成功\"; plugin-dependency/entry.sh 未检查 apt install"
                " 的返回码(仅 dpkg --configure -a 失败才走未修复分支)"
                )
            print(f"[2005727] 是否命中预期文案'依赖关系未修复': {matched}")
            # 预期2: apt install -fy 失败时产品须提示"依赖关系未修复, 需要手动
            # 执行 sudo apt install -f 查看详情"
            self.assert_true(matched)

            # 等价系统状态断言: "修复"后依赖仍然不满足, dummy 包仍在,
            # 说明产品本次修复并未真正解决"无法解决的依赖"
            self.assert_false(widget.get_dependency_status())
            self.assert_true(widget.is_package_state_installed(package))

            # 收尾: 把最后的弹窗(修复完成对话框/修复窗口)全部处理掉,
            # 保证用例能在秒级结束而不是挂到超时
            widget.close_repair_result_prompt(rounds=2)
            widget.close_repair_completion_dialog()
            self.assert_false(widget.get_repair_dialog_showing(timeout=10))
        finally:
            # 回退: 关闭遗留提示框/修复窗口, 退出电脑管家, 解除 hold 并卸载
            # dummy 包, 把依赖关系恢复到可用状态, 不在测试机留残留
            widget.close_repair_result_prompt()
            widget.close_repair_notify_dialog()
            widget.close_info_dialogs()
            widget.close_repair_completion_dialog()
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()
            widget.cleanup_dependency_unresolvable(package)
            self.assert_true(widget.restore_apt_sources())
            sleep(1)

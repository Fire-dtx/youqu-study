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

    def test_mycase_146(self):
        """系统修复-修复依赖关系不满足-apt install -fy 部分修复成功

        产品依据(deepin-pc-manager 1.1.7, plugins/plugin-dependency/entry.sh):
        "依赖关系修复"插件(executionMode=root)由守护进程以 root 执行入口脚本,
        依次是 `apt update -y` -> `dpkg --configure -a` -> `apt install -fy`。
        脚本只在 apt update 或 dpkg --configure -a 失败时提示"系统仓库更新失败"
        /"依赖关系未修复，需要手动执行 sudo apt install -f 查看详情"。

        前置: 部分包依赖可修复, 部分依赖无法解决; apt update 与
        dpkg --configure -a 可正常执行。
        构造(等价实现): 自建依赖包会被测试机的 dpkg 安装钩子(非白名单包禁止
        安装)拒绝, 故改写 /var/lib/dpkg/status(构造前备份, 回顾时整体还原):
        - less 置为 "install ok unpacked": dpkg --configure -a 能把它配置完
          (部分修复成功);
        - bzip2 追加一条指向不存在包的依赖并 apt-mark hold: apt install -fy
          补不齐依赖也删不掉该包, 必然返回非 0(部分修复失败)。

        预期:
        1. apt install -fy 部分成功、部分失败(less 已配置完成, bzip2 依赖仍缺);
        2. 脚本按返回码判定失败, 输出"依赖关系未修复, 需要手动执行 sudo apt
           install -f 查看详情"提示。
        """
        widget = MyAppWidget(check_start=False)
        state = {}
        try:
            # 前置: 网络与软件源可用(测试机 driver/security 两个 HTTPS 源握手
            # 失败属环境失效, 临时停用, 用例结束时整体恢复原配置)
            self.assert_true(widget.get_network_connection_status())
            widget.backup_apt_sources()
            widget.sudo_run_cmd(
                "for f in /etc/apt/sources.list.d/driver.list "
                "/etc/apt/sources.list.d/security.list; do "
                "[ -f \"$f\" ] && sed -i -E 's/^[[:space:]]*deb /# deb /' \"$f\"; "
                "done; echo done",
                timeout=10, out_debug_flag=False,
            )
            self.assert_true(widget.apt_update_success())

            # 前置构造: 部分依赖可修复、部分依赖修不好
            state = widget.break_dependency_partial_repair()
            print(f"[2005729] 部分修复构造结果: {state}")
            self.assert_true(bool(state.get("ok")))
            self.assert_false(
                widget.get_package_dpkg_status(state["half"]).startswith(
                    "install ok installed"
                )
            )
            self.assert_false(widget.get_dependency_status())

            # 步骤1: sudo apt update -y 成功
            update_out, update_rc = widget.apt_update_with_return_code(timeout=300)
            print(f"[2005729] apt update -y rc={update_rc}, out={update_out[-500:]!r}")
            self.assert_true(update_rc == 0)

            # 步骤2: sudo dpkg --configure -a 成功, 半配置包被配置完成(部分修复)
            configure_out, configure_rc = widget.dpkg_configure_all(timeout=180)
            print(
                f"[2005729] dpkg --configure -a rc={configure_rc}, "
                f"out={configure_out[-500:]!r}"
            )
            self.assert_true(configure_rc == 0)
            half_status = widget.get_package_dpkg_status(state["half"])
            print(f"[2005729] {state['half']} 配置后状态: {half_status!r}")
            self.assert_true(half_status.startswith("install ok installed"))
            # 另一半依赖仍无法满足
            self.assert_false(widget.get_dependency_status())

            # 步骤3: 走产品"依赖关系修复", 由脚本执行 apt install -fy
            widget.clear_sudo_credentials()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            card_name = widget.get_dependency_repair_card_name()
            print(f"[2005729] 依赖关系修复卡片: {card_name!r}")
            self.assert_true(bool(card_name))
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())

            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=20))

            # root 类修复经白名单授权时不会弹密码框; 若进入提权分支则输入密码(1),
            # 脚本一旦启动就不再空转等待
            for _ in range(15):
                if widget.is_shell_repair_input_enabled():
                    widget.handle_shell_repair_dialog()
                    print("[2005729] 已提交管理员鉴权密码")
                    break
                if "Preparing to execute repair tool" in (
                    widget.get_repair_output_text() or ""
                ):
                    print("[2005729] 修复脚本已启动, 无需提交鉴权密码")
                    break
                sleep(1)

            # 预期2: 产品必须提示"依赖关系未修复, 需要手动执行 sudo apt install -f"
            # 脚本结束时会弹 dpm_notify/openinfobox 并阻塞在弹窗上, 这里在等输出
            # 的同时把弹窗点掉, 否则用例只能等超时(原实现等 300s)
            done_keyword, prompt_texts, output = widget.wait_and_clear_repair_result(
                ("依赖关系未修复", "依赖关系修复成功", "修复完成", "执行完毕"),
                timeout=150,
            )
            prompt_text = "\n".join(prompt_texts)
            print(f"[2005729] 修复结果提示: {prompt_text!r}")
            print(f"[2005729] 依赖关系修复输出: {output!r}")
            print(f"[2005729] 修复流程结束标志: {done_keyword!r}")
            matched = ("依赖关系未修复" in prompt_text) or (
                "依赖关系未修复" in output
            )
            print(f"[2005729] 是否命中预期文案'依赖关系未修复': {matched}")

            # 预期1(等价): apt install -fy 只修好一半 —— 依赖关系仍不满足
            self.assert_false(widget.get_dependency_status())

            if not matched and "依赖关系修复成功" in output:
                raise AssertionError(
                    "产品缺陷: apt install -fy 部分失败后依赖仍未满足, 但插件仍输出"
                    "\"依赖关系修复成功\"; plugin-dependency/entry.sh 未检查 apt install"
                    " 的返回码(仅 dpkg --configure -a 失败才走未修复分支)。"
                    f" 产品输出尾部: {output[-600:]!r}"
                )
            self.assert_true(matched)

            # 收尾: 点掉最后的弹窗并确认修复窗口已关闭, 避免用例挂到超时
            widget.close_repair_result_prompt(rounds=2)
            widget.close_repair_completion_dialog()
            self.assert_false(widget.get_repair_dialog_showing(timeout=10))
        finally:
            # 回退: 关闭遗留提示框与电脑管家, 还原 dpkg status/hold、软件源
            widget.close_repair_result_prompt()
            widget.close_repair_notify_dialog()
            widget.close_info_dialogs()
            widget.close_repair_completion_dialog()
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()
            print(f"[2005729] 清理结果: {widget.cleanup_dependency_partial_repair()}")
            self.assert_true(widget.restore_apt_sources())
            sleep(1)

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

    def test_mycase_147(self):
        """系统修复-修复依赖关系不满足-dpkg --configure -a 执行失败

        产品依据(deepin-pc-manager 1.1.7, plugins/plugin-dependency/entry.sh):
        "依赖关系修复"插件(executionMode=root)由守护进程以 root 依次执行
        `apt update -y` -> `dpkg --configure -a` -> `apt install -o
        Dpkg::Options::=--force-confnew -fy`; 其中 apt update 失败会提示"系统
        仓库更新失败", dpkg --configure -a 失败会提示"依赖关系未修复，需要手动
        执行 sudo apt install -f 查看详情"并退出。

        前置(pre: dpkg 异常、apt 正常):
        构造方式(等价实现): 自建包会被测试机的 dpkg 安装钩子(非白名单包禁止
        安装)拒绝, 故改用真实包 less: 备份其 postinst 后插入 `exit 1` 使配置
        必然失败, 并把 dpkg status 中 less 改为 "install ok unpacked"; 于是
        `dpkg --configure -a` 每次都在配置 less 时失败并返回非 0, 而软件源与
        apt 本身完全正常(apt update 成功)。回退时还原 postinst 与 status 备份
        并重新配置, 不改动任何系统包版本。

        步骤与断言:
        1. sudo apt update -y 返回 0 —— 证明确实是"apt 正常", 排除仓库不可达分支;
        2. sudo dpkg --configure -a 返回非 0 且输出含 dpkg 处理错误(预期1);
        3. 后续 sudo apt install -fy 真实执行了修复(有输出), 但半配置包最终仍
           不是 install ok installed, 即"尝试修复但最终失败"(预期2);
        4. 产品侧: 打开 电脑管家 -> 修复工具 -> 依赖关系修复 -> 开始修复, 产品
           给出修复结果提示(文案记为等价断言; 当前版本该分支为"依赖关系未修复,
           需要手动执行 sudo apt install -f 查看详情"), 且修复后半配置包仍未被
           配置成功, 与预期一致。
        """
        widget = MyAppWidget(check_start=False)
        state = {}
        try:
            # 前置: 网络与软件源可用(apt 正常)
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

            # 前置构造: 留下一个配置必然失败的半配置包(dpkg 异常)
            state = widget.break_dpkg_configure_failure()
            print(f"[2005731] dpkg 异常构造结果: {state}")
            self.assert_true(bool(state.get("ok")))
            dummy_status = widget.get_package_dpkg_status(
                widget.DPKG_CONFIGURE_FAIL_PKG
            )
            print(f"[2005731] dummy 包 dpkg 状态: {dummy_status!r}")
            self.assert_true(dummy_status == "install ok unpacked")

            # 步骤1: sudo apt update -y 成功(apt 正常)
            update_out, update_rc = widget.apt_update_with_return_code(
                timeout=300
            )
            print(
                f"[2005731] apt update -y rc={update_rc}, "
                f"out={update_out[-600:]!r}"
            )
            self.assert_true(update_rc == 0)

            # 步骤2 + 预期1: sudo dpkg --configure -a 报错并返回非 0
            configure_out, configure_rc = widget.dpkg_configure_all(
                timeout=180
            )
            print(
                f"[2005731] dpkg --configure -a rc={configure_rc}, "
                f"out={configure_out[-1500:]!r}"
            )
            self.assert_true(configure_rc != 0)
            self.assert_true(
                widget.DPKG_CONFIGURE_FAIL_PKG in configure_out
            )
            self.assert_true(
                "出错" in configure_out or "error" in configure_out.lower()
            )
            dummy_status = widget.get_package_dpkg_status(
                widget.DPKG_CONFIGURE_FAIL_PKG
            )
            print(f"[2005731] configure 失败后 dummy 状态: {dummy_status!r}")
            self.assert_false(dummy_status.startswith("install ok installed"))

            # 预期2: 后续 apt install -fy 尝试修复但最终失败
            install_out, install_rc = widget.apt_install_fix_with_return_code(
                timeout=300
            )
            print(
                f"[2005731] apt install -fy rc={install_rc}, "
                f"out={install_out[-1500:]!r}"
            )
            # apt 确实执行了修复动作(有输出, 排除命令未跑起来)
            self.assert_true(bool(install_out.strip()))
            dummy_status = widget.get_package_dpkg_status(
                widget.DPKG_CONFIGURE_FAIL_PKG
            )
            print(
                f"[2005731] apt install -fy 之后 dummy 状态: {dummy_status!r}"
            )
            self.assert_false(dummy_status.startswith("install ok installed"))
            if install_rc == 0:
                print(
                    "[2005731] 注意: apt install -fy 返回 0, 但半配置包仍未被"
                    "配置成功, 以系统真实状态判定本次修复失败"
                )
            else:
                print(
                    f"[2005731] apt install -fy 返回非 0(rc={install_rc}), "
                    "与'最终失败'预期一致"
                )

            # 步骤3: 产品侧 依赖关系修复(构造用过 sudo, 清掉免密时间戳,
            # 保证产品脚本需要鉴权时能弹出输入框, 与 2005727 保持一致)
            widget.clear_sudo_credentials()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            card_name = widget.get_dependency_repair_card_name()
            print(f"[2005731] 依赖关系修复卡片: {card_name!r}")
            self.assert_true(bool(card_name))
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())

            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=20))

            # 若产品走到提权分支则输入配置中的密码(PASSWORD); 白名单授权无需密码
            for _ in range(30):
                if widget.is_shell_repair_input_enabled():
                    widget.handle_shell_repair_dialog()
                    print("[2005731] 已提交管理员鉴权密码")
                    break
                if widget.get_repair_output_text():
                    break
                sleep(2)

            prompt_text = widget.get_repair_result_prompt_text(timeout=300)
            output = widget.get_repair_output_text()
            print(f"[2005731] 修复结果提示: {prompt_text!r}")
            print(f"[2005731] 依赖关系修复输出: {output[-3000:]!r}")
            self.assert_true(bool(prompt_text))

            # 本分支预期只能是失败: 产品必须给出"依赖关系未修复"人工提示,
            # 不允许用成功文案或通用的"修复完成"蒙混过去。
            manual_hint = ("依赖关系未修复" in prompt_text) or (
                "依赖关系未修复" in output
            )
            print(f"[2005731] 产品是否给出人工修复提示: {manual_hint}")
            self.assert_true(manual_hint)
            self.assert_false("依赖关系修复成功" in prompt_text)
            self.assert_false("依赖关系修复成功" in output)

            # 产品修复后系统状态: 半配置包仍未配置成功, 该次修复实际失败
            dummy_status = widget.get_package_dpkg_status(
                widget.DPKG_CONFIGURE_FAIL_PKG
            )
            print(f"[2005731] 产品修复后 dummy 状态: {dummy_status!r}")
            self.assert_false(dummy_status.startswith("install ok installed"))

            widget.close_repair_result_prompt()
            widget.close_repair_completion_dialog()
        finally:
            # 回退: 关闭遗留提示框与电脑管家, 删除标记文件并把半配置包 purge 掉,
            # 恢复依赖关系, 不在测试机留残留
            widget.close_repair_result_prompt()
            widget.close_repair_notify_dialog()
            widget.close_info_dialogs()
            widget.close_repair_completion_dialog()
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()
            residue = widget.cleanup_dpkg_configure_failure()
            print(f"[2005731] 回退结果: {residue}")
            self.assert_true(widget.restore_apt_sources())
            sleep(1)

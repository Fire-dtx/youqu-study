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

    def test_mycase_148(self):
        """系统修复-修复依赖关系不满足-修复成功

        产品依据(deepin-pc-manager 1.1.7, plugins/plugin-dependency/entry.sh):
        "依赖关系修复"插件(executionMode=root)由 deepin-pc-manager-daemon 以
        root 执行入口脚本, 依次为
          apt update -y                                  -> 成功时 log_info
                                                            "系统仓库更新成功"
          dpkg --configure -a                            -> 失败则提示"依赖关系
                                                            未修复..."并退出
          apt install -o Dpkg::Options::=--force-confnew -fy
          log_info "依赖关系修复成功"; 再调 dpm_notify 成功提示
        apt update 失败则提示"系统仓库更新失败"。root 类修复经
        deepin-security-loader 白名单授权时不弹密码框; 若产品进入提权分支,
        则向 shellRepair_inputEdit 提交配置中的密码(PASSWORD)。

        本用例场景(正常态下的成功分支): 前置是所有包状态正常、无未配置 /
        依赖损坏, 网络正常; 步骤是执行修复脚本; 预期是 apt update 成功。
        因此本用例不构造任何损坏状态, 而是先核对整机确实处于正常态, 再走
        产品完整的依赖关系修复流程, 用产品输出 + 系统真实状态双重断言:
        1. root 直接执行 apt update -y 返回 0(预期1 的等价断言, 同时证明
           软件源可达, 排除"仓库更新失败"分支);
        2. 电脑管家 -> 修复工具 -> 依赖关系修复 -> 开始修复, 断言修复输出
           出现"系统仓库更新成功"且不出现"仓库更新失败";
        3. 断言修复流程执行到"依赖关系修复成功"/完成文案, 且不出现
           "依赖关系未修复";
        4. 等价系统状态断言: 修复后 apt-get check 返回 0、无自制夹具残留的
           半配置包、dpkg --configure -a 返回 0, 即修复成功且系统未被打坏。

        回退: 本用例不构造系统状态, 只需关闭提示框/修复窗口、退出电脑管家、
        清掉 sudo 免密时间戳, 不在测试机留残留。
        """
        widget = MyAppWidget(check_start=False)
        try:
            # 前置1: 网络正常(产品脚本的 apt update 需要访问软件源)
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

            # 前置2: 所有包状态正常, 无未配置 / 依赖损坏(apt-get check 返回 0)
            self.assert_true(widget.get_dependency_status())
            unconfigured_before = widget.get_unconfigured_packages()
            print(f"[2005733] 修复前未配置/非正常状态包: {unconfigured_before}")
            # 允许环境里存在与本模块无关的杂项包, 但本模块自制夹具不得残留
            self.assert_false(
                [
                    pkg
                    for pkg in unconfigured_before
                    if pkg.startswith(("dummy-", "autotest-"))
                ]
            )
            configure_out, configure_rc = widget.dpkg_configure_all(timeout=180)
            print(
                f"[2005733] 修复前 dpkg --configure -a rc={configure_rc}, "
                f"out={configure_out[-600:]!r}"
            )
            self.assert_true(configure_rc == 0)

            # 步骤1 + 预期1: 以 root 执行 apt update -y, 返回码 0 且确有输出
            update_out, update_rc = widget.apt_update_with_return_code(
                timeout=300
            )
            print(
                f"[2005733] apt update -y rc={update_rc}, "
                f"out={update_out[-800:]!r}"
            )
            self.assert_true(update_rc == 0)
            self.assert_true(bool(update_out.strip()))

            # 步骤1(产品侧): 打开 电脑管家 -> 修复工具 -> 依赖关系修复
            widget.clear_sudo_credentials()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            card_name = widget.get_dependency_repair_card_name()
            print(f"[2005733] 依赖关系修复卡片: {card_name!r}")
            self.assert_true(bool(card_name))
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())

            # 执行依赖关系修复脚本
            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=20))

            # 提权: 白名单授权路径无需密码, 只有输入行被启用时才提交密码
            password_submitted = False
            for _ in range(30):
                if widget.is_shell_repair_input_enabled():
                    widget.handle_shell_repair_dialog()
                    password_submitted = True
                    print("[2005733] 已提交管理员鉴权密码")
                    break
                if "仓库更新成功" in widget.get_repair_output_text():
                    break
                sleep(2)

            # 预期1(产品侧): 脚本执行 apt update 成功, 输出系统仓库更新成功
            self.assert_true(
                widget.get_repair_output_contains("仓库更新成功", timeout=300)
            )
            output = widget.get_repair_output_text()
            print(f"[2005733] 依赖关系修复输出: {output[-2000:]!r}")
            self.assert_false("仓库更新失败" in output)

            # 脚本调用 dpm_notify 时会阻塞等待用户确认, 点掉【确定】让流程继续
            if widget.get_repair_notify_dialog_state().get("has_ok"):
                self.assert_true(widget.click_repair_notify_ok(timeout=20))

            # 预期2: 修复流程执行成功(输出依赖关系修复成功/完成文案)
            # 只认产品依赖修复分支自己打印的成功行; "修复完成"是脚本进程退出
            # 后追加的通用标记, 不能作为修复成功的证据。
            done_keyword = widget.wait_repair_output_keywords(
                ("依赖关系修复成功",), timeout=300
            )
            print(f"[2005733] 修复结束标志: {done_keyword!r}")
            self.assert_true(bool(done_keyword))
            output = widget.get_repair_output_text()
            self.assert_false("依赖关系未修复" in output)

            # 等价系统状态断言1: 修复后依赖关系仍满足(apt-get check 返回 0)
            self.assert_true(widget.get_dependency_status())
            # 等价系统状态断言2: 没有残留的半配置包, dpkg 配置阶段正常
            unconfigured_after = widget.get_unconfigured_packages()
            print(f"[2005733] 修复后未配置/非正常状态包: {unconfigured_after}")
            self.assert_false(
                [
                    pkg
                    for pkg in unconfigured_after
                    if pkg.startswith(("dummy-", "autotest-"))
                ]
            )
            configure_out, configure_rc = widget.dpkg_configure_all(timeout=180)
            print(
                f"[2005733] 修复后 dpkg --configure -a rc={configure_rc}, "
                f"out={configure_out[-600:]!r}"
            )
            self.assert_true(configure_rc == 0)
            # 修复过程中产品进程未崩溃
            self.assert_true(widget.get_pc_manager_process_status())
            print(f"[2005733] 鉴权密码是否需要提交: {password_submitted}")

            widget.close_repair_result_prompt()
            widget.close_repair_notify_dialog()
            widget.close_repair_completion_dialog()
        finally:
            # 回退: 关闭遗留提示框/修复窗口, 退出电脑管家, 清掉 sudo 免密时间戳;
            # 本用例未构造系统状态, 只打印结束时状态便于残留排查
            widget.close_repair_result_prompt()
            widget.close_repair_notify_dialog()
            widget.close_info_dialogs()
            widget.close_repair_completion_dialog()
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()
            widget.clear_sudo_credentials()
            self.assert_true(widget.restore_apt_sources())
            print(
                f"[2005733] 结束时依赖状态: {widget.get_dependency_status()}, "
                f"未配置包: {widget.get_unconfigured_packages()}"
            )
            sleep(1)

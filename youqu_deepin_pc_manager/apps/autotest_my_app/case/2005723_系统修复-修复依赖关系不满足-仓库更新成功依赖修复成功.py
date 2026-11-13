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

    def test_mycase_267(self):
        """系统修复-修复依赖关系不满足-仓库更新成功+依赖修复成功

        产品依据(deepin-pc-manager 1.1.7): 修复工具中的"依赖关系修复"
        (parent=repair/system, executionMode=root)由 deepin-pc-manager-daemon
        以 root 执行入口脚本, 依次执行 `apt update -y`、`apt install -fy`、
        `dpkg --configure -a`; apt 源更新成功时经 dpmapi log_info 输出
        "[INFO] ...系统仓库更新成功", 修复结束时输出修复完成, 脚本若调用
        dpm_notify 则阻塞等待用户点【确定】。root 类修复经 deepin-security-loader
        白名单授权时不会弹密码框, 若产品进入提权分支则在鉴权框输入正确密码(1)。

        前置: 网络正常、软件源有效; 系统存在依赖关系不满足的软件包。
        构造(等价实现): 测试机装有 dpkg 安装钩子(非白名单包禁止安装), 自建 dummy
        包会被拒绝, 故强制卸载被 libdpkg-perl 依赖的 bzip2, 使 apt-get check
        失败; bzip2 可从有效源装回, 即"可修复"的依赖不满足。
        """
        widget = MyAppWidget(check_start=False)
        dep_pkg = ""
        try:
            # 前置1: 系统网络正常、软件源配置有效(仓库可访问且 apt update 成功)
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

            # 前置2: 构造"存在依赖关系不满足的软件包"(依赖本身可从有效源安装)
            dep_pkg = "bzip2"
            self.assert_true(widget.break_dependency_by_removal(dep_pkg))
            self.assert_false(widget.get_dependency_status())
            # 构造过程用过 sudo, 清掉免密时间戳, 避免产品脚本里的 sudo 不再要求输入密码
            widget.clear_sudo_credentials()

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            # 步骤1: 运行依赖关系修复脚本
            card_name = widget.get_dependency_repair_card_name()
            print(f"[2005723] 依赖关系修复卡片: {card_name!r}")
            self.assert_true(bool(card_name))
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())
            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=20))

            # 步骤2: 若产品走到提权分支, 在鉴权框输入配置中的密码(setting/globalconfig.ini 的 PASSWORD);
            # 白名单授权路径无需密码, 因此这里只在输入行被启用时才提交
            password_submitted = False
            for _ in range(30):
                if widget.is_shell_repair_input_enabled():
                    widget.handle_shell_repair_dialog()
                    password_submitted = True
                    print("[2005723] 已提交管理员鉴权密码")
                    break
                if "仓库更新成功" in widget.get_repair_output_text():
                    break
                sleep(2)

            # 预期1: apt update -y 执行成功, 输出系统仓库更新成功
            self.assert_true(
                widget.get_repair_output_contains("仓库更新成功", timeout=300)
            )
            output = widget.get_repair_output_text()
            print(f"[2005723] 依赖关系修复输出: {output!r}")
            self.assert_false("仓库更新失败" in output)

            # 脚本调用 dpm_notify 时会阻塞等待确认, 点掉【确定】让脚本继续
            if widget.get_repair_notify_dialog_state().get("has_ok"):
                self.assert_true(widget.click_repair_notify_ok(timeout=20))

            # 预期2: 依赖修复流程执行完成
            self.assert_true(widget.get_repair_completion_status(timeout=300))

            # 等价系统状态断言1: 依赖关系已修复(apt-get check 返回 0)
            self.assert_true(widget.get_dependency_status())
            # 等价系统状态断言2: dpkg --configure -a 正常执行(返回码 0)
            dpkg_out, dpkg_rc = widget.dpkg_configure_all()
            print(f"[2005723] dpkg --configure -a rc={dpkg_rc}, out={dpkg_out!r}")
            self.assert_true(dpkg_rc == 0)
            # 构造时卸载的被依赖包已被产品修复流程装回
            self.assert_true(widget.is_package_installed(dep_pkg))
            print(f"[2005723] 鉴权密码是否需要提交: {password_submitted}")

            widget.close_repair_completion_dialog()
        finally:
            # 回退: 关闭提示框/修复窗口与电脑管家, 卸掉 dummy 包与构造产物,
            # 把依赖关系恢复到可用状态, 不在测试机留残留
            widget.close_repair_notify_dialog()
            widget.close_repair_completion_dialog()
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()
            widget.cleanup_dependency_repairable()
            widget.restore_dependency_package(dep_pkg or "bzip2")
            self.assert_true(widget.restore_apt_sources())

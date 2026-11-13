#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import getpass
import shlex

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_035(self):
        """打印机修复：在修复工具中执行「打印机修复」并验证修复成功

        产品脚本(plugin-printer-fix/entry.sh)做三件事:
        1) 检查并把当前用户加入 lpadmin 组; 2) 检查 dde-printer 是否安装/可升级;
        3) 扫描 CUPS 日志中的联软管控特征, 最后输出「检查完成」。

        数据构造: 测试机已装 dde-printer 1.1.4 而源里有 1.1.8, 直接执行会触发
        apt 升级(联网改包)。用 apt preferences 把 dde-printer 钉在已安装版本,
        让脚本走「已是最新版本」分支, 只做只读检查; 结束后删除该 pin 文件。
        用例同时记录 lpadmin 组成员, 若脚本新加了成员则在回退时移除。
        """
        pin_file = "/etc/apt/preferences.d/autotest-hold-dde-printer"
        pin_content = ("Package: dde-printer\n"
                       "Pin: version %s\n"
                       "Pin-Priority: 1001\n")
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        had_lpadmin = True
        try:
            # 数据构造: 钉住 dde-printer 已安装版本, 避免脚本联网升级
            installed = widget.run_cmd(
                "dpkg-query -W -f='${Version}' dde-printer 2>/dev/null || true",
                timeout=10, out_debug_flag=False).strip()
            self.assert_true(bool(installed))
            pin = pin_content % installed
            widget.sudo_run_cmd(
                f"printf %s {shlex.quote(pin)} > {pin_file}",
                timeout=10, out_debug_flag=False,
            )
            upgradable = widget.run_cmd(
                "apt list --upgradable 2>/dev/null | grep -c dde-printer || true",
                timeout=30, out_debug_flag=False).strip()
            self.assert_equal("0", upgradable)

            groups = widget.run_cmd("id -nG", timeout=5, out_debug_flag=False).split()
            had_lpadmin = "lpadmin" in groups

            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            widget.click_repair_card_by_name("打印机修复")
            self.assert_true(widget.get_repair_detail_showing())

            widget.click_repair_start_button()
            # 修复脚本以 root 执行, 弹窗需要 sudo 密码
            widget.handle_shell_repair_dialog()
            self.assert_true(widget.get_repair_completion_status(timeout=180))

            output = widget.get_shell_repair_output_text()
            self.assert_true("[OK] dde-printer 已是最新版本" in output)
            self.assert_true("检查完成" in output)
            self.assert_true("[ERROR]" not in output)

            # 收尾: 插件 entry.sh 末尾 openinfobox timeoutMs=0 无超时, 脚本阻塞到
            # 用户应答; 必须点掉提示框否则弹窗残留且修复窗口无法关闭
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])
        finally:
            # 数据回退: 删除 apt pin; 脚本若新增了 lpadmin 成员则移除
            widget.sudo_run_cmd(f"rm -f {pin_file}", timeout=10, out_debug_flag=False)
            if not had_lpadmin:
                groups = widget.run_cmd("id -nG", timeout=5, out_debug_flag=False).split()
                if "lpadmin" in groups:
                    widget.sudo_run_cmd(f"gpasswd -d {getpass.getuser()} lpadmin",
                                        timeout=10, out_debug_flag=False)
            # 兜底: 前置断言失败时也点掉无超时的完成提示框, 避免残留遮挡桌面
            widget.finish_repair_flow()
            widget.kill_pc_manager()

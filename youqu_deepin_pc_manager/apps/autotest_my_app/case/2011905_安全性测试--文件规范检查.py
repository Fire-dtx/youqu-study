#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):

    def test_mycase_217(self):
        """安全性测试--文件规范检查：验证电脑管家安装文件符合安全规范"""
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        # 获取二进制文件权限信息（记录用于调试）
        permissions = widget.get_binary_permissions()
        self.assert_true(len(permissions) > 0)

        # 验证二进制文件不存在 SUID/SGID 位
        self.assert_true(widget.get_binary_no_setuid_setgid())

        # 验证二进制文件不可被其他用户写入（无 o+w 权限）
        self.assert_true(widget.get_binary_not_world_writable())

        # 获取 dpkg 安装文件列表，验证列表非空（避免包未安装时检查空通过）
        install_files = widget.run_cmd(
            "dpkg -L deepin-pc-manager 2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        self.assert_true(len(install_files.strip()) > 0)

        # 检查所有安装文件不应存在 world-writable 权限（o+w）
        world_writable = widget.run_cmd(
            "dpkg -L deepin-pc-manager 2>/dev/null | "
            "while read f; do test -f \"$f\" && "
            "find -L \"$f\" -perm -o+w -print; done 2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        self.assert_true(len(world_writable.strip()) == 0)

        # 检查所有安装文件不应存在 SUID/SGID 位
        suid_sgids = widget.run_cmd(
            "dpkg -L deepin-pc-manager 2>/dev/null | "
            "while read f; do test -f \"$f\" && "
            "find -L \"$f\" \\( -perm -4000 -o -perm -2000 \\) -print; done 2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        self.assert_true(len(suid_sgids.strip()) == 0)

        # 检查所有安装文件应属于 root 用户
        # 只检查普通文件: dpkg -L 会列出 /usr、/usr/lib 等共享系统目录,
        # 这些目录不属于包管理的文件规范检查范围。
        non_root_files = widget.run_cmd(
            "dpkg -L deepin-pc-manager 2>/dev/null | "
            "while read f; do test -f \"$f\" && "
            "stat -c '%U %n' \"$f\"; done | grep -v '^root ' 2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        self.assert_true(len(non_root_files.strip()) == 0)

        # 检查 desktop 文件存在
        desktop_file = widget.run_cmd(
            "dpkg -L deepin-pc-manager 2>/dev/null | grep '\\.desktop$' | head -1",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        self.assert_true(len(desktop_file) > 0)

        # 验证 desktop 文件不可被其他用户写入
        self.assert_true(widget.get_desktop_file_not_world_writable())

        # ===== 文件规范: 所有文件位于规范允许的目录下 =====
        # 依据《UOS 文件系统规范》: 安装文件只允许出现在 /usr、/etc、/lib;
        # 运行时数据只允许出现在 ~/.cache/deepin、~/.config/deepin(或 -pc-manager)、
        # ~/.local/share/deepin 及应用专属目录; 不允许在家目录顶层随意落文件。
        marker = "/tmp/pcm_filespec_marker"
        widget.run_cmd(f"touch {marker}", timeout=5, out_debug_flag=False)
        inventory = widget.collect_pc_manager_file_inventory(marker=marker)
        # marker 只用于本次采集, 立即清理, 断言失败也不留残留
        widget.run_cmd(f"rm -f {marker}", timeout=5, out_debug_flag=False)
        logger.info(
            f"[2011905] 安装文件 {len(inventory['install'])} 项, "
            f"运行时文件 {len(inventory['runtime'])} 项, "
            f"家目录顶层 {inventory['home_loose']}"
        )
        self.assert_true(len(inventory["install"]) > 0)

        install_violations = [
            path
            for path in inventory["install"]
            if path != "/."
            and path not in ("/usr", "/etc", "/lib", "/lib64")
            and not path.startswith(("/usr/", "/etc/", "/lib/", "/lib64/"))
        ]
        logger.info(f"[2011905] 安装路径越界: {install_violations}")
        self.assert_true(len(install_violations) == 0)

        home = widget.run_cmd("echo $HOME", timeout=5, out_debug_flag=False).strip()
        runtime_allowed = (
            f"{home}/.cache/deepin/",
            f"{home}/.config/deepin",
            f"{home}/.local/share/deepin/",
            f"{home}/.cache/deepin/deepin-pc-manager-session-daemon",
        )
        runtime_violations = [
            path for path in inventory["runtime"] if not path.startswith(runtime_allowed)
        ]
        logger.info(f"[2011905] 运行时路径越界: {runtime_violations}")
        self.assert_true(len(runtime_violations) == 0)

        # 家目录顶层不应有产品随手创建的文件(只统计本次用例开始后新增的条目)
        self.assert_true(len(inventory["home_loose"]) == 0)

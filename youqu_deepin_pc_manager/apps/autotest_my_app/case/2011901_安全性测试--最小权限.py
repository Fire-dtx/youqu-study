#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):
    def test_mycase_048(self):
        """安全性测试--最小权限：验证 deepin-pc-manager 遵循最小权限原则，包括
        二进制文件无 SUID/SGID 位、不可被其他用户写入，进程不以 root 身份运行，
        所有安装文件属主为 root 且无 world-writable 及 SUID/SGID 权限，
        desktop 文件不可被其他用户写入，在 V20 和 V25 两个平台上均满足要求"""
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        # ===== 1. 验证二进制文件无 SUID/SGID 位 =====
        self.assert_true(widget.get_binary_no_setuid_setgid())

        # ===== 2. 验证二进制文件不可被其他用户写入 =====
        self.assert_true(widget.get_binary_not_world_writable())

        # ===== 3. 验证进程不以 root 身份运行 =====
        self.assert_true(widget.get_process_not_root())

        # ===== 4. 验证 desktop 文件不可被其他用户写入 =====
        self.assert_true(widget.get_desktop_file_not_world_writable())

        # ===== 5. 验证所有安装文件属主为 root =====
        non_root_files = widget.run_cmd(
            "dpkg -L deepin-pc-manager 2>/dev/null | "
            'while read f; do test -f "$f" && '
            "stat -c '%U %n' \"$f\"; done | grep -v '^root ' 2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        self.assert_true(len(non_root_files.strip()) == 0)

        # ===== 6. 验证所有安装文件无 world-writable 权限 =====
        world_writable = widget.run_cmd(
            "dpkg -L deepin-pc-manager 2>/dev/null | "
            'while read f; do test -f "$f" && '
            'find "$f" -type f -perm -o+w -print; done 2>/dev/null',
            timeout=15,
            out_debug_flag=False,
        )
        self.assert_true(len(world_writable.strip()) == 0)

        # ===== 7. 验证所有安装文件无 SUID/SGID 位 =====
        suid_sgids = widget.run_cmd(
            "dpkg -L deepin-pc-manager 2>/dev/null | "
            'while read f; do test -f "$f" && '
            'find "$f" -type f \\( -perm -4000 -o -perm -2000 \\) -print; done 2>/dev/null',
            timeout=15,
            out_debug_flag=False,
        )
        self.assert_true(len(suid_sgids.strip()) == 0)

        # ===== 8. 验证用户配置目录权限不可被其他用户写入 =====
        config_dir_perms = widget.run_cmd(
            'stat -c "%a" ~/.config/deepin-pc-manager 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        perm = config_dir_perms.strip()
        if perm:
            # 判断 other 的写权限位(八进制最低位 & 0o2), 而不是比较最低位数值:
            # 755 的最低一位是 5(读+执行), 不含写权限, 却会误判为不安全。
            self.assert_true((int(perm, 8) & 0o2) == 0)

        # ===== 9. 日志文件权限: 不是 777, 且 other 不可写 =====
        log_path = widget.get_pc_manager_log_path()
        self.assert_true(bool(log_path))
        log_perm = widget.get_path_permission(log_path)
        logger.info(f"[2011901] 日志权限: {log_path} -> {log_perm}")
        self.assert_true(log_perm["perm"] != "")
        self.assert_true(log_perm["perm"] != "777")
        self.assert_true((int(log_perm["perm"], 8) & 0o2) == 0)
        self.assert_equal(log_perm["owner"], widget.run_cmd("id -un", timeout=5, out_debug_flag=False).strip())

        # ===== 10. 插件配置目录权限: 存在时不得 777/other 可写 =====
        plugin_dir = "~/.config/deepin-pc-manager"
        plugin_perm = widget.get_path_permission(plugin_dir)
        logger.info(f"[2011901] 配置目录权限: {plugin_dir} -> {plugin_perm}")
        if plugin_perm["perm"]:
            self.assert_true(plugin_perm["perm"] != "777")
            self.assert_true((int(plugin_perm["perm"], 8) & 0o2) == 0)
            bad_paths = widget.get_world_writable_paths(plugin_dir)
            logger.info(f"[2011901] 配置目录 other 可写路径: {bad_paths}")
            self.assert_true(len(bad_paths) == 0)

        # ===== 11. 日志所在缓存目录同样不得 other 可写 =====
        cache_bad = widget.get_world_writable_paths(
            "~/.cache/deepin/deepin-pc-manager"
        )
        logger.info(f"[2011901] 缓存目录 other 可写路径: {cache_bad}")
        self.assert_true(len(cache_bad) == 0)

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log


class TestMyCase(BaseCase):

    def test_mycase_366(self):
        """关键系统文件权限检测-SSH 主机密钥

        步骤: 1. ssh-keygen -A 生成 ssh_host_*_key 主机密钥(已存在时不覆盖);
        2. 执行「系统稳定性」分项检测。
        预期: 检测通过 -- 主机私钥仅属主可读写(root, 0600/0400),
        不属于权限过宽状态, 文件权限检测项结论应为通过。
        用例结束前删除本次新生成的密钥文件, 恢复原始密钥集合。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget

        def _list_keys():
            out = widget.run_cmd(
                "ls /etc/ssh/ssh_host_* 2>/dev/null", timeout=10, out_debug_flag=False,
            )
            return sorted(line.strip() for line in out.splitlines() if line.strip())

        widget.kill_pc_manager()
        widget.remove_test_junk_files()
        keys_before = _list_keys()
        try:
            out = widget.sudo_run_cmd(
                "ssh-keygen -A 2>&1; true", timeout=60, out_debug_flag=False,
            )
            log(f"[2032551] ssh-keygen -A 输出: {out.strip()!r}")
            self.assert_true("error" not in out.lower())
            self.assert_true("failed" not in out.lower())
            self.assert_true("无法" not in out and "失败" not in out)

            keys_after = _list_keys()
            created = sorted(set(keys_after) - set(keys_before))
            log(f"[2032551] 本次新增主机密钥: {created}")
            self.assert_true(len(keys_after) >= 6)

            key_list = widget.run_cmd(
                "ls -l /etc/ssh/ssh_host_*_key 2>/dev/null",
                timeout=10, out_debug_flag=False,
            )
            log(f"[2032551] 主机私钥权限: {key_list.strip()!r}")
            key_lines = [ln for ln in key_list.splitlines() if "ssh_host_" in ln]
            self.assert_true(len(key_lines) >= 3)
            for line in key_lines:
                mode = line.split()[0]
                self.assert_true(mode.startswith("-"))
                self.assert_true("------" in mode[4:])
            self.assert_true("root root" in key_list)

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统稳定性", timeout=300))
            self.assert_true(widget.get_detection_item_present("系统稳定性", "文件权限检测"))
            ok, detail = widget.get_detection_item_verdict("file_permissions")
            log(f"[2032551] 期望 file_permissions 通过(主机密钥权限正常), 实际 {ok}: {detail}")
            self.assert_true(ok is True)
        finally:
            if created:
                widget.sudo_run_cmd(
                    "rm -f " + " ".join(created), timeout=15, out_debug_flag=False,
                )
            keys_restored = _list_keys()
            log(f"[2032551] 密钥集合恢复校验: before={keys_before} after={keys_restored}")
            self.assert_true(keys_restored == keys_before)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

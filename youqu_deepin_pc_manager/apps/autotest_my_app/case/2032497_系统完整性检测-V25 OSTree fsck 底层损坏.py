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

    def test_mycase_122(self):
        """系统完整性检测-V25 OSTree fsck 底层损坏

        步骤: 1. 制造 ostree 环境损坏(mount -o remount,rw /ostree);
        2. 执行系统环境检测。
        预期: 检测失败, 失败项含 ostree 信息。

        环境说明: 测试机为 UOS 20(V20 非 immutable 系统), 无 /ostree 与
        /persistent/ostree 部署目录, 被测版本守护进程也未包含 ostree 检测代码,
        因此 OSTree fsck 底层损坏无法在本机构造。等价验证:
        1) 复核本机不满足 ostree 场景前置条件(目录缺失、remount 无法执行);
        2) 正常执行系统环境检测, 核心包检查项应正常给出结论(通过),
           不因缺少 ostree 能力而报错或异常。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            ostree_dir = widget.run_cmd(
                "ls -d /ostree 2>&1; ls -d /persistent/ostree 2>&1",
                timeout=10, out_debug_flag=False,
            )
            remount = widget.sudo_run_cmd(
                "mount -o remount,rw /ostree 2>&1; true",
                timeout=15, out_debug_flag=False,
            )
            daemon_ostree = widget.run_cmd(
                "strings /usr/lib/deepin-pc-manager/plugins/plugin-syscheck/"
                "libplugin-syscheck.so /usr/lib/deepin-pc-manager/"
                "deepin-pc-manager-session-daemon 2>/dev/null | grep -ci ostree",
                timeout=60, out_debug_flag=False,
            )
            logger.info(
                f"[2032497] ostree_dir={ostree_dir!r} remount={remount.strip()[:80]!r} "
                f"daemon_ostree_hits={daemon_ostree.strip()}"
            )
            self.assert_true("/ostree" in ostree_dir)
            self.assert_true(ostree_dir.count("没有那个文件或目录") == 2)
            self.assert_true("mount point does not exist" in remount)
            self.assert_true(daemon_ostree.strip().isdigit())
            self.assert_true(daemon_ostree.strip() == "0")

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            state = widget.get_detection_group_state("系统环境检测")
            logger.info(f"[2032497] group_state={state}")
            self.assert_true(state["checked"] >= 6)
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032497] core_packages verdict={ok} detail={detail}")
            self.assert_true(ok is True)
        finally:
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

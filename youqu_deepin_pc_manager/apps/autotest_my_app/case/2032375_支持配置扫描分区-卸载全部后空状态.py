#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep

M1 = "/media/autotest_p1"
M2 = "/media/autotest_p2"
M3 = "/media/autotest_p3"


class TestMyCase(BaseCase):

    def test_mycase_197(self):
        """支持配置扫描分区-卸载全部后空状态

        构造 3 个可扩展分区: /dev/sda6 挂到 p1, 将 /boot(/dev/sda2)、
        /recovery(/dev/sda4) 分别 bind 到 p2/p3(设备不同, 形成三行)。
        注: /dev/sdb 是 USB 总线上的移动盘, 按外接规则会被剔除, 不能用作
        正向对照。
        先进入设置页确认 3 行; 全部 umount 后关闭并重新打开设置页,
        断言列表清空、空状态可见。
        清理: umount/rmdir 全部临时挂载点。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.sudo_run_cmd(
                f"umount {M1} 2>/dev/null; umount {M2} 2>/dev/null; umount {M3} 2>/dev/null; "
                f"rmdir {M1} {M2} {M3} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {M1} {M2} {M3} && "
                f"mount /dev/sda6 {M1} && "
                f"mount --bind /boot {M2} && mount --bind /recovery {M3} && "
                f"findmnt -n -o SOURCE {M1} && findmnt -n -o SOURCE {M2} && "
                f"findmnt -n -o SOURCE {M3}",
                timeout=30,
                return_code=True,
            )
            logger.info(f"[2032375] mount rc={rc} out={out!r}")
            self.assert_true(rc == 0)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            def read_rows():
                widget.open_settings_dialog()
                self.assert_true(widget.get_settings_dialog_showing())
                self.assert_true(widget.click_settings_nav_item("清理设置"))
                widget.scroll_settings_content_to_bottom()
                self.assert_true(widget.get_extended_scan_partition_widget_showing())
                rows = []
                for expr in (
                    "$//settings_extendedScanPartition",
                    "$//extendedScanPartitionRow",
                ):
                    rows = widget.dog.find_elements_by_attr(expr) or []
                    if rows:
                        break
                return [getattr(r, "description", "") or "" for r in rows]

            mounts = read_rows()
            logger.info(f"[2032375] before={mounts!r}")
            self.assert_true(sorted(mounts) == sorted([M1, M2, M3]))
            widget.close_settings_dialog()
            sleep(1)

            # 全部卸载
            widget.sudo_run_cmd(
                f"umount {M1}; umount {M2}; umount {M3}",
                timeout=30,
            )
            left = widget.run_cmd(
                "awk '$2 ~ /^\\/media\\/autotest_p[123]$/ {print $2}' /proc/mounts",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            logger.info(f"[2032375] left_mounts={left!r}")
            self.assert_true(left == "")

            # 重新进入页面
            mounts = read_rows()
            logger.info(f"[2032375] after={mounts!r}")
            self.assert_true(mounts == [])
            empty = widget.dog.find_elements_by_attr(
                "$//settings_extendedScanPartitionEmptyText"
            )
            self.assert_true(bool(empty))
            empty = empty[0] if isinstance(empty, list) else empty
            self.assert_true(empty.showing)
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"umount {M1} 2>/dev/null; umount {M2} 2>/dev/null; "
                f"umount {M3} 2>/dev/null; umount -l {M1} 2>/dev/null; "
                f"umount -l {M2} 2>/dev/null; umount -l {M3} 2>/dev/null; "
                f"rmdir {M1} {M2} {M3} 2>/dev/null; true",
                timeout=30,
            )

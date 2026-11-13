#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep

A_MOUNT = "/media/autotest_noperm"


class TestMyCase(BaseCase):

    def test_mycase_204(self):
        """支持配置扫描分区-异常-无读写权限

        构造: /dev/sda6 挂载到 /media/autotest_noperm, 再把挂载点权限改为 000,
        使普通用户无法读写/遍历该目录。
        步骤: 进入设置-清理设置, 查看扩展扫描分区列表。
        断言: 列表仍显示该分区, 进程不崩溃; 恢复权限后可正常进入该目录。
        清理: 恢复权限、卸载并删除挂载点。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.sudo_run_cmd(
                f"chmod 755 {A_MOUNT} 2>/dev/null; "
                f"umount {A_MOUNT} 2>/dev/null; rmdir {A_MOUNT} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {A_MOUNT} && mount /dev/sda6 {A_MOUNT} && "
                f"chmod 000 {A_MOUNT} && echo DONE",
                timeout=40,
                return_code=True,
            )
            logger.info(f"[2032401] setup rc={rc} out={out!r}")
            self.assert_true(rc == 0 and "DONE" in out)
            _, rc = widget.run_cmd(
                f"ls -A {A_MOUNT}", timeout=5, return_code=True,
                out_debug_flag=False,
            )
            logger.info(f"[2032401] normal_user_ls_rc={rc}")
            self.assert_true(rc != 0)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            opened = False
            for _ in range(3):
                widget.open_settings_dialog()
                if widget.get_settings_dialog_showing(timeout=6):
                    opened = True
                    break
                sleep(1)
            self.assert_true(opened)
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())

            rows = {}
            for expr in (
                "$//settings_extendedScanPartition",
                "$//extendedScanPartitionRow",
            ):
                elems = widget.dog.find_elements_by_attr(expr) or []
                if elems:
                    rows = {
                        (getattr(e, "description", "") or ""): e for e in elems
                    }
                    break
            logger.info(f"[2032401] rows={sorted(rows)}")
            self.assert_true(A_MOUNT in rows)
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_extended_scan_partition_widget_showing())
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"chmod 755 {A_MOUNT} 2>/dev/null; "
                f"umount {A_MOUNT} 2>/dev/null; rmdir {A_MOUNT} 2>/dev/null; true",
                timeout=30,
            )
            _, rc = widget.run_cmd(
                f"ls -d {A_MOUNT}", timeout=5, return_code=True,
                out_debug_flag=False,
            )
            logger.info(f"[2032401] cleanup_ls_rc={rc}")

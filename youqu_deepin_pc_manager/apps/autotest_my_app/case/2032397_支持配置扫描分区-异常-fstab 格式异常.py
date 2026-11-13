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

A_MOUNT = "/media/autotest_fstab"
FSTAB = "/etc/fstab"
FSTAB_BAK = "/tmp/fstab.autotest_2032397.bak"


class TestMyCase(BaseCase):

    def test_mycase_203(self):
        """支持配置扫描分区-异常-fstab 格式异常

        构造: /dev/sda6 挂载到 /media/autotest_fstab 作为扩展扫描分区,
        备份 /etc/fstab 后追加缺少字段、非法字符的畸形行。
        步骤: 启动管家 -> 打开清理设置扩展扫描分区列表 -> 重启后再次打开,
        并触发一次重复文件清理扫描。
        断言: 畸形 fstab 下扩展分区行仍显示、进程存活、扫描流程可完成。
        清理: 还原 /etc/fstab、删除备份、卸载并删除挂载点。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.sudo_run_cmd(
                f"umount {A_MOUNT} 2>/dev/null; rmdir {A_MOUNT} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {A_MOUNT} && mount /dev/sda6 {A_MOUNT} && echo MOUNTED",
                timeout=40,
                return_code=True,
            )
            logger.info(f"[2032397] mount rc={rc} out={out!r}")
            self.assert_true(rc == 0 and "MOUNTED" in out)

            widget.sudo_run_cmd(
                f"cp -a {FSTAB} {FSTAB_BAK} && echo 'fstab backup done'",
                timeout=20,
            )

            def open_cleanup_settings():
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
                self.assert_true(
                    widget.get_extended_scan_partition_widget_showing()
                )

            def rows():
                elems = []
                for expr in (
                    "$//settings_extendedScanPartition",
                    "$//extendedScanPartitionRow",
                ):
                    elems = widget.dog.find_elements_by_attr(expr) or []
                    if elems:
                        break
                return {
                    (getattr(e, "description", "") or ""): e for e in elems
                }

            # 基线: fstab 正常时列表包含 A
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            open_cleanup_settings()
            base = rows()
            logger.info(f"[2032397] baseline rows={sorted(base)}")
            self.assert_true(A_MOUNT in base)
            widget.close_settings_dialog()
            sleep(1)

            # 破坏 fstab: 缺少字段行 + 非法转义/字符
            widget.sudo_run_cmd(
                'printf "%s\\n" "invalid_fstab_line_no_fields" '
                '"///dev/null /mnt bad ext4" '
                '"UUID=zzzz /mnt/x ext4 defaults 0 0 trailing_extra" '
                '>> /etc/fstab',
                timeout=10,
            )
            out = widget.sudo_run_cmd("cat /etc/fstab", timeout=10)
            logger.info(f"[2032397] fstab_tail={out[-160:]!r}")
            self.assert_true("invalid_fstab_line_no_fields" in out)

            # 重启管家后重新打开列表: 不因 fstab 解析失败崩溃
            widget.kill_pc_manager()
            sleep(2)
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            open_cleanup_settings()
            after = rows()
            logger.info(f"[2032397] broken_fstab rows={sorted(after)}")
            self.assert_true(A_MOUNT in after)
            widget.close_settings_dialog()
            sleep(1)
            self.assert_true(widget.get_pc_manager_process_status())

            # 畸形 fstab 下触发一次重复文件扫描, 页面与扫描流程正常
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_optimization_card_by_name("重复文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            widget.wait_dup_file_scan_running(timeout=20)
            self.assert_true(widget.get_dup_file_scan_completed(timeout=300))
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"[ -f {FSTAB_BAK} ] && cp -a {FSTAB_BAK} {FSTAB} && "
                f"rm -f {FSTAB_BAK}; true",
                timeout=20,
            )
            widget.sudo_run_cmd(
                f"umount {A_MOUNT} 2>/dev/null; rmdir {A_MOUNT} 2>/dev/null; true",
                timeout=30,
            )

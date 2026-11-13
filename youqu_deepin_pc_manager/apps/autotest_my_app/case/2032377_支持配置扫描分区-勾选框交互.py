#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep

A_MOUNT = "/media/autotest_a"
B_MOUNT = "/media/autotest_b"
C_MOUNT = "/media/autotest_c"
CONF = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
CONF_BAK = "/tmp/pcm_conf.autotest.bak"


class TestMyCase(BaseCase):

    def test_mycase_042(self):
        """支持配置扫描分区-勾选框交互

        构造 3 个可扩展分区(/dev/sda6→A, /boot→B, /recovery→C 的 bind),
        清空历史配置后逐项验证:
        1) 首次进入全部未勾选;
        2) 勾选 A 后配置文件立即含 A;
        3) 取消 A 后持久化取消;
        4) 勾选 A+B 后完全退出重启, 仍为 A+B, C 未勾选;
        5) 再勾选 C, 三项独立保存无互斥。
        清理: 还原配置文件备份, umount 全部挂载点并删除。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            widget.sudo_run_cmd(
                f"umount {A_MOUNT} 2>/dev/null; umount {B_MOUNT} 2>/dev/null; "
                f"umount {C_MOUNT} 2>/dev/null; "
                f"rmdir {A_MOUNT} {B_MOUNT} {C_MOUNT} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {A_MOUNT} {B_MOUNT} {C_MOUNT} && "
                f"mount /dev/sda6 {A_MOUNT} && "
                f"mount --bind /boot {B_MOUNT} && mount --bind /recovery {C_MOUNT}",
                timeout=30,
                return_code=True,
            )
            logger.info(f"[2032377] mount rc={rc} out={out!r}")
            self.assert_true(rc == 0)

            # 备份配置并清空历史勾选
            widget.run_cmd(
                f"cp -a {CONF} {CONF_BAK} && "
                f"grep -v 'extendedScanPaths' {CONF} > {CONF}.tmp && "
                f"mv {CONF}.tmp {CONF}",
                timeout=5,
                out_debug_flag=False,
            )
            self.assert_false(
                "extendedScanPaths"
                in widget.run_cmd(f"cat {CONF}", timeout=5, out_debug_flag=False)
            )

            def open_settings():
                widget.open_settings_dialog()
                self.assert_true(widget.get_settings_dialog_showing())
                self.assert_true(widget.click_settings_nav_item("清理设置"))
                widget.scroll_settings_content_to_bottom()
                self.assert_true(widget.get_extended_scan_partition_widget_showing())

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

            def state():
                return {
                    mp: bool(getattr(e, "checked", False))
                    for mp, e in rows().items()
                }

            def conf_text():
                return widget.run_cmd(
                    f"cat {CONF}", timeout=5, out_debug_flag=False
                )

            # 1. 首次进入: 全部未勾选
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            open_settings()
            st = state()
            logger.info(f"[2032377] initial={st}")
            self.assert_true(set(st) == {A_MOUNT, B_MOUNT, C_MOUNT})
            self.assert_true(not any(st.values()))

            # 2. 勾选 A, 配置立即生效
            rows()[A_MOUNT].click()
            sleep(1)
            self.assert_true(state()[A_MOUNT])
            text = conf_text()
            logger.info(f"[2032377] after_check_A={text!r}")
            self.assert_true(A_MOUNT in text)

            # 3. 取消 A, 取消状态持久化
            rows()[A_MOUNT].click()
            sleep(1)
            self.assert_true(not state()[A_MOUNT])
            text = conf_text()
            logger.info(f"[2032377] after_uncheck_A={text!r}")
            self.assert_true(A_MOUNT not in text)

            # 4. 勾选 A+B, 完全退出后重启仍保持
            rows()[A_MOUNT].click()
            sleep(1)
            rows()[B_MOUNT].click()
            sleep(1)
            st = state()
            logger.info(f"[2032377] check_AB={st}")
            self.assert_true(st[A_MOUNT] and st[B_MOUNT] and not st[C_MOUNT])
            widget.close_settings_dialog()
            widget.kill_pc_manager()
            sleep(2)
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            open_settings()
            st = state()
            logger.info(f"[2032377] after_restart={st}")
            self.assert_true(st[A_MOUNT] and st[B_MOUNT] and not st[C_MOUNT])

            # 5. 再勾选 C, 三项独立保存
            rows()[C_MOUNT].click()
            sleep(1)
            st = state()
            logger.info(f"[2032377] check_ABC={st}")
            self.assert_true(all(st.values()))
            text = conf_text()
            logger.info(f"[2032377] final_conf={text!r}")
            for mp in (A_MOUNT, B_MOUNT, C_MOUNT):
                self.assert_true(mp in text)
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.run_cmd(
                f"[ -f {CONF_BAK} ] && cp -a {CONF_BAK} {CONF} && rm -f {CONF_BAK}; true",
                timeout=5,
                out_debug_flag=False,
            )
            widget.sudo_run_cmd(
                f"umount {C_MOUNT} 2>/dev/null; umount {B_MOUNT} 2>/dev/null; "
                f"umount {A_MOUNT} 2>/dev/null; "
                f"rmdir {A_MOUNT} {B_MOUNT} {C_MOUNT} 2>/dev/null; true",
                timeout=30,
            )

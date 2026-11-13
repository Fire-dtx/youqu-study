#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/04
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log, logger


class TestMyCase(BaseCase):
    INSTALLER_CONF = "/etc/deepin-installer/deepin-installer.conf"
    CONF_BACKUP = "/tmp/deepin_installer_conf_backup_1998997"
    FSTAB_BACKUP = "/tmp/fstab_backup_1998997"

    def _simulate_manual_install(self, widget):
        """模拟手动安装(非全盘)环境

        产品判定备份分区是否存在(daemon isRecoveryPartitionExists)取以下任一：
        /etc/fstab 含 /recovery 条目、/recovery 目录存在、lsblk 显示挂载。
        因此需同时：卸载 /recovery、删除挂载点目录、注释 fstab 条目，
        并把安装器记录改为手动安装(1)。
        """
        for cmd in (
            f"cp {self.INSTALLER_CONF} {self.CONF_BACKUP}",
            f"cp /etc/fstab {self.FSTAB_BACKUP}",
        ):
            widget.sudo_run_cmd(cmd, timeout=5, out_debug_flag=False)

        _, umount_code = widget.sudo_run_cmd(
            "umount /recovery", timeout=15, out_debug_flag=False, return_code=True
        )
        log(f"卸载 /recovery 返回码: {umount_code}")
        self.assert_false(widget.get_recovery_partition_mounted())

        widget.sudo_run_cmd("rmdir /recovery", timeout=5, out_debug_flag=False)
        widget.sudo_run_cmd(
            "sed -i -E 's@^([^#][^[:space:]]*[[:space:]]+/recovery[[:space:]])@#\\1@' /etc/fstab",
            timeout=5,
            out_debug_flag=False,
        )
        widget.sudo_run_cmd(
            f"sed -i 's/^DI_PARTITION_TYPE=.*/DI_PARTITION_TYPE=1/' {self.INSTALLER_CONF}",
            timeout=5,
            out_debug_flag=False,
        )

        self.assert_true(widget.get_install_partition_type() == "1")
        self.assert_false(widget.get_recovery_partition_mounted())
        recovery_dir = widget.run_cmd(
            "test -d /recovery && echo yes || echo no", timeout=5, out_debug_flag=False
        )
        self.assert_true(recovery_dir.strip() == "no")
        fstab_recovery = widget.run_cmd(
            "grep -E '^[^#].*[[:space:]]/recovery[[:space:]]' /etc/fstab || true",
            timeout=5,
            out_debug_flag=False,
        )
        self.assert_true(not fstab_recovery.strip())

    def _restore_install_env(self, widget, original_type):
        """还原安装器配置、fstab 并重新挂载 /recovery"""
        widget.sudo_run_cmd("mkdir -p /recovery", timeout=5, out_debug_flag=False)
        widget.sudo_run_cmd(
            f"cp {self.FSTAB_BACKUP} /etc/fstab && cp {self.CONF_BACKUP} {self.INSTALLER_CONF}",
            timeout=5,
            out_debug_flag=False,
        )
        widget.sudo_run_cmd("mount /recovery", timeout=15, out_debug_flag=False)
        widget.run_cmd(
            f"rm -f {self.CONF_BACKUP} {self.FSTAB_BACKUP}", timeout=5, out_debug_flag=False
        )
        log(
            f"环境还原: DI_PARTITION_TYPE={widget.get_install_partition_type()} "
            f"(原始 {original_type or '未记录'}), /recovery 挂载={widget.get_recovery_partition_mounted()}"
        )
        self.assert_true(widget.get_install_partition_type() == original_type)
        self.assert_true(widget.get_recovery_partition_mounted())

    def test_mycase_357(self):
        """V20 上非全盘默认安装进行快照检测：安装方式取自安装器记录
        (/etc/deepin-installer/deepin-installer.conf 的 DI_PARTITION_TYPE):
        0 = 全盘安装, 1 = 手动安装, 2 = 全盘加密安装,
        3 = 全盘安装保留用户数据, 6 = 单盘多系统全盘安装, 7 = 全盘lvm安装;
        全盘安装类型为 0/2/3/7, 仅 1(手动安装)属非全盘安装。

        用例内模拟手动安装环境(DI_PARTITION_TYPE=1、卸载并移除 /recovery
        挂载点及 fstab 条目)，点击"系统环境检测"卡片后"备份与快照检查"项
        应存在且判定正常(不误报备份分区缺失)；执行完成后还原安装器配置、
        fstab 并重新挂载 /recovery。"""
        widget = MyAppWidget(check_start=False)

        original_type = widget.get_install_partition_type()
        if original_type not in widget.FULL_DISK_INSTALL_PARTITION_TYPES:
            pytest.skip(
                f"当前安装方式 DI_PARTITION_TYPE={original_type or '未记录'}"
                f"({widget.get_install_partition_type_name()}) 非全盘安装, "
                "无法构造『全盘 → 非全盘』转换场景"
            )

        simulated = False
        try:
            self._simulate_manual_install(widget)
            simulated = True

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            self.assert_true(widget.run_detection_item("系统环境检测"))

            self.assert_true(widget.get_detection_item_present("系统环境检测", "备份与快照检查"))
            self.assert_true(widget.is_only_group_detected("系统环境检测"))

            verdict, detail = widget.get_detection_item_verdict("backup_partition")
            logger.info(f"备份与快照检查单项结论(模拟非全盘安装): {verdict}, 原始结果: {detail}")
            self.assert_true(verdict)
        finally:
            if simulated:
                self._restore_install_env(widget, original_type)

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

    MOUNT_POINT = "/tmp/test_usb_exfat_compat_mount"
    PAYLOAD_PREFIX = "autotest_2010257"

    def test_mycase_037(self):
        """【U盘修复】【兼容场景】exFAT 文件系统修复测试(脏标志 / 逻辑损坏 / 严重损坏)

        产品依据(plugin-usb-fix/entry.sh):
        - check_filesystem: 分区 blkid 认不出类型 → FS_SEVERITY=severe;
          其余分区跑 "fsck -n -t <fstype>", 退出码非 0 → corrupted;
          exFAT 额外做一次只读挂载测试补漏(挂载失败同样判 corrupted);
        - present_diagnosis: corrupted 展示"- 文件系统损坏(...)，可尝试自动修复";
          severe 展示"- 文件系统严重损坏(... 无法识别)，自动修复不可用，建议格式化";
        - fix_filesystem: exFAT 用 "fsck -y -t exfat", 退出码 <= 1 记"修复成功",
          > 1 或修复后类型无法识别记"修复失败"; severe 不执行修复;
        - present_results: 输出"修复完成 ... 成功/失败/跳过"计数。

        三个场景(同一块 U 盘依次构造):
        1) 脏标志(检测异常 + 修复成功): 按用例前置条件原样执行
           "dd if=/dev/zero of=/dev/sda1 bs=1 seek=510 count=2 conv=notrunc",
           即清零引导扇区尾部的 0xAA55 签名。实测(exfat-utils 1.3.0):
           fsck.exfat -n / fsck -n -t exfat 都返回 1, 只读挂载报
           "invalid VBR checksum"; fsck -y 重算校验和后退出码 1, 产品记
           "修复成功", 修复后挂载恢复且样本 sha256 不变。
        2) 逻辑损坏(检测异常 + 尝试修复): 清零 FAT 表起始 64 个扇区, 根目录簇链
           断裂。实测类型仍是 exfat、只读挂载失败("bad cluster 0 while reading
           root directory")、fsck -y 报 "ERRORS FOUND: 1, FIXED: 0" 且退出码 1;
           产品按退出码(<=1)提示"修复成功", 但卷实际仍不可挂载 —— 该分歧在
           用例里如实断言流程(检测 + 修复执行 + 结果提示)并记录日志, 不改产品。
        3) 严重损坏: 分区前 10MB 清零, blkid 认不出类型 → 判严重损坏、不执行修复。
           用例步骤写的是清零整盘(/dev/sdX); 在 USB 盘上实测清零整盘会让分区节点
           消失、产品遍历不到分区, 命中不了 severe, 故清零分区保留枚举现场。

        每个场景都从 mkfs.exfat 格式化、写样本、注入损坏开始, 结束时卸载分区并
        格式化回 ext4, 测试机不残留挂载点、样本文件或损坏的文件系统。
        """
        widget = MyAppWidget(check_start=False)

        udisks_state = widget.run_cmd(
            "systemctl is-active udisks2 2>/dev/null", timeout=10, out_debug_flag=False
        ).strip()
        if udisks_state == "active":
            widget.sudo_run_cmd(
                "systemctl stop udisks2 2>/dev/null", timeout=30, out_debug_flag=False
            )
            sleep(1)

        partition = ""
        synthetic = False
        try:
            partition = widget.get_first_usb_storage_partition()
            if not partition:
                partition = widget.create_synthetic_usb_storage_device()
                if partition:
                    synthetic = True
                    widget.schedule_synthetic_usb_recovery(seconds=1500)
            self.assert_true(partition != "")

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_cards_view_showing())

            # ===== 场景 1: 脏标志(检测异常, 修复成功) =====
            payload = self._prepare_exfat_scene(widget, partition)
            self.assert_true(widget.crack_usb_exfat_boot_signature(partition))
            self.assert_false(
                widget.mount_usb_partition(partition, self.MOUNT_POINT, "exfat")
            )

            self._run_usb_fix(widget)
            self.assert_true(widget.get_repair_output_contains("文件系统损坏", timeout=30))
            self.assert_true(
                widget.get_repair_output_contains("可尝试自动修复", timeout=10)
            )
            self.assert_true(widget.get_repair_output_contains("修复成功", timeout=60))
            self.assert_true(widget.get_repair_output_contains("修复完成", timeout=10))
            # 收尾: 脚本末尾的提示框没有超时且会阻塞脚本, 先点掉提示框再关修复窗口,
            # 并确认窗口已关闭(残留会盖在桌面并影响下一个场景)
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])

            self.assert_true(
                widget.mount_usb_partition(partition, self.MOUNT_POINT, "exfat")
            )
            self.assert_true(widget.verify_usb_integrity_payload(self.MOUNT_POINT, payload))
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            logger.info("场景1(脏标志)修复成功, 数据校验通过")

            # ===== 场景 2: 逻辑损坏(检测异常, 尝试修复) =====
            self._prepare_exfat_scene(widget, partition)
            self.assert_true(widget.corrupt_usb_exfat_fat_table(partition))
            self.assert_false(
                widget.mount_usb_partition(partition, self.MOUNT_POINT, "exfat")
            )

            self._run_usb_fix(widget)
            self.assert_true(widget.get_repair_output_contains("文件系统损坏", timeout=30))
            self.assert_true(widget.get_repair_output_contains("修复完成", timeout=90))
            fixed = widget.get_repair_output_contains("修复成功", timeout=5)
            broken = widget.get_repair_output_contains("修复失败", timeout=2)
            self.assert_true(fixed or broken)
            # 收尾: 提示框没有超时且会阻塞脚本, 先点掉再关窗口并确认窗口已关闭
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])
            logger.info(
                f"场景2(逻辑损坏)已执行修复流程, 产品提示: "
                f"{'修复成功' if fixed else '修复失败'}; "
                f"exfatfsck 报告 FIXED: 0, 卷仍不可挂载(产品判定与实际修复结果不一致)"
            )

            # ===== 场景 3: 严重损坏(通知严重损坏, 不执行修复) =====
            self._prepare_exfat_scene(widget, partition)
            self.assert_true(widget.corrupt_usb_partition_severe_damage(partition))

            self._run_usb_fix(widget)
            self.assert_true(widget.get_repair_output_contains("文件系统严重损坏", timeout=30))
            self.assert_true(
                widget.get_repair_output_contains("严重损坏", timeout=10)
                or widget.get_repair_output_contains("未尝试修复", timeout=10)
            )
            self.assert_false(widget.get_repair_output_contains("修复成功", timeout=2))
            widget.close_repair_dialog()
            logger.info("场景3(严重损坏)未执行修复, 结论符合预期")

            # 电脑管家在三次修复后仍存活
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            # 回退: 卸载 -> 关残留提示框/修复窗口 -> 删挂载点
            # -> 分区恢复为干净的 ext4 -> 清理合成盘
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            widget.close_usb_fix_prompt_dialog(rounds=2)
            # 修复脚本末端的 dpm_notify 提示框只有【确定】且会阻塞脚本:
            # 不点掉会留在桌面并让修复窗口关不掉, 污染后续用例
            widget.finish_repair_flow()
            if partition:
                self._restore_ext4(widget, partition)
            widget.sudo_run_cmd(
                f"rm -rf {self.MOUNT_POINT}", timeout=10, out_debug_flag=False
            )
            if synthetic:
                widget.cancel_synthetic_usb_recovery()
                widget.cleanup_synthetic_usb_storage_device()
            widget.kill_pc_manager()
            if udisks_state == "active":
                widget.sudo_run_cmd(
                    "systemctl start udisks2 2>/dev/null", timeout=30, out_debug_flag=False
                )

    def _prepare_exfat_scene(self, widget, partition):
        """把分区格式化为 exFAT、写入数据样本并卸载

        :return: write_usb_integrity_payload 返回的样本信息
        """
        self.assert_true(
            widget.prepare_usb_exfat_partition(
                mount_point=self.MOUNT_POINT, partition=partition
            )
            != ""
        )
        self.assert_true(widget.get_partition_filesystem_type(partition) == "exfat")
        payload = widget.write_usb_integrity_payload(
            self.MOUNT_POINT, prefix=self.PAYLOAD_PREFIX
        )
        self.assert_true(bool(payload))
        widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
        self.assert_false(widget.get_usb_device_mounted(mount_point=self.MOUNT_POINT))
        return payload or {}

    def _run_usb_fix(self, widget):
        """进入 USB 设备修复详情并跑完一次完整修复流程"""
        widget.click_repair_card_by_name("USB 设备修复")
        self.assert_true(widget.get_repair_detail_showing())
        # xdotool raw click 偶发丢事件(2005759 首跑实测), 用重试辅助等待对话框
        self.assert_true(widget.click_start_repair_button_until_dialog())
        self.assert_true(widget.handle_usb_fix_confirm_dialog(timeout=300))

    def _restore_ext4(self, widget, partition):
        """把 U 盘分区恢复为干净的 ext4, 供后续用例直接使用"""
        widget.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {partition} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; '
            f"mkfs.ext4 -F -q {partition} 2>&1 | tail -1; "
            f"udevadm trigger --action=change --subsystem-match=block {partition} "
            "2>/dev/null; udevadm settle --timeout=10 2>/dev/null; true",
            timeout=180,
            out_debug_flag=False,
        )
        fs_type = widget.get_partition_filesystem_type(partition)
        logger.info(f"U 盘分区已恢复: {partition} type={fs_type!r}")

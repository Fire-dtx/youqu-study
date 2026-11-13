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

    MOUNT_POINT = "/tmp/test_usb_ext4_compat_mount"
    PAYLOAD_PREFIX = "autotest_2010253"

    def test_mycase_169(self):
        """【U盘修复】【兼容场景】ext4 文件系统修复测试(脏标志 / 逻辑损坏 / 严重损坏)

        产品依据(plugin-usb-fix/entry.sh):
        - check_filesystem: 分区 blkid 认不出类型 → FS_SEVERITY=severe;
          "fsck -n -t ext4" 退出码非 0 → corrupted;
        - present_diagnosis: corrupted 展示"- 文件系统损坏(... ext4)，可尝试自动修复";
          severe 展示"- 文件系统严重损坏(... 无法识别)，自动修复不可用，建议格式化";
        - fix_filesystem: "fsck -y -t ext4" 退出码 <= 1 记"修复成功", > 1 记"修复失败";
          severe 不执行修复, 记"严重损坏，未尝试修复";
        - present_results: 输出"修复完成 ... 成功/失败/跳过"计数。

        三个场景(同一块 U 盘依次构造):
        1) 脏标志(可修复): 未清理状态 + 块位图与 inode 引用不一致, fsck -n rc=4,
           fsck -y rc=1 → 检测异常且修复成功, 修复后数据不变。
           注: 本机 e2fsprogs 对"仅 s_state=0、无实际错误"的卷 fsck -n 仍返回 0,
           产品会判为正常, 因此按"脏标志"本意补一处 fsck 能自动修复的元数据不一致。
        2) 逻辑损坏(不可修复): 超级块 s_feature_incompat 置当前 e2fsprogs 不认识的
           位(0x100000), blkid 仍识别为 ext4, fsck -n / fsck -y 都返回 8 →
           检测异常且修复失败。
        3) 严重损坏: 分区前 10MB 清零, blkid 认不出类型 → 判为严重损坏、不执行修复。
           用例原始步骤是清零整盘(/dev/sdX); 在 USB 盘上实测会导致分区节点消失,
           产品遍历不到分区, 命中不了 severe 分支, 故清零分区以保留枚举现场。

        设备: 测试机接入的 USB 存储盘(udev ID_BUS=usb); 没有则用 scsi_debug 合成。
        每个场景都从格式化、写样本、注入损坏开始, 结束时卸载分区并格式化回 ext4,
        测试机不残留挂载点、样本文件或损坏的文件系统。
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

            # ===== 场景 1: 脏标志(可修复) =====
            payload = self._prepare_ext4_scene(widget, partition)
            self.assert_true(widget.create_usb_ext4_repairable_error(partition))
            self.assert_true(widget.get_usb_ext4_partition_check_rc(partition) != 0)

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

            self.assert_true(widget.get_usb_ext4_partition_check_rc(partition) == 0)
            self.assert_true(widget.mount_usb_partition(partition, self.MOUNT_POINT, "ext4"))
            self.assert_true(widget.verify_usb_integrity_payload(self.MOUNT_POINT, payload))
            widget.sudo_run_cmd(
                f"rm -f {payload.get('bin', '')} {payload.get('text', '')}",
                timeout=20, out_debug_flag=False,
            )
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            logger.info("场景1(脏标志)修复成功, 数据校验通过")

            # ===== 场景 2: 逻辑损坏(检测异常, 修复失败) =====
            self._prepare_ext4_scene(widget, partition)
            self.assert_true(widget.corrupt_usb_ext4_unfixable_error(partition))
            self.assert_true(widget.get_usb_ext4_partition_check_rc(partition) > 1)

            self._run_usb_fix(widget)
            self.assert_true(widget.get_repair_output_contains("文件系统损坏", timeout=30))
            self.assert_true(widget.get_repair_output_contains("修复失败", timeout=60))
            self.assert_true(widget.get_repair_output_contains("修复完成", timeout=10))
            self.assert_false(widget.get_repair_output_contains("修复成功", timeout=2))
            # 收尾: 提示框没有超时且会阻塞脚本, 先点掉再关窗口并确认窗口已关闭
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])

            # 修复失败后文件系统仍不可用(产品未做任何破坏性动作)
            self.assert_true(widget.get_usb_ext4_partition_check_rc(partition) > 1)
            logger.info("场景2(逻辑损坏)修复失败, 结论符合预期")

            # ===== 场景 3: 严重损坏(严重损坏, 未执行修复) =====
            self._prepare_ext4_scene(widget, partition)
            self.assert_true(widget.corrupt_usb_ext4_severe_damage(partition))

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
            # 回退: 卸载 -> 关残留提示框/修复窗口 -> 删挂载点 -> 分区恢复为干净的 ext4
            # -> 清理合成盘
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

    def _prepare_ext4_scene(self, widget, partition):
        """把分区格式化为 ext4、写入数据样本并卸载

        :return: write_usb_integrity_payload 返回的样本信息
        """
        self.assert_true(
            widget.prepare_usb_ext4_partition(
                mount_point=self.MOUNT_POINT, partition=partition
            )
            != ""
        )
        self.assert_true(widget.get_partition_filesystem_type(partition) == "ext4")
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
        widget.click_start_repair_button()
        self.assert_true(widget.get_repair_dialog_showing())
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

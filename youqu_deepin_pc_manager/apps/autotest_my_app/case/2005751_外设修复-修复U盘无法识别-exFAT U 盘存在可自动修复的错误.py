#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):
    MOUNT_POINT = "/tmp/test_usb_exfat_error_mount"
    PAYLOAD_PREFIX = "autotest_2005751"

    def test_mycase_247(self):
        """外设修复-修复U盘无法识别-exFAT U 盘存在可自动修复的错误

        验证 usb-fix 插件对"存在可自动修复错误的 exFAT U 盘"的完整处理:
        枚举设备 -> 选中设备 -> 诊断出文件系统损坏(可自动修复) -> 用户确认 ->
        执行 fsck -y -t exfat 修复 -> 输出修复成功 -> 修复后文件系统不再有错误,
        且 U 盘数据不丢失。

        错误注入(等价实现): 清零 exFAT 引导扇区尾部的 0xAA55 签名
        ("dd if=/dev/zero of=/dev/sdX1 bs=1 seek=510 count=2 conv=notrunc"),
        与同模块 exFAT"脏标志"场景使用同一条命令。实测(exfat-utils 1.3.0):
        fsck.exfat -n 与 fsck -n -t exfat 都返回 1, 只读挂载报
        "invalid VBR checksum"; "fsck -y -t exfat" 重算校验和后退出码 1,
        修复后挂载恢复、样本 sha256 不变 —— 属于"存在可自动修复的错误"。

        设备来源(等价实现): usb-fix 只枚举 /sys/block/sd* 中 udev 属性
        ID_BUS=usb 的整盘(见产品 plugin-usb-fix/entry.sh 的 enumerate_usb_devices),
        loop 设备不会被识别, 测试机也没有实体 U 盘。因此用内核 scsi_debug 造一块
        内存盘(设备名仍是 sdX), 再用只匹配 scsi_debug 设备(vendor=Linux /
        model=scsi_debug)的 udev 规则把 ID_BUS 覆写为 usb, 对插件而言与实体
        "存在可自动修复错误的 exFAT U 盘"完全等价, 且不接触任何真实磁盘。本用例
        只用合成盘: 真实 U 盘上要执行 mkfs 与错误注入, 不可恢复, 故不退化到真实
        设备。执行期间停止 udisks2, 避免桌面自动挂载干扰格式化与修复, 结束后恢复。

        产品依据(plugin-usb-fix/entry.sh):
        - check_filesystem 对 exFAT 分区跑 "fsck -n -t exfat", 退出码非 0 →
          corrupted, 输出"分区 /dev/sdX1 (exfat) 文件系统损坏 (fsck -n exit=1)";
        - present_diagnosis 输出"- 文件系统损坏(exfat)，可尝试自动修复"并弹确认框;
        - fix_filesystem 执行 "fsck -y -t exfat", 退出码 <= 1 → "分区 ... 修复成功";
        - present_results 输出"修复完成 ... 成功"计数。
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
        payload = {}
        try:
            # 1) 构造 U 盘: 只用 scsi_debug 合成盘。真实 U 盘上要执行 mkfs 与错误
            #    注入, 这些操作不可恢复, 故即使测试机接入了真实 U 盘也不退化到真实
            #    设备(避免误格式化用户磁盘)。
            partition = widget.create_synthetic_usb_storage_device()
            self.assert_true(partition != "")
            # 用例被强杀/超时时兜底清理合成盘与 udev 规则
            widget.schedule_synthetic_usb_recovery(seconds=1500)

            # 2) 前置: 分区格式化为 exFAT, 写入数据样本后卸载
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
            # 构造前确认文件系统健康, 排除"本来就坏"导致的假阳性
            self.assert_equal(0, widget.get_usb_exfat_filesystem_check_rc(partition))

            # 3) 注入可自动修复的错误: 引导签名被清零, 类型仍为 exfat 且 fsck 报错
            self.assert_true(widget.crack_usb_exfat_boot_signature(partition))
            self.assert_true(widget.get_partition_filesystem_type(partition) == "exfat")
            self.assert_not_equal(0, widget.get_usb_exfat_filesystem_check_rc(partition))
            self.assert_false(
                widget.mount_usb_partition(partition, self.MOUNT_POINT, "exfat")
            )

            # 4) 启动电脑管家并进入修复工具页面
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_cards_view_showing())

            # 5) 进入"USB 设备修复"详情并点击开始修复
            widget.click_repair_card_by_name("USB 设备修复")
            self.assert_true(widget.get_repair_detail_showing())
            # xdotool raw click 偶发丢事件(2005759 首跑实测), 用重试辅助等待对话框
            self.assert_true(widget.click_start_repair_button_until_dialog())
            self.assert_true(widget.handle_usb_fix_confirm_dialog(timeout=300))

            # 6) 产品输出证据: 选中设备 -> 检测到文件系统损坏且可自动修复 ->
            #    修复成功 -> 流程结束
            self.assert_true(widget.get_repair_output_contains("已选择设备", timeout=10))
            self.assert_true(widget.get_repair_output_contains("exfat", timeout=10))
            self.assert_true(widget.get_repair_output_contains("文件系统损坏", timeout=30))
            self.assert_true(
                widget.get_repair_output_contains("可尝试自动修复", timeout=10)
            )
            self.assert_true(widget.get_repair_output_contains("修复成功", timeout=60))
            self.assert_true(widget.get_repair_output_contains("修复完成", timeout=10))
            # 收尾: 脚本末尾的提示框没有超时且会阻塞脚本, 必须先点掉提示框再关窗口,
            # 并确认窗口已关闭(残留会盖在桌面污染后续用例)
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])

            # 7) 物理校验: 修复后文件系统无错误、可挂载、数据完整、类型未变
            #    fsck 前必须先卸载, 已挂载分区会被判 in use/dirty 而误报
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            self.assert_equal(0, widget.get_usb_exfat_filesystem_check_rc(partition))
            self.assert_false(widget.get_usb_exfat_filesystem_has_errors(partition))
            self.assert_true(
                widget.mount_usb_partition(partition, self.MOUNT_POINT, "exfat")
            )
            self.assert_true(widget.verify_usb_integrity_payload(self.MOUNT_POINT, payload))
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            self.assert_true(widget.get_partition_filesystem_type(partition) == "exfat")
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            # 回退: 卸载/删挂载点 -> 关交互框 -> 清理合成盘(udev 规则+scsi_debug)
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            widget.sudo_run_cmd(
                f"rm -rf {self.MOUNT_POINT}", timeout=10, out_debug_flag=False
            )
            widget.close_usb_fix_prompt_dialog(rounds=2)
            # 修复脚本末端的 dpm_notify 提示框只有【确定】且会阻塞脚本:
            # 不点掉会留在桌面并让修复窗口关不掉, 污染后续用例
            widget.finish_repair_flow()
            widget.cancel_synthetic_usb_recovery()
            widget.cleanup_synthetic_usb_storage_device()
            # 合成盘必须清理干净: 残留的 udev 规则或 scsi_debug 模块会污染后续用例
            self.assert_false(os.path.exists(widget.SYNTH_USB_UDEV_RULE))
            self.assert_false(widget.is_kernel_module_loaded("scsi_debug"))
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())
            logger.info(f"USB 分区已卸载: {partition or '(未准备)'}")
            if udisks_state == "active":
                widget.sudo_run_cmd(
                    "systemctl start udisks2 2>/dev/null", timeout=30, out_debug_flag=False
                )

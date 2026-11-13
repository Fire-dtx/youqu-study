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
    MOUNT_POINT = "/tmp/test_usb_fat32_mount"
    USB_CARD_NAME = "USB 设备修复"

    def test_mycase_245(self):
        """外设修复-U盘修复-- FAT32 U 盘损坏严重

        验证 usb-fix 对"严重损坏的 FAT32 U 盘"的处理: 枚举设备 -> 选中设备 ->
        诊断出"文件系统无法识别(严重损坏)" -> 提示"自动修复不可用，建议格式化" ->
        不执行自动修复、流程直接结束, 且流程结束后分区仍处于损坏状态(产品没有
        擅自格式化、没有丢数据)。

        用例描述的预期是"命令无法自动修复，报错退出"。产品 1.1.7 的 usb-fix 在
        FS_SEVERITY=severe 时不调用 fsck, 而是输出"文件系统严重损坏，自动修复
        不可用，建议格式化。"后结束流程 —— 因此以该告警文本 + 流程结束 +
        输出中不存在任何"修复成功"作为等价断言, 并物理校验分区仍无法识别。

        设备来源(等价实现): usb-fix 只枚举 udev 属性 ID_BUS=usb 的 /sys/block/sd*
        (见产品 plugin-usb-fix/entry.sh 的 enumerate_usb_devices), loop 设备不会
        被识别, 测试机也没有实体 U 盘。因此用内核 scsi_debug 造一块内存盘(sdX),
        再用只匹配 scsi_debug 设备的 udev 规则把 ID_BUS 覆写为 usb, 对插件而言
        与实体 U 盘等价, 且不接触任何真实磁盘。本用例只用合成盘: 真实 U 盘上要
        执行 mkfs 与严重破坏注入, 不可恢复, 故不退化到真实设备。
        执行期间停止 udisks2, 避免桌面自动挂载损坏分区, 结束后恢复。
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
        try:
            # 1) 构造 U 盘: 只用 scsi_debug 合成盘。真实 U 盘上要执行 mkfs 与严重
            #    破坏注入, 这些操作不可恢复, 故即使测试机接入了真实 U 盘也不退化到
            #    真实设备(避免毁掉用户磁盘)。
            partition = widget.create_synthetic_usb_storage_device()
            self.assert_true(partition != "")
            # 用例被强杀/超时时兜底清理合成盘与 udev 规则
            widget.schedule_synthetic_usb_recovery(seconds=1500)

            # 2) 前置: 分区格式化为 FAT32 并挂载
            partition = widget.prepare_usb_fat32_partition(
                mount_point=self.MOUNT_POINT, partition=partition
            )
            self.assert_true(partition != "")
            self.assert_true(widget.get_usb_device_mounted(mount_point=self.MOUNT_POINT))
            self.assert_equal("vfat", widget.get_partition_filesystem_type(partition))

            # 3) 初始文件系统健康, 排除"本来就坏"导致的假阳性
            self.assert_true(widget.get_usb_fat32_filesystem_healthy(partition))

            # 4) 前置"已卸载 U 盘": 卸载后注入严重损坏(引导扇区 + FAT 表 + 根目录)
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            self.assert_false(widget.get_usb_device_mounted(mount_point=self.MOUNT_POINT))
            self.assert_true(widget.create_fat32_severe_corruption(partition))
            self.assert_true(widget.get_fat32_filesystem_unrecognized(partition))
            # 严重损坏已破坏引导区, blkid 不再识别为 vfat; 记录修复前的类型快照,
            # 修复流程结束后必须与之一致(未被产品格式化/重建)
            fs_type_before = widget.get_partition_filesystem_type(partition)
            logger.info(f"严重损坏后的文件系统类型: {fs_type_before!r}")
            fsck_rc = widget.get_fat32_filesystem_check_rc(partition)
            logger.info(f"严重损坏后 fsck.vfat -n 退出码: {fsck_rc}")
            self.assert_not_equal(0, fsck_rc)

            # 5) 启动电脑管家并进入修复工具页面
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            widget.get_repair_cards_view_showing()

            # 6) 进入 USB 设备修复并点击开始修复
            widget.click_repair_card_by_name(self.USB_CARD_NAME)
            self.assert_true(widget.get_repair_detail_showing())
            # xdotool raw click 偶发丢事件, 用重试辅助等待对话框
            self.assert_true(
                widget.click_start_repair_button_until_dialog(attempts=3, timeout=30)
            )

            # 7) 依次应答 设备选择 / 诊断结果 交互框, 直到流程结束
            self.assert_true(widget.handle_usb_fix_confirm_dialog(timeout=240))

            # 8) 输出证据: 设备被枚举选中 -> 诊断出文件系统无法识别(严重损坏)
            self.assert_true(widget.get_repair_output_contains("已选择设备", timeout=10))
            self.assert_true(widget.get_repair_output_contains("文件系统无法识别", timeout=10))

            # 9) 关键预期"命令无法自动修复": 产品明确给出自动修复不可用并结束流程
            self.assert_true(widget.get_repair_output_contains("自动修复不可用", timeout=10))
            self.assert_true(widget.get_repair_output_contains("建议格式化", timeout=5))
            self.assert_true(widget.get_repair_output_contains("USB 修复流程结束", timeout=10))

            # 10) 断言产品没有执行/声称任何一次修复成功(等价于"命令报错退出")
            output_text = widget.get_repair_output_text()
            self.assert_false("修复成功" in output_text)

            # 11) 收尾: 流程结束后脚本末端的提示框没有超时且会阻塞脚本, 先点掉提示框
            #     再关修复窗口, 并确认窗口已关闭(残留会盖在桌面污染后续用例)
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])

            # 12) 物理校验: 流程结束后文件系统类型与损坏后快照一致、fsck 仍报错、
            #     依然无法识别, 且全程没有"修复成功", 即产品没有擅自格式化/重建
            self.assert_equal(
                fs_type_before, widget.get_partition_filesystem_type(partition)
            )
            self.assert_not_equal(
                0, widget.get_usb_partition_fsck_check_rc(partition, "vfat")
            )
            self.assert_true(widget.get_fat32_filesystem_unrecognized(partition))
        finally:
            # 回退: 关残留交互框/修复框 -> 卸载分区 -> 取消兜底定时器 -> 清理合成 U 盘
            try:
                widget.close_usb_fix_prompt_dialog(rounds=2)
                # 修复脚本末端的 dpm_notify 提示框只有【确定】且会阻塞脚本:
                # 不点掉会留在桌面并让修复窗口关不掉, 污染后续用例
                widget.finish_repair_flow()
            except BaseException as exc:
                logger.error(f"关闭修复窗口失败: {exc}")
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            widget.cancel_synthetic_usb_recovery()
            widget.cleanup_synthetic_usb_storage_device()
            # 合成盘必须清理干净: 残留的 udev 规则或 scsi_debug 模块会污染后续用例
            self.assert_false(os.path.exists(widget.SYNTH_USB_UDEV_RULE))
            self.assert_false(widget.is_kernel_module_loaded("scsi_debug"))
            widget.sudo_run_cmd(
                f"rm -rf {self.MOUNT_POINT}", timeout=10, out_debug_flag=False
            )
            logger.info(f"USB 分区已卸载: {partition or '(未准备)'}")
            if udisks_state == "active":
                widget.sudo_run_cmd(
                    "systemctl start udisks2 2>/dev/null", timeout=30, out_debug_flag=False
                )
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())

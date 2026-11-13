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
    SAMPLE_NAME = "autotest_2005745_sample.bin"

    def test_mycase_244(self):
        """外设修复-U盘修复--FAT32 U 盘存在可自动修复的错误

        验证 usb-fix 插件对"存在可自动修复错误的 FAT32 U 盘"的完整处理:
        枚举设备 -> 诊断出"文件系统损坏(可修复)" -> 用户确认 -> 执行 fsck 修复 ->
        输出修复成功, 且修复后文件系统在物理上不再有错误。

        设备来源(等价实现): usb-fix 插件只枚举 /sys/block/sd* 中 udev 属性
        ID_BUS=usb 的整盘(见产品 plugin-usb-fix/entry.sh 的 enumerate_usb_devices),
        loop 设备不会被识别; 测试机也没有实体 U 盘。因此用内核 scsi_debug 造一块
        内存盘(设备名仍是 sdX), 再用一条只匹配 scsi_debug 设备
        (vendor=Linux / model=scsi_debug) 的 udev 规则把 ID_BUS 覆写为 usb,
        对插件而言与实体 U 盘完全等价, 又不接触任何真实磁盘。本用例只用合成盘:
        真实 U 盘上要执行 mkfs 与错误注入, 不可恢复, 故不退化到真实设备。
        执行期间停止 udisks2, 避免桌面自动挂载干扰格式化与修复, 结束后恢复。
        """
        widget = MyAppWidget(check_start=False)

        udisks_state = widget.run_cmd(
            "systemctl is-active udisks2 2>/dev/null", timeout=10, out_debug_flag=False
        ).strip()
        if udisks_state == "active":
            widget.sudo_run_cmd("systemctl stop udisks2 2>/dev/null", timeout=30, out_debug_flag=False)
            sleep(1)

        partition = ""
        try:
            # 1) 构造 U 盘: 只用 scsi_debug 合成盘。真实 U 盘上要执行 mkfs 与错误
            #    注入, 这些操作不可恢复, 故即使测试机接入了真实 U 盘也不退化到真实
            #    设备(避免误格式化用户磁盘)。
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

            # 2.1) 挂载状态下写入 4MB 样本并记录 sha256, 修复后校验数据未被破坏
            sample_path = f"{self.MOUNT_POINT}/{self.SAMPLE_NAME}"
            widget.sudo_run_cmd(
                f"dd if=/dev/urandom of={sample_path} bs=1M count=4 2>/dev/null; sync",
                timeout=60,
                out_debug_flag=False,
            )
            sample_sha256 = widget.run_cmd(
                f"sha256sum {sample_path} 2>/dev/null | cut -d' ' -f1",
                timeout=20,
                out_debug_flag=False,
            ).strip()
            self.assert_equal(64, len(sample_sha256))

            # 3) 初始文件系统健康, 排除"本来就坏"导致的假阳性
            #    判定口径与产品一致("fsck -n -t vfat" 退出码 0); 已挂载的 vfat 会被
            #    fsck.fat 判为 in use 而返回 1, 因此先干净卸载再检查
            self.assert_true(widget.get_usb_device_mounted(mount_point=self.MOUNT_POINT))
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            self.assert_equal(
                0, widget.get_usb_partition_fsck_check_rc(partition, "vfat")
            )

            # 4) 注入可被 fsck 自动修复的 FAT 表错误(只破坏 FAT1 中段簇项,
            #    不动 FAT[0]/FAT[1] 保留项与 BPB, 因此仍可自动修复);
            #    用例描述的前置是"已卸载 U 盘", 注入后保持卸载状态交给产品诊断
            self.assert_true(widget.create_fat32_repairable_error(partition))
            self.assert_not_equal(
                0, widget.get_usb_partition_fsck_check_rc(partition, "vfat")
            )
            self.assert_true(widget.get_partition_filesystem_type(partition) == "vfat")
            self.assert_false(widget.get_usb_device_mounted(mount_point=self.MOUNT_POINT))

            # 5) 启动电脑管家并进入修复工具页面
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_cards_view_showing())

            # 6) 进入 USB 设备修复并点击开始修复
            widget.click_repair_card_by_name("USB 设备修复")
            self.assert_true(widget.get_repair_detail_showing())
            # xdotool raw click 偶发丢事件(2005759 首跑实测), 用重试辅助等待对话框
            self.assert_true(widget.click_start_repair_button_until_dialog())

            # 8) 依次确认 设备选择 / 诊断结果 / 修复文件系统 弹窗, 直到流程结束
            self.assert_true(widget.handle_usb_fix_confirm_dialog(timeout=240))

            # 9) 产品输出证据: 选中设备 -> 诊断出可修复的文件系统损坏 -> 修复成功
            self.assert_true(widget.get_repair_output_contains("已选择设备", timeout=10))
            self.assert_true(widget.get_repair_output_contains("文件系统损坏", timeout=10))
            self.assert_true(widget.get_repair_output_contains("修复成功", timeout=10))
            self.assert_true(widget.get_repair_output_contains("USB 修复流程结束", timeout=10))

            # 10) 关闭修复对话框: 脚本末尾的提示框没有超时且会阻塞脚本, 必须先点掉
            #     提示框再关窗口, 并确认窗口已关闭(残留会盖在桌面污染后续用例)
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])

            # 11) 物理校验: 修复后文件系统不再有错误(与产品同一判定口径)
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            self.assert_equal(
                0, widget.get_usb_partition_fsck_check_rc(partition, "vfat")
            )

            # 12) 数据校验: 重新挂载后用同一路径重算 sha256, 样本未被修复流程破坏
            self.assert_true(
                widget.mount_usb_partition(partition, self.MOUNT_POINT, "vfat")
            )
            repaired_sha256 = widget.run_cmd(
                f"sha256sum {sample_path} 2>/dev/null | cut -d' ' -f1",
                timeout=20,
                out_debug_flag=False,
            ).strip()
            self.assert_equal(sample_sha256, repaired_sha256)
            # 删除样本后再卸载, 不在 U 盘留残留
            widget.sudo_run_cmd(
                f"rm -f {sample_path}", timeout=20, out_debug_flag=False
            )
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
        finally:
            # 回退: 卸载分区 -> 关闭残留交互框/修复窗口 -> 清理合成 U 盘
            # (udev 规则 + scsi_debug 模块), 并核验清理彻底
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            try:
                widget.close_usb_fix_prompt_dialog(rounds=2)
            except BaseException as exc:
                logger.error(f"关闭 USB 修复交互框失败: {exc}")
            # 修复脚本末端的 dpm_notify 提示框只有【确定】且会阻塞脚本:
            # 不点掉会留在桌面并让修复窗口关不掉, 污染后续用例
            widget.finish_repair_flow()
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

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
    MOUNT_POINT = "/tmp/test_usb_ext4_error_mount"
    PAYLOAD_PREFIX = "autotest_2005759"

    def test_mycase_251(self):
        """外设修复-修复U盘无法识别-- ext4 U 盘存在可自动修复的错误

        验证 usb-fix 插件对"存在可自动修复错误的 ext4 U 盘"的完整处理:
        枚举设备 -> 选择设备 -> 诊断出文件系统损坏(可自动修复) -> 用户确认 ->
        执行 fsck -y -t ext4 修复 -> 输出修复成功, 修复后文件系统不再有错误,
        且 U 盘上的数据不丢失。

        设备来源(等价实现): usb-fix 只枚举 /sys/block/sd* 中 udev 属性
        ID_BUS=usb 的整盘(见产品 plugin-usb-fix/entry.sh 的 enumerate_usb_devices),
        loop 设备不会被识别, 测试机也没有实体 U 盘。因此用内核 scsi_debug 造一块
        内存盘(设备名仍是 sdX), 再用只匹配 scsi_debug 设备(vendor=Linux /
        model=scsi_debug)的 udev 规则把 ID_BUS 覆写为 usb, 对插件而言与实体
        "存在可自动修复错误的 ext4 U 盘"完全等价, 且不接触任何真实磁盘。本用例
        只用合成盘: 真实 U 盘上要执行 mkfs 与错误注入, 不可恢复, 故不退化到真实
        设备。执行期间停止 udisks2, 避免桌面自动挂载干扰格式化与修复, 结束后恢复。

        错误注入(等价实现): 取 ext4 根目录 inode 的数据块, 用 debugfs 在块位图中
        把它标记为空闲, 并把超级块 s_state 置为未清理 —— 这是 fsck 可自动修复的
        元数据错误(块位图与 inode 引用不一致), 只改位图与超级块、不动数据块;
        本机实测注入后 "fsck -n -t ext4" 报 "Free blocks count wrong ... Fix? no"
        且返回 4, "fsck -y -t ext4" 报 "Block bitmap differences: +N Fix? yes" 返回 1,
        修复后 rc=0 且文件内容不变。

        产品依据(deepin-pc-manager 的 plugin-usb-fix/entry.sh):
        - enumerate_usb_devices 输出"正在检测 USB 设备", dpm_select 让用户选设备,
          选中后输出"已选择设备: /dev/sdX";
        - check_filesystem 对 ext4 分区执行 "fsck -n -t ext4", 退出码非 0 时输出
          "分区 /dev/sdX1 (ext4) 文件系统损坏 (fsck -n exit=N)" 并置
          FS_SEVERITY=corrupted(文件系统诊断结果: corrupted);
        - present_diagnosis 输出"- 文件系统损坏(... ext4)，可尝试自动修复"并弹出
          "诊断结果"确认框;
        - execute_repairs 弹出"修复文件系统"确认框后, fix_filesystem 执行
          "fsck -y -t ext4", 退出码 <= 1 输出"分区 ... (ext4) 修复成功";
        - present_results 输出"修复完成 ... 成功: 1  失败: 0  跳过: 0";
        - 主流程最后输出"USB 修复流程结束"。
        """
        widget = MyAppWidget(check_start=False)

        # 桌面自动挂载会与用例的手工挂载/格式化抢设备, 执行期间停掉 udisks2
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

            # 2) 前置: 分区格式化为 ext4 并挂载
            partition = widget.prepare_usb_ext4_partition(
                mount_point=self.MOUNT_POINT, partition=partition
            )
            self.assert_true(partition != "")
            self.assert_true(widget.get_usb_device_mounted(mount_point=self.MOUNT_POINT))
            self.assert_true(widget.get_partition_filesystem_type(partition) == "ext4")

            # 3) 写入数据完整性样本(4MB 随机内容 + 中文名文本), 记录 sha256/大小
            payload = widget.write_usb_integrity_payload(
                self.MOUNT_POINT, prefix=self.PAYLOAD_PREFIX
            )
            self.assert_true(bool(payload))

            # 4) 前置是"已卸载 U 盘": 卸载后先确认文件系统本来健康, 排除假阳性
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            self.assert_false(widget.get_usb_device_mounted(mount_point=self.MOUNT_POINT))
            self.assert_true(widget.get_usb_ext4_partition_check_rc(partition) == 0)
            self.assert_false(widget.get_usb_ext4_partition_has_errors(partition))

            # 5) 注入 ext4 可自动修复错误, 注入后仍保持卸载状态交给产品诊断
            self.assert_true(widget.create_usb_ext4_repairable_error(partition))
            self.assert_true(widget.get_partition_filesystem_type(partition) == "ext4")
            self.assert_false(widget.get_usb_device_mounted(mount_point=self.MOUNT_POINT))
            self.assert_true(widget.get_usb_ext4_partition_check_rc(partition) != 0)
            self.assert_true(widget.get_usb_ext4_partition_has_errors(partition))

            # 6) 启动电脑管家并进入修复工具页面
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_cards_view_showing())

            # 7) 描述步骤1: 进入"USB 设备修复"详情并点击开始修复
            widget.click_repair_card_by_name("USB 设备修复")
            self.assert_true(widget.get_repair_detail_showing())
            # xdotool raw click 偶发丢事件(2005759 首跑实测), 用重试辅助等待对话框
            self.assert_true(widget.click_start_repair_button_until_dialog())

            # 8) 依次确认 设备选择 / 诊断结果 / 修复文件系统 弹窗, 直到流程结束
            self.assert_true(widget.handle_usb_fix_confirm_dialog(timeout=300))

            # 9) 产品输出证据: 枚举 -> 选中设备 -> 诊断出可修复的文件系统损坏 ->
            #    执行修复 -> 汇总"修复完成"
            self.assert_true(
                widget.get_repair_output_contains("正在检测 USB 设备", timeout=30)
            )
            self.assert_true(widget.get_repair_output_contains("已选择设备", timeout=30))
            self.assert_true(widget.get_repair_output_contains("ext4", timeout=10))
            self.assert_true(widget.get_repair_output_contains("文件系统损坏", timeout=30))
            self.assert_true(
                widget.get_repair_output_contains("可尝试自动修复", timeout=10)
            )
            self.assert_true(widget.get_repair_output_contains("修复成功", timeout=30))
            self.assert_true(widget.get_repair_output_contains("修复完成", timeout=10))
            self.assert_true(
                widget.get_repair_output_contains("USB 修复流程结束", timeout=30)
            )

            # 10) 关闭修复对话框: 脚本末尾的提示框没有超时且会阻塞脚本, 必须先点掉
            #     提示框再关窗口, 并确认窗口已关闭(残留会盖在桌面污染后续用例)
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])

            # 11) 物理校验: 修复后文件系统不再有错误(产品命令真的修好了),
            #     重挂载后数据样本 sha256/大小/文本一致, 文件系统类型未变
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            self.assert_true(widget.get_usb_ext4_partition_check_rc(partition) == 0)
            self.assert_false(widget.get_usb_ext4_partition_has_errors(partition))
            self.assert_true(
                widget.mount_usb_partition(partition, self.MOUNT_POINT, "ext4")
            )
            self.assert_true(widget.verify_usb_integrity_payload(self.MOUNT_POINT, payload))
            # 删除样本文件后再卸载, 不在测试机/U 盘留残留
            widget.sudo_run_cmd(
                f"rm -f {payload.get('bin', '')} {payload.get('text', '')}",
                timeout=20,
                out_debug_flag=False,
            )
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            self.assert_true(widget.get_partition_filesystem_type(partition) == "ext4")
            # 电脑管家在修复结束后仍存活(流程未把系统带崩)
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            # 回退: 卸载/删挂载点 -> 关闭修复框与交互框 -> 清理合成盘(udev 规则+scsi_debug)
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

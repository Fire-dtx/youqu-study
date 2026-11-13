#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):
    MOUNT_POINT = "/tmp/test_usb_exfat_mount"
    PAYLOAD_PREFIX = "autotest_2005749"
    # 产品在"设备无问题"分支可能直接以"设备状态正常，无需修复"收尾, 也可能继续
    # 走到脚本末尾的"USB 修复流程结束", 两种收尾都视为流程正常终止
    DONE_TEXTS = ("设备状态正常", "无需修复", "未检测到问题")

    def test_mycase_246(self):
        """外设修复-修复U盘无法识别--无错误的 exFAT U 盘

        验证 usb-fix 插件对"无错误的 exFAT U 盘"的完整处理:
        枚举设备 -> 选择设备 -> 诊断文件系统/分区表/写保护 -> 判定设备状态正常
        ("未检测到问题") -> 不做任何修复 -> 流程正常结束, 输出无错误信息;
        整个修复过程不得破坏文件系统、不得丢失 U 盘上的数据。

        设备来源(等价实现): usb-fix 只枚举 /sys/block/sd* 中 udev 属性
        ID_BUS=usb 的整盘(见 plugin-usb-fix/entry.sh 的 enumerate_usb_devices),
        loop 设备不会被识别, 测试机也没有实体 U 盘。因此用内核 scsi_debug 造一块
        内存盘(设备名仍是 sdX), 再用只匹配 scsi_debug 设备(vendor=Linux /
        model=scsi_debug)的 udev 规则把 ID_BUS 覆写为 usb, 对插件而言与实体
        "无错误的 exFAT U 盘"完全等价, 且不接触任何真实磁盘。本用例只用合成盘:
        真实 U 盘上要执行 mkfs 与错误注入, 不可恢复, 故不退化到真实设备。
        执行期间停止 udisks2, 避免桌面自动挂载干扰格式化与修复, 结束后恢复。

        产品依据(deepin-pc-manager 1.1.7 的 plugin-usb-fix/entry.sh):
        - 枚举后 openlistview 让用户选设备, 选中后输出"已选择设备: /dev/sdX";
        - check_filesystem 对每个分区执行 fsck -n, 干净时输出
          "分区 /dev/sdX1 (exfat) 文件系统正常" / "文件系统诊断结果: ok";
        - check_partition_table 干净时输出"分区表诊断结果: ok (类型: dos)";
        - present_diagnosis 在无问题时输出"未检测到问题, /dev/sdX 设备状态正常。",
          不弹修复确认框、不执行任何修复动作;
        - 全程无 [ERROR]/修复失败/文件系统损坏 等错误输出。
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

            # 2) 前置: 分区格式化为 exFAT 并挂载(描述前置"无错误的 exFAT U 盘")
            partition = widget.prepare_usb_exfat_partition(
                mount_point=self.MOUNT_POINT, partition=partition
            )
            self.assert_true(partition != "")
            self.assert_true(widget.get_usb_device_mounted(mount_point=self.MOUNT_POINT))
            self.assert_true(widget.get_partition_filesystem_type(partition) == "exfat")

            # 3) 写入数据完整性样本(4MB 随机内容 + 中文名文本), 记录 sha256/大小
            payload = widget.write_usb_integrity_payload(
                self.MOUNT_POINT, prefix=self.PAYLOAD_PREFIX
            )
            self.assert_true(bool(payload))

            # 4) 交给产品诊断前卸载: 产品会对分区做只读挂载探测, 且 fsck 对已挂载
            #    分区会判 dirty; 卸载后确认这就是"无错误的 exFAT U 盘"
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            self.assert_false(widget.get_usb_device_mounted(mount_point=self.MOUNT_POINT))
            self.assert_true(widget.get_usb_exfat_filesystem_check_rc(partition) == 0)
            self.assert_false(widget.get_usb_exfat_filesystem_has_errors(partition))

            # 5) 启动电脑管家并进入修复工具页面
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_cards_view_showing())

            # 6) 描述步骤1: 进入"USB 设备修复"详情并点击开始修复
            widget.click_repair_card_by_name("USB 设备修复")
            self.assert_true(widget.get_repair_detail_showing())
            # xdotool raw click 偶发丢事件(2005759 首跑实测), 用重试辅助等待对话框
            self.assert_true(widget.click_start_repair_button_until_dialog())

            # 7) 应答修复过程中的交互框: 健康盘只需选择设备一次, 之后产品直接收尾
            self.assert_true(
                widget.handle_usb_fix_confirm_dialog(
                    timeout=240, done_texts=self.DONE_TEXTS
                )
            )

            # 8) 输出证据: 枚举 -> 选中设备 -> exFAT 文件系统正常 -> 诊断 ok ->
            #    未检测到问题/设备状态正常
            self.assert_true(
                widget.get_repair_output_contains("正在检测 USB 设备", timeout=30)
            )
            self.assert_true(widget.get_repair_output_contains("已选择设备", timeout=30))
            self.assert_true(widget.get_repair_output_contains("exfat", timeout=10))
            self.assert_true(widget.get_repair_output_contains("文件系统正常", timeout=30))
            self.assert_true(
                widget.get_repair_output_contains("文件系统诊断结果: ok", timeout=10)
            )
            self.assert_true(
                widget.get_repair_output_contains("分区表诊断结果: ok", timeout=10)
            )
            self.assert_true(
                widget.get_repair_output_contains("未检测到问题", timeout=30)
                or widget.get_repair_output_contains("设备状态正常", timeout=10)
            )
            # 9) 预期"命令无报错, 输出无错误信息"; 无问题分支也不应出现任何
            #    修复动作/损坏结论文案
            output = widget.get_repair_output_text()
            error_lines = widget.get_repair_output_error_lines()
            print(f"[2005749] 修复输出(无错误 exFAT 分支): {output!r}")
            print(f"[2005749] 输出中的错误/告警行: {error_lines!r}")
            for keyword in (
                "[ERROR]",
                "ERROR:",
                "修复失败",
                "文件系统损坏",
                "文件系统严重损坏",
                "自动修复不可用",
                "可尝试自动修复",
                "用户取消",
            ):
                self.assert_false(keyword in output)
            # 产品自有文案可能包含"无错误"等带"错误"二字的正常表述,
            # 故只把错误级别日志([ERROR]/ERROR:)作为硬失败, 其余告警行仅打印留档
            self.assert_false(any("[ERROR]" in line or "ERROR:" in line for line in error_lines))

            # 10) 关闭修复对话框: 脚本末尾的提示框没有超时且会阻塞脚本, 必须先点掉
            #     提示框再关窗口, 并确认窗口已关闭(残留会盖在桌面污染后续用例)
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])

            # 11) 物理校验: 重新挂载后数据样本 sha256/大小/文本全部一致(数据未丢失),
            #     exFAT 文件系统仍健康(未被修复流程破坏), 类型未被改动
            self.assert_true(
                widget.mount_usb_partition(partition, self.MOUNT_POINT, "exfat")
            )
            self.assert_true(widget.verify_usb_integrity_payload(self.MOUNT_POINT, payload))
            self.assert_true(widget.get_partition_filesystem_type(partition) == "exfat")
            widget.unmount_usb_partition(partition, mount_point=self.MOUNT_POINT)
            self.assert_true(widget.get_usb_exfat_filesystem_check_rc(partition) == 0)
            self.assert_false(widget.get_usb_exfat_filesystem_has_errors(partition))
            # 电脑管家在修复结束后仍存活(流程未把系统带崩)
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            # 回退: 卸载/删挂载点 -> 关闭修复框 -> 清理合成盘(udev 规则+scsi_debug)
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

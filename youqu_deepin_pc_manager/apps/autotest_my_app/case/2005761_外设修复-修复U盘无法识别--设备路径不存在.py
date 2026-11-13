#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    # 产品(plugin-usb-fix/entry.sh)枚举不到 USB 存储设备时的提示文案。各版本/
    # 语言的用词不同, 用关键词集合做等价断言: 命中任意一个即视为"命令报错,
    # 提示设备不存在"。
    NO_DEVICE_KEYWORDS = (
        "未检测到",
        "未找到",
        "检测不到",
        "没有检测到",
        "未发现",
        "不存在",
        "无可用设备",
        "no usb",
        "not found",
    )
    # 出现这些文案说明产品已进入"选设备/诊断/修复"分支, 与"设备路径不存在"预期相反
    REPAIR_PATH_TEXTS = ("已选择设备", "正在修复", "修复成功", "修复完成")

    def test_mycase_032(self):
        """外设修复-修复U盘无法识别--设备路径不存在

        描述: 前置"无 U 盘插入"; 步骤"点击开始修复"; 预期"命令报错, 提示设备不存在"。
        验证 usb-fix 插件枚举不到任何 USB 存储设备时不进入选设备/诊断/修复流程,
        而是以错误提示结束, 且电脑管家进程存活、设备现场不被改动。

        设备现场(等价实现): usb-fix 只枚举 /sys/block/sd* 中 udev 属性 ID_BUS=usb
        的整盘(见产品 plugin-usb-fix/entry.sh 的 enumerate_usb_devices)。测试机
        通常没有实体 U 盘, 天然就是"设备路径不存在"现场; 若接了实体 U 盘, 用只作用
        于该盘的 udev 规则把 ID_BUS 临时改写为 scsi, 使插件枚举结果为空(对插件等价
        于设备不存在), 用例结束在 finally 里删除规则并重新触发块设备事件恢复原属性,
        全程不写、不格式化、不卸载任何真实磁盘。

        断言等价说明: "命令报错, 提示设备不存在"在产品 1.1.7 上表现为插件输出
        未检测到/未找到设备等错误提示, 文案随版本不同, 故以关键词集合 + 未进入
        修复分支 + 进程存活作为等价断言; 提示框只作日志留档, 不能替代输出关键词,
        避免流程卡在提示框时被误判为"命令已报错"。
        """
        widget = MyAppWidget(check_start=False)

        try:
            # ---- 1) 前置: 现场没有任何被 usb-fix 枚举到的 USB 存储设备 ----
            # 先清掉上一轮可能残留的合成盘/udev 规则(正常不会命中)
            widget.cleanup_synthetic_usb_storage_device()
            # 记录屏蔽前的真实 USB 存储盘快照, 收尾时撤销屏蔽后比对现场未变
            usb_disks_before = widget.get_usb_storage_disks()
            widget.mask_usb_storage_devices()
            if not widget.get_no_usb_device_present():
                logger.error("环境中仍存在 USB 存储设备, 无法构造无 U 盘现场")
            self.assert_true(widget.get_no_usb_device_present())
            if bool(widget.get_usb_storage_disks()):
                logger.error("usb-fix 的枚举结果不为空, 无法验证无设备分支")
            self.assert_false(bool(widget.get_usb_storage_disks()))

            # ---- 2) 启动电脑管家并进入 USB 设备修复详情页 ----
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            widget.click_repair_card_by_name("USB 设备修复")
            self.assert_true(widget.get_repair_detail_showing())

            # ---- 3) 描述步骤1: 点击开始修复 ----
            widget.click_repair_start_button()
            if not widget.get_repair_dialog_showing(timeout=20):
                logger.error("点击开始修复后未出现修复对话框")
            self.assert_true(widget.get_repair_dialog_showing(timeout=5))

            # ---- 4) 预期: 命令报错, 提示设备不存在(不得进入修复分支) ----
            result = widget.wait_repair_no_device_result(
                self.NO_DEVICE_KEYWORDS, timeout=120
            )
            output = result["text"]
            logger.info(f"[2005761] 修复输出(无设备分支): {output!r}")
            logger.info(
                f"[2005761] 命中关键词={result['matched']!r} "
                f"提示框={result['notify_seen']} 点掉提示框={result['notify_dismissed']}"
            )
            if not output:
                logger.error("修复脚本未产生任何输出")
            self.assert_true(bool(output))
            # 只认输出文本里的"未检测到/设备不存在"类提示: 提示框可能只是流程阻塞,
            # 不能单独作为"命令报错"的证据
            self.assert_true(bool(result["matched"]))
            for text in self.REPAIR_PATH_TEXTS:
                if text in output:
                    logger.error(f"无设备场景不应进入修复分支, 但输出包含 {text!r}")
                self.assert_false(text in output)

            # ---- 5) 收尾核验: 撤销枚举屏蔽后设备现场与用例开始时一致, 管家进程仍存活
            self.assert_true(widget.unmask_usb_storage_devices())
            self.assert_equal(
                sorted(usb_disks_before), sorted(widget.get_usb_storage_disks())
            )
            self.assert_true(widget.get_pc_manager_process_status())
            widget.close_repair_dialog()
        finally:
            # 回退: 关修复框/提示框 -> 撤销 USB 枚举屏蔽并恢复实体盘属性 -> 清合成盘残留
            if widget.get_repair_dialog_showing(timeout=2):
                widget.close_repair_dialog()
            widget.close_repair_notify_dialog()
            widget.close_usb_fix_prompt_dialog(rounds=2)
            # 屏蔽撤销必须成功, 否则后续用例会把真实 U 盘当成"不存在"
            self.assert_true(widget.unmask_usb_storage_devices())
            widget.cleanup_synthetic_usb_storage_device()
            widget.kill_pc_manager()

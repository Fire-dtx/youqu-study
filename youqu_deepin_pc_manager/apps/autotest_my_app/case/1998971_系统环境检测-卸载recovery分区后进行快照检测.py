#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/04
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep, logger


class TestMyCase(BaseCase):

    def test_mycase_059(self):
        """系统环境检测-卸载 /recovery 分区后进行快照检测：
        卸载 /recovery 后点击"系统环境检测"卡片，仅该分项执行检测，
        "备份与快照检查"项存在并给出异常结论（备份分区不可用），
        用例结束后重新挂载 /recovery 恢复环境。"""
        widget = MyAppWidget(check_start=False)

        # 前置: 确认 /recovery 已挂载, 否则跳过
        if not widget.get_recovery_partition_mounted():
            pytest.skip("当前环境无 /recovery 分区或未挂载, 跳过此用例")
        mount_source = widget.get_recovery_mount_source()

        # 卸载 /recovery 分区, 构造备份分区不可用场景
        self.assert_true(widget.unmount_recovery_partition())
        self.assert_false(widget.get_recovery_partition_mounted())

        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            # 点击"系统环境检测"卡片, 真实触发该分项检测
            self.assert_true(widget.run_detection_item("系统环境检测"))

            self.assert_true(widget.get_detection_item_present("系统环境检测", "备份与快照检查"))
            # 只点了"系统环境检测", 其它分项不应被检查(区别于全面检测)
            self.assert_true(widget.is_only_group_detected("系统环境检测"))

            verdict, detail = widget.get_detection_item_verdict("backup_partition")
            logger.info(f"备份与快照检查单项结论(未挂载 /recovery): {verdict}, 原始结果: {detail}")
            self.assert_false(verdict)
        finally:
            widget.kill_pc_manager()
            # 恢复 /recovery 挂载
            if mount_source:
                widget.sudo_run_cmd(f"mount {mount_source} /recovery 2>/dev/null", timeout=10, out_debug_flag=False)
            self.assert_true(widget.get_recovery_partition_mounted())

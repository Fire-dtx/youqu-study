#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

# 用例要求"有检测结果"的检测项（备份还原分区）
BACKUP_PARTITION_ITEM = "备份与快照检查"
BACKUP_PARTITION_ID = "backup_partition"

# 用例要求"状态显示"的检测项：列表可见 + 能读到该项检测状态
STATUS_DISPLAY_ITEMS = {
    "SSH密钥": "ssh_key",
    "时间配置": "time_config",
    "系统版本检测": "system_version",
}


class TestMyCase(BaseCase):

    def test_mycase_058(self):
        """系统环境检测-正常状态：
        点击"系统环境检测"卡片真实执行该分项检测，校验：
        1. 备份还原分区（备份与快照检查 / backup_partition）有检测结果；
        2. SSH密钥、时间配置、系统版本检测三项状态正常显示
           （检测项在列表中可见，且能读到该项的检测状态）。

        不校验各检测项结论是否为"通过"：机器存在可升级包时，
        系统版本检测如实返回「有更新可用」(failure:2511)，
        这属于正常的状态显示，不影响本用例。"""
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        # 导航到系统检测页面
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        # 点击"系统环境检测"卡片, 真实触发该分项检测
        self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))

        item_names = widget.get_detection_item_names("系统环境检测")
        logger.info(f"系统环境检测分项: {item_names}")
        # 备份还原分区检测项显示
        self.assert_true(BACKUP_PARTITION_ITEM in item_names)
        # SSH密钥 / 时间配置 / 系统版本检测项显示
        for item_name in STATUS_DISPLAY_ITEMS:
            self.assert_true(item_name in item_names)

        # 只点了"系统环境检测", 其它分项不应被检查
        self.assert_true(widget.is_only_group_detected("系统环境检测"))

        state = widget.get_detection_group_state("系统环境检测")
        logger.info(f"系统环境检测状态: {state}")
        self.assert_true(state["total"] > 0)
        self.assert_true(state["checked"] == state["total"])

        # 1. 备份还原分区有检测结果
        verdict, detail = widget.get_detection_item_verdict(BACKUP_PARTITION_ID)
        logger.info(
            f"系统环境检测/{BACKUP_PARTITION_ITEM}({BACKUP_PARTITION_ID}) 结论: {verdict}, 原始结果: {detail}"
        )
        self.assert_true(verdict is not None)
        self.assert_true(bool(str(detail or "").strip()))

        # 2. 各检测项状态正常显示(能读到该检测项的检测状态)
        for item_name, item_id in STATUS_DISPLAY_ITEMS.items():
            verdict, detail = widget.get_detection_item_verdict(item_id)
            logger.info(
                f"系统环境检测/{item_name}({item_id}) 显示状态: {verdict}, 原始结果: {detail}"
            )
            self.assert_true(verdict is not None)
            self.assert_true(bool(str(detail or "").strip()))

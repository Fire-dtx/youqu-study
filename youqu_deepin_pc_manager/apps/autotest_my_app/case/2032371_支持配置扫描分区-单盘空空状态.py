#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_195(self):
        """支持配置扫描分区-单盘空空状态

        前置: 单盘环境(仅 / 与 /home, 无 /media 下数据分区); 用例开始前
        校验确实没有 /media 挂载。
        断言: 复选框列表隐藏; 空状态文案控件可见; 列表容器隐藏;
        空状态文案在卡片内水平居中(位置与尺寸等价校验)。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            media_mounts = widget.run_cmd(
                "findmnt -rn -o TARGET | grep '^/media/' || true",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            logger.info(f"[2032371] media_mounts={media_mounts!r}")
            self.assert_true(media_mounts == "")

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())

            # 复选框列表为空
            rows = []
            for expr in (
                "$//settings_extendedScanPartition",
                "$//extendedScanPartitionRow",
            ):
                rows = widget.dog.find_elements_by_attr(expr) or []
                if rows:
                    break
            logger.info(f"[2032371] rows={len(rows)}")
            self.assert_true(len(rows) == 0)

            empty = widget.dog.find_elements_by_attr(
                "$//settings_extendedScanPartitionEmptyText"
            )
            self.assert_true(bool(empty))
            empty = empty[0] if isinstance(empty, list) else empty
            logger.info(
                f"[2032371] empty name={getattr(empty, 'name', None)!r} "
                f"text={getattr(empty, 'text', None)!r} showing={empty.showing}"
            )
            self.assert_true(empty.showing)

            # 列表容器应隐藏
            holders = widget.dog.find_elements_by_attr(
                "$//extendedScanPartitionList"
            )
            if holders and not isinstance(holders, bool):
                for holder in holders:
                    logger.info(f"[2032371] list showing={holder.showing}")
                    self.assert_false(holder.showing)

            # 空状态文案水平居中于卡片
            card = widget.dog.find_elements_by_attr(
                "$//settings_extendedScanPartitions"
            )
            card = card[0] if card and not isinstance(card, bool) else None
            if card is not None:
                cx = empty.position[0] + empty.size[0] / 2
                ccx = card.position[0] + card.size[0] / 2
                logger.info(
                    f"[2032371] empty_center={cx} card_center={ccx} "
                    f"card={card.size}"
                )
                self.assert_true(abs(cx - ccx) <= card.size[0] * 0.1)
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)

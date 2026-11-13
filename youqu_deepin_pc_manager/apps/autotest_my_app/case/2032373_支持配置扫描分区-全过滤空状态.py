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

RO_MOUNT = "/media/autotest_ro"
OTHER_MOUNT = "/mnt/autotest_else"


class TestMyCase(BaseCase):

    def test_mycase_196(self):
        """支持配置扫描分区-全过滤空状态

        构造多块磁盘并存但全部被过滤: 系统分区 /boot、/recovery 命中
        黑名单; /dev/sdb1 只读挂载 /media/autotest_ro(只读剔除);
        /dev/sda6 挂载 /mnt/autotest_else(非 /media 剔除)。
        断言: 复选框列表为空, 空状态文案可见, 列表容器隐藏, 文案居中。
        清理: umount 并删除临时挂载点。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            # 多块磁盘前置
            disks = widget.run_cmd(
                "lsblk -dn -o NAME,TYPE | awk '$2==\"disk\"{print $1}'",
                timeout=5,
                out_debug_flag=False,
            )
            logger.info(f"[2032373] disks={disks!r}")
            self.assert_true(len(disks.split()) >= 2)

            widget.sudo_run_cmd(
                f"umount {RO_MOUNT} 2>/dev/null; umount {OTHER_MOUNT} 2>/dev/null; "
                f"rmdir {RO_MOUNT} {OTHER_MOUNT} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {RO_MOUNT} {OTHER_MOUNT} && "
                f"mount -o ro /dev/sdb1 {RO_MOUNT} && "
                f"mount /dev/sda6 {OTHER_MOUNT} && "
                f"findmnt -n -o SOURCE {RO_MOUNT} && "
                f"findmnt -n -o SOURCE {OTHER_MOUNT}",
                timeout=30,
                return_code=True,
            )
            logger.info(f"[2032373] mount rc={rc} out={out!r}")
            self.assert_true(rc == 0)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())

            rows = []
            for expr in (
                "$//settings_extendedScanPartition",
                "$//extendedScanPartitionRow",
            ):
                rows = widget.dog.find_elements_by_attr(expr) or []
                if rows:
                    break
            logger.info(f"[2032373] rows={len(rows)}")
            self.assert_true(len(rows) == 0)

            empty = widget.dog.find_elements_by_attr(
                "$//settings_extendedScanPartitionEmptyText"
            )
            self.assert_true(bool(empty))
            empty = empty[0] if isinstance(empty, list) else empty
            logger.info(
                f"[2032373] empty showing={empty.showing} text={getattr(empty, 'text', None)!r}"
            )
            self.assert_true(empty.showing)

            holders = widget.dog.find_elements_by_attr(
                "$//extendedScanPartitionList"
            )
            if holders and not isinstance(holders, bool):
                for holder in holders:
                    self.assert_false(holder.showing)

            card = widget.dog.find_elements_by_attr(
                "$//settings_extendedScanPartitions"
            )
            card = card[0] if card and not isinstance(card, bool) else None
            if card is not None:
                cx = empty.position[0] + empty.size[0] / 2
                ccx = card.position[0] + card.size[0] / 2
                logger.info(f"[2032373] empty_center={cx} card_center={ccx}")
                self.assert_true(abs(cx - ccx) <= card.size[0] * 0.1)
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"umount {RO_MOUNT} 2>/dev/null; umount -l {RO_MOUNT} 2>/dev/null; "
                f"umount {OTHER_MOUNT} 2>/dev/null; umount -l {OTHER_MOUNT} 2>/dev/null; "
                f"rmdir {RO_MOUNT} {OTHER_MOUNT} 2>/dev/null; true",
                timeout=30,
            )

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

MOUNT_OK = "/media/autotest_int"
MOUNT_TMP = "/mnt/test"
DEV_OK = "/dev/sda6"
DEV_TMP = "/dev/sdb1"


class TestMyCase(BaseCase):

    def test_mycase_192(self):
        """支持配置扫描分区-分区过滤白名单

        前置: 内置盘(NVMe 位置以 /dev/sda 代替)与 USB 移动硬盘均 fstab
        挂载; 另手动 mount 一个块设备到 /mnt/test 但不写 fstab。测试机无
        USB 移动硬盘(无法伪造 removable=1), 但可用内核属性等价校验:
        列表中出现的每一项, 其承载盘 removable 都必须为 0。

        构造: /dev/sda6 写入 /etc/fstab 并挂载到 /media/autotest_int;
        /dev/sdb1 直接挂载到 /mnt/test(不写 fstab)。
        清理: umount 两个挂载点、删除目录、还原 /etc/fstab。

        断言: 内置盘出现在列表; /mnt/test 临时挂载不出现; 列表项均为
        /media 下、removable==0 的固定盘。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        fstab_backup = "/tmp/fstab.autotest.bak"
        ok = False
        try:
            # 清理上次异常中断可能残留的挂载点
            widget.sudo_run_cmd(
                f"umount {MOUNT_OK} 2>/dev/null; umount {MOUNT_TMP} 2>/dev/null; "
                f"rmdir {MOUNT_OK} {MOUNT_TMP} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"cp -a /etc/fstab {fstab_backup} && "
                f"mkdir -p {MOUNT_OK} {MOUNT_TMP} && "
                f"grep -q ' {MOUNT_OK} ' /etc/fstab || "
                f"echo '{DEV_OK} {MOUNT_OK} ext4 defaults 0 2' >> /etc/fstab; "
                f"mount {MOUNT_OK} && mount {DEV_TMP} {MOUNT_TMP} && "
                f"findmnt -n -o SOURCE {MOUNT_OK} && "
                f"findmnt -n -o SOURCE {MOUNT_TMP}",
                timeout=30,
                return_code=True,
            )
            logger.info(f"[2032363] mount rc={rc} out={out!r}")
            self.assert_true(rc == 0)
            ok = True

            # /mnt/test 未写入 fstab
            fstab_hit = widget.run_cmd(
                f"grep -c '{MOUNT_TMP}' /etc/fstab || true",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            logger.info(f"[2032363] fstab_hit={fstab_hit!r}")
            self.assert_true(fstab_hit in ("", "0"))

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
            mounts = [getattr(r, "description", "") or "" for r in rows]
            logger.info(f"[2032363] mounts={mounts!r}")

            # 内置盘(fstab 静态挂载)应展示
            self.assert_true(MOUNT_OK in mounts)
            # 未写 fstab 的临时挂载(/mnt/test)不应展示
            self.assert_true(MOUNT_TMP not in mounts)

            # 每个展示项: /media 下、承载盘 removable==0(removable=1 一律不展示)
            for mp in mounts:
                self.assert_true(mp.startswith("/media/"))
                src = widget.run_cmd(
                    f"findmnt -n -o SOURCE {mp} 2>/dev/null",
                    timeout=5,
                    out_debug_flag=False,
                ).strip()
                self.assert_true(bool(src))
                node = widget.run_cmd(
                    f"basename $(readlink -f {src})",
                    timeout=5,
                    out_debug_flag=False,
                ).strip()
                removable = widget.run_cmd(
                    f"cat /sys/class/block/{node}/../removable 2>/dev/null || echo 1",
                    timeout=5,
                    out_debug_flag=False,
                ).strip()
                logger.info(f"[2032363] mount={mp} src={src} node={node} removable={removable}")
                self.assert_true(removable == "0")
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"umount {MOUNT_TMP} 2>/dev/null; umount {MOUNT_OK} 2>/dev/null; "
                f"rmdir {MOUNT_TMP} {MOUNT_OK} 2>/dev/null; "
                f"[ -f {fstab_backup} ] && cp -a {fstab_backup} /etc/fstab && "
                f"rm -f {fstab_backup}; true",
                timeout=30,
            )
            logger.info(f"[2032363] cleanup done, ok={ok}")

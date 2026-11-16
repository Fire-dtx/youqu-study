#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os
import re
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep

MOUNT = "/media/autotest_a"
CONF = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
CONF_BAK = "/tmp/pcm_conf.largefile.bak"
# daemon 每次 StartLargeFileScan 都会重扫(无结果缓存), 日志是「本次是否真扫描、
# 是否扫到该分区」的唯一直接证据; UI 上扫描视图只存在 0.6s 左右, 抓不到
DAEMON_LOG = os.path.expanduser(
    "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager-session-daemon.log"
)


class TestMyCase(BaseCase):

    def test_mycase_043(self):
        """支持配置扫描分区-大文件扫描联动

        构造: /dev/sda6 挂到 /media/autotest_a, 在其中创建 5GB 大文件;
        在设置页勾选该分区(配置写入 basic.cleanup.extendedScanPaths),
        进入系统优化->大文件清理触发扫描。
        断言: 扫描完成后结果页显示、文件名为本次运行唯一命名的
        autotest_big_5g_<时间戳>.bin, 且 daemon 日志显示本次确实启动了扫描
        (extraRoots 1)并在 /media/autotest_a 命中 >=1 个大文件。
        清理: 删除大文件、还原配置、umount 并删除挂载点。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        try:
            saved_media = widget.isolate_media_mounts()
            widget.sudo_run_cmd(
                f"umount {MOUNT} 2>/dev/null; rmdir {MOUNT} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {MOUNT} && mount /dev/sda6 {MOUNT} && "
                f"df -B1 --output=avail {MOUNT} | tail -1",
                timeout=60,
                return_code=True,
            )
            logger.info(f"[2032379] mount+df rc={rc} out={out!r}")
            self.assert_true(rc == 0)
            # 前置容量校验: 该盘曾被 201 的 dm-linear+mkfs 覆盖成 5GiB,
            # 导致 5GiB 大文件 ENOSPC 却看不出原因, 这里先明确报出来
            # sudo -S 的「请输入密码」提示会与数字粘在同一行, 按长数字匹配
            numbers = re.findall(r"\d{7,}", out or "")
            avail = int(numbers[-1]) if numbers else 0
            logger.info(f"[2032379] {MOUNT} 可用={avail} B")
            self.assert_true(avail >= 6 * 1024 ** 3)

            # 文件名带本次时间戳: 产品无扫描结果缓存, 唯一名可排除「结果页残留」
            big_file = f"{MOUNT}/autotest_big_5g_{int(time.time())}.bin"
            out, rc = widget.sudo_run_cmd(
                f"fallocate -l 5G {big_file} && stat -c %s {big_file}",
                timeout=60,
                return_code=True,
            )
            logger.info(f"[2032379] file rc={rc} out={out!r}")
            self.assert_true(rc == 0)
            self.assert_true("5368709120" in out)

            widget.run_cmd(
                f"cp -a {CONF} {CONF_BAK} && "
                f"grep -v 'extendedScanPaths' {CONF} > {CONF}.tmp && "
                f"mv {CONF}.tmp {CONF}",
                timeout=5,
                out_debug_flag=False,
            )

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            # 设置页勾选数据盘 A
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())
            target = None
            for expr in (
                "$//settings_extendedScanPartition",
                "$//extendedScanPartitionRow",
            ):
                for elem in widget.dog.find_elements_by_attr(expr, probe=True) or []:
                    if (getattr(elem, "description", "") or "") == MOUNT:
                        target = elem
                        break
                if target:
                    break
            self.assert_true(target is not None)
            target.click()
            sleep(1)
            conf = widget.run_cmd(f"cat {CONF}", timeout=5, out_debug_flag=False)
            logger.info(f"[2032379] conf={conf!r}")
            self.assert_true(MOUNT in conf)
            widget.close_settings_dialog()
            sleep(2)

            # 触发大文件清理扫描; 先记日志偏移, 只认本次点击之后产生的扫描记录
            log_offset = int(
                widget.run_cmd(f"stat -c %s {DAEMON_LOG} 2>/dev/null || echo 0",
                               timeout=10, out_debug_flag=False).strip() or 0
            )
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_large_file_scan_completed(timeout=240))
            self.assert_true(widget.get_large_file_result_showing())
            filenames = widget.get_large_file_table_filenames()
            logger.info(f"[2032379] filenames={filenames} big_file={big_file}")
            self.assert_true(
                any(os.path.basename(big_file) in name for name in filenames)
            )
            # 扫描真的发生了: 本次窗口内 daemon 启动了 StartLargeFileScan 且
            # 在目标分区扫到文件(UI 结果页本身不能区分「扫描过」与「直接空页」)
            root_done = 'Directory scan completed: "%s"' % MOUNT
            pattern = "Scan started|" + root_done
            scan_log = widget.run_cmd(
                "tail -c +%d %s 2>/dev/null | grep -aE '%s'"
                % (log_offset + 1, DAEMON_LOG, pattern),
                timeout=20,
                out_debug_flag=False,
            )
            logger.info("[2032379] scan_log=%r" % (scan_log[-600:],))
            self.assert_true("Scan started" in scan_log)
            self.assert_true(root_done in scan_log)
            found = [
                int(n)
                for n in re.findall(
                    r'Directory scan completed: "%s"[^\n]*found: (\d+)' % MOUNT,
                    scan_log,
                )
            ]
            logger.info(f"[2032379] found={found}")
            self.assert_true(bool(found) and found[-1] >= 1)
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"rm -f {MOUNT}/autotest_big_5g_*.bin; umount {MOUNT} 2>/dev/null; "
                f"umount -l {MOUNT} 2>/dev/null; rmdir {MOUNT} 2>/dev/null; true",
                timeout=30,
            )
            widget.run_cmd(
                f"[ -f {CONF_BAK} ] && cp -a {CONF_BAK} {CONF} && rm -f {CONF_BAK}; true",
                timeout=5,
                out_debug_flag=False,
            )
            widget.restore_media_mounts(saved_media)

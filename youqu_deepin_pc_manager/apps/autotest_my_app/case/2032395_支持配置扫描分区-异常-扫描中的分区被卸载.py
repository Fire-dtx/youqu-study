#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep

MOUNT = "/media/autotest_a"
A_LOAD = f"{MOUNT}/many"
HOME_DIR_DUP = os.path.expanduser("~/autotest_dup_unmount")
CONF = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
CONF_BAK = "/tmp/pcm_conf.unmount_scan.bak"


class TestMyCase(BaseCase):

    def test_mycase_202(self):
        """支持配置扫描分区-异常-扫描中的分区被卸载

        构造: A 盘挂载并勾选, 盘内 2 万个 1MB 稀疏文件(拉长扫描);
        A 盘内放 30 万个唯一尺寸稀疏文件拉长扫描窗口; /home 放一组 3MB
        有效重复文件作为已扫数据。
        步骤: 触发重复文件清理扫描, 扫描视图出现后立即 umount -l A。
        断言: 扫描不卡死/不崩溃(进程存活), 最终展示结果页并保留 /home 的
        有效重复文件, 结果不含 A 盘文件。
        清理: 重新挂载校验 A 数据仍在, 删除负载/测试文件、还原配置、
        umount/rmdir、恢复隔离文件。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        isolated = []
        try:
            widget.sudo_run_cmd(
                f"umount {MOUNT} 2>/dev/null; rmdir {MOUNT} 2>/dev/null; true",
                timeout=20,
            )
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {MOUNT} && mount /dev/sda6 {MOUNT} && echo MOUNTED",
                timeout=40,
                return_code=True,
            )
            logger.info(f"[2032395] mount rc={rc} out={out!r}")
            self.assert_true(rc == 0 and "MOUNTED" in out)

            widget.run_cmd(
                f"cp -a {CONF} {CONF_BAK} && "
                f"grep -v 'extendedScanPaths' {CONF} > {CONF}.tmp && "
                f"mv {CONF}.tmp {CONF}",
                timeout=5,
                out_debug_flag=False,
            )
            isolated = widget.isolate_foreign_dup_files()

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            opened = False
            for _ in range(3):
                widget.open_settings_dialog()
                if widget.get_settings_dialog_showing(timeout=6):
                    opened = True
                    break
                sleep(1)
            self.assert_true(opened)
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            target = None
            for expr in (
                "$//settings_extendedScanPartition",
                "$//extendedScanPartitionRow",
            ):
                for elem in widget.dog.find_elements_by_attr(expr) or []:
                    if (getattr(elem, "description", "") or "") == MOUNT:
                        target = elem
                        break
                if target:
                    break
            self.assert_true(target is not None)
            target.click()
            sleep(1)
            widget.close_settings_dialog()
            sleep(2)
            ok = False
            for _ in range(10):
                if MOUNT in widget.run_cmd(
                    f"cat {CONF}", timeout=5, out_debug_flag=False
                ):
                    ok = True
                    break
                sleep(0.5)
            self.assert_true(ok)

            # 设置页勾选完成后再铺扫描负载, 避免对话框打开期间大量文件影响 UI 操作
            out, rc = widget.sudo_run_cmd(
                f"mkdir -p {A_LOAD} && "
                f"python3 - <<'PYEOF'\n"
                f"import os\n"
                f"d = '{A_LOAD}'\n"
                f"for i in range(300000):\n"
                f"    p = os.path.join(d, 'a_load_%07d.bin' % i)\n"
                f"    fd = os.open(p, os.O_CREAT | os.O_WRONLY, 0o644)\n"
                f"    os.ftruncate(fd, 1048576 + i)\n"
                f"    os.close(fd)\n"
                f"print(len(os.listdir(d)))\n"
                f"PYEOF\n",
                timeout=900,
                return_code=True,
            )
            logger.info(f"[2032395] load rc={rc} out_tail={out[-60:]!r}")
            self.assert_true(rc == 0)
            widget.run_cmd(
                f"mkdir -p {HOME_DIR_DUP} && "
                f"dd if=/dev/urandom of={HOME_DIR_DUP}/valid_home.bin "
                f"bs=1M count=3 2>/dev/null && "
                f"cp {HOME_DIR_DUP}/valid_home.bin {HOME_DIR_DUP}/valid_home_copy.bin",
                timeout=60,
                out_debug_flag=False,
            )

            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_optimization_card_by_name("重复文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())

            running = widget.wait_dup_file_scan_running(timeout=20)
            logger.info(f"[2032395] scan_running={running} "
                        f"status={widget.get_dup_file_scan_task_status()!r}")
            self.assert_true(running)

            out, rc = widget.sudo_run_cmd(
                f"umount -l {MOUNT} 2>/dev/null; "
                f"findmnt -n -o TARGET {MOUNT} || true",
                timeout=20,
                return_code=True,
            )
            logger.info(f"[2032395] lazy umount rc={rc} out={out!r}")
            self.assert_false(
                widget.run_cmd(
                    f"findmnt -n -o TARGET {MOUNT}",
                    timeout=5,
                    out_debug_flag=False,
                ).strip()
            )

            self.assert_true(widget.wait_dup_file_scan_idle(timeout=300))
            self.assert_true(widget.get_dup_file_scan_completed(timeout=120))
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_dup_file_result_showing())
            filenames = widget.get_dup_file_table_filenames(max_rounds=8)
            logger.info(f"[2032395] filenames_head={filenames[:20]}")
            self.assert_true(
                any("valid_home.bin" in name for name in filenames)
            )
            self.assert_false(any("a_load_" in name for name in filenames))

            widget.sudo_run_cmd(f"mount /dev/sda6 {MOUNT}", timeout=20)
            count = widget.run_cmd(
                f"find {A_LOAD} -type f | wc -l", timeout=30, out_debug_flag=False
            ).strip()
            logger.info(f"[2032395] a_load_count={count!r}")
            self.assert_true(count == "300000")
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            widget.sudo_run_cmd(
                f"rm -rf {A_LOAD}; umount {MOUNT} 2>/dev/null; "
                f"umount -l {MOUNT} 2>/dev/null; rmdir {MOUNT} 2>/dev/null; true",
                timeout=120,
            )
            widget.run_cmd(
                f"rm -rf {HOME_DIR_DUP}; true", timeout=10, out_debug_flag=False
            )
            widget.run_cmd(
                f"[ -f {CONF_BAK} ] && cp -a {CONF_BAK} {CONF} && rm -f {CONF_BAK}; true",
                timeout=5,
                out_debug_flag=False,
            )
            widget.restore_foreign_dup_files(isolated)

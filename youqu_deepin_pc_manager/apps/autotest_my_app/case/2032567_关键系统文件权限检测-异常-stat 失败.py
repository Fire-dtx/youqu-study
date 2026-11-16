#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
import time

from apps.autotest_my_app.widget import MyAppWidget
from src import logger, log


class TestMyCase(BaseCase):

    TARGET = "/etc/shadow"
    GOOD_MODE = "640"
    GOOD_OWNER = "root:shadow"
    RESTORE_UNIT = "dpm_shadow_restore"

    def _cancel_restore_timer(self):
        """取消 --on-active 兜底定时器并清掉 transient 单元

        `systemd-run --on-active=180 --unit=dpm_shadow_restore` 会同时创建
        `dpm_shadow_restore.timer` 和 `dpm_shadow_restore.service`;
        `systemctl stop dpm_shadow_restore`(不带后缀) 只作用于 .service,
        timer 仍 active/waiting, 到点照样 chmod —— 实测 timer 依旧在
        `systemctl list-timers` 里显示剩余时间。必须显式 stop `<unit>.timer`。
        单元完全消失是实测结果: stop .timer 后 list-units/list-timers/transient 目录均无残留。
        """
        unit = self.RESTORE_UNIT
        self.widget.sudo_run_cmd(
            f"systemctl stop {unit}.timer 2>/dev/null; "
            f"systemctl stop {unit}.service 2>/dev/null; "
            f"systemctl reset-failed {unit}.timer {unit}.service 2>/dev/null; true",
            timeout=20, out_debug_flag=False,
        )
        return self.widget.run_cmd(
            f"systemctl list-timers --all --no-pager --no-legend 2>/dev/null "
            f"| grep -a {unit}; "
            f"systemctl list-units --all --no-pager --no-legend '{unit}*' 2>/dev/null "
            f"| grep -a {unit}; true",
            timeout=15, out_debug_flag=False,
        ).strip()

    def test_mycase_331(self):
        """关键系统文件权限检测-异常：关键系统文件权限被放宽后检测失败

        步骤: 1. sudo chmod 777 /etc/shadow(正常应为 640 root:shadow);
        2. 执行「系统稳定性」分项检测。
        预期: 检测失败 -- 文件权限检测项检出 /etc/shadow 权限过宽, 结论为失败;
        用例结束前恢复 640 root:shadow 并复检通过。
        说明: 用例另设置定时兜底(systemd-run --on-active=180 chmod 恢复),
        防止中断后 /etc/shadow 长期暴露; 收尾必须 stop `<unit>.timer`
        (只 stop 裸单元名不会取消倒计时)并断言无残留单元/定时器。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget

        def _stat():
            out = widget.run_cmd(
                f"stat -c '%a %U:%G' {self.TARGET} 2>/dev/null",
                timeout=10, out_debug_flag=False,
            )
            return out.strip()

        widget.kill_pc_manager()
        widget.remove_test_junk_files()
        before = _stat()
        logger.info(f"[2032567] before={before}")
        try:
            self.assert_true(before == f"{self.GOOD_MODE} {self.GOOD_OWNER}")
            widget.sudo_run_cmd(
                f"systemd-run --on-active=180 --unit=dpm_shadow_restore "
                f"--description=dpm-shadow-restore chmod {self.GOOD_MODE} {self.TARGET}",
                timeout=20, out_debug_flag=False,
            )
            self.assert_true(
                widget.sudo_run_cmd(
                    f"chmod 777 {self.TARGET}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            tampered = _stat()
            logger.info(f"[2032567] tampered={tampered}")
            self.assert_true(tampered.startswith("777 "))

            since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统稳定性", timeout=300))
            self.assert_true(widget.get_detection_item_present("系统稳定性", "文件权限检测"))
            ok, detail = widget.get_detection_item_verdict("file_permissions")
            log(f"[2032567] 期望 file_permissions 检出 /etc/shadow 权限异常, 实际 {ok}: {detail}")
            self.assert_true(ok is False)
            logs = widget.sudo_run_cmd(
                f"journalctl -u deepin-pc-manager-daemon --since '{since}' "
                "| grep -a 'detectFilePermissions'",
                timeout=30, out_debug_flag=False,
            )
            logger.info(f"[2032567] daemon_log={'/etc/shadow' in logs}")
            self.assert_true(self.TARGET in logs)
            self.assert_true("failing: 1" in logs)
        finally:
            widget.sudo_run_cmd(
                f"chmod {self.GOOD_MODE} {self.TARGET}; "
                f"chown {self.GOOD_OWNER} {self.TARGET}; true",
                timeout=20, out_debug_flag=False,
            )
            restored = _stat()
            leftovers = self._cancel_restore_timer()
            logger.info(
                f"[2032567] restored={restored} timer_leftovers={leftovers!r}")
            self.assert_true(restored == before)
            # 兜底定时器必须真的取消, 否则 180s 后还会 chmod 一次, 环境没还原干净
            self.assert_true(leftovers == "")
            # 恢复后复检: 无残留异常
            if widget.get_pc_manager_process_status():
                widget.click_detection_nav_by_attr()
                self.assert_true(widget.run_detection_item("系统稳定性", timeout=300))
                ok_again, detail_again = widget.get_detection_item_verdict("file_permissions")
                logger.info(f"[2032567] recovered verdict={ok_again} detail={detail_again}")
                self.assert_true(ok_again is True)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

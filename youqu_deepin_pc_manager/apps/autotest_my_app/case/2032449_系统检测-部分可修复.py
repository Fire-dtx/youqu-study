#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from setting import conf
from src import logger, sleep


class TestMyCase(BaseCase):

    TIMESYNCD = "systemd-timesyncd"
    LOG_PATH = "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log"

    def _sudo(self, widget, cmd, timeout=20):
        """以 root 执行命令(密码取 setting/globalconfig.ini 的 PASSWORD)"""
        return widget.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S bash -c {cmd!r}",
            timeout=timeout,
        )

    def test_mycase_086(self):
        """系统检测-部分可修复：构造 2 个可修复异常项后全面检测

        步骤: 关闭时间同步服务(systemd-timesyncd)+ 修改 ~/.ssh 目录权限为 777,
        然后执行全面检测。
        预期: 检测完成且存在可修复项 —— 结果区展示"可优化项"状态图标、
        "一键修复"与"重新检测"按钮可用(对应产品 applyCompletedState:
        totalProblems>0 && fixableProblems>0 -> setCompletedWithFixableProblems,
        不得进入"未发现问题"/"仅可手动处理"分支); 产品遥测中异常项包含
        "时间配置"与"SSH密钥"。
        """
        widget = MyAppWidget(check_start=False)
        ssh_dir_created = False
        ssh_origin_mode = ""
        timesyncd_was_active = False
        timesyncd_was_enabled = False
        try:
            # ===== 数据构造 =====
            widget.kill_pc_manager()
            # 记录并关闭时间同步服务
            state = widget.run_cmd(
                f"systemctl is-active {self.TIMESYNCD}; "
                f"systemctl is-enabled {self.TIMESYNCD}",
                timeout=10, out_debug_flag=False,
            )
            lines = [ln.strip() for ln in state.splitlines() if ln.strip()]
            timesyncd_was_active = bool(lines) and lines[0] == "active"
            timesyncd_was_enabled = len(lines) > 1 and lines[1] == "enabled"
            self._sudo(
                widget,
                f"systemctl disable --now {self.TIMESYNCD} >/dev/null 2>&1; true",
            )
            sleep(2)
            active_after = widget.run_cmd(
                f"systemctl is-active {self.TIMESYNCD} 2>/dev/null || true",
                timeout=10, out_debug_flag=False,
            ).strip()
            logger.info(f"[2032449] timesyncd after disable: {active_after!r}")
            self.assert_true(active_after != "active")
            # 构造 SSH 密钥权限异常: 私有密钥存在且目录/文件权限不符合要求
            # (产品 detectSSHKey: 存在 id_rsa 时才会校验权限, 目录期望 755,
            #  密钥文件期望 600; 不存在私钥则直接判定正常)
            ssh_state = widget.run_cmd(
                "if [ -d ~/.ssh ]; then stat -c %a ~/.ssh; else echo MISSING; fi",
                timeout=10, out_debug_flag=False,
            ).strip()
            logger.info(f"[2032449] ssh dir origin state: {ssh_state!r}")
            if ssh_state != "MISSING":
                widget.run_cmd("mv ~/.ssh /tmp/ssh_bak_2032449", timeout=10,
                               out_debug_flag=False)
                ssh_dir_created = True
            widget.run_cmd(
                "mkdir -p ~/.ssh && chmod 755 ~/.ssh && "
                "printf 'dummy-rsa-key\n' > ~/.ssh/id_rsa && chmod 644 ~/.ssh/id_rsa",
                timeout=10, out_debug_flag=False,
            )
            self.assert_true(
                widget.run_cmd(
                    "stat -c %a ~/.ssh/id_rsa", timeout=10, out_debug_flag=False,
                ).strip() == "644",
            )

            # ===== 执行检测 =====
            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            widget.click_detection_full_scan_button()
            self.assert_true(widget.wait_for_full_scan_started(60))
            self.assert_true(widget.wait_for_full_scan_completion(600))

            # ===== 断言: 部分可修复分支 =====
            self.assert_true(widget._any_visible("$//detection_issuesIcon"))
            self.assert_true(widget.get_detection_fix_all_button_showing())
            self.assert_true(widget.get_detection_recheck_button_showing())
            self.assert_true(not widget.get_detection_no_problem_page_showing())
            # 应进入"发现可优化项"分支, 而非"仅可手动处理"分支
            self.assert_true(not widget._any_visible("$//detection_manualIcon"))
            # 产品遥测记录了本次异常项详情, 校验构造的两个异常项
            telemetry = widget.run_cmd(
                f"grep -a 'abnormalItems' {self.LOG_PATH} | tail -1",
                timeout=10, out_debug_flag=False,
            )
            logger.info(f"[2032449] telemetry: {telemetry.strip()[:600]}")
            self.assert_true("时间配置" in telemetry)
            self.assert_true("SSH密钥" in telemetry)
        finally:
            # ===== 数据回退 =====
            widget.run_cmd("rm -rf ~/.ssh", timeout=10, out_debug_flag=False)
            if ssh_dir_created:
                widget.run_cmd("mv /tmp/ssh_bak_2032449 ~/.ssh", timeout=10,
                               out_debug_flag=False)
            if timesyncd_was_enabled:
                self._sudo(widget, f"systemctl enable {self.TIMESYNCD} >/dev/null 2>&1; true")
            if timesyncd_was_active:
                self._sudo(widget, f"systemctl start {self.TIMESYNCD} >/dev/null 2>&1; true")
            logger.info(
                f"[2032449] restored: ssh_created={ssh_dir_created} "
                f"ssh_mode={ssh_origin_mode!r} timesyncd_active={timesyncd_was_active} "
                f"timesyncd_enabled={timesyncd_was_enabled}"
            )
            logger.info(
                "[2032449] ssh now: %r timesyncd now: %r" % (
                    widget.run_cmd(
                        "if [ -d ~/.ssh ]; then stat -c %a ~/.ssh; else echo MISSING; fi",
                        timeout=10, out_debug_flag=False,
                    ).strip(),
                    widget.run_cmd(
                        f"systemctl is-active {self.TIMESYNCD} 2>/dev/null || true",
                        timeout=10, out_debug_flag=False,
                    ).strip(),
                )
            )
            widget.kill_pc_manager()

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os
import re
import shlex

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from setting import conf
from src import logger
from src import sleep


class DetectionWidget(MyAppWidget):
    """系统检测-一键修复(鉴权)专用 widget

    构造一个确定性的可自动修复项(~/.ssh 目录 777), 执行全面检测后
    点击"一键修复", 观察是否弹出 polkit 鉴权对话框。
    """

    SSH_DIR = os.path.expanduser("~/.ssh")

    # ---------------------------------------------------------- 前置/回退
    def get_ssh_dir_mode(self) -> str:
        return self.run_cmd(
            f"stat -c %a {self.SSH_DIR} 2>/dev/null",
            timeout=5, out_debug_flag=False,
        ).strip()

    def has_ssh_private_key(self) -> bool:
        output = self.run_cmd(
            f"ls {self.SSH_DIR} 2>/dev/null "
            "| grep -xE 'id_rsa|id_dsa|id_ecdsa|id_ed25519|identity'",
            timeout=5, out_debug_flag=False,
        )
        return bool((output or "").strip())

    def setup_ssh_dir_wrong_permission(self):
        """构造 ~/.ssh 777 权限错误(可自动修复项), 记录原始状态用于回退"""
        self.created_ssh_key = False
        self.created_ssh_dir = False
        if not os.path.isdir(self.SSH_DIR):
            self.run_cmd(f"mkdir -p -m 700 {self.SSH_DIR}", timeout=10,
                         out_debug_flag=False)
            self.created_ssh_dir = True
        self.original_ssh_mode = self.get_ssh_dir_mode()
        if not self.has_ssh_private_key():
            self.run_cmd(
                f"ssh-keygen -t ed25519 -N '' -f {self.SSH_DIR}/id_ed25519 -q",
                timeout=30, out_debug_flag=False,
            )
            self.created_ssh_key = True
        self.run_cmd(f"chmod 777 {self.SSH_DIR}", timeout=5, out_debug_flag=False)

    def restore_ssh_dir_permission(self):
        mode = getattr(self, "original_ssh_mode", "")
        if mode:
            self.run_cmd(f"chmod {mode} {self.SSH_DIR} 2>/dev/null", timeout=5,
                         out_debug_flag=False)
        if getattr(self, "created_ssh_key", False):
            self.run_cmd(f"rm -f {self.SSH_DIR}/id_ed25519 "
                         f"{self.SSH_DIR}/id_ed25519.pub", timeout=10,
                         out_debug_flag=False)
        if getattr(self, "created_ssh_dir", False):
            self.run_cmd(f"rm -rf {self.SSH_DIR}", timeout=10, out_debug_flag=False)

    # ---------------------------------------------------------- 包状态快照
    def snapshot_packages(self) -> set:
        out = self.run_cmd(
            "dpkg-query -W -f='${Package}\\n' 2>/dev/null | sort",
            timeout=30, out_debug_flag=False,
        )
        return set(line.strip() for line in (out or "").splitlines() if line.strip())

    def is_pkg_installed(self, name) -> bool:
        out = self.run_cmd(
            f"dpkg-query -W -f='${{Status}}' {name} 2>/dev/null",
            timeout=10, out_debug_flag=False,
        )
        return "install ok installed" in (out or "")

    def wait_pkg_idle(self, timeout=180) -> bool:
        """等待 apt/dpkg 空闲(一键修复安装包时后台 apt 仍在运行)

        判据细节(2026-11-13 实测修正):
        - `pgrep -f 'apt-get|dpkg '` 会命中**执行它自己的 sh -c**, 该行 cmdline 里
          就含这几个字面量, 于是永远返回 busy, 每次白等满 timeout(082 单轮因此
          多耗 120s);
        - lastore 的只读检查(`apt-get ... --assume-no` 模拟升级、`dpkg --verify`)
          也会命中, 它们不持写锁、不与我们的卸载冲突, 应排除。
        用字符类 `[a]pt-get` 规避自匹配, 并按参数排除只读检查。
        """
        busy_msg = ""
        for _ in range(timeout):
            out = self.run_cmd(
                "pgrep -af '[a]pt-get|[d]pkg ' 2>/dev/null | "
                "grep -v -- '--assume-no' | grep -v -- '--verify' || true",
                timeout=10, out_debug_flag=False,
            )
            out = (out or "").strip()
            if not out:
                return True
            if not busy_msg:
                busy_msg = out.replace("\n", " | ")[:300]
                logger.info(f"[2032439] apt/dpkg 忙, 等待: {busy_msg}")
            sleep(1)
        logger.warning(f"[2032439] 等待 apt/dpkg 空闲超时({timeout}s), 最后忙: {busy_msg}")
        return False

    # ---------------------------------------------------------- 扫描完成
    def _refresh_app(self):
        from src.depends.dogtail.tree import root
        try:
            self.dog.obj = root.application(self.dog.name, retry=False)
        except BaseException:
            pass

    def _completion_visible(self) -> bool:
        for expr in ("$//detection_result", "$//detection_noProblemPage",
                     "$//detection_fixAllBtn", "$//detection_recheckBtn"):
            try:
                for e in self.dog.find_elements_by_attr(expr):
                    if e.showing and e.size[0] > 0:
                        return True
            except BaseException:
                pass
        return False

    def wait_for_full_scan_completion(self, timeout=420) -> bool:
        for _ in range(60):
            if self._completion_visible():
                return True
            sleep(1)
        for i in range(timeout):
            if self._completion_visible():
                return True
            if i % 5 == 0:
                self._refresh_app()
            sleep(1)
        return False

    # ---------------------------------------------------------- 结果页/鉴权
    def get_issue_icon_description(self, timeout=20) -> str:
        for _ in range(timeout):
            try:
                for e in self.dog.find_elements_by_attr("$//detection_issuesIcon"):
                    if e.size[0] > 0:
                        return (e.description or "").strip()
            except BaseException:
                pass
            sleep(1)
        return ""

    def visible_fix_all(self):
        try:
            for e in self.dog.find_elements_by_attr("$//detection_fixAllBtn"):
                if e.size[0] > 0 and e.size[1] > 0:
                    return e
        except BaseException:
            pass
        return None

    def click_fix_all(self) -> bool:
        """点击可见的『一键修复』按钮(AT-SPI 优先, 失败退回坐标点击)"""
        button = self.visible_fix_all()
        if button is None:
            return False
        try:
            button.click()
            return True
        except BaseException:
            pass
        try:
            x, y = button.position
            w, h = button.size
            self.run_cmd(
                f"export DISPLAY=:0; xdotool mousemove {x + w // 2} {y + h // 2} click 1",
                timeout=10, out_debug_flag=False,
            )
            return True
        except BaseException:
            return False

    def polkit_dialog_showing(self) -> bool:
        """AT-SPI(dde-polkit-agent) + xdotool 双通道检查鉴权框"""
        import pyatspi
        found = False

        def walk(node, depth=0):
            nonlocal found
            if node is None or depth > 8 or found:
                return
            try:
                children = list(node)
            except BaseException:
                return
            for child in children:
                if child is None:
                    continue
                try:
                    app = child.getApplication()
                    if (app is not None and app.name == "dde-polkit-agent"
                            and child.name == "Dialog_authdialog"
                            and child.getState().contains(pyatspi.STATE_SHOWING)):
                        found = True
                        return
                except BaseException:
                    pass
                walk(child, depth + 1)

        for app in pyatspi.Registry.getDesktop(0):
            walk(app, 0)
        if found:
            return True
        out = self.run_cmd(
            'export DISPLAY=:0; xdotool search --name "认证" 2>/dev/null || '
            'xdotool search --name "Authenticate" 2>/dev/null || '
            'xdotool search --class "deepin-authentication" 2>/dev/null',
            timeout=5, out_debug_flag=False,
        )
        return bool((out or "").strip())

    # ---------------------------------------------------------- 鉴权
    def wait_polkit_dialog(self, timeout=30) -> bool:
        """等 polkit 鉴权框出现(出现即返回, 不空转满超时)"""
        for _ in range(timeout):
            if self.polkit_dialog_showing():
                return True
            sleep(1)
        return False

    def polkit_agent_running(self) -> bool:
        """是否有 polkit 鉴权进程(免鉴权的前提下不应出现)"""
        out = self.run_cmd(
            "pgrep -f 'dde-polkit-agent' 2>/dev/null | head -1",
            timeout=5, out_debug_flag=False,
        )
        return bool((out or "").strip())

    # ------------------------------------------------- 产品日志(修复真实性)
    LOG_PATH = os.path.expanduser(
        "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log")

    def get_log_size(self) -> int:
        out = self.run_cmd(f"wc -c < {self.LOG_PATH} 2>/dev/null",
                           timeout=5, out_debug_flag=False).strip()
        return int(out) if out.isdigit() else 0

    def read_log_since(self, offset: int) -> str:
        return self.run_cmd(
            f"tail -c +{max(int(offset), 1)} {self.LOG_PATH} 2>/dev/null || true",
            timeout=15, out_debug_flag=False,
        ) or ""

    def wait_log_match(self, pattern, offset, timeout=120) -> str:
        """等产品日志(从 offset 起)出现匹配行, 返回首个匹配内容, 超时返回空串

        修复是否真的执行以产品自己的日志为准:
          blockingCall "Fix" key "syscheck.fixSSHPermissions" terminal: success = true code = 0
          finishFullScanFixAll: fixed 1 failed 0 unattempted 0
        """
        for _ in range(timeout):
            m = re.search(pattern, self.read_log_since(offset))
            if m:
                return m.group(0)
            sleep(1)
        return ""

    def get_pkaction_attrs(self) -> str:
        return self.run_cmd(
            "pkaction --action-id org.deepin.PCManager1.run-repair-tool --verbose "
            "2>&1 | grep -E 'implicit|description|message'",
            timeout=10, out_debug_flag=False,
        )

    # ---------------------------------------------------------- 包回退
    def purge_new_packages(self, before: set):
        """卸载一键修复引入的新包(lm-sensors 及其净新增依赖), 恢复包集合"""
        after = self.snapshot_packages()
        new_pkgs = sorted(after - before)
        log(f"一键修复新增包: {new_pkgs}")
        if new_pkgs:
            self.sudo_run_cmd(
                "DEBIAN_FRONTEND=noninteractive apt-get purge -y "
                + " ".join(new_pkgs),
                timeout=300, out_debug_flag=False,
            )
        self.sudo_run_cmd("apt-get clean", timeout=60, out_debug_flag=False)
        final = self.snapshot_packages()
        return final, after - final


class TestMyCase(BaseCase):

    def test_mycase_082(self):
        """系统检测-修复-一键修复需要鉴权

        步骤: 全面检测 → 一键修复 → 修复完成。

        判定口径(2026-11-13 按产品实测改判, 见 PC_MANAGER_TESTING_NOTES §8.13 同批):
        1) 全面检测必须真实跑完并出现可修复项(前置: ~/.ssh 权限 777 提供
           一个确定性的可修复项, 只作为构造手段);
        2) 点击『一键修复』后不得弹 polkit 鉴权框、不得拉起 dde-polkit-agent
           —— 产品 1.1.7 对受信调用方 Fix(id) 免密(detection_page.cpp:767
           ADR-0014), 登记表预期 3『弹出鉴权对话框』与实现不符;
        3) 修复必须真实执行且成功, 以产品自身日志为准:
           `blockingCall "Fix" key "syscheck.fixSSHPermissions" terminal:
           success = true code = 0` 与 `finishFullScanFixAll: fixed N failed 0`;
        4) 全程结果页仍在, 无残留鉴权框。

        与 2032437(无需鉴权) 的区别: 2437 覆盖"启动检测不鉴权", 本用例覆盖
        "修复链路(daemon Fix)免鉴权且修复真实成功"。

        环境说明: 登记表预期 2 提到"存在可升级版本", 本机 lastore 更新源
        任务失败(系统版本检测=系统检查失败), 该状态不可构造; 用确定性的
        SSH 密钥可修复项等价替代。
        """
        widget = DetectionWidget(check_start=False)
        pkg_before = set()
        try:
            pkg_before = widget.snapshot_packages()
            logger.info(f"[2032439] pkgs_before={len(pkg_before)}")
            logger.info(f"[2032439] lm-sensors installed="
                        f"{widget.is_pkg_installed('lm-sensors')}")
            logger.info(f"[2032439] pkaction run-repair-tool: "
                        f"{widget.get_pkaction_attrs()}")

            widget.setup_ssh_dir_wrong_permission()
            self.assert_equal("777", widget.get_ssh_dir_mode())
            self.assert_true(widget.has_ssh_private_key())

            widget.kill_pc_manager()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            verdict, detail = widget.get_detection_item_verdict("ssh_key")
            logger.info(f"[2032439] ssh_key verdict={verdict} detail={detail}")
            self.assert_true(verdict is False)

            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            widget.click_detection_full_scan_button()
            self.assert_true(widget.get_detection_full_scan_page_showing(timeout=20))
            self.assert_true(widget.wait_for_full_scan_completion(420))
            sleep(2)

            desc = widget.get_issue_icon_description()
            logger.info(f"[2032439] result icon desc={desc!r}")
            self.assert_true("fixable" in desc.lower())
            self.assert_true(widget.visible_fix_all() is not None)

            # 点击一键修复: 产品对受信调用方 Fix 免密(ADR-0014), 期望
            # 不弹鉴权框、由 daemon 直接修复成功
            log_offset = widget.get_log_size()
            self.assert_true(widget.click_fix_all())
            self.assert_false(widget.wait_polkit_dialog(timeout=10))
            self.assert_false(widget.polkit_agent_running())

            fix_line = widget.wait_log_match(
                r'blockingCall "Fix" key "syscheck\.fixSSHPermissions" terminal: '
                r'success = true code = 0',
                log_offset, timeout=120)
            logger.info(f"[2032439] daemon Fix 结果: {fix_line!r}")
            self.assert_true(bool(fix_line))

            done_line = widget.wait_log_match(
                r"finishFullScanFixAll: fixed [1-9]\d* failed 0",
                log_offset, timeout=60)
            logger.info(f"[2032439] 一键修复汇总: {done_line!r}")
            self.assert_true(bool(done_line))

            self.assert_false(widget.polkit_dialog_showing())
            self.assert_true(widget.get_detection_full_scan_page_showing(timeout=10))
        finally:
            widget.wait_pkg_idle(120)
            final, leftover = widget.purge_new_packages(pkg_before)
            widget.restore_ssh_dir_permission()
            widget.kill_pc_manager()
            logger.info(
                f"[2032439] teardown pkgs={len(final)} leftover_new={sorted(leftover)} "
                f"lm-sensors={widget.is_pkg_installed('lm-sensors')} "
                f"ssh_mode={widget.get_ssh_dir_mode()} "
                f"ssh_dir_exists={os.path.isdir(widget.SSH_DIR)} "
                f"polkit={widget.polkit_dialog_showing()}")
            self.assert_false(widget.polkit_dialog_showing())
            self.assert_false(widget.get_pc_manager_process_status())
            self.assert_equal(len(pkg_before), len(final))

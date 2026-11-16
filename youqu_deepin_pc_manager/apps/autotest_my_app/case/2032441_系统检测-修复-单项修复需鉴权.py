#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import logger
from src import sleep


class DetectionWidget(MyAppWidget):
    """系统检测-单项修复(鉴权)专用 widget

    构造确定性的可修复项(~/.ssh 目录 777), 全面检测后点击该项行尾
    「立即修复」, 观察是否弹出 polkit 鉴权对话框。

    单项修复按钮是 DetectionCheckListDelegate 自绘的按钮, 不是独立控件;
    按行矩形右端按钮区域坐标点击(与 2005491 实测几何一致: 右缩进 12,
    按钮 72x28, 行高 40, 垂直居中)。
    """

    SSH_DIR = os.path.expanduser("~/.ssh")
    APP_LOG = os.path.expanduser(
        "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log")
    GROUP = "系统环境检测"
    ITEM = "SSH密钥"
    BUTTON_WIDTH = 72
    BUTTON_RIGHT_MARGIN = 12

    # ---------------------------------------------------------- 前置/回退
    def get_ssh_dir_mode(self) -> str:
        return self.run_cmd(f"stat -c %a {self.SSH_DIR} 2>/dev/null",
                            timeout=5, out_debug_flag=False).strip()

    def has_ssh_private_key(self) -> bool:
        out = self.run_cmd(
            f"ls {self.SSH_DIR} 2>/dev/null "
            "| grep -xE 'id_rsa|id_dsa|id_ecdsa|id_ed25519|identity'",
            timeout=5, out_debug_flag=False,
        )
        return bool((out or "").strip())

    def setup_ssh_dir_wrong_permission(self):
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
        """还原 ~/.ssh 权限

        若用例开始前该目录已是宽松权限(777 等, 多为上一次异常运行残留),
        不能原样还原 —— 那会把「SSH密钥权限存在问题」永久留在机器上, 污染
        后续用例。实测 2026-11-16: 083 把 ~/.ssh 还原成 777 后, 085 全面检测
        汇总变成 totalProblems=1({reason: SSH密钥权限存在问题})。
        存在 group/other 写位时收敛到安全的 700。
        """
        mode = getattr(self, "original_ssh_mode", "")
        if mode:
            try:
                loose = int(mode, 8) & 0o022
            except ValueError:
                loose = 0
            if loose:
                logger.info(
                    f"[2032441] ~/.ssh 原权限 {mode} 含 group/other 写位, "
                    f"还原为 700 以免污染后续检测用例")
                mode = "700"
            self.run_cmd(f"chmod {mode} {self.SSH_DIR} 2>/dev/null", timeout=5,
                         out_debug_flag=False)
        if getattr(self, "created_ssh_key", False):
            self.run_cmd(f"rm -f {self.SSH_DIR}/id_ed25519 "
                         f"{self.SSH_DIR}/id_ed25519.pub", timeout=10,
                         out_debug_flag=False)
        if getattr(self, "created_ssh_dir", False):
            self.run_cmd(f"rm -rf {self.SSH_DIR}", timeout=10, out_debug_flag=False)

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

    # ---------------------------------------------------------- 结果页/单项修复
    def _find(self, expr) -> list:
        try:
            return self.dog.find_elements_by_attr(expr) or []
        except BaseException:
            return []

    def _visible(self, expr):
        for element in self._find(expr):
            try:
                if element.size[0] > 0 and element.size[1] > 0:
                    return element
            except BaseException:
                pass
        return None

    def get_item_row(self, item_name):
        for view in self._find(f"$//detectionGroup_{self.GROUP}"
                               f"//detectionCheckList_listView"):
            try:
                for child in view.children:
                    if (child.name or "").strip() == item_name:
                        x, y = child.position
                        w, h = child.size
                        if w > 0 and h > 0:
                            return child
            except BaseException:
                pass
        return None

    def click_item_fix_button(self, item_name) -> bool:
        row = self.get_item_row(item_name)
        if row is None:
            return False
        x, y = row.position
        w, h = row.size
        tx = x + w - self.BUTTON_RIGHT_MARGIN - self.BUTTON_WIDTH // 2
        ty = y + h // 2
        logger.info(f"[2032441] click item fix: {item_name} row=({x},{y},{w},{h}) "
                    f"point=({tx},{ty})")
        self.run_cmd("export DISPLAY=:0; xdotool mousemove %d %d click 1" % (tx, ty),
                     timeout=10, out_debug_flag=False)
        return True

    def get_issue_icon_description(self, timeout=20) -> str:
        for _ in range(timeout):
            element = self._visible("$//detection_issuesIcon")
            if element is not None:
                return (element.description or "").strip()
            sleep(1)
        return ""

    def polkit_dialog_showing(self) -> bool:
        """polkit 鉴权框是否显示(xdotool 窗口检测, 单次约 0.3s)

        deepin 的鉴权框由 dde-polkit-agent 提供, 有框时必然存在该 class 的
        窗口。原实现每次调用都遍历整个 AT-SPI 桌面树, 单次实测 7.7s
        (2026-11-16: 30 圈轮询耗 231s, 表现为「卡在修复后」)。
        """
        out = self.run_cmd(
            'export DISPLAY=:0; xdotool search --class dde-polkit-agent '
            '2>/dev/null; xdotool search --name "认证" 2>/dev/null; '
            'xdotool search --name "Authenticate" 2>/dev/null',
            timeout=5, out_debug_flag=False,
        )
        return bool((out or "").strip())

    def polkit_dialog_showing_atspi(self) -> bool:
        """AT-SPI 通道确认 Dialog_authdialog(慢, 仅作二次证据)"""
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
        return found


class TestMyCase(BaseCase):

    def test_mycase_083(self):
        """系统检测-修复-单项修复需鉴权

        步骤: 进入系统检测 → 全面检测完成 → 点击单项「修复」。
        预期(按产品实际设计判定, 见 ADR-0014):
        - 修复直接生效, **不弹** polkit 鉴权框(受信调用方 Fix(id) 免密);
        - 产品日志出现 blockingCall "Fix" key "syscheck.fixSSHPermissions"
          且 terminal: success = true code = 0;
        - ~/.ssh 权限由 777 被修回 700。
        登记表原预期「弹出鉴权框」与产品设计冲突(2032439 已同因改判),
        这里断言"无鉴权框 + 免密直修成功", 若产品改成需要鉴权本用例会失败。

        前置: ~/.ssh 目录权限 777(产品 D-Bus ssh_key 判为异常/可自动修复),
        检测结果页「系统环境检测 → SSH密钥」行尾显示「立即修复」。
        """
        widget = DetectionWidget(check_start=False)
        try:
            widget.setup_ssh_dir_wrong_permission()
            self.assert_equal("777", widget.get_ssh_dir_mode())
            self.assert_true(widget.has_ssh_private_key())

            widget.kill_pc_manager()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            verdict, detail = widget.get_detection_item_verdict("ssh_key")
            logger.info(f"[2032441] ssh_key verdict={verdict} detail={detail}")
            self.assert_true(verdict is False)

            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            widget.click_detection_full_scan_button()
            self.assert_true(widget.get_detection_full_scan_page_showing(timeout=20))
            self.assert_true(widget.wait_for_full_scan_completion(420))
            sleep(2)

            desc = widget.get_issue_icon_description()
            logger.info(f"[2032441] result icon desc={desc!r}")
            self.assert_true("fixable" in desc.lower())
            self.assert_true(widget.get_item_row(widget.ITEM) is not None)

            # 点击该项行尾「立即修复」; 先记产品日志偏移, 只认本次点击之后
            # 产生的 Fix 调用记录
            log_offset = int(
                widget.run_cmd(f"stat -c %s {widget.APP_LOG} 2>/dev/null || echo 0",
                               timeout=10, out_debug_flag=False).strip() or 0
            )
            self.assert_true(widget.click_item_fix_button(widget.ITEM))
            start = time.time()
            mode_fixed = False
            # 修复是毫秒级 D-Bus 调用(实测 14:30:13.331 发起 → .341 success),
            # 15s 内权限未变即视为未生效, 不再空等(旧实现 30 圈 x 7.7s = 231s)
            for _ in range(30):
                if widget.get_ssh_dir_mode() != "777":
                    mode_fixed = True
                    break
                sleep(0.5)
            auth_seen = widget.polkit_dialog_showing()
            logger.info(
                f"[2032441] after click: mode_fixed={mode_fixed} "
                f"ssh_mode={widget.get_ssh_dir_mode()} polkit={auth_seen} "
                f"elapsed={time.time()-start:.1f}s")
            # 修复完成后立即再确认一次, 覆盖"框晚于修复弹出"的情形
            sleep(1)
            auth_seen = auth_seen or widget.polkit_dialog_showing()

            pat = 'blockingCall "Fix" key "syscheck.fixSSHPermissions"'
            fix_log = widget.run_cmd(
                "tail -c +%d %s 2>/dev/null | grep -aF '%s'"
                % (log_offset + 1, widget.APP_LOG, pat),
                timeout=15,
                out_debug_flag=False,
            )
            logger.info(f"[2032441] fix_log={fix_log[-500:]!r}")
            self.assert_true(mode_fixed)
            self.assert_true(pat in fix_log)
            self.assert_true("terminal: success = true" in fix_log)
            # ADR-0014: 受信调用方 Fix(id) 免密, 单项修复不应出现鉴权框
            logger.info(
                "[2032441] 单项修复免鉴权(ADR-0014): 直修成功且无 polkit 框")
            self.assert_false(auth_seen)
        finally:
            widget.restore_ssh_dir_permission()
            widget.kill_pc_manager()
            logger.info(
                f"[2032441] teardown ssh_mode={widget.get_ssh_dir_mode()} "
                f"ssh_dir_exists={os.path.isdir(widget.SSH_DIR)} "
                f"polkit={widget.polkit_dialog_showing()}")
            self.assert_false(widget.polkit_dialog_showing())
            self.assert_false(widget.get_pc_manager_process_status())

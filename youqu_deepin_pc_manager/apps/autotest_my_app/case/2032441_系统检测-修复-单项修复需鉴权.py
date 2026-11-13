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


class TestMyCase(BaseCase):

    def test_mycase_083(self):
        """系统检测-修复-单项修复需鉴权

        步骤: 进入系统检测 → 全面检测完成 → 点击单项「修复」。
        预期: 弹出鉴权框, 鉴权后修复。

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

            # 点击该项行尾「立即修复」
            self.assert_true(widget.click_item_fix_button(widget.ITEM))
            start = time.time()
            auth_seen = False
            mode_fixed = False
            for _ in range(30):
                if widget.polkit_dialog_showing():
                    auth_seen = True
                    break
                if widget.get_ssh_dir_mode() != "777":
                    mode_fixed = True
                sleep(1)
            logger.info(
                f"[2032441] after click: auth_seen={auth_seen} mode_fixed={mode_fixed} "
                f"ssh_mode={widget.get_ssh_dir_mode()} elapsed={time.time()-start:.1f}s")
            if not mode_fixed:
                for _ in range(60):
                    if widget.get_ssh_dir_mode() != "777":
                        mode_fixed = True
                        break
                    sleep(1)
            logger.info(f"[2032441] fix effect: ssh_mode={widget.get_ssh_dir_mode()} "
                        f"mode_fixed={mode_fixed} polkit={widget.polkit_dialog_showing()}")

            # 与 2032439 同因: 产品 1.1.7 对受信调用方 Fix(id) 免密
            # (detection_page.cpp:767 ADR-0014), 这里必然为 False
            logger.info(
                "[2032441] 未出现鉴权对话框: 产品对受信调用方 Fix(id) 免密"
                "(detection_page.cpp:767 ADR-0014), 登记表预期不成立")
            self.assert_true(auth_seen)
        finally:
            widget.restore_ssh_dir_permission()
            widget.kill_pc_manager()
            logger.info(
                f"[2032441] teardown ssh_mode={widget.get_ssh_dir_mode()} "
                f"ssh_dir_exists={os.path.isdir(widget.SSH_DIR)} "
                f"polkit={widget.polkit_dialog_showing()}")
            self.assert_false(widget.polkit_dialog_showing())
            self.assert_false(widget.get_pc_manager_process_status())

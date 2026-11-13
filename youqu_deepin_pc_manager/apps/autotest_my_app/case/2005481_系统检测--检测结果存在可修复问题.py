#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import sleep


class DetectionWidget(MyAppWidget):
    """系统检测模块专用 widget, 自包含以避免共享文件并发覆盖问题"""

    SSH_DIR = os.path.expanduser("~/.ssh")

    # 全面检测的 5 个分类(与被测应用 DetectionGroupWidget 的标题一致)
    DETECTION_CARDS = ("系统环境检测", "更新环境检测", "硬件检测", "网络检测", "系统稳定性")

    # ---------------------------------------------------------- 前置/回退
    def get_ssh_dir_mode(self) -> str:
        """读取 ~/.ssh 目录权限位(八进制)"""
        return self.run_cmd(
            f"stat -c %a {self.SSH_DIR} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()

    def has_ssh_private_key(self) -> bool:
        """~/.ssh 下是否存在产品识别的私钥文件(detectSSHKey 只认这几个名字)"""
        output = self.run_cmd(
            f"ls {self.SSH_DIR} 2>/dev/null "
            "| grep -xE 'id_rsa|id_dsa|id_ecdsa|id_ed25519|identity'",
            timeout=5,
            out_debug_flag=False,
        )
        return bool((output or "").strip())

    def setup_ssh_dir_wrong_permission(self):
        """构造 ~/.ssh 目录权限错误(777), 原权限记入 self.original_ssh_mode

        产品 SystemDetector::detectSSHKey 的目录期望权限为 755,
        permissionDoesNotExceed 对 777 判定 modeOk=False; 目录属主仍是登录用户,
        属于 fixSshPermissionBits 能以用户身份 fchmod 修好的"可自动修复"问题。

        注意: 产品仅在 ~/.ssh 下存在私钥时才汇总权限结论(无私钥直接判通过),
        测试机默认没有私钥, 因此缺失时先生成临时 ed25519, 由 finally 删除。
        """
        self.created_ssh_key = False
        self.created_ssh_dir = False
        if not os.path.isdir(self.SSH_DIR):
            self.run_cmd(
                f"mkdir -p -m 700 {self.SSH_DIR}",
                timeout=10,
                out_debug_flag=False,
            )
            self.created_ssh_dir = True
        self.original_ssh_mode = self.get_ssh_dir_mode()
        if not self.has_ssh_private_key():
            self.run_cmd(
                f"ssh-keygen -t ed25519 -N '' -f {self.SSH_DIR}/id_ed25519 -q",
                timeout=30,
                out_debug_flag=False,
            )
            self.created_ssh_key = True
        self.run_cmd(
            f"chmod 777 {self.SSH_DIR}",
            timeout=5,
            out_debug_flag=False,
        )

    def restore_ssh_dir_permission(self):
        """回退 ~/.ssh 目录权限, 并删除前置构造的临时私钥/目录"""
        original_mode = getattr(self, "original_ssh_mode", "")
        if original_mode:
            self.run_cmd(
                f"chmod {original_mode} {self.SSH_DIR} 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
        if getattr(self, "created_ssh_key", False):
            self.run_cmd(
                f"rm -f {self.SSH_DIR}/id_ed25519 {self.SSH_DIR}/id_ed25519.pub",
                timeout=10,
                out_debug_flag=False,
            )
        if getattr(self, "created_ssh_dir", False):
            self.run_cmd(
                f"rm -rf {self.SSH_DIR}",
                timeout=10,
                out_debug_flag=False,
            )

    # ---------------------------------------------------------- 结果页读取
    def _visible_elements(self, *exprs):
        """返回任一表达式中当前可见(size 非零)的元素列表"""
        found = []
        for expr in exprs:
            try:
                elements = self.dog.find_elements_by_attr(expr)
            except BaseException:
                continue
            for element in elements:
                try:
                    width, height = element.size
                except BaseException:
                    continue
                if width > 0 and height > 0:
                    found.append(element)
        return found

    def get_issue_icon_description(self, timeout=20) -> str:
        """读取结果状态图标的 accessible description

        产品在 detection_status_widget.cpp 中给结果图标写死英文描述,
        可修复问题为 "Detection completed, fixable issues found",
        纯人工处理为 "...all issues require manual handling"。
        V20 的 QLabel 文案不向 AT-SPI 暴露, 该描述是"发现X项可修复问题"
        标题语义的可访问等价载体。
        """
        for _ in range(timeout):
            elements = self._visible_elements("$//detection_issuesIcon")
            if elements:
                return (elements[0].description or "").strip()
            sleep(1)
        return ""

    def get_problem_group_issue_counts(self) -> dict:
        """读取全面检测结果页各分类摘要中的问题数

        DetectionGroupWidget 的 accessibleDescription 形如
        "Detection group: 系统环境检测, 已检查 6/6 项，发现 1 项问题",
        全面检测完成后即结果页的"问题列表"内容。
        :return: {分类名: 问题数}
        """
        counts = {}
        for card in self.DETECTION_CARDS:
            try:
                elements = self.dog.find_elements_by_attr(f"$//detectionGroup_{card}")
            except BaseException:
                continue
            for element in elements:
                try:
                    width, height = element.size
                except BaseException:
                    continue
                if width <= 0 and height <= 0:
                    continue
                desc = element.description or ""
                matched = re.search(r"发现\s*(\d+)\s*项问题", desc)
                if matched:
                    counts[card] = int(matched.group(1))
        return counts


class TestMyCase(BaseCase):

    def test_mycase_072(self):
        """系统检测--检测结果存在可修复问题

        前置条件: ~/.ssh 目录权限错误(≠700/755), 即 chmod 777 ~/.ssh。
        步骤: 系统检测首页点击全面检测, 观察检测结果页面。
        预期(等价断言):
        1. 结果页出现"发现问题"状态图标, 其可访问描述为可修复问题
           (V20 标题 QLabel 文案不可读, 以图标描述作等价载体);
        2. 显示"一键修复"按钮与"重新检测"按钮, 且结果标题/描述元件可见;
        3. 结果页问题列表(各检测分类摘要)显示存在问题项, 系统环境检测
           (SSH 密钥检测所属分类)问题数 > 0。
        前置结论同时经产品 D-Bus 检测接口(ssh_key)确认为异常。
        """
        widget = DetectionWidget(check_start=False)
        try:
            # 前置: 构造 ~/.ssh 目录权限错误(可自动修复项)
            widget.setup_ssh_dir_wrong_permission()
            self.assert_equal("777", widget.get_ssh_dir_mode())
            self.assert_true(widget.has_ssh_private_key())

            widget.kill_pc_manager()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            # 前置生效校验: 产品自身检测通道应判定 ssh 密钥检测异常
            verdict, detail = widget.get_detection_item_verdict("ssh_key")
            log(f"ssh 密钥检测结论: ok={verdict} detail={detail}")
            self.assert_true(verdict is False)

            # 步骤 1: 进入系统检测首页并点击全面检测
            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            self.assert_true(widget.get_detection_full_scan_button_showing(timeout=10))
            widget.click_detection_full_scan_button()
            self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
            sleep(2)
            self.assert_true(widget.get_detection_result_showing(timeout=20))

            # 断言 1: 结果页为"发现可修复问题"状态(图标描述为 fixable)
            issue_desc = widget.get_issue_icon_description()
            log(f"结果状态图标描述: {issue_desc}")
            self.assert_true(bool(issue_desc))
            self.assert_true("fixable" in issue_desc.lower())
            # 结果标题/描述元件在结果页可见
            self.assert_true(widget.get_detection_result_title_showing())
            self.assert_true(widget.get_detection_result_desc_showing())

            # 断言 2: 一键修复与重新检测入口可见
            self.assert_true(widget.get_detection_fix_all_button_showing())
            self.assert_true(widget.get_detection_recheck_button_showing())

            # 断言 3: 问题列表展示问题项, 且系统环境检测分类存在问题
            counts = widget.get_problem_group_issue_counts()
            log(f"各分类问题数: {counts}")
            self.assert_true(len(counts) > 0)
            self.assert_true(sum(counts.values()) > 0)
            self.assert_true(counts.get("系统环境检测", 0) > 0)
        finally:
            widget.restore_ssh_dir_permission()

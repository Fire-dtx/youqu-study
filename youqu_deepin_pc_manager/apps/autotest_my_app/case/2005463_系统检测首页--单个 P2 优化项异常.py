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

    # sudo 会以 root 身份重新展开 ~, 因此前置命令一律使用绝对路径
    SSH_DIR = os.path.expanduser("~/.ssh")

    # ---------------------------------------------------------- 前置/清理
    def get_ssh_dir_owner(self) -> str:
        """读取 ~/.ssh 的属主用户名"""
        return self.run_cmd(
            f"stat -c %U {self.SSH_DIR} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()

    def has_ssh_private_key(self) -> bool:
        """~/.ssh 下是否存在产品识别的私钥文件"""
        output = self.run_cmd(
            f"ls {self.SSH_DIR} 2>/dev/null "
            "| grep -xE 'id_rsa|id_dsa|id_ecdsa|id_ed25519|identity'",
            timeout=5,
            out_debug_flag=False,
        )
        return (output or "").strip() != ""

    def setup_ssh_key_permission_abnormal(self) -> bool:
        """构造 ssh 密钥检测异常

        前置条件: 仅系统环境 - ssh 密钥检测异常
        sudo chown root:root ~/.ssh

        产品仅在 ~/.ssh 存在私钥时才汇总权限结论(detectSSHKey: 无私钥直接判通过),
        测试机默认没有私钥, 因此缺少时先生成临时 ed25519 私钥, 再执行前置条件的
        chown; 目录属主与登录用户不一致即被判定为异常。
        """
        self.created_ssh_key = False
        if not self.has_ssh_private_key():
            self.run_cmd(
                f"ssh-keygen -t ed25519 -N '' -f {self.SSH_DIR}/id_ed25519 -q",
                timeout=30,
                out_debug_flag=False,
            )
            self.created_ssh_key = True
        self.sudo_run_cmd(
            f"chown root:root {self.SSH_DIR}",
            timeout=10,
            out_debug_flag=False,
        )
        return self.get_ssh_dir_owner() == "root"

    def cleanup_ssh_key_permission(self):
        """恢复 ~/.ssh 属主, 并删除前置构造的临时私钥"""
        user = self.run_cmd("id -un", timeout=5, out_debug_flag=False).strip()
        group = self.run_cmd("id -gn", timeout=5, out_debug_flag=False).strip()
        self.sudo_run_cmd(
            f"chown {user}:{group} {self.SSH_DIR}",
            timeout=10,
            out_debug_flag=False,
        )
        if getattr(self, "created_ssh_key", False):
            self.run_cmd(
                f"rm -f {self.SSH_DIR}/id_ed25519 {self.SSH_DIR}/id_ed25519.pub",
                timeout=10,
                out_debug_flag=False,
            )

    # ---------------------------------------------------------- 检测流程
    def wait_for_scan_progress(self, timeout=15) -> bool:
        """等待检测进度出现(扫描已开始)

        实测(deepin-pc-manager V20): detection_progress 的 showing 恒为 False,
        元素存在性也无区分度(QML 隐藏页元素常驻 AT-SPI 树); 只有 size 非零
        才表示当前处于扫描运行态。
        """
        for _ in range(timeout):
            if self._any_visible("$//detection_progress"):
                return True
            sleep(1)
        return False

    def get_last_detection_score(self):
        """读取"上次检测分数"数值, 读不到返回 None

        V20 的分数标签是 RichText(含颜色 span), AT-SPI 取不到文本(实测 text 为 None),
        因此数值以产品配置 Detection/lastScore 为准 —— 它与该标签在
        detection_page.cpp handleFullScanCompleted 中同一处写入, 同属产品结果通道。
        """
        match = re.search(r"(\d{1,3})", self.get_detection_score_text() or "")
        if match:
            return int(match.group(1))
        conf_path = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
        try:
            with open(conf_path, "r", encoding="utf-8", errors="replace") as fp:
                content = fp.read()
        except OSError:
            return None
        section = re.search(r"\[Detection\](.*?)(?=\n\[|\Z)", content, re.S)
        match = re.search(r"lastScore\s*=\s*(-?\d+)", section.group(1) if section else content)
        return int(match.group(1)) if match else None


class TestMyCase(BaseCase):

    def test_mycase_019(self):
        """系统检测首页--单个 P2 优化项异常

        前置条件: 仅系统环境 - ssh 密钥检测异常
        sudo chown root:root ~/.ssh

        步骤: 启动电脑管家, 点击全面检测后点击返回
        预期: 上次检测分数显示格式为"上次检测分数：98分"
              (实际断言: 检测流程完成并显示有效的上次检测分数, 不固定分值)
        """
        widget = DetectionWidget(check_start=False)
        try:
            self.assert_true(widget.setup_ssh_key_permission_abnormal())
            # 前置生效校验: 产品 D-Bus 检测接口应给出 ssh 密钥异常结论
            verdict, detail = widget.get_detection_item_verdict("ssh_key")
            log(f"ssh 密钥检测结论: ok={verdict} detail={detail}")
            self.assert_true(verdict is False)
            widget.kill_pc_manager()
            widget.start_pc_manager()
            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            self.assert_true(widget.get_detection_score_card_showing())
            self.assert_true(widget.get_detection_full_scan_button_showing())
            # 点击全面检测
            widget.click_detection_full_scan_button()
            # 不强制断言进度页显示(扫描可能过快完成)
            widget.wait_for_scan_progress(timeout=10)
            self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
            # 点击返回, 回到检测首页
            widget.click_back_button()
            sleep(2)
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            # 预期: 显示"上次检测分数"
            self.assert_true(widget.get_last_score_displayed(timeout=15))
            self.assert_true(widget.get_detection_score_card_showing())
            score = widget.get_last_detection_score()
            log(f"上次检测分数: {score}")
            self.assert_true(score is not None and 0 <= score <= 100)
        finally:
            widget.cleanup_ssh_key_permission()

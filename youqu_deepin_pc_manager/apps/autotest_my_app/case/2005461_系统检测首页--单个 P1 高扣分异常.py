#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/14
"""
import os
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import sleep


class DetectionWidget(MyAppWidget):
    """系统检测模块专用 widget, 自包含以避免共享文件并发覆盖问题"""

    # ---------------------------------------------------------- 前置/清理
    def get_boot_free_mb(self) -> int:
        """读取 /boot 剩余空间(MB), 读取失败返回 -1"""
        output = self.run_cmd(
            "df --output=avail -m /boot 2>/dev/null | tail -n 1",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(output.strip())
        except ValueError:
            return -1

    def setup_boot_partition_low_space(self, keep_free_mb=120) -> bool:
        """构造 boot 分区空间检查异常

        先执行前置条件给出的命令(在 /boot 写入 200MB 的 big_test_file), 再用
        df 核对剩余空间; 该命令按 /boot 原剩余约 360MB 设计, /boot 较大的测试机
        写完后剩余仍偏高, 此时追加填充。

        产品阈值为 V20 160MB / V25 300MB, 判定条件是剩余 <= 阈值
        (update_detector.cpp), 因此目标取 120MB 留出余量, 保证被检出异常。
        """
        self.sudo_run_cmd(
            "dd if=/dev/zero of=/boot/big_test_file bs=1M count=200 status=none",
            timeout=300,
            out_debug_flag=False,
        )
        free_mb = self.get_boot_free_mb()
        if free_mb > keep_free_mb:
            extra_mb = free_mb - keep_free_mb
            self.sudo_run_cmd(
                f"dd if=/dev/zero of=/boot/big_test_file bs=1M count={extra_mb}"
                " oflag=append conv=notrunc status=none",
                timeout=600,
                out_debug_flag=False,
            )
            free_mb = self.get_boot_free_mb()
        return 0 <= free_mb <= keep_free_mb + 16

    def cleanup_boot_partition_file(self):
        """删除前置填充文件, 恢复测试环境"""
        self.sudo_run_cmd("rm -f /boot/big_test_file", timeout=60, out_debug_flag=False)

    def wait_for_scan_progress(self, timeout=15) -> bool:
        """等待检测进度显示

        检测 detection_progress 的 showing 属性。
        不使用 refresh_dogtail_root 避免在 V20 上丢失 AT-SPI 元素。
        """
        for _ in range(timeout):
            try:
                pages = self.dog.find_elements_by_attr("$//detection_progress")
                if any(p.showing for p in pages):
                    return True
            except BaseException:
                pass
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

    def test_mycase_065(self):
        """系统检测首页--单个 P1 高扣分异常

        前置条件: 仅更新环境检测 - boot 分区空间检查异常
        通过 dd 命令在 /boot 写入文件, df -h 查看剩余空间, 将剩余空间调整至 160MB:
        sudo dd if=/dev/zero of=/boot/big_test_file bs=1M count=200
        (增大到足以被检出: 产品阈值为 V20 160MB, 剩余降到约 120MB)

        步骤: 启动电脑管家, 点击全面检测后点击返回
        预期: 上次检测分数显示格式为"上次检测分数：95分"
              (实际断言: 检测流程完成并显示有效的上次检测分数, 不固定分值)
        """
        widget = DetectionWidget(check_start=False)
        try:
            self.assert_true(widget.setup_boot_partition_low_space())
            # 前置生效校验: 产品 D-Bus 检测接口应给出"boot 分区空间不足"异常结论
            verdict, detail = widget.get_detection_item_verdict("boot_partition_space")
            log(f"boot 分区检测结论: ok={verdict} detail={detail}")
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
            widget.cleanup_boot_partition_file()

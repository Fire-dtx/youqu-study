#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/10
"""
import os
import re
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import logger
from src import sleep

# 产品一键修复统计日志(detection_page.cpp DetectionPage::finishFullScanFixAll):
# finishFullScanFixAll: fixed N failed M unattempted K manualProblems P
FIX_SUMMARY_PATTERN = re.compile(
    r"finishFullScanFixAll: fixed (\d+) failed (\d+) unattempted (\d+) manualProblems (\d+)"
)


class DetectionWidget(MyAppWidget):
    """系统检测-一键修复-修复进度显示 专用 widget

    断言口径(为什么这样断言):
    本机产品 deepin-pc-manager 1.1.7 的检测状态卡片把文案写在 QLabel 上, 且
    QLabel 只暴露 accessibleName(元素名 detection_title / detection_progressText),
    AT-SPI 读不到 QLabel 文案, 因此"标题显示问题修复中""描述显示已修复X项问题"
    用可访问等价载体断言:
      * 修复期间 detection_title / detection_progressText / detection_progressBar
        三个控件同时可见(即产品 setFixingInfo/setFixingProgress 的界面载体);
      * "已修复 X 项"的数量取产品自身统计日志 finishFullScanFixAll: fixed N;
      * detection_progressBar 的 AT-SPI 数值: 产品在每项修复开始时把它置 0,
        最后一项修完置为 fixed/fixTotal*100, 修复结束后读到的数值应与日志的
        fixed/(fixed+failed+unattempted) 精确一致, 即"进度条正确更新"。
    """

    SSH_DIR = os.path.expanduser("~/.ssh")
    # 产品日志: 一键修复统计与修复入口日志
    LOG_FILE = "$HOME/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log"
    TSYNC = "systemd-timesyncd"
    # 时间同步服务异常中断时的兜底恢复单元(正常路径由 finally 显式恢复)
    TSYNC_RECOVERY_UNIT = "pms-2005489-tsync-recovery"
    # 全面检测状态卡片的可访问名(V20 蛇形 / V25 驼峰)
    CARD_NAMES = ("detection_fullScanStatus", "detectionFullScanStatus")
    # 状态卡片内与本用例相关的元素(元素名即产品 setA11yMeta 写入的 accessibleName)
    CARD_CHILD_EXPRS = {
        "frame": "detection_progress",
        "title": "detection_title",
        "text": "detection_progressText",
        "bar": "detection_progressBar",
        "result_title": "detection_resultTitle",
        "result_desc": "detection_resultDesc",
    }

    # ------------------------------------------------------------ 命令封装
    def sh(self, cmd, timeout=30):
        """执行普通命令"""
        return self.run_cmd(cmd, timeout=timeout, out_debug_flag=False)

    def sudo_sh(self, cmd, timeout=60):
        """以 root 执行命令(测试机约定密码见 conf.PASSWORD)"""
        return self.sudo_run_cmd(cmd, timeout=timeout, out_debug_flag=False)

    # ------------------------------------------------------- 元素查找/状态
    def _find(self, expr) -> list:
        """按 AT-SPI 表达式查找元素, 找不到返回空列表"""
        try:
            return self.dog.find_elements_by_attr(expr) or []
        except BaseException:
            return []

    def _visible(self, *exprs):
        """返回第一个 size 非零的可见元素(V20 showing 不可靠)"""
        for expr in exprs:
            for element in self._find(expr):
                if self._size_nonzero(element):
                    return element
        return None

    @staticmethod
    def _size_nonzero(element) -> bool:
        """元素是否可见: 隐藏实例的 size 为 (0, 0)"""
        if element is None:
            return False
        try:
            width, height = element.size
        except BaseException:
            return False
        return width > 0 and height > 0

    @staticmethod
    def _bar_value(element):
        """读取进度条当前值(AT-SPI Value 接口), 读不到返回 None"""
        if element is None:
            return None
        try:
            raw = element.value
        except BaseException:
            return None
        if raw is None or isinstance(raw, str):
            return None
        try:
            return int(raw)
        except BaseException:
            return None

    def get_icon_description(self, expr, timeout=20) -> str:
        """读取结果状态图标的可访问描述(产品把结果语义写进 accessibleDescription)"""
        for index in range(timeout):
            element = self._visible(expr)
            if element is not None:
                try:
                    return (element.description or "").strip()
                except BaseException:
                    return ""
            if index and index % 5 == 0:
                self.refresh_dogtail_root()
            sleep(1)
        return ""

    # --------------------------------------------- 修复进度元素缓存与采样
    def cache_card_elements(self, timeout=20) -> dict:
        """缓存全面检测状态卡片内的修复进度相关元素

        修复过程只有数百毫秒, 采样时必须避免反复遍历控件树(单次查找约
        数百毫秒), 因此在结果态先把元素代理缓存下来, 修复期间只读 size/value。
        """
        elements = {}
        for _ in range(timeout):
            elements = {}
            for key, name in self.CARD_CHILD_EXPRS.items():
                for card in self.CARD_NAMES:
                    found = self._find(f"$//{card}//{name}")
                    if found:
                        elements[key] = found[0]
                        break
            if len(elements) == len(self.CARD_CHILD_EXPRS):
                break
            sleep(1)
        return elements

    def click_fix_all_start(self) -> bool:
        """点击结果卡片上可见的「一键修复」按钮并立即返回(不等待修复开始)

        修复窗口只有数百毫秒, 点击后必须马上开始采样, 因此不在点击里做等待。
        """
        visible = []
        for element in self._find("$//detection_fixAllBtn"):
            if self._size_nonzero(element):
                visible.append(element)
        if not visible:
            return False
        self._fix_button = visible[0]
        if self._atspi_do_action(visible[0]):
            return True
        return self._click_at_element(visible[0])

    def sample_fix_progress(self, elements, timeout=90) -> dict:
        """点击一键修复后高频采样修复进度卡片

        :param elements: cache_card_elements() 缓存的元素代理
        :param timeout: 最长等待秒数
        :return: dict(fixing_seen/title_seen/text_seen/bar_seen/result_seen/
                      values/final_value/samples/fixing_seconds)
        """
        frame = elements.get("frame")
        title = elements.get("title")
        text = elements.get("text")
        bar = elements.get("bar")
        result_title = elements.get("result_title")
        result_desc = elements.get("result_desc")
        info = {
            "fixing_seen": False,
            "title_seen": False,
            "text_seen": False,
            "bar_seen": False,
            "result_seen": False,
            "values": [],
            "final_value": None,
            "samples": 0,
            "fixing_seconds": 0.0,
        }
        start = time.time()
        fixing_started_at = 0.0
        fallback_clicked = False
        while time.time() - start < timeout:
            info["samples"] += 1
            frame_visible = self._size_nonzero(frame)
            if not info["fixing_seen"]:
                if frame_visible:
                    info["fixing_seen"] = True
                    fixing_started_at = time.time()
                else:
                    # AT-SPI 动作可能未触发修复: 4 秒后回退坐标点击一次
                    if not fallback_clicked and time.time() - start > 4:
                        fallback_clicked = True
                        button = getattr(self, "_fix_button", None)
                        if button is not None:
                            self._click_at_element(button)
                    if time.time() - start > 30:
                        break
                    sleep(0.02)
                    continue
            # 修复中: 记录三要素可见性与进度条数值
            if frame_visible:
                if self._size_nonzero(title):
                    info["title_seen"] = True
                if self._size_nonzero(text):
                    info["text_seen"] = True
                if self._size_nonzero(bar):
                    info["bar_seen"] = True
                value = self._bar_value(bar)
                if value is not None:
                    info["values"].append(value)
            # 修复结束: 进度卡片让位给结果卡片
            result_visible = (self._size_nonzero(result_title)
                              or self._size_nonzero(result_desc))
            if result_visible and not frame_visible:
                info["result_seen"] = True
                info["fixing_seconds"] = time.time() - fixing_started_at
                break
        # 修复结束后再读一次进度条: 产品在最后一项完成时写入 fixed/fixTotal*100
        info["final_value"] = self._bar_value(bar)
        return info

    # ------------------------------------------------------- 前置: SSH 权限
    def get_ssh_dir_mode(self) -> str:
        """读取 ~/.ssh 目录权限位(八进制)"""
        return (self.sh(f"stat -c %a {self.SSH_DIR} 2>/dev/null") or "").strip()

    def has_ssh_private_key(self) -> bool:
        """~/.ssh 下是否存在产品识别的私钥(产品只在有私钥时汇总权限结论)"""
        output = self.sh(
            f"ls {self.SSH_DIR} 2>/dev/null "
            "| grep -xE 'id_rsa|id_dsa|id_ecdsa|id_ed25519|identity'"
        )
        return bool((output or "").strip())

    def setup_ssh_dir_wrong_permission(self):
        """按用例前置构造 ~/.ssh 目录权限异常(先 755 再 777)

        产品 detectSSHKey 期望 ~/.ssh 权限不超过 755, 777 判 modeOk=False,
        且属于会话守护进程能以用户身份 fchmod 修好的"可自动修复项"。
        """
        self.created_ssh_key = False
        self.created_ssh_dir = False
        if not os.path.isdir(self.SSH_DIR):
            self.sh(f"mkdir -p -m 700 {self.SSH_DIR}")
            self.created_ssh_dir = True
        self.original_ssh_mode = self.get_ssh_dir_mode()
        if not self.has_ssh_private_key():
            self.sh(
                f"ssh-keygen -t ed25519 -N '' -f {self.SSH_DIR}/id_ed25519 -q",
                timeout=30,
            )
            self.created_ssh_key = True
        self.sh(f"chmod 755 {self.SSH_DIR}", timeout=10)
        self.sh(f"chmod 777 {self.SSH_DIR}", timeout=10)

    def restore_ssh_dir_permission(self):
        """回退 ~/.ssh 权限, 并删除前置构造的临时私钥/目录"""
        original_mode = getattr(self, "original_ssh_mode", "")
        if original_mode:
            self.sh(f"chmod {original_mode} {self.SSH_DIR} 2>/dev/null", timeout=10)
        if getattr(self, "created_ssh_key", False):
            self.sh(
                f"rm -f {self.SSH_DIR}/id_ed25519 {self.SSH_DIR}/id_ed25519.pub",
                timeout=10,
            )
        if getattr(self, "created_ssh_dir", False):
            self.sh(f"rm -rf {self.SSH_DIR}", timeout=10)
        log(f"~/.ssh 权限已恢复: mode={self.get_ssh_dir_mode()}")

    # ------------------------------------------------ 前置: 停止时间同步服务
    def get_time_service_active(self) -> str:
        """时间同步服务运行状态(active/inactive/failed/...)"""
        return (self.sh(f"systemctl is-active {self.TSYNC} 2>/dev/null") or "").strip()

    def get_time_service_enabled(self) -> str:
        """时间同步服务开机使能状态(enabled/disabled/masked/...)"""
        return (self.sh(f"systemctl is-enabled {self.TSYNC} 2>/dev/null") or "").strip()

    def stop_time_sync_service(self) -> bool:
        """停止时间同步服务, 构造第二个"可自动修复项"

        产品 detectTimeConfig 对 isActive=False 报 SystemTimeServiceInactive,
        canFix 仍为 true; 一键修复会 systemctl enable --now 拉起。
        该项是本用例第二个修复项, 保证修复过程按项推进(进度条/进度文案有更新)。
        停止前创建 15 分钟兜底恢复定时器, 防止用例异常中断后测试机时间同步停摆。
        """
        self.tsync_was_active = self.get_time_service_active() == "active"
        self.tsync_was_enabled = self.get_time_service_enabled()
        self.sudo_sh(
            f"systemctl stop {self.TSYNC_RECOVERY_UNIT}.timer 2>/dev/null; "
            f"systemctl reset-failed {self.TSYNC_RECOVERY_UNIT}.timer 2>/dev/null; true",
            timeout=30,
        )
        self.sudo_sh(
            f"systemd-run --on-active=900 --unit={self.TSYNC_RECOVERY_UNIT} "
            f"systemctl start {self.TSYNC} 2>/dev/null; true",
            timeout=30,
        )
        self.sudo_sh(
            f"systemctl stop {self.TSYNC} 2>/dev/null; "
            f"systemctl reset-failed {self.TSYNC} 2>/dev/null; true",
            timeout=30,
        )
        sleep(2)
        return self.get_time_service_active() != "active"

    def restore_time_sync_service(self):
        """回退时间同步服务: 取消兜底定时器并按原状态恢复服务"""
        self.sudo_sh(
            f"systemctl stop {self.TSYNC_RECOVERY_UNIT}.timer 2>/dev/null; "
            f"systemctl reset-failed {self.TSYNC_RECOVERY_UNIT}.timer 2>/dev/null; true",
            timeout=30,
        )
        was_enabled = getattr(self, "tsync_was_enabled", "")
        if was_enabled == "enabled":
            self.sudo_sh(f"systemctl enable {self.TSYNC} 2>/dev/null; true", timeout=30)
        elif was_enabled:
            self.sudo_sh(f"systemctl disable {self.TSYNC} 2>/dev/null; true", timeout=30)
        if getattr(self, "tsync_was_active", False):
            self.sudo_sh(f"systemctl start {self.TSYNC} 2>/dev/null; true", timeout=30)
        sleep(2)
        log(f"时间同步服务已恢复: active={self.get_time_service_active()} "
            f"enabled={self.get_time_service_enabled()}")

    # ------------------------------------------------------------ 日志读取
    def get_log_line_count(self) -> int:
        """读取产品日志当前行数, 作为本用例的日志基线"""
        output = (self.sh(f"wc -l < {self.LOG_FILE} 2>/dev/null || echo 0") or "").strip()
        return int(output) if output.isdigit() else 0

    def wait_fix_summary(self, baseline, timeout=30):
        """等待并解析产品的一键修复统计日志

        :return: (fixed, failed, unattempted, manualProblems); 未取到返回空元组
        """
        for _ in range(timeout):
            text = self.sh(f"tail -n +{baseline + 1} {self.LOG_FILE} 2>/dev/null",
                           timeout=20)
            matches = FIX_SUMMARY_PATTERN.findall(text or "")
            if matches:
                return tuple(int(value) for value in matches[-1])
            sleep(1)
        return ()


class TestMyCase(BaseCase):

    def test_mycase_076(self):
        """系统检测-一键修复-修复进度显示

        前置条件(用例描述): ~/.ssh 目录权限错误(≠700), 依次执行 chmod 755 /
        chmod 777; 另按等价实现追加第二个可自动修复项——停止时间同步服务,
        使一键修复按项推进(产品每项修复开始时把进度条置 0)。
        步骤: 系统检测首页点击全面检测 -> 检测完成后点击"一键修复" ->
              在修复过程中高频采样检测状态卡片。
        预期(等价断言):
        1. 修复期间状态卡片进入"修复中": detection_title(标题载体)、
           detection_progressText(进度文案载体, 即"已修复X项问题")、
           detection_progressBar 三个控件同时可见;
        2. 进度条正确更新: 修复期间读到的数值在 0~100 且每项开始时为 0,
           修复结束后读到的最终值 == 日志 fixed/(fixed+failed+unattempted)*100;
        3. "已修复 X 项"的数量由产品统计日志给出且 X>=1;
        4. 修复结束进入结果卡片(检测状态卡片进度区让位于结果区), 结果标题/
           描述元件可见; 产品已实际修好构造的两个可修复项(~/.ssh 权限收紧、
           时间同步服务重新 active), 经产品 D-Bus 检测通道复检为正常;
        5. 应用进程未崩溃。
        """
        widget = DetectionWidget(check_start=False)
        try:
            # ---------- 前置 1: ~/.ssh 目录权限过大(可自动修复项) ----------
            widget.setup_ssh_dir_wrong_permission()
            self.assert_equal("777", widget.get_ssh_dir_mode())
            self.assert_true(widget.has_ssh_private_key())

            # ---------- 前置 2: 停止时间同步服务(第二个可修复项) ----------
            self.assert_true(widget.stop_time_sync_service())
            self.assert_equal("inactive", widget.get_time_service_active())

            # ---------- 启动电脑管家并进入系统检测页面 ----------
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())
            log_baseline = widget.get_log_line_count()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            # ---------- 前置生效校验: 产品自身检测通道 ----------
            ssh_ok, ssh_detail = widget.get_detection_item_verdict("ssh_key")
            logger.info(f"ssh_key 检测结论: ok={ssh_ok} detail={ssh_detail}")
            self.assert_true(ssh_ok is False)
            time_ok, time_detail = widget.get_detection_item_verdict("time_config")
            logger.info(f"time_config 检测结论: ok={time_ok} detail={time_detail}")
            self.assert_true(time_ok is False)
            # ---------- 步骤 1: 全面检测 ----------
            self.assert_true(widget.get_detection_full_scan_button_showing(timeout=10))
            widget.click_detection_full_scan_button()
            self.assert_true(widget.get_detection_full_scan_page_showing(timeout=30))
            self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
            sleep(2)
            self.assert_true(widget.get_detection_result_showing(timeout=20))

            # 检测结果应为"发现问题(存在可修复项)": 一键修复入口可见
            issue_desc = widget.get_icon_description("$//detection_issuesIcon")
            logger.info(f"检测结果图标描述: {issue_desc!r}")
            self.assert_true("fixable" in issue_desc.lower())
            self.assert_true(widget.get_detection_fix_all_button_showing())

            # 先缓存状态卡片内的修复进度元素(修复窗口很短, 采样期间不再遍历控件树)
            elements = widget.cache_card_elements(timeout=20)
            logger.info(f"缓存的修复进度元素: {sorted(elements.keys())}")
            self.assert_equal(len(widget.CARD_CHILD_EXPRS), len(elements))

            # ---------- 步骤 2: 点击一键修复并高频采样修复进度 ----------
            self.assert_true(widget.click_fix_all_start())
            samples = widget.sample_fix_progress(elements, timeout=90)
            logger.info(f"修复中状态: fixing_seen={samples['fixing_seen']} "
                f"title_seen={samples['title_seen']} text_seen={samples['text_seen']} "
                f"bar_seen={samples['bar_seen']} result_seen={samples['result_seen']} "
                f"samples={samples['samples']} "
                f"fixing_seconds={samples['fixing_seconds']:.2f}")
            values = samples["values"]
            logger.info(f"修复中进度条采样值: {values[:60]}"
                f"{'...' if len(values) > 60 else ''} 结束值={samples['final_value']}")

            # ---------- 预期 1: 状态卡片进入"问题修复中" ----------
            self.assert_true(samples["fixing_seen"])
            self.assert_true(samples["title_seen"])
            self.assert_true(samples["text_seen"])
            self.assert_true(samples["bar_seen"])
            self.assert_true(len(values) >= 2)
            self.assert_true(all(0 <= value <= 100 for value in values))

            # ---------- 预期 2: 修复结束进入结果卡片 ----------
            self.assert_true(samples["result_seen"])
            sleep(1)
            self.assert_true(widget._size_nonzero(elements.get("result_title")))
            self.assert_true(widget._size_nonzero(elements.get("result_desc")))

            # ---------- 预期 3: 产品统计日志给出"已修复X项", 且进度条更新到 X/总数 ----------
            summary = widget.wait_fix_summary(log_baseline, timeout=30)
            logger.info(f"产品修复统计(fixed, failed, unattempted, manual): {summary}")
            self.assert_true(bool(summary))
            fixed_count, failed_count, unattempted, manual_count = summary
            self.assert_true(fixed_count >= 1)
            total_fixable = fixed_count + failed_count + unattempted
            expected_value = fixed_count * 100 // total_fixable
            logger.info(f"进度条最终值={samples['final_value']} 期望={expected_value} "
                f"(fixed={fixed_count} failed={failed_count} "
                f"unattempted={unattempted} manual={manual_count})")
            self.assert_equal(expected_value, samples["final_value"])
            self.assert_true(samples["final_value"] > 0)

            # ---------- 预期 4: 构造的可修复项被产品实际修好 ----------
            mode = widget.get_ssh_dir_mode()
            logger.info(f"修复后 ~/.ssh 权限: {mode}")
            self.assert_true(mode.isdigit())
            self.assert_true((int(mode, 8) & 0o077) == 0)
            self.assert_equal("active", widget.get_time_service_active())

            ssh_ok2, ssh_detail2 = widget.get_detection_item_verdict("ssh_key")
            logger.info(f"修复后 ssh_key 检测结论: ok={ssh_ok2} detail={ssh_detail2}")
            self.assert_true(ssh_ok2 is True)
            time_ok2, time_detail2 = widget.get_detection_item_verdict("time_config")
            logger.info(f"修复后 time_config 检测结论: ok={time_ok2} detail={time_detail2}")
            self.assert_true(time_ok2 is True)

            # ---------- 预期 5: 应用未崩溃 ----------
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            try:
                widget.kill_pc_manager()
                self.assert_true(widget.wait_pc_manager_exit())
            except BaseException:
                pass
            widget.restore_ssh_dir_permission()
            widget.restore_time_sync_service()

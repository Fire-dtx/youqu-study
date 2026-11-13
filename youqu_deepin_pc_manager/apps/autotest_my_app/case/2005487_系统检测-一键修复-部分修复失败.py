#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/10
"""
import re
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import sleep

# ---------------------------------------------------------------------------
# 用例前置与等价实现说明
#
# 用例描述的前置:
#   1) 删除整个备份目录: sudo rm -rf /recovery/backup
#      -> 产品 backup_partition 检测项报 SystemBackupDirectoryMissing,
#         且该检测项注册时 canFix 恒为 false(plugin-syscheck/src/entry.cpp),
#         属于"不可自动修复(需人工处理)"项;
#   2) 停止时间同步: sudo systemctl stop systemd-timesyncd.service
#      -> 产品 detectTimeConfig 报 SystemTimeServiceInactive(canFix 仍为 true),
#         属于"可自动修复"项, 一键修复会 systemctl enable --now 修好。
#
# 因此全面检测后聚合态为"有问题且可修复"(detection_issuesIcon); 一键修复后
# applyFixCompletedState 的剩余不可修复数>0, 进入
# DetectionStatusWidget::setFixCompletedManualRemaining:
#   * 图标 detection_fixPartialIcon, 可访问描述 "Some issues remain unfixed"
#     (即"修复已完成，剩余X项未修复", V20 标题 QLabel 文案不对外暴露);
#   * 描述 "Most optimizations are done automatically. Seek professional help
#     or handle the rest manually"(即"未修复项请手动处理或联系管理员");
#   * 一键修复入口隐藏, 重新检测仍可用。
#
# 等价实现(全部在 finally 回退, 测试机不留残留):
#   * 备份目录缺失用同分区 mv 改名代替 sudo rm -rf(目录对产品不可见, 不复制数据);
#   * 停止 timesyncd 时额外用 transient 定时器做 15 分钟兜底恢复, 正常路径由
#     restore_time_sync_service 显式恢复, 避免用例异常中断后测试机时间同步长期不可用。
# ---------------------------------------------------------------------------


class DetectionWidget(MyAppWidget):
    """系统检测模块专用 widget: 构造"部分修复失败"前置并读取部分修复结果态"""

    BACKUP_DIR = "/recovery/backup"
    # 等价实现: 同分区改名(不复制数据, finally 原位改回)
    BACKUP_BAK = "/recovery/backup.autotest_2005487_bak"
    LOG_FILE = "$HOME/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log"
    # 时间同步服务异常中断时的兜底恢复单元
    TSYNC_RECOVERY_UNIT = "pms-2005487-tsync-recovery"
    # 产品 finishFullScanFixAll 的统计日志
    FIX_SUMMARY_PATTERN = re.compile(
        r"finishFullScanFixAll: fixed (\d+) failed (\d+) unattempted (\d+) "
        r"manualProblems (\d+)"
    )
    # 分组摘要中的异常项数(中文/英文)
    ISSUES_FOUND_PATTERN = re.compile(
        r"(?:发现\s*)?(\d+)\s*(?:项问题|issues found)\s*$"
    )

    # ------------------------------------------------------------ 命令封装
    def sh(self, cmd, timeout=30):
        """执行普通命令"""
        return self.run_cmd(cmd, timeout=timeout, out_debug_flag=False)

    def sudo_sh(self, cmd, timeout=60):
        """以 root 执行命令(测试机约定密码见 conf.PASSWORD)"""
        return self.sudo_run_cmd(cmd, timeout=timeout, out_debug_flag=False)

    # ------------------------------------------------- 前置: 备份目录缺失
    def path_exists(self, path) -> bool:
        """判断测试机上的路径是否存在"""
        out = self.sh(f"test -e {path} && echo yes || echo no", timeout=10)
        return (out or "").strip() == "yes"

    def setup_backup_dir_missing(self) -> bool:
        """前置 1: 让 /recovery/backup 整个目录不存在

        产品 backup_partition 检测项在 /recovery/backup 缺失时报
        SystemBackupDirectoryMissing, 且该项 canFix 恒为 false, 即"不可自动
        修复项"。用同分区 mv 代替 sudo rm -rf: 目录对产品检测不可见, 数据不
        落地复制, finally 中改名回原位, 测试机不留残留。
        """
        self.moved_backup_dir = False
        if not self.path_exists(self.BACKUP_DIR):
            log(f"{self.BACKUP_DIR} 原本不存在, 前置条件已满足")
            return True
        if self.path_exists(self.BACKUP_BAK):
            self.sudo_sh(f"mv {self.BACKUP_BAK} {self.BACKUP_DIR}", timeout=60)
            return False
        self.sudo_sh(f"mv {self.BACKUP_DIR} {self.BACKUP_BAK}", timeout=60)
        self.moved_backup_dir = not self.path_exists(self.BACKUP_DIR)
        log(f"备份目录改名后 {self.BACKUP_DIR} 已不存在={self.moved_backup_dir}")
        return self.moved_backup_dir

    def restore_backup_dir(self):
        """回退前置 1: 把备份目录改名回原位"""
        if not getattr(self, "moved_backup_dir", False):
            return
        if not self.path_exists(self.BACKUP_BAK):
            log(f"回退异常: 未找到 {self.BACKUP_BAK}, 请人工检查 /recovery")
            return
        self.sudo_sh(f"mv {self.BACKUP_BAK} {self.BACKUP_DIR}", timeout=60)
        log(f"备份目录已恢复: exists={self.path_exists(self.BACKUP_DIR)}")

    # ------------------------------------------- 前置: 停止时间同步服务
    def get_time_service_active(self) -> str:
        """时间同步服务运行状态(active/inactive/failed/...)"""
        return (self.sh("systemctl is-active systemd-timesyncd.service 2>/dev/null")
                or "").strip()

    def get_time_service_enabled(self) -> str:
        """时间同步服务开机使能状态(enabled/disabled/masked/...)"""
        return (self.sh("systemctl is-enabled systemd-timesyncd.service 2>/dev/null")
                or "").strip()

    def stop_time_sync_service(self) -> bool:
        """前置 2: 停止时间同步服务(等价 sudo systemctl stop systemd-timesyncd)

        产品 detectTimeConfig 判 isActive=False 且 isEnabled=True 时给出
        SystemTimeServiceInactive, canFix 仍为 true, 属"可自动修复项"。
        停止前创建 15 分钟兜底恢复定时器, 防止用例中断后测试机时间同步停摆。
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
            "systemctl start systemd-timesyncd 2>/dev/null; true",
            timeout=30,
        )
        self.sudo_sh(
            "systemctl stop systemd-timesyncd 2>/dev/null; "
            "systemctl reset-failed systemd-timesyncd.service 2>/dev/null; true",
            timeout=30,
        )
        sleep(2)
        return self.get_time_service_active() != "active"

    def restore_time_sync_service(self) -> bool:
        """回退时间同步服务: 取消兜底定时器, 按原 enabled/active 状态恢复并校验

        :return: True 表示最终 active/enabled 与用例开始前一致
        """
        TSYNC = "systemd-timesyncd"
        self.sudo_sh(
            f"systemctl stop {self.TSYNC_RECOVERY_UNIT}.timer 2>/dev/null; "
            f"systemctl reset-failed {self.TSYNC_RECOVERY_UNIT}.timer 2>/dev/null; true",
            timeout=30,
        )
        was_enabled = getattr(self, "tsync_was_enabled", "")
        was_active = getattr(self, "tsync_was_active", False)
        if was_enabled == "enabled":
            self.sudo_sh(f"systemctl enable {TSYNC} 2>/dev/null; true", timeout=30)
        elif was_enabled:
            self.sudo_sh(f"systemctl disable {TSYNC} 2>/dev/null; true", timeout=30)
        if was_active:
            self.sudo_sh(f"systemctl start {TSYNC} 2>/dev/null; true", timeout=30)
        else:
            self.sudo_sh(f"systemctl stop {TSYNC} 2>/dev/null; true", timeout=30)
        sleep(2)
        active = self.get_time_service_active()
        enabled = self.get_time_service_enabled()
        log(f"时间同步服务已恢复: active={active} enabled={enabled} "
            f"(原 active={was_active} enabled={was_enabled})")
        active_ok = (active == "active") if was_active else (active != "active")
        enabled_ok = True if not was_enabled else (enabled == was_enabled)
        return active_ok and enabled_ok

    # ------------------------------------------------------------ UI 读取
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

    def get_icon_description(self, expr, timeout=20) -> str:
        """读取结果状态图标的可访问描述

        产品 DetectionStatusWidget 把结果标题语义写进图标的
        accessibleDescription(标题 QLabel 只暴露 accessibleName, 读不到文案),
        "Some issues remain unfixed" 即"修复已完成, 剩余X项未修复"的可访问等价载体。
        """
        for i in range(timeout):
            elements = self._visible_elements(expr)
            if elements:
                return (elements[0].description or "").strip()
            if i > 0 and i % 5 == 0:
                self.refresh_dogtail_root()
            sleep(1)
        return ""

    def get_group_summaries(self, log_all=False) -> dict:
        """读取全面检测结果页各分组的可访问描述

        产品 DetectionGroupWidget 把摘要文案写进分组的
        accessibleDescription(见 DetectionGroupWidget::updateAccessibilityDescription),
        可作为"该分组当前异常项数"的可访问等价载体。中文环境下摘要形如
        "发现 3 项问题", 分组描述为 "Detection group: 系统环境检测, 发现 3 项问题"。
        """
        summaries = {}
        try:
            elements = self.dog.find_elements_by_attr("$//detectionGroup_.*")
        except BaseException:
            return summaries
        for element in elements:
            try:
                width, height = element.size
                name = (element.name or "").strip()
                desc = (element.description or "").strip()
            except BaseException:
                continue
            if width <= 0 or height <= 0 or not name:
                continue
            summaries[name] = desc
        if log_all:
            log(f"检测分组可访问描述: {summaries}")
        return summaries

    def get_syscheck_issue_count(self, timeout=20) -> int:
        """读取"系统环境检测"分组的异常项数

        仅匹配 filterFullScanToAbnormal 写入的最终摘要
        ("发现 N 项问题" / "N issues found"), 排除检测过程中的进度摘要
        ("已检查 x/y 项，发现 N 项问题" / "Checked x/y items, N issues found")。
        :return: 异常项数, 读不到返回 -1
        """
        keywords = ("系统环境", "System Environment")
        for index in range(timeout):
            for name, desc in self.get_group_summaries(
                log_all=(index == timeout - 1)
            ).items():
                if not any(key in name for key in keywords):
                    continue
                if "Checked" in desc or "已检查" in desc:
                    continue
                match = self.ISSUES_FOUND_PATTERN.search(desc)
                if match:
                    return int(match.group(1))
            sleep(1)
        return -1

    def click_fix_all_button(self) -> bool:
        """点击结果卡片上可见的「一键修复」按钮

        同名按钮在分项运行时卡片与全面检测卡片中各有一份, 隐藏副本 size 为 0,
        只点可见实例; AT-SPI press 无效时回退 xdotool 坐标点击。
        """
        for _ in range(4):
            buttons = self._visible_elements("$//detection_fixAllBtn")
            if not buttons:
                return False
            self._atspi_do_action(buttons[0])
            if self.wait_fix_started(10):
                return True
            self._click_at_element(buttons[0])
            if self.wait_fix_started(10):
                return True
            self.refresh_dogtail_root()
        return False

    def wait_fix_started(self, timeout=10) -> bool:
        """等待修复确实开始: 修复进度卡片出现 / 时间同步服务被拉起 / 已到结果态"""
        for _ in range(timeout * 2):
            if self._any_visible("$//detection_progress"):
                return True
            if self.get_time_service_active() == "active":
                return True
            if self._any_visible(
                "$//detection_fixPartialIcon", "$//detection_fixDoneIcon"
            ):
                return True
            sleep(0.5)
        return False

    def wait_for_partial_fix_done(self, timeout=180):
        """等待一键修复结束并进入"部分修复失败"结果态

        完成信号: 结果卡片切到 detection_fixPartialIcon
        (setFixCompletedManualRemaining); 若切到 detection_fixDoneIcon 说明
        全部修复成功(与本用例预期不符, 交由断言暴露)。期间持续采样修复进度卡片。
        :return: (是否结束, 是否采样到修复进度卡片)
        """
        saw_progress = False
        deadline = time.time() + timeout
        rounds = 0
        while time.time() < deadline:
            rounds += 1
            if self._any_visible("$//detection_progress"):
                saw_progress = True
            if self._any_visible(
                "$//detection_fixPartialIcon", "$//detection_fixDoneIcon"
            ):
                return True, saw_progress
            if rounds % 20 == 0:
                self.refresh_dogtail_root()
                self._focus_windows_safe()
            sleep(1)
        return False, saw_progress

    # ------------------------------------------------------------ 日志读取
    def get_log_line_count(self) -> int:
        """读取产品日志当前行数, 作为本用例的日志基线"""
        out = (self.sh(f"wc -l < {self.LOG_FILE} 2>/dev/null || echo 0") or "").strip()
        return int(out) if out.isdigit() else 0

    def wait_fix_summary(self, baseline: int, timeout=30):
        """等待并解析产品的一键修复统计日志

        :return: (fixed, failed, unattempted, manualProblems); 未取到返回空元组
        """
        for _ in range(timeout):
            text = self.sh(
                f"tail -n +{baseline + 1} {self.LOG_FILE} 2>/dev/null", timeout=20
            )
            matches = self.FIX_SUMMARY_PATTERN.findall(text or "")
            if matches:
                return tuple(int(value) for value in matches[-1])
            sleep(1)
        return ()


class TestMyCase(BaseCase):

    def test_mycase_075(self):
        """系统检测-一键修复-部分修复失败

        前置条件: 备份目录整体缺失(/recovery/backup, 不可自动修复项) +
                  停止时间同步服务(systemd-timesyncd, 可自动修复项)。
        步骤: 系统检测首页点击全面检测 -> 检测完成后点击"一键修复" -> 观察修复过程与结果。
        预期(等价断言):
        1. 结果卡片进入"修复已完成，剩余X项未修复": 图标 detection_fixPartialIcon
           的可访问描述为 "Some issues remain unfixed", 结果标题/描述元件已渲染,
           一键修复入口隐藏、重新检测按钮可见;
        2. 时间配置检测项状态更新为"修复成功": systemd-timesyncd 被产品修复流程
           拉起并启用, 且产品自身检测通道(D-Bus Detect time_config)复检为正常,
           该项也从异常分组列表中移除;
        3. 备份还原分区检测项仍为不可修复/需人工处理(产品文案为 "Needs manual
           handling", 本版本未提供"请联系技术服务"字样, 语义等价): 产品自身检测
           通道仍判 backup_partition 异常, 且系统环境分组仍保留异常项(无自动修复
           出口, 行尾不提供可点击的修复按钮);
        4. 产品修复统计(finishFullScanFixAll)为"修复成功>=1, 修复失败0, 未尝试0,
           待人工处理>=1", 与"部分修复"一致;
        5. 应用进程未崩溃。
        """
        widget = DetectionWidget(check_start=False)
        try:
            # ---------- 前置 1: 备份目录整体缺失(等价 sudo rm -rf /recovery/backup) ----------
            self.assert_true(widget.setup_backup_dir_missing())
            self.assert_false(widget.path_exists(widget.BACKUP_DIR))

            # ---------- 前置 2: 停止时间同步服务(等价 systemctl stop systemd-timesyncd) ----------
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
            backup_ok, backup_detail = widget.get_detection_item_verdict("backup_partition")
            log(f"backup_partition 检测结论: ok={backup_ok} detail={backup_detail}")
            self.assert_true(backup_ok is False)
            time_ok, time_detail = widget.get_detection_item_verdict("time_config")
            log(f"time_config 检测结论: ok={time_ok} detail={time_detail}")
            self.assert_true(time_ok is False)
            # ---------- 步骤 1: 全面检测 ----------
            self.assert_true(widget.get_detection_full_scan_button_showing(timeout=10))
            widget.click_detection_full_scan_button()
            self.assert_true(widget.get_detection_full_scan_page_showing(timeout=30))
            self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
            sleep(2)
            self.assert_true(widget.get_detection_result_showing(timeout=20))

            # 检测结果应为"发现问题(存在可修复项)": 一键修复与重新检测均可见
            issue_desc = widget.get_icon_description("$//detection_issuesIcon")
            log(f"检测结果图标描述: {issue_desc!r}")
            self.assert_true("fixable" in issue_desc.lower())
            self.assert_true(widget.get_detection_fix_all_button_showing())
            self.assert_true(widget.get_detection_recheck_button_showing())

            issues_before = widget.get_syscheck_issue_count()
            log(f"修复前系统环境分组异常项数: {issues_before}")
            self.assert_true(issues_before >= 2)

            # ---------- 步骤 2: 点击一键修复, 等待修复结束 ----------
            self.assert_true(widget.click_fix_all_button())
            done, saw_progress = widget.wait_for_partial_fix_done(timeout=180)
            log(f"修复进度卡片采样={saw_progress} 部分修复结束={done}")
            self.assert_true(done)

            # ---------- 预期 1: "修复已完成，剩余X项未修复" ----------
            partial_desc = widget.get_icon_description("$//detection_fixPartialIcon")
            log(f"修复结果图标描述: {partial_desc!r}")
            self.assert_true("some issues remain unfixed" in partial_desc.lower())
            self.assert_true(widget.get_detection_result_title_showing())
            self.assert_true(widget.get_detection_result_desc_showing())
            # 存在未修复项时不再提供一键修复入口(避免反复无效修复), 重新检测仍可用
            self.assert_false(widget.get_detection_fix_all_button_showing())
            self.assert_true(widget.get_detection_recheck_button_showing())

            # ---------- 预期 2: 时间配置检测项状态更新为"修复成功" ----------
            self.assert_equal("active", widget.get_time_service_active())
            self.assert_equal("enabled", widget.get_time_service_enabled())
            fixed_ok, fixed_detail = widget.get_detection_item_verdict("time_config")
            log(f"修复后 time_config 检测结论: ok={fixed_ok} detail={fixed_detail}")
            self.assert_true(fixed_ok is True)
            # 修复成功的检测项从异常分组列表中移除
            issues_after = widget.get_syscheck_issue_count()
            log(f"修复后系统环境分组异常项数: {issues_after}")
            self.assert_true(issues_after >= 1)
            self.assert_true(issues_before - issues_after >= 1)

            # ---------- 预期 3: 备份还原分区仍为不可修复项(需人工处理, 无修复入口) ----------
            backup_ok2, backup_detail2 = widget.get_detection_item_verdict("backup_partition")
            log(f"修复后 backup_partition 检测结论: ok={backup_ok2} detail={backup_detail2}")
            self.assert_true(backup_ok2 is False)

            # ---------- 预期 4: 产品修复统计为"部分修复" ----------
            summary = widget.wait_fix_summary(log_baseline, timeout=30)
            log(f"产品修复统计(fixed, failed, unattempted, manual): {summary}")
            self.assert_true(bool(summary))
            fixed_count, failed_count, unattempted, manual_count = summary
            self.assert_true(fixed_count >= 1)
            self.assert_true(failed_count == 0)
            self.assert_true(unattempted == 0)
            self.assert_true(manual_count >= 1)

            # ---------- 预期 5: 应用未崩溃 ----------
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            try:
                widget.kill_pc_manager()
                self.assert_true(widget.wait_pc_manager_exit())
            except BaseException:
                pass
            self.assert_true(widget.restore_time_sync_service())
            widget.restore_backup_dir()

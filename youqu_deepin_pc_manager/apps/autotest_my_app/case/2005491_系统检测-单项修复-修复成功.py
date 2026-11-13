#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/10
"""
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import logger
from src import sleep


class DetectionWidget(MyAppWidget):
    """系统检测-单项修复-修复成功 专用 widget

    断言口径(为什么这样断言):
    本机产品 deepin-pc-manager 1.1.7 的检测结果页由 DetectionGroupWidget +
    DetectionCheckListView 组成, 每个检测项是 QListView 的一行, 行尾的
    "立即修复"是 DetectionCheckListDelegate::paint 里自绘的按钮(不是独立控件),
    AT-SPI 只能拿到每行的 list item(accessibleName=检测项标题)及其行矩形,
    因此按行矩形右端的按钮区域做坐标点击(行右缩进 12px, 按钮 72x28, 垂直居中)。
    行内状态文字("已修复")同样是自绘文本, AT-SPI 读不到, 故"时间配置检测项
    状态为修复成功"用以下可访问等价载体断言:
      1. 结果状态卡片的图标 accessibleName 由 detection_issuesIcon
         (存在可修复问题)切换为 detection_fixDoneIcon / detection_fixPartialIcon
         (修复完成, 描述分别为 All issues have been fixed /
         Some issues remain unfixed), 即产品 applyFixCompletedState 的
         手动单项修复完成分支;
      2. 修复完成后一键修复入口隐藏、重新检测入口保留
         (产品 setFixCompleted* 的固定动作);
      3. 时间同步服务被产品的 root 侧修复动作(systemctl enable --now)真正拉起,
         is-active=active 且 is-enabled=enabled;
      4. 产品自身 D-Bus 检测通道(Detect time_config)复检为 success,
         即该检测项已由异常转为正常。
    """

    TSYNC = "systemd-timesyncd"
    # 用例异常中断时的兜底恢复单元(正常路径由 finally 显式恢复)
    TSYNC_RECOVERY_UNIT = "pms-2005491-tsync-recovery"
    # 时间配置所属检测分组(与产品 plugin-syscheck 的分组一致)
    GROUP = "系统环境检测"
    ITEM = "时间配置"
    # 结果状态卡片的状态图标(同一 QLabel 随状态切换 accessibleName)
    ICON_FIXABLE = "detection_issuesIcon"
    ICON_MANUAL = "detection_manualIcon"
    ICON_MANUAL_PARTIAL = "detection_manualPartialIcon"
    ICON_FIX_DONE = "detection_fixDoneIcon"
    ICON_FIX_PARTIAL = "detection_fixPartialIcon"
    # 自绘修复按钮几何(与 detection_check_list_view.cpp 常量一致)
    BUTTON_WIDTH = 72
    BUTTON_RIGHT_MARGIN = 12

    # ------------------------------------------------------------ 命令封装
    def sh(self, cmd, timeout=30):
        """执行普通命令"""
        return self.run_cmd(cmd, timeout=timeout, out_debug_flag=False)

    def sudo_sh(self, cmd, timeout=60):
        """以 root 执行命令(测试机约定密码见 conf.PASSWORD)"""
        return self.sudo_run_cmd(cmd, timeout=timeout, out_debug_flag=False)

    # ------------------------------------------------------- 元素查找/状态
    def _find(self, expr) -> list:
        """按 AT-SPI 表达式查找元素, 找不到返回空列表(探测语义)"""
        try:
            return self.dog.find_elements_by_attr(expr, probe=True) or []
        except BaseException:
            return []

    @staticmethod
    def _rect(element) -> tuple:
        """元素屏幕矩形 (x, y, w, h), 读不到返回全 0"""
        try:
            x, y = element.position
            width, height = element.size
            return int(x), int(y), int(width), int(height)
        except BaseException:
            return 0, 0, 0, 0

    @classmethod
    def _size_nonzero(cls, element) -> bool:
        """元素是否可见: 隐藏实例的 size 为 (0, 0)"""
        if element is None:
            return False
        x, y, width, height = cls._rect(element)
        return width > 0 and height > 0

    def _visible(self, *exprs):
        """返回第一个 size 非零的可见元素(showing 在 V20 上不可靠)"""
        for expr in exprs:
            for element in self._find(expr):
                if self._size_nonzero(element):
                    return element
        return None

    # ------------------------------------------------ 前置: 停止时间同步服务
    def get_time_service_active(self) -> str:
        """时间同步服务运行状态(active/inactive/failed/...)"""
        return (self.sh(f"systemctl is-active {self.TSYNC} 2>/dev/null") or "").strip()

    def get_time_service_enabled(self) -> str:
        """时间同步服务开机使能状态(enabled/disabled/masked/...)"""
        return (self.sh(f"systemctl is-enabled {self.TSYNC} 2>/dev/null") or "").strip()

    def stop_time_sync_service(self) -> bool:
        """停止时间同步服务, 构造可自动修复项

        产品 detectTimeConfig 对 isActive=False 报 SystemTimeServiceInactive,
        canFix 仍为 true(plugin-syscheck 的 fixTimeConfig: systemctl enable --now)。
        停止前创建 15 分钟兜底恢复定时器, 防止用例异常中断后测试机时间同步停摆;
        不能沿用基类 60 秒兜底, 否则全面检测尚未结束服务就被拉起, 检测项会恢复正常。
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

    def restore_time_sync_service(self) -> bool:
        """回退时间同步服务: 取消兜底定时器, 按原 enabled/active 状态恢复并校验

        :return: True 表示最终 active/enabled 与用例开始前一致
        """
        self.sudo_sh(
            f"systemctl stop {self.TSYNC_RECOVERY_UNIT}.timer 2>/dev/null; "
            f"systemctl reset-failed {self.TSYNC_RECOVERY_UNIT}.timer 2>/dev/null; true",
            timeout=30,
        )
        was_enabled = getattr(self, "tsync_was_enabled", "")
        was_active = getattr(self, "tsync_was_active", False)
        if was_enabled == "enabled":
            self.sudo_sh(f"systemctl enable {self.TSYNC} 2>/dev/null; true", timeout=30)
        elif was_enabled:
            self.sudo_sh(f"systemctl disable {self.TSYNC} 2>/dev/null; true", timeout=30)
        if was_active:
            self.sudo_sh(f"systemctl start {self.TSYNC} 2>/dev/null; true", timeout=30)
        else:
            self.sudo_sh(f"systemctl stop {self.TSYNC} 2>/dev/null; true", timeout=30)
        sleep(2)
        active = self.get_time_service_active()
        enabled = self.get_time_service_enabled()
        log(f"时间同步服务已恢复: active={active} enabled={enabled} "
            f"(原 active={was_active} enabled={was_enabled})")
        active_ok = (active == "active") if was_active else (active != "active")
        enabled_ok = True if not was_enabled else (enabled == was_enabled)
        return active_ok and enabled_ok

    # ------------------------------------------------ 结果页: 状态卡片图标
    def get_result_icon(self, timeout=20) -> tuple:
        """读取结果状态卡片当前可见的状态图标

        :return: (accessibleName, accessibleDescription); 未出现返回 ("", "")
        """
        names = (self.ICON_FIXABLE, self.ICON_MANUAL, self.ICON_MANUAL_PARTIAL,
                 self.ICON_FIX_DONE, self.ICON_FIX_PARTIAL)
        for index in range(timeout):
            for name in names:
                element = self._visible(f"$//{name}")
                if element is not None:
                    try:
                        return name, (element.description or "").strip()
                    except BaseException:
                        return name, ""
            if index and index % 5 == 0:
                self.refresh_dogtail_root()
            sleep(1)
        return "", ""

    # ------------------------------------------------ 结果页: 检测项列表行
    def get_group_list_view(self):
        """获取"系统环境检测"分组内的检测项列表(detectionCheckList_listView)"""
        for element in self._find(
            f"$//detectionGroup_{self.GROUP}//detectionCheckList_listView"
        ):
            if self._size_nonzero(element):
                return element
        group = None
        for element in self._find(f"$//detectionGroup_{self.GROUP}"):
            if self._size_nonzero(element):
                group = element
                break
        if group is None:
            return None
        return self._find_descendant_by_name(
            group, ("detectionCheckList_listView", "detection_checkList_listView")
        )

    def get_item_row(self, item_name):
        """获取检测项列表中指定标题的行元素(list item)"""
        list_view = self.get_group_list_view()
        if list_view is None:
            return None
        try:
            for child in list_view.children:
                if (child.name or "").strip() == item_name and self._size_nonzero(child):
                    return child
        except BaseException:
            return None
        return None

    def ensure_item_row_visible(self, item_name, tries=12) -> bool:
        """把检测项行滚动到全面检测结果滚动区的可视范围内"""
        row = self.get_item_row(item_name)
        if row is None:
            return False
        area = self._visible("$//detection_fullScanScrollArea")
        if area is None:
            return True
        ax, ay, aw, ah = self._rect(area)
        for _ in range(tries):
            x, y, width, height = self._rect(row)
            if y >= ay and y + height <= ay + ah:
                return True
            button = 5 if y > ay else 4
            self._safe_focus_windows()
            self.run_cmd(
                f"xdotool mousemove {ax + aw // 2} {ay + ah // 2} "
                f"click --repeat 3 --delay 60 {button}",
                timeout=10,
                out_debug_flag=False,
            )
            sleep(1)
            row = self.get_item_row(item_name)
            if row is None:
                return False
        return False

    def click_item_fix_button(self, item_name) -> bool:
        """点击指定检测项行尾的"立即修复"自绘按钮

        按钮不是独立控件, 只能按行矩形计算: 行右缩进 12px、按钮宽 72、高 28、
        垂直居中(行高 40), 取按钮中心点做 xdotool 坐标点击。
        """
        if not self.ensure_item_row_visible(item_name):
            return False
        row = self.get_item_row(item_name)
        if row is None:
            return False
        x, y, width, height = self._rect(row)
        if width <= 0 or height <= 0:
            return False
        target_x = x + width - self.BUTTON_RIGHT_MARGIN - self.BUTTON_WIDTH // 2
        target_y = y + height // 2
        self.click_point = (target_x, target_y)
        self._safe_focus_windows()
        sleep(1)
        self.run_cmd(
            f"xdotool mousemove {target_x} {target_y} click 1",
            timeout=10,
            out_debug_flag=False,
        )
        log(f"点击单项修复按钮: 检测项={item_name} 行矩形={(x, y, width, height)} "
            f"点击点={(target_x, target_y)}")
        return True

    def wait_single_fix_result(self, timeout=120) -> dict:
        """等待单项修复完成

        完成判据(三者同时满足): 结果卡片进入"修复完成"状态图标、时间同步服务
        active、时间同步服务 enabled(即产品 root 侧修复动作已真实执行成功)。
        """
        info = {"icon": "", "desc": "", "active": "", "enabled": "", "seconds": 0.0}
        start = time.time()
        for index in range(timeout):
            icon, desc = self.get_result_icon(timeout=1)
            active = self.get_time_service_active()
            enabled = self.get_time_service_enabled()
            info.update(icon=icon, desc=desc, active=active, enabled=enabled)
            if (icon in (self.ICON_FIX_DONE, self.ICON_FIX_PARTIAL)
                    and active == "active" and enabled == "enabled"):
                info["seconds"] = time.time() - start
                return info
            if index and index % 5 == 0:
                self.refresh_dogtail_root()
                self._safe_focus_windows()
            sleep(1)
        return info


class TestMyCase(BaseCase):

    def test_mycase_077(self):
        """系统检测-单项修复-修复成功

        前置条件(用例描述): 停止时间同步(sudo systemctl stop
        systemd-timesyncd.service), 全面检测完成且结果页存在可修复问题。
        步骤: 在检测结果页点击"时间配置"检测项的"立即修复"按钮 -> 等待修复完成
              -> 观察界面变化。
        预期(等价断言):
        1. 结果页为"发现可修复问题"(detection_issuesIcon, 描述含 fixable),
           一键修复/重新检测入口可见, 检测项列表中存在"时间配置"行;
        2. 点击行尾"立即修复"后, 产品进入修复完成状态: 状态图标切换为
           detection_fixDoneIcon / detection_fixPartialIcon, 一键修复入口隐藏、
           重新检测入口保留;
        3. 时间同步服务被产品 root 侧修复动作重新拉起(active + enabled);
        4. 产品 D-Bus 检测通道复检 time_config 为 success, 该检测项已恢复正常;
        5. 应用进程未崩溃。
        """
        widget = DetectionWidget(check_start=False)
        try:
            # ---------- 前置: 停止时间同步(构造可自动修复的时间配置异常) ----------
            self.assert_true(widget.stop_time_sync_service())
            self.assert_equal("inactive", widget.get_time_service_active())

            # ---------- 启动电脑管家并进入系统检测页面 ----------
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            # 前置生效校验: 产品自身检测通道应判定时间配置异常
            time_ok, time_detail = widget.get_detection_item_verdict("time_config")
            logger.info(f"时间配置检测结论: ok={time_ok} detail={time_detail}")
            self.assert_true(time_ok is False)
            # ---------- 步骤 1: 全面检测, 得到"存在可修复问题"的结果页 ----------
            self.assert_true(widget.get_detection_full_scan_button_showing(timeout=10))
            widget.click_detection_full_scan_button()
            self.assert_true(widget.get_detection_full_scan_page_showing(timeout=30))
            self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
            sleep(2)
            self.assert_true(widget.get_detection_result_showing(timeout=20))

            icon_name, icon_desc = widget.get_result_icon(timeout=20)
            logger.info(f"检测结果图标: name={icon_name} desc={icon_desc!r}")
            self.assert_equal(widget.ICON_FIXABLE, icon_name)
            self.assert_true("fixable" in icon_desc.lower())
            self.assert_true(widget.get_detection_fix_all_button_showing())
            self.assert_true(widget.get_detection_recheck_btn_showing())

            # ---------- 步骤 2: 在结果列表中定位"时间配置"检测项 ----------
            self.assert_true(widget.ensure_item_row_visible(widget.ITEM))
            row = widget.get_item_row(widget.ITEM)
            self.assert_true(row is not None)
            logger.info(f"时间配置检测项行矩形: {widget._rect(row)}")

            # ---------- 步骤 3: 点击该检测项的"立即修复"并等待修复完成 ----------
            self.assert_true(widget.click_item_fix_button(widget.ITEM))
            result = widget.wait_single_fix_result(timeout=120)
            logger.info(f"单项修复结果: {result}")
            if result["icon"] not in (widget.ICON_FIX_DONE, widget.ICON_FIX_PARTIAL):
                # 坐标点击若未命中自绘按钮则重试一次; 修复已开始/已完成时该行
                # 按钮已隐藏(hasButton=false), 重复点击不会触发第二次修复。
                logger.info("首次点击未触发修复, 重试一次")
                widget.click_item_fix_button(widget.ITEM)
                result = widget.wait_single_fix_result(timeout=120)
                logger.info(f"单项修复重试结果: {result}")

            # ---------- 预期 1: 产品进入"修复完成"状态(检测项修复成功) ----------
            self.assert_true(
                result["icon"] in (widget.ICON_FIX_DONE, widget.ICON_FIX_PARTIAL)
            )
            self.assert_true("fixed" in result["desc"].lower())
            logger.info(f"修复耗时约 {result['seconds']:.1f}s, "
                f"状态图标={result['icon']} 描述={result['desc']!r}")

            # ---------- 预期 2: 修复后入口变化(产品修复完成状态的固定动作) ----------
            self.assert_true(not widget.get_detection_fix_all_button_showing())
            self.assert_true(widget.get_detection_recheck_btn_showing())

            # ---------- 预期 3: 时间同步服务已被产品真正修复 ----------
            self.assert_equal("active", result["active"])
            self.assert_equal("enabled", result["enabled"])
            self.assert_true(widget.get_time_config_status())

            # ---------- 预期 4: 产品 D-Bus 检测通道复检该检测项为正常 ----------
            time_ok2, time_detail2 = widget.get_detection_item_verdict("time_config")
            logger.info(f"修复后时间配置检测结论: ok={time_ok2} detail={time_detail2}")
            self.assert_true(time_ok2 is True)

            # ---------- 预期 5: 应用进程未崩溃 ----------
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            try:
                widget.kill_pc_manager()
                self.assert_true(widget.wait_pc_manager_exit())
            except BaseException:
                pass
            self.assert_true(widget.restore_time_sync_service())

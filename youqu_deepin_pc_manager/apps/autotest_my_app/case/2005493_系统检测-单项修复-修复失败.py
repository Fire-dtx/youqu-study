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


class DetectionWidget(MyAppWidget):
    """系统检测-单项修复-修复失败 专用 widget

    ------------------------------------------------------------------
    用例前置与等价实现说明（为什么这样构造/断言）
    ------------------------------------------------------------------
    用例描述的前置: 时间配置检测存在不可修复问题，构造方式为
        sudo chmod 000 /lib/systemd/system/systemd-timesyncd.service
        sudo systemctl daemon-reload
    实测(本机 systemd 以 root 运行, root 不受 000 权限限制): 执行上述两步后
    `systemctl show --property=LoadState --value systemd-timesyncd.service` 仍返回
    loaded, 产品 detectTimeConfig 也不会判定"服务不存在", 因此该前置在本环境
    无法直接复现期望 1 的"检测失败/服务不存在"。

    本版本产品(deepin-pc-manager 1.1.7)的真实行为:
      * 服务不存在(SystemTimeServiceMissing)时 detectTimeConfig 直接置
        canFix=false, 结果行只给"需人工处理"提示, 不提供"立即修复"按钮;
      * 服务存在但未运行(SystemTimeServiceInactive)时 canFix=true, 结果行有
        "立即修复"按钮, 点击后产品执行系统侧修复(systemctl enable --now);
      * 修复失败时 DetectionPluginBase::onSingleItemFixCompleted 把该行置为
        "异常/自动修复未成功", 状态卡片进入"修复完成但仍有余项未修复"态
        (detection_manualPartialIcon, 描述 "some issues fixed manually, some remain",
        即旧版本"修复失败，请联系技术服务"的语义等价物)。
    因此为了让产品真正走到"单项修复-修复失败"分支(用例标题/步骤 2 的核心),
    采用等价前置:
      1) 先 `systemctl stop systemd-timesyncd` 让时间配置检测失败且该项可修复
         (结果行出现"立即修复");
      2) 全面检测完成、结果行已带上修复入口后, 把
         /usr/lib/systemd/system/systemd-timesyncd.service 移到 /tmp 备份目录并
         daemon-reload, 让 LoadState 变成 not-found（即描述里 chmod 000 的意图:
         单元文件对 systemd 不可用），于是产品本次修复命中
         fixTimeConfig 的"服务不存在"分支并返回失败;
      3) 断言产品日志里出现它自己的失败提示
         "systemd-timesyncd.service does not exist. Please install the
         corresponding package..."（对应期望 1/2 的"systemd-timesyncd.service
         不存在"），且状态卡片没有报告修复成功。
    断言载体说明: 行内状态文字/提示/按钮都是 DetectionCheckListDelegate 自绘文本,
    AT-SPI 读不到, 故用以下产品可观测等价载体:
      * 状态卡片图标 accessibleName/description(产品 applyFixCompletedState 分支);
      * 产品自身 D-Bus 检测通道(Detect time_config + Task.GetResult)的检测结论;
      * systemd 单元的真实状态(LoadState/is-active/is-enabled);
      * 产品日志(插件 dCWarning "Time config fix failed: <diagnostic>")。
    全部构造在 finally 回退: 单元文件移回原位 + daemon-reload + enable --now、
    关闭 900s 兜底恢复定时器、删除 /tmp 备份目录, 测试机不留残留。
    ------------------------------------------------------------------
    """

    TSYNC = "systemd-timesyncd"
    UNIT_PATH = "/usr/lib/systemd/system/systemd-timesyncd.service"
    UNIT_BACKUP_DIR = "/tmp/pcm_2005493_unit_bak"
    UNIT_BACKUP = UNIT_BACKUP_DIR + "/systemd-timesyncd.service"
    # 服务异常中断时的兜底恢复单元(正常路径由 finally 显式恢复)
    RECOVERY_UNIT = "pms-2005493-tsync-recovery"
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
    # 产品日志(UI 进程: 插件 dCWarning 记录修复失败原因; 会话守护进程: 修复调用链)
    LOG_PATHS = (
        ("app", "$HOME/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log"),
        ("session", "$HOME/.cache/deepin/deepin-pc-manager/deepin-pc-manager-session-daemon.log"),
    )

    # ------------------------------------------------------------ 命令封装
    def sh(self, cmd, timeout=30):
        """执行普通命令"""
        return self.run_cmd(cmd, timeout=timeout, out_debug_flag=False)

    def sudo_sh(self, cmd, timeout=60):
        """以 root 执行命令(测试机约定密码见 conf.PASSWORD)"""
        return self.sudo_run_cmd(cmd, timeout=timeout, out_debug_flag=False)

    def path_exists(self, path) -> bool:
        """判断测试机上的路径是否存在"""
        out = self.sh(f"test -e {path} && echo yes || echo no", timeout=10)
        return (out or "").strip() == "yes"

    # ------------------------------------------------------- 元素查找/状态
    def _find(self, expr) -> list:
        """按 AT-SPI 表达式查找元素, 找不到返回空列表"""
        try:
            return self.dog.find_elements_by_attr(expr) or []
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

    # ------------------------------------------- 前置: 时间同步服务状态
    def get_time_service_load_state(self) -> str:
        """单元加载状态(loaded / not-found / masked ...)"""
        return (self.sh(f"systemctl show --property=LoadState --value {self.TSYNC} 2>/dev/null")
                or "").strip()

    def get_time_service_active(self) -> str:
        """时间同步服务运行状态(active/inactive/failed/...)"""
        return (self.sh(f"systemctl is-active {self.TSYNC} 2>/dev/null") or "").strip()

    def get_time_service_enabled(self) -> str:
        """时间同步服务开机使能状态(enabled/disabled/masked/...)"""
        return (self.sh(f"systemctl is-enabled {self.TSYNC} 2>/dev/null") or "").strip()

    def stop_time_sync_service(self) -> bool:
        """停止时间同步服务, 构造"时间配置检测失败且可修复"的前置

        产品 detectTimeConfig 对 isActive=False 报 SystemTimeServiceInactive,
        canFix 仍为 true(plugin-syscheck 的 fixTimeConfig: systemctl enable --now),
        因此全面检测结果里该行会带"立即修复"入口。
        停止前创建 900s 兜底恢复定时器, 防止用例异常中断后测试机时间同步长期停摆;
        正常路径由 restore_time_sync_service 显式恢复并清掉定时器。
        """
        self.tsync_was_active = self.get_time_service_active() == "active"
        self.tsync_was_enabled = self.get_time_service_enabled()
        self.sudo_sh(
            f"systemctl stop {self.RECOVERY_UNIT}.timer 2>/dev/null; "
            f"systemctl reset-failed {self.RECOVERY_UNIT}.timer 2>/dev/null; true",
            timeout=30,
        )
        self.sudo_sh(
            f"systemd-run --on-active=900 --unit={self.RECOVERY_UNIT} "
            f"systemctl start {self.TSYNC} 2>/dev/null; true",
            timeout=30,
        )
        self.sudo_sh(
            f"systemctl stop {self.TSYNC} 2>/dev/null; "
            f"systemctl reset-failed {self.TSYNC} 2>/dev/null; true",
            timeout=30,
        )
        sleep(2)
        log(f"时间同步服务已停止: load={self.get_time_service_load_state()} "
            f"active={self.get_time_service_active()} "
            f"enabled={self.get_time_service_enabled()}")
        return self.get_time_service_active() != "active"

    def restore_time_sync_service(self) -> bool:
        """回退时间同步服务: 取消兜底定时器, 按原 enabled/active 状态恢复并校验

        :return: True 表示最终 active/enabled 与用例开始前一致
        """
        self.sudo_sh(
            f"systemctl stop {self.RECOVERY_UNIT}.timer 2>/dev/null; "
            f"systemctl reset-failed {self.RECOVERY_UNIT}.timer 2>/dev/null; true",
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

    # ------------------------------- 前置等价实现: 单元文件对 systemd 不可用
    def hide_service_unit(self) -> bool:
        """把时间同步服务的单元文件移走并 daemon-reload, 使 LoadState 变为 not-found

        等价于用例描述里 `chmod 000 + daemon-reload` 的意图(让 systemd/产品读不到
        该单元文件); 由于 systemd 以 root 运行、不受 000 权限限制, 改用移走文件
        才能让产品 fixTimeConfig 真正命中"服务不存在"的失败分支。
        """
        self.unit_hidden = False
        if not self.path_exists(self.UNIT_PATH):
            log(f"单元文件 {self.UNIT_PATH} 不存在, 无法构造")
            return False
        if self.path_exists(self.UNIT_BACKUP):
            # 上次异常中断残留: 先还原再重新构造, 避免覆盖备份
            self.restore_service_unit()
        self.sudo_sh(f"mkdir -p {self.UNIT_BACKUP_DIR}", timeout=30)
        self.sudo_sh(f"mv {self.UNIT_PATH} {self.UNIT_BACKUP}", timeout=30)
        self.sudo_sh("systemctl daemon-reload", timeout=30)
        sleep(1)
        load_state = self.get_time_service_load_state()
        self.unit_hidden = load_state != "loaded"
        log(f"单元文件已移走: backup_exists={self.path_exists(self.UNIT_BACKUP)} "
            f"LoadState={load_state!r} hidden={self.unit_hidden}")
        return self.unit_hidden

    def restore_service_unit(self):
        """回退: 单元文件移回原位 + daemon-reload + 重新 enable --now"""
        try:
            if self.path_exists(self.UNIT_BACKUP):
                self.sudo_sh(f"mv {self.UNIT_BACKUP} {self.UNIT_PATH}", timeout=30)
            self.sudo_sh("systemctl daemon-reload", timeout=30)
            self.sudo_sh(f"systemctl enable --now {self.TSYNC} 2>/dev/null; true", timeout=60)
            self.sudo_sh(f"rm -rf {self.UNIT_BACKUP_DIR}", timeout=30)
            self.unit_hidden = False
            sleep(2)
            log(f"服务单元已恢复: file_exists={self.path_exists(self.UNIT_PATH)} "
                f"load={self.get_time_service_load_state()} "
                f"active={self.get_time_service_active()} "
                f"enabled={self.get_time_service_enabled()}")
        except BaseException as exc:
            log(f"恢复服务单元异常: {exc}")

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

    def wait_fix_failure(self, timeout=90) -> dict:
        """等待单项修复结束并返回状态卡片结果

        产品单项修复失败后进入 applyFixCompletedState(manualRepair=True):
        仍有可修复项未修完 -> setManualRepairPartial(detection_manualPartialIcon,
        "some issues fixed manually, some remain"); 全部修完 -> fixDoneIcon。
        因此以状态图标离开"发现可修复问题"态作为修复结束信号, 由调用方断言方向。
        """
        info = {"icon": "", "desc": "", "seconds": 0.0}
        start = time.time()
        done_icons = (self.ICON_MANUAL, self.ICON_MANUAL_PARTIAL,
                      self.ICON_FIX_DONE, self.ICON_FIX_PARTIAL)
        for index in range(timeout):
            icon, desc = self.get_result_icon(timeout=1)
            info.update(icon=icon, desc=desc)
            if icon in done_icons:
                info["seconds"] = time.time() - start
                return info
            if index and index % 5 == 0:
                self.refresh_dogtail_root()
                self._safe_focus_windows()
            sleep(1)
        return info

    # ------------------------------------------------------------ 日志读取
    def log_line_count(self, path) -> int:
        """读取日志文件当前行数, 作为本次修复的日志基线

        用显式标记解析, 避免日志不存在/命令回显干扰导致的误判(0 会让
        tail 从第 1 行开始, 把历史日志当成本次证据)。
        """
        out = self.sh(f"echo PCM_LINES=$(wc -l < {path} 2>/dev/null || echo -1)", timeout=20) or ""
        match = re.search(r"PCM_LINES=(\d+)", out)
        return int(match.group(1)) if match else -1

    def log_baselines(self) -> dict:
        """记录产品日志的当前行数"""
        return {name: self.log_line_count(path) for name, path in self.LOG_PATHS}

    def read_log_since(self, path, baseline) -> str:
        """读取基线之后的日志内容(基线无效时不读, 避免误用历史日志)"""
        if baseline is None or baseline < 0:
            return ""
        cmd = f"tail -n +{int(baseline) + 1} {path} 2>/dev/null"
        return self.sh(cmd, timeout=30) or ""

    def collect_fix_failure_evidence(self, baselines) -> str:
        """收集本次修复期间产品日志的新增内容"""
        chunks = []
        for name, path in self.LOG_PATHS:
            text = self.read_log_since(path, baselines.get(name, -1))
            if text:
                chunks.append(f"===== {name} =====\n{text}")
        return "\n".join(chunks)


class TestMyCase(BaseCase):

    def test_mycase_078(self):
        """系统检测-单项修复-修复失败

        前置条件(等价实现, 见 DetectionWidget 文档): 时间配置检测失败且该项可修复
        —— 停止 systemd-timesyncd 服务; 全面检测完成后把单元文件移走 + daemon-reload,
        使产品本次修复命中"服务不存在"的失败分支。
        步骤: 系统检测首页点击全面检测 -> 结果页点击"时间配置"行的"立即修复" -> 观察结果。
        预期(等价断言):
        1. 检测阶段"时间配置"检测项判定失败(产品 D-Bus Detect time_config = false),
           结果页为"发现可修复问题"(detection_issuesIcon), 该行带"立即修复"入口;
        2. 点击"立即修复"后产品执行系统侧修复并失败: 状态卡片进入
           "修复完成但仍有余项未修复"态(detection_manualPartialIcon,
           描述含 "some issues fixed manually, some remain"), 不得报告"全部修复成功";
        3. 产品自己的失败提示为 "systemd-timesyncd.service does not exist. Please
           install the corresponding package..."(即期望里的"systemd-timesyncd.service
           不存在"), 出现在产品日志中;
        4. 修复未真正生效: D-Bus 复检 time_config 仍为 false, 服务单元仍不可用
           (LoadState != loaded, is-active != active);
        5. 应用进程未崩溃; finally 中单元文件/服务/兜底定时器全部回退。
        """
        widget = DetectionWidget(check_start=False)
        try:
            # ---------- 前置: 停止时间同步(检测失败且可修复) ----------
            self.assert_true(widget.path_exists(widget.UNIT_PATH))
            self.assert_true(widget.stop_time_sync_service())
            self.assert_equal("inactive", widget.get_time_service_active())
            self.assert_equal("loaded", widget.get_time_service_load_state())

            # ---------- 启动电脑管家并进入系统检测页面 ----------
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            time_ok, time_detail = widget.get_detection_item_verdict("time_config")
            log(f"时间配置检测结论: ok={time_ok} detail={time_detail}")
            self.assert_true(time_ok is False)
            # ---------- 步骤 1: 全面检测 ----------
            self.assert_true(widget.get_detection_full_scan_button_showing(timeout=10))
            widget.click_detection_full_scan_button()
            self.assert_true(widget.get_detection_full_scan_page_showing(timeout=30))
            self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
            sleep(2)
            self.assert_true(widget.get_detection_result_showing(timeout=20))

            # 预期 1: 结果页为"发现可修复问题", 时间配置行存在且带修复入口
            icon_name, icon_desc = widget.get_result_icon(timeout=20)
            log(f"检测结果图标: name={icon_name} desc={icon_desc!r}")
            self.assert_equal(widget.ICON_FIXABLE, icon_name)
            self.assert_true("fixable" in icon_desc.lower())
            self.assert_true(widget.ensure_item_row_visible(widget.ITEM))
            row = widget.get_item_row(widget.ITEM)
            self.assert_true(row is not None)
            row_rect = widget._rect(row)
            log(f"时间配置检测项行矩形: {row_rect}")
            self.assert_true(widget.get_time_config_status() is False)

            # ---------- 等价前置: 让服务单元对 systemd 不可用(见类文档) ----------
            self.assert_true(widget.hide_service_unit())
            self.assert_true(widget.get_time_service_load_state() != "loaded")

            # ---------- 步骤 2: 点击"时间配置"行的"立即修复" ----------
            baselines = widget.log_baselines()
            self.assert_true(widget.click_item_fix_button(widget.ITEM))
            info = widget.wait_fix_failure(timeout=90)
            if info["icon"] == "" or info["icon"] == widget.ICON_FIXABLE:
                # 坐标点击若未命中自绘按钮, 重试一次；修复已结束/按钮已隐藏时不会重复触发
                log(f"首次点击未观察到修复结束, 重试一次: {info}")
                widget.click_item_fix_button(widget.ITEM)
                info = widget.wait_fix_failure(timeout=90)
            log(f"单项修复结果: {info}")

            # 预期 2: 修复失败(未报告成功), 状态卡片进入"仍有余项未修复"态
            self.assert_true(
                info["icon"] in (widget.ICON_MANUAL_PARTIAL, widget.ICON_FIX_PARTIAL)
            )
            self.assert_false(info["icon"] == widget.ICON_FIX_DONE)
            desc_lower = info["desc"].lower()
            self.assert_true("remain" in desc_lower or "some issues" in desc_lower)
            log(f"修复结束耗时约 {info['seconds']:.1f}s, 状态图标={info['icon']} "
                f"描述={info['desc']!r}")

            # 预期 3: 产品自己的失败提示("systemd-timesyncd.service 不存在")
            # 只认本次修复期间新增的日志: 插件 dCWarning "Time config fix failed: ..."
            evidence = widget.collect_fix_failure_evidence(baselines)
            fix_failed_logged = "time config fix failed" in evidence.lower()
            not_exist_logged = ("does not exist" in evidence.lower()
                                or "不存在" in evidence or "未找到" in evidence)
            if not (fix_failed_logged and not_exist_logged):
                log(f"产品日志片段({len(evidence)} 字节): {evidence[-1500:]}")
            self.assert_true(fix_failed_logged)
            self.assert_true(not_exist_logged)

            # 预期 4: 修复未真正生效
            fixed_ok, fixed_detail = widget.get_detection_item_verdict("time_config")
            log(f"修复后时间配置检测结论: ok={fixed_ok} detail={fixed_detail}")
            self.assert_true(fixed_ok is False)
            self.assert_true(widget.get_time_service_load_state() != "loaded")
            self.assert_true(widget.get_time_service_active() != "active")
            self.assert_false(widget.get_time_config_status())

            # 预期 5: 应用未崩溃
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            try:
                widget.kill_pc_manager()
                self.assert_true(widget.wait_pc_manager_exit())
            except BaseException:
                pass
            widget.restore_service_unit()
            self.assert_true(widget.restore_time_sync_service())

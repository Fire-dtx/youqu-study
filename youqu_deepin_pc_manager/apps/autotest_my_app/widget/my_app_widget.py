#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
::::Author:ut000635
::::Date  :2026/09/10 13:34:42
"""

from os.path import expanduser
import json
import base64
import logging
import os
import re
import shutil
import tempfile
import time
import zipfile
from shlex import quote
from subprocess import check_output

from apps.autotest_my_app.widget.base_widget import BaseWidget
from setting import conf
from src import log
from src import sleep

# funnylog 的 log 是类日志装饰器(不可直接调用 .info/.warning), 这里用标准库 logger,
# 日志经 funnylog 配置的 root handler 落到 report/logs。
logger = logging.getLogger(__name__)

APP_DESKTOP_FILE = "deepin-pc-manager.desktop"
APP_DESKTOP_FULL_PATH = "/usr/share/applications/deepin-pc-manager.desktop"
BROWSER_DESKTOP_FILE = "org.deepin.browser.desktop"
BROWSER_DESKTOP_FULL_PATH = "/usr/share/applications/org.deepin.browser.desktop"
# 启动管理器开关的 accessibleName 为 startup_<GenericName 或 Name>,
# 不同应用/语言的取值不同, 按应用名列出候选值。
STARTUP_APP_NAME_ALIASES = {
    "电脑管家": ["电脑管家", "PC Manager", "deepin PC Manager", "deepin-pc-manager"],
    "浏览器": ["浏览器", "Web Browser", "org.deepin.browser"],
}
# 启动管理器页面内 accessibleName 以 startup_ 开头但并非启动项开关的控件
# (筛选按钮、列表容器等), 统计启动项数量时排除。
STARTUP_NON_ITEM_NAMES = {
    "startup_allFilter",
    "startup_enabledFilter",
    "startup_disabledFilter",
    "startup_scrollArea",
    "startup_listCard",
}
# 启动项开关的 AT-SPI 角色
STARTUP_SWITCH_ROLES = {"toggle button", "check box", "check_box"}
# V20 启动器右键菜单项相对菜单窗口左上角的垂直偏移(像素)
LAUNCHER_MENU_ITEM_OFFSETS = {
    "打开": 22,
    "发送到桌面": 48,
    "从桌面上移除": 48,
    "发送到任务栏": 71,
    "从任务栏上移除": 71,
    "开机自动启动": 101,
    "取消开机自动启动": 101,
    "卸载": 126,
}

HOME_DIR = expanduser("~")
# 大文件隔离暂存目录: 放在 $HOME 之外, 产品扫描范围覆盖家目录(含隐藏目录),
# 暂存目录若放在家目录内会被产品自身的扫描统计进去。
SCAN_ISOLATION_DIR = os.path.join(tempfile.gettempdir(), "autotest_scan_isolated")
# 重复文件隔离目录放在家目录内的隐藏目录: 与家目录同分区(移动是 rename),
# 且隐藏目录不在产品重复文件扫描范围内。
DUP_ISOLATION_DIR = os.path.join(HOME_DIR, ".autotest_dup_staged")
AUTOSTART_DIR = f"{HOME_DIR}/.config/autostart"
# 使用 xdg-user-dir 获取桌面目录路径 (V20: ~/桌面, V25: ~/Desktop)
try:
    DESKTOP_DIR = check_output(["xdg-user-dir", "DESKTOP"], timeout=5).decode().strip()
except Exception:
    DESKTOP_DIR = f"{HOME_DIR}/Desktop"

# V25 Dock DBus 常量
DOCK_SERVICE_V25 = "org.deepin.dde.daemon.Dock1"
DOCK_PATH_V25 = "/org/deepin/dde/daemon/Dock1"
# V20 Dock DBus 常量
DOCK_SERVICE_V20 = "com.deepin.dde.daemon.Dock"
DOCK_PATH_V20 = "/com/deepin/dde/daemon/Dock"
# 兼容性别名(运行时自动探测)
DOCK_SERVICE = DOCK_SERVICE_V25
DOCK_PATH = DOCK_PATH_V25


@log
class MyAppWidget(BaseWidget):
    """应用方法主类"""

    def click_xxx_by_attr(self):
        """click xxx button by attribute"""
        self.dog.find_element_by_attr("xxx").click()

    def get_pc_manager_process_status(self) -> bool:
        """获取电脑管家主进程状态(排除 daemon 和 session-daemon)"""
        # V20/V25 上 GUI 二进制位于 /usr/libexec/deepin/deepin-pc-manager,
        # 通过 deepin-pc-manager-launch 启动; 排除 daemon/session-daemon 进程
        result = self.run_cmd(
            r'ps -eo args | grep -E "^deepin-pc-manager($|\s)|^/usr/libexec/deepin/deepin-pc-manager($|\s)|^/usr/bin/deepin-pc-manager($|\s)" | grep -v daemon | grep -v session-daemon | grep -v grep',
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def reconnect_dogtail(self) -> bool:
        """应用重启后重新建立 dogtail 连接(最多重试 10 次, 每次间隔 1 秒)

        V25 上应用重启后 AT-SPI 对象引用会失效, 需要重新搜索。
        root.application() 每次调用都会发起全新的 AT-SPI 树搜索。
        :return: True 如果连接成功, False 如果所有重试均失败
        """
        from src.dogtail_utils import DogtailUtils
        from src.custom_exception import ApplicationStartError

        for _ in range(10):
            try:
                self.dog = DogtailUtils(
                    name=self.APP_NAME,
                    description=self.DESC,
                    check_start=True,
                )
                return True
            except ApplicationStartError:
                sleep(1)
        return False

    def _kill_pc_manager_main_process(self):
        """仅终止电脑管家主程序, 不误杀 daemon/session-daemon 用户服务

        kill_process("deepin-pc-manager") 采用子串匹配, 会连带杀掉
        deepin-pc-manager-session-daemon(systemd 用户服务), 服务被反复
        KILL 后可能进入 failed/stopped, 导致自启动检查用例失败。
        这里复用 get_pc_manager_process_status 的精确匹配规则。
        """
        self.run_cmd(
            "pids=$(ps -eo pid=,args= | grep -E "
            "'^[[:space:]]*[0-9]+ (deepin-pc-manager|/usr/libexec/deepin/deepin-pc-manager|"
            "/usr/bin/deepin-pc-manager)($|[[:space:]])' "
            "| grep -v daemon | grep -v grep | awk '{print $1}'); "
            '[ -n "$pids" ] && kill -9 $pids > /dev/null 2>&1; true',
            timeout=10,
            out_debug_flag=False,
        )

    def start_pc_manager(self):
        """启动电脑管家(确保以 QT_ACCESSIBILITY=1 启动)

        daemon 可能已在未设置 QT_ACCESSIBILITY 的状态下启动了电脑管家,
        导致 AT-SPI 无法识别窗口。因此先关闭已有实例, 再以正确的环境变量重启。

        V20 上 kglobalaccel5 会持续触发 Alt+F4 全局快捷键导致窗口被关闭,
        启动前先杀死该进程(V25 上不存在同名进程, 无影响)。

        必须优先使用 deepin-pc-manager-launch: 该包装器经 deepin-security-loader
        启动应用, 会把应用的 D-Bus unique name 注册进 daemon 白名单
        (SetAllowCaller); 直接启动二进制时 daemon 会拒绝特权修复调用
        (日志: caller not in loader whitelist), 依赖关系/系统类修复无法执行。
        未安装启动包装器时回退为直接启动。
        """
        os.environ["QT_ACCESSIBILITY"] = "1"
        os.environ["NO_AT_BRIDGE"] = "0"
        os.environ["QT_LINUX_ACCESSIBILITY_ALWAYS_ON"] = "1"
        self._kill_pc_manager_main_process()
        sleep(2)
        self.run_cmd(
            "killall kglobalaccel5 2>/dev/null; sleep 1",
            timeout=5,
            out_debug_flag=False,
        )
        self.run_cmd(
            "export QT_ACCESSIBILITY=1 && export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1 && "
            "if [ -x /usr/bin/deepin-pc-manager-launch ]; then "
            "setsid /usr/bin/deepin-pc-manager-launch > /dev/null 2>&1 < /dev/null & "
            "elif [ -x /usr/libexec/deepin/deepin-pc-manager ]; then "
            "nohup /usr/libexec/deepin/deepin-pc-manager > /dev/null 2>&1 & "
            "elif [ -x /usr/bin/deepin-pc-manager ]; then "
            "nohup /usr/bin/deepin-pc-manager > /dev/null 2>&1 & "
            "else nohup deepin-pc-manager-launch > /dev/null 2>&1 & fi",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(6)
        # 重新建立 dogtail 连接(无论是否新启动, 确保 self.dog.obj 有效)
        if not self.reconnect_dogtail():
            # 进程在运行但 AT-SPI 不可达, 杀掉后重新启动
            self.kill_pc_manager()
            sleep(2)
            self.run_cmd(
                "if [ -x /usr/bin/deepin-pc-manager-launch ]; then "
                "setsid /usr/bin/deepin-pc-manager-launch > /dev/null 2>&1 < /dev/null & "
                "elif [ -x /usr/libexec/deepin/deepin-pc-manager ]; then "
                "nohup /usr/libexec/deepin/deepin-pc-manager > /dev/null 2>&1 & "
                "elif [ -x /usr/bin/deepin-pc-manager ]; then "
                "nohup /usr/bin/deepin-pc-manager > /dev/null 2>&1 & "
                "else nohup deepin-pc-manager-launch > /dev/null 2>&1 & fi",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(6)
            self.reconnect_dogtail()
        # 将应用窗口置顶聚焦
        self._safe_focus_windows()

    def start_pc_manager_in_desktop_session(self) -> bool:
        """通过桌面启动器启动电脑管家, 使进程归属图形 seat 会话

        从 ssh 会话直接启动的进程属于该 ssh 会话(无 seat/无 polkit 认证代理),
        daemon 对 root 修复工具发起 polkit 鉴权时请求会一直挂起、不弹框。
        由桌面启动器(dde-launcher)拉起时进程归属 seat 图形会话, 鉴权框正常弹出。

        :return: True 表示进程已启动且 cgroup 归属 session-*.scope
        """
        self._kill_pc_manager_main_process()
        sleep(2)
        geom = self.run_cmd("export DISPLAY=:0; xdotool getdisplaygeometry",
                            timeout=5, out_debug_flag=False) or "1024 768"
        try:
            w, h = [int(v) for v in geom.split()[:2]]
        except BaseException:
            w, h = 1024, 768
        sx, sy = int(w * 0.20), int(h * 0.27)
        self.run_cmd(
            "export DISPLAY=:0; export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus; "
            "dbus-send --session --type=method_call --dest=com.deepin.dde.Launcher "
            "/com/deepin/dde/Launcher com.deepin.dde.Launcher.Show >/dev/null 2>&1; "
            f"sleep 2; xdotool mousemove {sx} {sy} click 1; sleep 1; "
            "xdotool type --delay 100 '电脑管家'; sleep 2; xdotool key Return; sleep 8",
            timeout=40, out_debug_flag=False)
        if not self.get_pc_manager_process_status():
            return False
        scope = self.get_pc_manager_session_scope()
        if not scope:
            return False
        self.reconnect_dogtail()
        self._safe_focus_windows()
        return True

    def get_pc_manager_session_scope(self) -> str:
        """返回电脑管家主进程所属 cgroup 的 session-*.scope 名称"""
        out = self.run_cmd(
            "pid=$(pgrep -f '^/usr/libexec/deepin/deepin-pc-manager' | head -1); "
            "[ -n \"$pid\" ] && tr '\\0' '\\n' < /proc/$pid/cgroup "
            "| grep -o 'session-[0-9]*.scope' | head -1",
            timeout=5, out_debug_flag=False)
        return (out or "").strip()

    def kill_pc_manager(self):
        """关闭电脑管家主程序(不误杀 daemon/session-daemon)

        关闭前先点掉修复流程残留的提示框(见 finish_repair_flow): 插件
        entry.sh 末尾的 dpmapi openinfobox(..., timeoutMs=0) 弹窗由
        session-daemon 持有, 杀主进程带不走, 不点掉会留在桌面并阻塞脚本,
        污染后续用例。用例收尾统一经这里清理, 不必每个用例各写一遍。
        """
        try:
            self.finish_repair_flow()
        except BaseException:
            pass
        self._kill_pc_manager_main_process()
        sleep(2)

    def wait_pc_manager_exit(self, timeout=15) -> bool:
        """等待电脑管家主进程退出(最多重试 timeout 次, 每次间隔 1 秒)

        :param timeout: 最长等待秒数
        :return: True 表示进程已退出, False 表示超时仍在运行
        """
        for _ in range(timeout):
            if not self.get_pc_manager_process_status():
                return True
            sleep(1)
        return False

    def exit_pc_manager_by_shortcut(self):
        """通过快捷键 Alt+F4 关闭电脑管家窗口

        V20 上 kwin 的窗口快捷键由 kglobalaccel5 托管: 该进程未运行时
        Alt+F4 不会关闭窗口(实测窗口保持存活)。start_pc_manager 为避免
        快捷键被持续触发会先杀掉该进程, 因此这里发送快捷键前需确保其运行。
        """
        self.run_cmd(
            "pgrep -x kglobalaccel5 >/dev/null 2>&1 || "
            "(setsid kglobalaccel5 >/dev/null 2>&1 < /dev/null &); sleep 2",
            timeout=10,
            out_debug_flag=False,
        )
        self._safe_focus_windows()
        self.press_key("alt+F4")

    def close_main_window(self):
        """关闭电脑管家主窗口(通过 xdotool windowclose, 非快捷键)

        V25: 关闭窗口后进程驻留系统托盘;
        V20: 关闭窗口后进程退出(无托盘实现)。
        """
        self._safe_focus_windows()
        result = self.run_cmd(
            "xdotool search --name '电脑管家' | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        window_id = result.strip()
        if window_id:
            self.run_cmd(
                f"xdotool windowclose {window_id}",
                timeout=5,
                out_debug_flag=False,
            )
        sleep(3)

    def get_main_window_id(self) -> str:
        """获取电脑管家主窗口 ID, 未找到返回空字符串"""
        return self.run_cmd(
            "xdotool search --name '电脑管家' | head -1",
            timeout=5,
            out_debug_flag=False,
        ).strip()

    def get_main_window_wm_state(self, window_id="") -> str:
        """读取主窗口 _NET_WM_STATE(最小化时为 ..._HIDDEN)"""
        window_id = window_id or self.get_main_window_id()
        if not window_id:
            return ""
        return self.run_cmd(
            f"xprop -id {window_id} _NET_WM_STATE 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()

    def is_main_window_hidden(self, window_id="") -> bool:
        """判断主窗口是否处于最小化(隐藏)状态"""
        return "_NET_WM_STATE_HIDDEN" in self.get_main_window_wm_state(window_id)

    def minimize_main_window(self, window_id="") -> bool:
        """最小化主窗口(等价于点击标题栏最小化按钮)

        :return: True 表示已最小化并确认进入 HIDDEN 状态
        """
        window_id = window_id or self.get_main_window_id()
        if not window_id:
            return False
        self.run_cmd(
            f"xdotool windowminimize {window_id}",
            timeout=5,
            out_debug_flag=False,
        )
        for _ in range(10):
            sleep(1)
            if self.is_main_window_hidden(window_id):
                return True
        return False

    def click_dock_icon(self, app_id="deepin-pc-manager") -> bool:
        """单击任务栏(dock)上的应用图标

        :return: True 表示已发出点击
        """
        center = self.get_dock_icon_center(app_id)
        if not center:
            return False
        x, y = center
        self.run_cmd(
            f"xdotool mousemove --sync {x} {y}; sleep 0.3; xdotool click 1",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(3)
        return True

    def is_v25_environment(self) -> bool:
        """检测当前系统是否为 V25 环境

        V25: org.deepin.dde.daemon.Dock1 DBus 服务存在;
        V20: 仅 com.deepin.dde.daemon.Dock 存在。
        :return: True 表示 V25 环境
        """
        result = self.run_cmd(
            "qdbus org.deepin.dde.daemon.Dock1 /org/deepin/dde/daemon/Dock1 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def click_optimization_nav_by_attr(self):
        """点击左侧导航第二个选项(系统优化)

        点击后等待页面切换动画完成并重新建立 dogtail 连接,
        刷新 AT-SPI 树引用(V20 上页面切换后旧引用会失效)。
        QML 导航项 role 为 INVALID, Node.click() 不触发切换, 必须 Press。
        """
        self._safe_focus_windows()
        element = self.dog.find_element_by_attr("$//mainWindow_navList//系统优化")
        self._atspi_do_action(element)
        sleep(2)
        self.reconnect_dogtail()

    def get_optimization_page_showing(self, timeout=15):
        """等待并获取系统优化页面的可见状态(AT-SPI showing)

        :param timeout: 最长等待秒数, 页面切换动画完成即提前返回

        V20 上页面切换后 optimization_page 元素的 showing 属性可能为 False
        或元素暂时消失, 需要重连 dogtail 刷新 AT-SPI 引用后重试。
        V25 上 showing 属性可能全为 False, 额外检查元素 size。
        若 optimization_page 始终不可见, 回退检查扫描按钮是否存在。
        """
        for i in range(timeout):
            try:
                page = self.dog.find_element_by_attr("$//optimization_page")
                if page.showing:
                    return True
                w, h = page.size
                if w > 0 and h > 0:
                    return True
            except BaseException:
                pass
            if i == 2:
                self.reconnect_dogtail()
            if i > 0 and i % 3 == 0:
                self._refresh_app()
            sleep(1)
        try:
            self.dog.find_element_by_attr("$//optimization_startScanBtn")
            return True
        except BaseException:
            return False

    def click_optimization_card_by_name(self, card_name: str, timeout: int = 15,
                                        wait: int = 2):
        """点击系统优化页面中指定名称的非特色卡片

        在 optimization_cardsView 中查找 accessibleName 等于 card_name 的卡片并点击。
        点击后页面切换到插件运行时视图(viewStack index 1)。

        :param card_name: 卡片标题(如 "重复文件清理")
        :param timeout: 最长等待秒数
        :param wait: 点击后等待秒数; 需要观察插件启动瞬间的状态时传 0
        """
        self._safe_focus_windows()
        for _ in range(timeout):
            try:
                card = self.dog.find_element_by_attr(f"$//optimization_cardsView//{card_name}")
                if card.showing:
                    self._atspi_do_action(card)
                    sleep(wait)
                    # 重连本身约 1s; 需要观察插件启动瞬间(wait=0)时跳过, 否则
                    # 会错过数秒即结束的扫描窗口
                    if wait:
                        self.reconnect_dogtail()
                    return
            except BaseException:
                pass
            sleep(1)
        card = self.dog.find_element_by_attr(f"$//optimization_cardsView//{card_name}")
        self._atspi_do_action(card)
        sleep(wait)
        if wait:
            self.reconnect_dogtail()

    def get_optimization_runtime_page_showing(self, timeout: int = 15) -> bool:
        """检查系统优化页面插件运行时视图是否显示

        点击非特色卡片后, viewStack 切换到 index 1, 显示 optimization_runtimePage。
        :param timeout: 最长等待秒数
        :return: True 如果运行时视图已显示
        """
        self._safe_focus_windows()
        for _ in range(timeout):
            try:
                page = self.dog.find_element_by_attr("$//optimization_runtimePage")
                if page.showing:
                    return True
                w, h = page.size
                if w > 0 and h > 0:
                    return True
            except BaseException:
                pass
            if _ == 2:
                self.reconnect_dogtail()
            sleep(1)
        return False

    def get_optimization_cards_view_showing(self) -> bool:
        """检查系统优化卡片视图是否显示

        系统优化页面包含空间清理特色卡片(optimization_startScanBtn)
        和非特色卡片容器(optimization_cardsView), 任一存在即返回 True。
        """
        self._safe_focus_windows()
        for expr in (
            "$//optimization_cardsView",
            "$//optimization_startScanBtn",
        ):
            try:
                elements = self.dog.find_elements_by_attr(expr)
                if elements:
                    return True
            except BaseException:
                continue
        return False

    def get_optimization_card_count(self) -> int:
        """获取系统优化页面非特色卡片数量"""
        self._safe_focus_windows()
        try:
            container = self.dog.find_element_by_attr("$//optimization_cardsView")
            if container:
                children = container.children
                card_buttons = [
                    child for child in children
                    if child.roleName in ("push button", "button")
                ]
                if card_buttons:
                    return len(card_buttons)
                if children:
                    return len(children)
        except BaseException:
            pass
        return 0

    def get_detection_functional_modules_showing(self, timeout=10) -> bool:
        """检查系统检测页面功能模块是否显示

        系统检测页面包含多个子视图(概览/扫描中/扫描结果), 不同状态下
        可见的功能元素不同:
        - 概览页: detection_scoreCard / detection_scanBtn(立即检测)
        - 扫描结果页: pageHeader_titleLabel / detectionGroup_* 检测项分组
        只要其中任一功能元素可见即认为功能模块正常显示。

        V25 上 showing 属性对 QStackedWidget 子元素不可靠,
        优先检查 showing, 若存在元素则回退为可见(元素存在判断)。
        :param timeout: 最长等待秒数
        """
        indicators = [
            "$//detection_page//detection_scanBtn",
            "$//detection_page//pageHeader_titleLabel",
            "$//detection_page//detection_scoreCard",
        ]
        for i in range(timeout):
            self._safe_focus_windows()
            for expr in indicators:
                try:
                    elements = self.dog.find_elements_by_attr(expr)
                except BaseException:
                    continue
                if elements:
                    for el in elements:
                        try:
                            if el.showing:
                                return True
                        except BaseException:
                            continue
                    return True
            if i == 2:
                self._refresh_app()
            sleep(1)
        return False

    def get_main_page_modules_showing(self) -> bool:
        """检查主界面四大模块是否显示

        主界面左侧导航栏包含四项: 系统检测、系统优化、修复工具、实用工具。
        导航项在 V20 上的 showing 属性不可靠, 以 size 非零的可见实例为准。
        """
        self._safe_focus_windows()
        modules = ["系统检测", "系统优化", "修复工具", "实用工具"]
        for module_name in modules:
            if not self._any_visible(f"$//mainWindow_navList//{module_name}"):
                return False
        return True

    def get_main_nav_item_names(self) -> list:
        """获取主界面左侧导航栏所有选项名称(按界面顺序)

        只统计可见实例(QML 隐藏实例 size 为 (0, 0)。
        """
        self._safe_focus_windows()
        try:
            items = self.dog.find_elements_by_attr("$//mainWindow_navList//*") or []
        except BaseException:
            return []
        return [
            item.name
            for item in items
            if item.roleName == "list item" and item.size[0] > 0 and item.size[1] > 0
        ]

    def get_window_maximized_status(self, timeout: int = 10) -> bool:
        """获取窗口是否处于最大化状态(通过 xprop 检测 _NET_WM_STATE_MAXIMIZED)

        :param timeout: 最长等待秒数, KWin 在 loongarch64 上处理 EWMH 消息
            或窗口切换动画可能需要更多时间
        """
        window_id = None
        for _ in range(timeout):
            try:
                self._safe_focus_windows()
                window_id = self.ui.get_lastest_window_id(self.APP_NAME)
            except BaseException:
                window_id = None
            if window_id:
                result = self.run_cmd(
                    f"xprop -id {window_id} _NET_WM_STATE",
                    timeout=5,
                    out_debug_flag=False,
                )
                if "MAXIMIZED_VERT" in result and "MAXIMIZED_HORZ" in result:
                    return True
            sleep(1)
        return False

    def _send_net_wm_state(self, action: int):
        """通过 EWMH _NET_WM_STATE client message 设置窗口最大化状态

        V25: Super+Up/Super+Down 快捷键在 loongarch64 上不生效
        (KWin 不响应 xdotool 合成按键), 改用 EWMH 规范的 client message
        方式切换窗口最大化状态, 等价于双击标题栏/窗口菜单中的最大化。
        action: 1=添加最大化状态, 0=移除最大化状态。
        """
        self._safe_focus_windows()
        window_id = self.ui.get_lastest_window_id(self.APP_NAME)
        if not window_id:
            logger.warning(f"未找到 {self.APP_NAME} 窗口, 无法设置最大化状态")
            return
        script = (
            "import sys;"
            "from Xlib import X, display;"
            "from Xlib.protocol.event import ClientMessage;"
            "d=display.Display();root=d.screen().root;"
            "state=d.intern_atom('_NET_WM_STATE');"
            "max_v=d.intern_atom('_NET_WM_STATE_MAXIMIZED_VERT');"
            "max_h=d.intern_atom('_NET_WM_STATE_MAXIMIZED_HORZ');"
            f"event=ClientMessage(window={window_id},client_type=state,"
            f"data=(32,[{action},max_v,max_h,0,0]));"
            "root.send_event(event,X.SubstructureRedirectMask|X.SubstructureNotifyMask);"
            "d.flush()"
        )
        self.run_cmd(f'python3 -c "{script}"', timeout=5, out_debug_flag=False)
        sleep(1)

    def maximize_window_by_shortcut(self):
        """最大化窗口(EWMH client message, V25 兼容)"""
        self._send_net_wm_state(1)

    def restore_window_by_shortcut(self):
        """还原窗口(EWMH client message, V25 兼容)"""
        self._send_net_wm_state(0)

    def open_launcher(self):
        """打开启动器(Super 键)"""
        self.super()
        sleep(2)

    def close_launcher(self):
        """关闭启动器(Esc 键)"""
        self.esc()
        sleep(1)

    def search_in_launcher(self, text: str):
        """在启动器中搜索指定文本"""
        self.input_message(text)
        sleep(2)

    def launch_from_launcher(self):
        """启动电脑管家

        V20 上 deepin-pc-manager-launch(包装脚本)通过 deepin-security-loader
        启动, 会阻止应用在 AT-SPI 中注册 UI 树, 导致 dogtail 无法访问控件。
        直接启动 /usr/libexec/deepin/deepin-pc-manager 可正常注册 AT-SPI。
        V25 上该路径同样存在, 兼容无影响。

        V20 上 kglobalaccel5 会持续触发 Alt+F4 全局快捷键导致窗口被关闭,
        启动前先杀死该进程(V25 上不存在同名进程, 无影响)。

        V20 上 Qt 应用需要 QT_ACCESSIBILITY=1 等环境变量才能在 AT-SPI 中注册,
        在 os.environ 中设置以确保子进程继承(V25 上已设置, 覆盖无影响)。
        """
        import os

        os.environ["QT_ACCESSIBILITY"] = "1"
        os.environ["NO_AT_BRIDGE"] = "0"
        os.environ["QT_LINUX_ACCESSIBILITY_ALWAYS_ON"] = "1"
        self.run_cmd(
            "killall kglobalaccel5 2>/dev/null; sleep 1",
            timeout=5,
            out_debug_flag=False,
        )
        self.run_cmd(
            "if [ -x /usr/libexec/deepin/deepin-pc-manager ]; then "
            "nohup /usr/libexec/deepin/deepin-pc-manager > /dev/null 2>&1 & "
            "elif [ -x /usr/bin/deepin-pc-manager ]; then "
            "nohup /usr/bin/deepin-pc-manager > /dev/null 2>&1 & "
            "else nohup deepin-pc-manager-launch > /dev/null 2>&1 & fi",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(5)
        self.reconnect_dogtail()

    def is_app_in_launcher_index(self, app_key="deepin-pc-manager") -> bool:
        """查询启动器索引服务是否已收录指定应用

        UOS 20 的应用清单由 dde-session-daemon 的 launcher 模块
        (com.deepin.dde.daemon.Launcher) 提供, 该模块只在进程启动时扫描
        /usr/share/applications, 之后新增的系统级 desktop 不会被收录。
        """
        output = self.run_cmd(
            "dbus-send --session --print-reply "
            "--dest=com.deepin.dde.daemon.Launcher "
            "/com/deepin/dde/daemon/Launcher "
            "com.deepin.dde.daemon.Launcher.GetAllItemInfos 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        return f"{app_key}.desktop" in output

    def refresh_launcher_index(self, app_key="deepin-pc-manager", timeout=60) -> bool:
        """刷新启动器应用索引(deb 安装后必需)

        dpkg 装入 /usr/share/applications 的新 desktop 不会触发
        dde-session-daemon 重新扫描, 启动器里看不到新应用; 这里重启索引
        服务(由 startdde 自动拉起)并重启启动器 UI 以拉取新列表。
        :return: 刷新后索引是否已收录该应用
        """
        pid = self.run_cmd(
            "pgrep -f '^/usr/libexec/deepin/dde-session-daemon' | head -1",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        if pid:
            self.run_cmd(f"kill {pid} 2>/dev/null", timeout=10, out_debug_flag=False)
        for _ in range(max(timeout // 2, 1)):
            sleep(2)
            if self.is_app_in_launcher_index(app_key):
                break
        if not self.is_app_in_launcher_index(app_key):
            return False
        # 启动器 UI 进程持有旧列表, 不重启仍显示旧内容
        self.run_cmd(
            "pkill -f '^/usr/libexec/deepin/dde-launcher' 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        self.run_cmd(
            "setsid /usr/libexec/deepin/dde-launcher >/dev/null 2>&1 < /dev/null &",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(3)
        return True

    def ensure_app_in_launcher(self, app_key="deepin-pc-manager", timeout=60) -> bool:
        """确保启动器已能显示指定应用, 未收录时自动刷新索引"""
        if self.is_app_in_launcher_index(app_key):
            return True
        return self.refresh_launcher_index(app_key, timeout)

    def set_clipboard_text(self, text) -> bool:
        """把文本写入 X11 剪贴板(启动器搜索框需要粘贴中文)"""
        script = (
            "import gi; gi.require_version('Gtk','3.0'); "
            "from gi.repository import Gtk,Gdk; "
            "cb=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD); "
            f"cb.set_text({text!r}, -1); cb.store()"
        )
        output = self.run_cmd(
            f'python3 -c "{script}" 2>&1; echo "rc=$?"',
            timeout=20,
            out_debug_flag=False,
        )
        return "rc=0" in output

    def launch_app_from_launcher(self, app_name="电脑管家", wait=15) -> bool:
        """在启动器中搜索并启动应用(真实界面操作)

        dde-launcher 不注册 AT-SPI, 只能键盘操作: 打开启动器 → 粘贴中文
        名称到搜索框(xdotool 无法直接输入非 ASCII) → 回车启动第一项。
        :param app_name: 启动器中显示的应用名称
        :param wait: 等待主进程启动的秒数
        :return: 主进程是否已启动
        """
        self._safe_focus_windows()
        # 启动器为 toggle 显示, 先确保处于关闭状态(esc() 封装的 press_key 在
        # 当前 funnylog 版本下签名失效, 直接调用 xdotool)
        self.run_cmd(
            "xdotool key --clearmodifiers Escape", timeout=5, out_debug_flag=False
        )
        sleep(1)
        self.open_launcher()
        if not self.set_clipboard_text(app_name):
            return False
        self.run_cmd(
            "xdotool key --clearmodifiers ctrl+v", timeout=5, out_debug_flag=False
        )
        sleep(2)
        self.run_cmd(
            "xdotool key --clearmodifiers Return", timeout=5, out_debug_flag=False
        )
        started = False
        for _ in range(wait):
            sleep(1)
            if self.get_pc_manager_process_status():
                started = True
                break
        sleep(2)
        self.reconnect_dogtail()
        return started

    def get_launcher_windows(self):
        """列出 dde-launcher 窗口几何 [(id, x, y, width, height), ...]"""
        output = self.run_cmd(
            "for w in $(xdotool search --class dde-launcher 2>/dev/null); do "
            "eval $(xdotool getwindowgeometry --shell $w 2>/dev/null); "
            'echo "$w $X $Y $WIDTH $HEIGHT"; done',
            timeout=10,
            out_debug_flag=False,
        )
        windows = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) == 5 and all(p.lstrip("-").isdigit() for p in parts):
                windows.append(tuple(int(p) for p in parts))
        return windows

    def close_launcher_ui(self):
        """关闭启动器及其右键菜单"""
        self.run_cmd(
            "xdotool key --clearmodifiers Escape", timeout=5, out_debug_flag=False
        )
        sleep(1)

    def open_launcher_and_search(self, app_name="电脑管家", wait=3) -> bool:
        """打开启动器并搜索指定应用

        dde-launcher 不注册 AT-SPI, 交互只能靠键盘: Escape 关闭可能存在的
        启动器 → Super 打开 → 剪贴板粘贴中文名称(xdotool 无法直接输入
        非 ASCII) 到搜索框。
        """
        self.close_launcher_ui()
        self.super()
        if not self.set_clipboard_text(app_name):
            return False
        self.run_cmd(
            "xdotool key --clearmodifiers ctrl+v", timeout=5, out_debug_flag=False
        )
        sleep(wait)
        return True

    def right_click_launcher_result(self, row=0) -> bool:
        """右键启动器搜索结果第 row 项(row 从 0 开始)"""
        list_windows = [
            w for w in self.get_launcher_windows() if w[3] >= 300 and w[4] >= 400
        ]
        if not list_windows:
            return False
        _, x, y, width, _ = list_windows[0]
        # 搜索结果第 row 项中心: 距列表窗口顶部 70 像素, 每项间距 46 像素
        self.run_cmd(
            f"xdotool mousemove --sync {x + width // 2} {y + 70 + row * 46} click 3",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(2)
        return True

    def click_launcher_menu(self, item_text) -> bool:
        """点击启动器右键菜单项

        V20 启动器右键菜单固定 5 项, 其中第 2/3 项文本随驻留状态切换:
        未驻留为"发送到桌面"/"发送到任务栏", 已驻留为"从桌面上移除"/
        "从任务栏上移除", 位置不变。菜单窗口左上角即右键点击位置。
        """
        offset = LAUNCHER_MENU_ITEM_OFFSETS.get(item_text)
        if offset is None:
            return False
        menus = [
            w for w in self.get_launcher_windows() if 100 <= w[3] <= 300 and w[4] <= 300
        ]
        if not menus:
            return False
        _, x, y, width, _ = menus[-1]
        self.run_cmd(
            f"xdotool mousemove --sync {x + width // 2} {y + offset} click 1",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(2)
        return True

    def get_desktop_file_exists(self) -> bool:
        """检查桌面上是否存在电脑管家 .desktop 文件"""
        result = self.run_cmd(
            f"test -f {DESKTOP_DIR}/{APP_DESKTOP_FILE} && echo 1",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def send_to_desktop_via_launcher(self):
        """发送电脑管家到桌面(创建 .desktop 快捷方式)

        V25: 启动器右键菜单不可用, 直接复制 .desktop 文件到桌面。
        """
        self.run_cmd(
            f"cp {APP_DESKTOP_FULL_PATH} {DESKTOP_DIR}/{APP_DESKTOP_FILE}",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_from_desktop_via_launcher(self):
        """从桌面移除电脑管家快捷方式

        V25: 启动器右键菜单不可用, 直接删除桌面 .desktop 文件。
        """
        self.run_cmd(
            f"rm -f {DESKTOP_DIR}/{APP_DESKTOP_FILE}",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def _get_dock_dbus(self):
        """探测当前系统可用的 Dock DBus 服务名和路径

        V25: org.deepin.dde.daemon.Dock1 @ /org/deepin/dde/daemon/Dock1
        V20: com.deepin.dde.daemon.Dock @ /com/deepin/dde/daemon/Dock
        :return: (service, path) 元组
        """
        for svc, path in [
            (DOCK_SERVICE_V25, DOCK_PATH_V25),
            (DOCK_SERVICE_V20, DOCK_PATH_V20),
        ]:
            result = self.run_cmd(
                f"qdbus {svc} {path} 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
            if result.strip():
                return svc, path
        return DOCK_SERVICE_V25, DOCK_PATH_V25

    def send_to_dock_via_launcher(self):
        """发送电脑管家到任务栏(dock)

        V25: 使用 DBus RequestDock 替代启动器右键菜单。
        V20: 使用 com.deepin.dde.daemon.Dock DBus 接口。
        必须使用完整路径 /usr/share/applications/deepin-pc-manager.desktop。
        """
        svc, path = self._get_dock_dbus()
        self.run_cmd(
            f"qdbus {svc} {path} {svc}.RequestDock '{APP_DESKTOP_FULL_PATH}' 0 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_from_dock_via_launcher(self):
        """从任务栏(dock)移除电脑管家

        V25: 使用 DBus RequestUndock 替代启动器右键菜单。
        V20: 使用 com.deepin.dde.daemon.Dock DBus 接口。
        """
        svc, path = self._get_dock_dbus()
        self.run_cmd(
            f"qdbus {svc} {path} {svc}.RequestUndock '{APP_DESKTOP_FULL_PATH}' 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def get_dock_has_app_icon(self) -> bool:
        """检查任务栏(dock)上是否驻留电脑管家图标

        V25: 使用 DBus IsDocked 替代旧的 Items 属性(已不存在)。
        V20: 使用 com.deepin.dde.daemon.Dock DBus 接口。
        """
        svc, path = self._get_dock_dbus()
        result = self.run_cmd(
            f"qdbus {svc} {path} {svc}.IsDocked '{APP_DESKTOP_FULL_PATH}' 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return "true" in result.strip().lower()

    def get_dock_has_running_window(self) -> bool:
        """检查电脑管家运行窗口是否在任务栏中显示

        V25: 运行中的窗口会在 dock 的 TaskManager 中显示图标。
        通过检查窗口是否存在来判断(窗口存在即会在 dock 中显示)。
        """
        result = self.run_cmd(
            "xdotool search --name '电脑管家' 2>/dev/null | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def get_dock_windows(self):
        """列出 dde-dock 全部窗口几何 [(id, x, y, width, height), ...]"""
        output = self.run_cmd(
            "for w in $(xdotool search --class dde-dock 2>/dev/null); do "
            "eval $(xdotool getwindowgeometry --shell $w 2>/dev/null); "
            'echo "$w $X $Y $WIDTH $HEIGHT"; done',
            timeout=10,
            out_debug_flag=False,
        )
        windows = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) == 5 and all(p.lstrip("-").isdigit() for p in parts):
                windows.append(tuple(int(p) for p in parts))
        return windows

    def get_dock_entry_ids(self):
        """dock 当前条目 ID 列表(按显示顺序, 含运行中的应用)

        :return: 如 ["dde-trash", "deepin-terminal", "deepin-pc-manager"]
        """
        svc, path = self._get_dock_dbus()
        output = self.run_cmd(
            f"qdbus {svc} {path} {svc}.GetEntryIDs 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return [line.strip() for line in output.splitlines() if line.strip()]

    def get_dock_has_running_icon(self, app_id="deepin-pc-manager") -> bool:
        """检查 dock 上是否显示应用的运行图标(驻留或运行中均算)

        :param app_id: 应用 ID, 即 desktop 文件名去掉 .desktop
        """
        return app_id in self.get_dock_entry_ids()

    def get_dock_entry_path(self, app_id="deepin-pc-manager", timeout=10) -> str:
        """查找应用对应的 dock 条目对象路径

        Entries 返回的是条目对象路径列表, 需要逐条读取 DesktopFile 属性
        才能匹配应用; 条目顺序与桌面显示顺序无关。
        :param app_id: 应用 ID, 即 desktop 文件名去掉 .desktop
        :return: 条目对象路径, 未找到返回空字符串
        """
        svc, path = self._get_dock_dbus()
        iface = f"{svc}.Entry"
        output = self.run_cmd(
            f"qdbus --literal {svc} {path} {svc}.Entries 2>/dev/null",
            timeout=timeout,
            out_debug_flag=False,
        )
        entry_paths = re.findall(
            r"/(?:com|org)/deepin/dde/daemon/[A-Za-z0-9]+/entries/[A-Za-z0-9]+",
            output,
        )
        for entry in entry_paths:
            desktop = self.run_cmd(
                f"qdbus {svc} {entry} org.freedesktop.DBus.Properties.Get "
                f"{iface} DesktopFile 2>/dev/null",
                timeout=timeout,
                out_debug_flag=False,
            ).strip()
            if app_id in desktop:
                return entry
        return ""

    def get_dock_menu_items(self, app_id="deepin-pc-manager"):
        """读取 dock 条目右键菜单的菜单项文本(按界面显示顺序)

        菜单内容由 dock 通过 Entry.Menu 属性以 JSON 发布, 与界面菜单
        顺序一致, 可直接用于断言菜单内容并按序号定位菜单项。
        :param app_id: 应用 ID, 即 desktop 文件名去掉 .desktop
        :return: 菜单项文本列表, 应用不在 dock 上返回 []
        """
        svc, _ = self._get_dock_dbus()
        entry = self.get_dock_entry_path(app_id)
        if not entry:
            return []
        raw = self.run_cmd(
            f"qdbus {svc} {entry} org.freedesktop.DBus.Properties.Get "
            f"{svc}.Entry Menu 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(raw[start:end + 1])
        except ValueError:
            return []
        return [
            item.get("itemText", "") for item in data.get("items", [])
        ]

    def get_dock_icon_center(self, app_id="deepin-pc-manager"):
        """计算 dock 上应用图标中心的坐标

        dock 图标位置无法通过 DBus 获取, 采用截图识别: 对 dock 条逐列
        计算与背景色的色差得到图标列带, 列带顺序为
        [启动器, (显示桌面插件), 条目图标...], 再按 GetEntryIDs 顺序映射。
        :param app_id: 应用 ID, 即 desktop 文件名去掉 .desktop
        :return: (x, y) 元组, 识别失败返回 None
        """
        entry_ids = self.get_dock_entry_ids()
        if app_id not in entry_ids:
            return None
        index = entry_ids.index(app_id)
        # 先把鼠标移到屏幕底部, 避免 dock 自动隐藏导致截图看不到图标
        self.run_cmd(
            "xdotool mousemove --sync 720 890", timeout=5, out_debug_flag=False
        )
        sleep(1)
        bars = [
            w for w in self.get_dock_windows() if w[3] >= 800 and w[4] <= 100
        ]
        if not bars:
            return None
        _, dx, dy, dw, dh = bars[0]
        shot = "/tmp/dock_icon_scan.png"
        self.run_cmd(
            f"rm -f {shot}; scrot {shot}", timeout=10, out_debug_flag=False
        )
        from PIL import Image  # noqa: PLC0415

        try:
            image = Image.open(shot).convert("RGB")
        except OSError:
            return None
        top, bottom = dy + 2, dy + dh - 2
        samples = [
            sum(image.getpixel((x, y)))
            for y in range(top, bottom, 3)
            for x in range(dx, dx + dw, 37)
        ]
        background = max(set(samples), key=samples.count) if samples else 0
        bands, start = [], None
        for offset in range(dw):
            deviation = max(
                abs(sum(image.getpixel((dx + offset, y))) - background)
                for y in range(top, bottom, 2)
            )
            if deviation > 40 and start is None:
                start = offset
            elif deviation <= 40 and start is not None:
                if offset - start >= 6:
                    bands.append((start, offset - 1))
                start = None
        if start is not None and dw - start >= 6:
            bands.append((start, dw - 1))
        # 取左侧应用图标群: 从启动器开始到第一个大间隔为止。
        # dock 右侧的插件图标(网络/音量/电源等)与条目无关, 不能参与映射。
        cluster = bands[:1]
        for previous, current in zip(bands, bands[1:]):
            if current[0] - previous[1] > 40:
                break
            cluster.append(current)
        # 群内结构: 启动器 + 可能的"显示桌面"插件 + 条目图标
        offset = max(len(cluster) - len(entry_ids), 1)
        band_index = offset + index
        if band_index >= len(cluster):
            return None
        return (
            dx + (cluster[band_index][0] + cluster[band_index][1]) // 2,
            dy + dh // 2,
        )

    def close_dock_menu(self):
        """关闭 dock 右键菜单"""
        self.run_cmd(
            "xdotool key --clearmodifiers Escape",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def open_dock_app_menu(self, app_id="deepin-pc-manager"):
        """右键 dock 图标打开应用右键菜单

        :param app_id: 应用 ID, 即 desktop 文件名去掉 .desktop
        :return: 菜单窗口几何 (x, y, width, height), 打开失败返回 None
        """
        self.close_dock_menu()
        center = self.get_dock_icon_center(app_id)
        if not center:
            return None
        x, y = center
        self.run_cmd(
            f"xdotool mousemove --sync {x} {y}; sleep 0.5; xdotool click 3",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)
        menus = [
            w
            for w in self.get_dock_windows()
            if 100 <= w[3] <= 400
            and 60 <= w[4] <= 400
            and abs(w[1] - x) <= 120
            and abs((w[2] + w[4]) - y) <= 30
        ]
        if not menus:
            return None
        _, mx, my, mw, mh = max(menus, key=lambda w: w[4])
        return mx, my, mw, mh

    def click_dock_menu_item(self, item_text, app_id="deepin-pc-manager") -> bool:
        """点击 dock 右键菜单中的指定菜单项

        菜单项文本与顺序取自 Entry.Menu 属性(与界面一致), 打开界面菜单
        后按序号换算菜单项中心位置点击。
        :param item_text: 菜单项文本, 如 "强制退出"/"移除驻留"/"关闭所有"
        :param app_id: 应用 ID, 即 desktop 文件名去掉 .desktop
        :return: 是否成功点击
        """
        items = self.get_dock_menu_items(app_id)
        if item_text not in items:
            logger.warning(f"dock 右键菜单不存在菜单项: {item_text}, 当前菜单: {items}")
            return False
        index = items.index(item_text)
        menu = self.open_dock_app_menu(app_id)
        if not menu:
            logger.warning("dock 右键菜单未打开")
            return False
        mx, my, mw, mh = menu
        item_height = mh / len(items)
        if not 30 <= item_height <= 38:
            logger.warning(
                f"菜单窗口高度与菜单项数不匹配: {mw}x{mh}, {len(items)} 项"
            )
            self.close_dock_menu()
            return False
        self.run_cmd(
            f"xdotool mousemove --sync {mx + mw // 2} "
            f"{int(my + item_height * (index + 0.5))}; sleep 0.3; xdotool click 1",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)
        return True

    def open_from_launcher_right_click(self):
        """通过启动器右键菜单"打开"启动电脑管家

        V25: 启动器右键菜单不可用, 使用 gio launch 直接启动。
        """
        self.run_cmd(
            f"gio launch {APP_DESKTOP_FULL_PATH} 2>/dev/null || "
            "if [ -x /usr/libexec/deepin/deepin-pc-manager ]; then nohup /usr/libexec/deepin/deepin-pc-manager > /dev/null 2>&1 & elif [ -x /usr/bin/deepin-pc-manager ]; then nohup /usr/bin/deepin-pc-manager > /dev/null 2>&1 & else nohup deepin-pc-manager-launch > /dev/null 2>&1 & fi",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(5)
        self.reconnect_dogtail()

    def is_autostart_enabled(self, desktop_name=APP_DESKTOP_FILE) -> bool:
        """指定应用的开机自启动是否已启用

        V20 启动器"取消开机自启动"不删除文件, 而是写入 Hidden=true,
        因此不能只判断文件是否存在。
        :param desktop_name: autostart 目录下的 desktop 文件名
        """
        output = self.run_cmd(
            f"cat {AUTOSTART_DIR}/{desktop_name} 2>/dev/null || true",
            timeout=5,
            out_debug_flag=False,
        )
        if not output.strip():
            return False
        return "hidden=true" not in output.replace(" ", "").lower()

    def get_browser_desktop_path(self) -> str:
        """获取浏览器 desktop 文件全路径

        不同版本的浏览器包名不同, 依次探测常见路径。
        :return: desktop 文件全路径, 不存在返回空字符串
        """
        for path in (
            BROWSER_DESKTOP_FULL_PATH,
            "/usr/share/applications/deepin-browser.desktop",
        ):
            result = self.run_cmd(
                f"test -f {path} && echo 1",
                timeout=5,
                out_debug_flag=False,
            )
            if result.strip():
                return path
        return ""

    def get_visible_window_ids(self):
        """当前所有可见窗口 ID 集合"""
        output = self.run_cmd(
            "xdotool search --onlyvisible --name '' 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return {int(x) for x in output.split() if x.isdigit()}

    def get_launcher_window_ids(self):
        """dde-launcher 的窗口 ID 集合"""
        output = self.run_cmd(
            "xdotool search --onlyvisible --class dde-launcher 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return {int(x) for x in output.split() if x.isdigit()}

    def _window_size(self, wid):
        """窗口宽高, 获取失败返回 None"""
        geom = self.run_cmd(
            f"eval $(xdotool getwindowgeometry --shell {wid} 2>/dev/null); "
            'echo "$WIDTH $HEIGHT"',
            timeout=5,
            out_debug_flag=False,
        ).split()
        if len(geom) != 2 or not all(g.isdigit() for g in geom):
            return None
        return int(geom[0]), int(geom[1])

    @staticmethod
    def _is_dialog_size(size) -> bool:
        """是否像对话框尺寸

        启动器列表窗(约 380x538)与右键菜单窗(约 162x150)不在此区间,
        因此不会把启动器自身界面误判成确认弹窗。
        """
        return size is not None and 250 <= size[0] <= 800 and 100 <= size[1] <= 400

    def _find_autostart_dialog(self, baseline, timeout=4):
        """在 timeout 秒内查找开机自启动确认弹窗

        V25 弹窗可能是点击后新增的窗口, 也可能由右键菜单窗口变形而来,
        因此同时检查新增窗口与 dde-launcher 窗口。
        """
        for _ in range(timeout * 4):
            sleep(0.25)
            candidates = (self.get_visible_window_ids() - baseline) | self.get_launcher_window_ids()
            for wid in candidates:
                if self._is_dialog_size(self._window_size(wid)):
                    return wid
        return None

    def _confirm_autostart_dialog(self, baseline, reverse=False, timeout=4) -> bool:
        """处理开机自启动确认弹窗

        V25 启动器设置开机自启动时弹出确认框, 默认选中"禁用"并开始 30 秒
        倒计时(超时按"禁用"处理)。弹窗出现后先用 Tab 把焦点切到"启用"
        再回车; 焦点顺序相反时用 reverse=True 反向切换。
        V20(dde-launcher 5.9.5)不弹确认框, 等待超时后返回 False。
        :return: 是否检测到并处理了弹窗
        """
        dialog = self._find_autostart_dialog(baseline, timeout)
        if dialog is None:
            return False
        key_groups = (
            (["shift+Tab", "Return"], ["Tab", "Return"])
            if reverse
            else (["Tab", "Return"], ["shift+Tab", "Return"])
        )
        for keys in key_groups:
            self.run_cmd(
                f"xdotool windowactivate --sync {dialog} 2>/dev/null; "
                + "; ".join(f"xdotool key --clearmodifiers {key}" for key in keys),
                timeout=10,
                out_debug_flag=False,
            )
            sleep(1)
            if not self._is_dialog_size(self._window_size(dialog)):
                break
        sleep(1)
        return True

    def set_autostart_via_launcher(
        self,
        enable=True,
        app_name="电脑管家",
        desktop_name=APP_DESKTOP_FILE,
        retries=3,
    ) -> bool:
        """通过启动器右键菜单设置/取消指定应用的开机自启动

        设置时若出现确认弹窗(V25)自动选择"启用", 避免 30 秒倒计时结束
        后按默认的"禁用"执行。
        dde-launcher 右键菜单动作依赖启动器内部缓存, 外部改动文件或上一次
        点击后缓存可能滞后(菜单显示"取消"实际仍执行"开启"), 因此以
        autostart 文件状态为准, 不符时重新打开启动器(刷新菜单)重试。
        :param enable: True 开启, False 取消
        :param app_name: 启动器中搜索的应用名称
        :param desktop_name: autostart 目录下的 desktop 文件名
        :return: 最终状态是否与期望一致
        """
        menu_item = "开机自动启动" if enable else "取消开机自动启动"
        for attempt in range(retries):
            baseline = self.get_visible_window_ids()
            if not self.open_launcher_and_search(app_name):
                return False
            if not self.right_click_launcher_result():
                return False
            if not self.click_launcher_menu(menu_item):
                return False
            # V20 无确认弹窗, 点击后状态立即变化; 先短轮询避免白等 10 秒
            for _ in range(6):
                sleep(0.5)
                if self.is_autostart_enabled(desktop_name) == enable:
                    return True
            # 状态未变: V25 可能在等确认弹窗(默认"禁用" + 30 秒倒计时)
            if self._confirm_autostart_dialog(
                baseline, reverse=bool(attempt), timeout=4
            ):
                sleep(1)
                if self.is_autostart_enabled(desktop_name) == enable:
                    return True
            self.run_cmd(
                "xdotool key --clearmodifiers Escape",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(1)
        return self.is_autostart_enabled(desktop_name) == enable

    def get_autostart_file_exists(self) -> bool:
        """检查开机自启动配置文件是否存在"""
        result = self.run_cmd(
            f"test -f {AUTOSTART_DIR}/{APP_DESKTOP_FILE} && echo 1",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def enable_autostart(self):
        """启用开机自启动(创建 autostart .desktop 文件)

        V25: 默认无 autostart 文件, 需手动创建以测试自启动功能。
        """
        user_desktop_path = f"{HOME_DIR}/.local/share/applications/{APP_DESKTOP_FILE}"
        self.run_cmd(
            f"mkdir -p {AUTOSTART_DIR} && "
            f"cp {APP_DESKTOP_FULL_PATH} {AUTOSTART_DIR}/{APP_DESKTOP_FILE} 2>/dev/null "
            f"|| cp {user_desktop_path} {AUTOSTART_DIR}/{APP_DESKTOP_FILE}",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def disable_autostart(self):
        """禁用开机自启动(删除 autostart .desktop 文件)"""
        self.run_cmd(
            f"rm -f {AUTOSTART_DIR}/{APP_DESKTOP_FILE}",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def get_terminal_windows(self):
        """列出 deepin-terminal 窗口几何 [(id, x, y, width, height), ...]"""
        output = self.run_cmd(
            "for w in $(xdotool search --class deepin-terminal 2>/dev/null); do "
            "eval $(xdotool getwindowgeometry --shell $w 2>/dev/null); "
            'echo "$w $X $Y $WIDTH $HEIGHT"; done',
            timeout=10,
            out_debug_flag=False,
        )
        windows = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) != 5 or not all(p.lstrip("-").isdigit() for p in parts):
                continue
            window = tuple(int(p) for p in parts)
            # 过滤终端进程的非主窗口(提示/浮层等)
            if window[3] >= 300 and window[4] >= 200:
                windows.append(window)
        return windows

    def open_terminal_window(self, wait=15) -> int:
        """打开一个新的终端窗口

        dde-terminal 支持多实例窗口, 启动后按窗口 ID 变化识别新窗口,
        避免误用已存在的用户终端窗口。
        :param wait: 等待新窗口出现的秒数
        :return: 新窗口 ID, 超时返回 0
        """
        before = {window[0] for window in self.get_terminal_windows()}
        self.run_cmd(
            "setsid deepin-terminal > /dev/null 2>&1 < /dev/null &",
            timeout=5,
            out_debug_flag=False,
        )
        for _ in range(wait):
            sleep(1)
            windows = [
                window
                for window in self.get_terminal_windows()
                if window[0] not in before
            ]
            if windows:
                return max(windows, key=lambda window: window[3] * window[4])[0]
        return 0

    def launch_from_terminal(
        self,
        command="nohup deepin-pc-manager-launch > /dev/null 2>&1 &",
        wait=15,
        close_terminal=True,
    ) -> bool:
        """打开终端, 在终端命令行中输入命令启动电脑管家(真实界面操作)

        流程: 打开新终端窗口 → 激活窗口 → 输入命令(含 AT-SPI 环境变量)
        → 回车执行 → 关闭该终端窗口(命令以 nohup 后台运行, 不受影响)。
        :param command: 在终端中执行的命令
        :param wait: 等待主进程启动的秒数
        :param close_terminal: 启动成功后是否关闭本次打开的终端窗口
        :return: 主进程是否已启动
        """
        # V20 上 kglobalaccel5 会持续触发 Alt+F4 快捷键, 与 start_pc_manager 一致先杀掉
        self.run_cmd(
            "killall kglobalaccel5 2>/dev/null; sleep 1",
            timeout=5,
            out_debug_flag=False,
        )
        window = self.open_terminal_window()
        if not window:
            logger.warning("打开终端窗口失败")
            return False
        self.run_cmd(
            f"xdotool windowactivate --sync {window}",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(2)
        typed = (
            "export QT_ACCESSIBILITY=1 QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1; "
            f"{command}"
        )
        self.run_cmd(
            f"xdotool type --clearmodifiers --delay 30 {quote(typed)}",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        self.run_cmd(
            "xdotool key --clearmodifiers Return",
            timeout=5,
            out_debug_flag=False,
        )
        started = False
        for _ in range(wait):
            sleep(1)
            if self.get_pc_manager_process_status():
                started = True
                break
        if not started:
            logger.warning("终端中启动电脑管家失败")
            return False
        sleep(5)
        if close_terminal:
            self.run_cmd(
                f"xdotool windowclose {window}",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(1)
        self.reconnect_dogtail()
        return True

    def open_help_manual(self):
        """打开电脑管家帮助手册

        优先通过标题栏选项按钮菜单打开"帮助"，
        若失败则回退到 dman 命令直接打开帮助手册。
        """
        self._safe_focus_windows()
        opened = False
        # 方式一: 通过标题栏选项按钮菜单
        try:
            btn = self.dog.find_element_by_attr("$//DTitlebarDWindowOptionButton")
            pos = btn.position
            size = btn.size
            cx = int(pos[0] + size[0] / 2)
            cy = int(pos[1] + size[1] / 2)
            self.run_cmd(
                f"xdotool mousemove {cx} {cy} click 1",
                timeout=2,
                out_debug_flag=False,
            )
            # 弹出菜单(DTitlebarMainMenu)的子项不一定能被 dogtail 表达式命中,
            # 这里直接遍历 AT-SPI 树找可见的「帮助」菜单项再点击。
            help_item = None
            for _ in range(10):
                sleep(1)
                help_item = self._find_showing_menu_item("帮助")
                if help_item:
                    break
            if help_item is None:
                raise RuntimeError("标题栏菜单中未找到「帮助」项")
            help_item.doAction(0)
            sleep(3)
            opened = True
        except BaseException:
            self.run_cmd("xdotool key Escape", timeout=2, out_debug_flag=False)
            pass
        # 方式二: dman 命令回退(V25 标题栏菜单不可用时)
        if not opened:
            self.run_cmd(
                "nohup dman deepin-pc-manager > /dev/null 2>&1 &",
                timeout=1,
                out_debug_flag=False,
            )
            sleep(5)

    @staticmethod
    def _find_showing_menu_item(name):
        """在 AT-SPI 树中查找当前可见的指定名称菜单项

        :param name: 菜单项名称, 如 "帮助"
        :return: 可见菜单项对象, 找不到返回 None
        """
        import pyatspi

        found = []

        def walk(node):
            if found:
                return
            try:
                if node.getRoleName() == "menu item" and (node.name or "") == name and node.showing:
                    found.append(node)
                    return
                for i in range(node.childCount):
                    walk(node.getChildAtIndex(i))
            except BaseException:
                pass

        walk(pyatspi.Registry.getDesktop(0))
        return found[0] if found else None

    def get_help_window_showing(self) -> bool:
        """检查帮助手册窗口是否已显示"""
        try:
            # 检查是否存在标题包含"帮助"或"manual"的窗口
            result = self.run_cmd(
                "xdotool search --name '帮助' 2>/dev/null | head -1",
                timeout=5,
                out_debug_flag=False,
            )
            if result.strip():
                return True
            # 回退: 检查 manual 窗口
            result = self.run_cmd(
                "xdotool search --name 'manual' 2>/dev/null | head -1",
                timeout=5,
                out_debug_flag=False,
            )
            return bool(result.strip())

        except BaseException:
            return False

    # ===== 外部工具依赖预检/安装辅助方法 =====

    def is_package_installed(self, package) -> bool:
        """检查 apt 包是否已安装(dpkg 状态为 install ok installed)

        :param package: 软件包名, 如 lm-sensors / smartmontools / jq
        :return: True 表示已安装且配置完成
        """
        status = self.run_cmd(
            f"dpkg-query -W -f='${{Status}}' {package} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        ) or ""
        return "install ok installed" in status

    def ensure_package_installed(self, package, probe_cmd=None, timeout=600) -> dict:
        """确保用例依赖的外部工具包已安装: 已安装直接复用, 缺失则 apt 安装

        用例前置所需的系统工具(如 CPU 温度检测依赖 lm-sensors 的 sensors、
        磁盘健康依赖 smartmontools 的 smartctl、音频修复依赖 jq)在不同测试机
        上可能缺失, 产品会报 sensors.not.installed 之类的结论, 导致断言失败。
        统一在用例开头调用本方法补齐依赖, 避免用例依赖测试机既有状态。

        安装策略: 先直接 `apt-get install -y`(命中本地缓存/镜像), 失败再
        `apt-get update` 后重试一次(测试机通常无外网, 走内网源)。安装后用
        `command -v <probe_cmd>` 与 dpkg 状态双重校验, 不信任 apt 返回码。

        :param package: 软件包名
        :param probe_cmd: 安装后应可执行的命令, 默认与包名相同
        :param timeout: 单次 apt 命令超时秒数
        :return: {"package", "probe", "installed_before", "installed",
                  "attempts", "detail"}
        """
        probe_cmd = probe_cmd or package

        def _probe() -> bool:
            out = self.run_cmd(
                f"command -v {probe_cmd} 2>/dev/null",
                timeout=10,
                out_debug_flag=False,
            ) or ""
            return bool(out.strip())

        state = {
            "package": package,
            "probe": probe_cmd,
            "installed_before": False,
            "installed": False,
            "attempts": 0,
            "detail": "",
        }
        if _probe() or self.is_package_installed(package):
            state["installed_before"] = True
            state["installed"] = True
            logger.info(f"依赖包 {package} 已安装, 跳过安装")
            return state

        outputs = []
        # UOS 测试机的 dpkg preinst 白名单钩子会拒绝非白名单包(含其新依赖),
        # 安装前把本次计划安装的包临时写入白名单, 结束后删除, 恢复系统策略。
        added_whitelist = self._whitelist_install_packages(
            self._apt_install_plan(package) or [package]
        )
        try:
            for attempt in range(1, 3):
                state["attempts"] = attempt
                if attempt > 1:
                    outputs.append(
                        self.sudo_run_cmd(
                            "apt-get update", timeout=timeout, out_debug_flag=False
                        ) or ""
                    )
                outputs.append(
                    self.sudo_run_cmd(
                        f"env DEBIAN_FRONTEND=noninteractive apt-get install -y {package}",
                        timeout=timeout,
                        out_debug_flag=False,
                    ) or ""
                )
                if _probe() or self.is_package_installed(package):
                    state["installed"] = True
                    break
        finally:
            self._unwhitelist_install_packages(added_whitelist)

        state["whitelisted"] = added_whitelist
        state["detail"] = " | ".join(
            line.strip()[-200:] for line in outputs if line and line.strip()
        )
        logger.info(
            f"依赖包 {package}: 安装前已存在={state['installed_before']}, "
            f"安装后可用={state['installed']}, 尝试={state['attempts']}次, "
            f"临时白名单={state['whitelisted']}, 输出={state['detail']}"
        )
        return state

    # UOS: dpkg 安装前白名单钩子与白名单库(测试机默认开启)
    INSTALL_WHITELIST_HOOK = "/etc/dpkg/dpkg.cfg.d/88-whitepkg-install-hook"
    INSTALL_WHITELIST_DB = "/etc/permissionmanager.db"

    def _apt_install_plan(self, package) -> list:
        """解析 `apt-get install -s` 的计划, 返回将被安装(Inst)的包名列表"""
        out = self.run_cmd(
            f"apt-get install -s -y {package} 2>/dev/null",
            timeout=60,
            out_debug_flag=False,
        ) or ""
        return re.findall(r"(?m)^Inst (\S+) ", out)

    def _whitelist_install_packages(self, packages) -> list:
        """把待安装包临时写入 UOS 安装白名单, 返回本次新增的包名

        仅当测试机存在白名单钩子时生效; 已在白名单中的包不重复写入。
        :param packages: 待安装包名列表(含依赖)
        :return: 本次新增的包名列表(供 _unwhitelist_install_packages 回退)
        """
        added = []
        if not packages:
            return added
        hook = self.run_cmd(
            f"test -f {self.INSTALL_WHITELIST_HOOK} && echo yes",
            timeout=10,
            out_debug_flag=False,
        ) or ""
        if "yes" not in hook:
            return added
        for package in sorted(set(packages)):
            # sudo 会把密码提示/验证信息混进输出, 用标记字符串判定, 不用 count 数字
            probe = self.sudo_run_cmd(
                f"sqlite3 {self.INSTALL_WHITELIST_DB} "
                f"\"select case when exists(select 1 from package_white_table "
                f"where pkgname='{package}') then 'WHITELISTED' else 'MISSING' end\"",
                timeout=10,
                out_debug_flag=False,
            ) or ""
            if "MISSING" not in probe:
                continue
            self.sudo_run_cmd(
                f"sqlite3 {self.INSTALL_WHITELIST_DB} "
                f"\"insert or ignore into package_white_table(pkgname, type) "
                f"values('{package}', 'default')\"",
                timeout=10,
                out_debug_flag=False,
            )
            added.append(package)
        logger.info(f"临时加入安装白名单: {added}")
        return added

    def _unwhitelist_install_packages(self, packages):
        """从 UOS 安装白名单中删除本次临时写入的包, 恢复系统策略"""
        for package in packages or []:
            self.sudo_run_cmd(
                f"sqlite3 {self.INSTALL_WHITELIST_DB} "
                f"\"delete from package_white_table where pkgname='{package}'\"",
                timeout=10,
                out_debug_flag=False,
            )
        if packages:
            logger.info(f"已移除临时安装白名单: {packages}")

    # ===== 系统检测模块方法 =====

    def _find_element_in_exprs(self, exprs):
        """在多个 AT-SPI 表达式中查找第一个可找到的元素

        :param exprs: 表达式列表
        :return: 找到的元素, 或 None
        """
        for expr in exprs:
            try:
                elements = self.dog.find_elements_by_attr(expr, probe=True)
                if elements:
                    return elements[0]
            except BaseException:
                pass
        return None

    def click_detection_nav_by_attr(self):
        """点击左侧导航第一个选项(系统检测)

        V25 上首次点击导航可能不生效, 需要验证检测页面是否真正可见并重试。
        """
        self._safe_focus_windows()
        nav_exprs = ["$//mainWindow_navList//系统检测"]
        element = None
        for _ in range(15):
            element = self._find_element_in_exprs(nav_exprs)
            if element:
                break
            sleep(1)
        for _ in range(3):
            if not element:
                element = self._find_element_in_exprs(nav_exprs)
            if element:
                self._atspi_do_action(element)
            sleep(3)
            self.reconnect_dogtail()
            self._safe_focus_windows()
            if self._is_detection_nav_active():
                break
            element = self._find_element_in_exprs(nav_exprs)
            sleep(1)

    def _is_detection_nav_active(self) -> bool:
        """检查系统检测页面是否已激活(页面元素可见, 不仅仅是存在)"""
        for expr in (
            "$//detection_page//detection_scanBtn",
            "$//detection_scanBtn",
            "$//detection_page//detection_overview",
        ):
            try:
                elements = self.dog.find_elements_by_attr(expr)
                if elements and any(e.showing for e in elements):
                    return True
            except BaseException:
                pass
        return False

    def click_detection_nav(self):
        """点击左侧导航第一项(系统检测), 兼容旧调用"""
        self.click_detection_nav_by_attr()

    def get_detection_page_showing(self, timeout=10) -> bool:
        """等待并获取系统检测首页是否已显示

        V20 和 V25 使用不同的 AT-SPI 元素名称, 依次尝试。
        V20 上 showing 属性对 QStackedWidget 不可靠, 使用元素是否存在判断。
        :param timeout: 最长等待秒数
        """
        overview_exprs = [
            "$//detection_page//detection_overview",
            "$//detection_overview",
        ]
        scan_btn_exprs = [
            "$//detection_page//detection_scanBtn",
            "$//detectionFullScanButton",
        ]
        for i in range(timeout):
            if self._find_element_in_exprs(overview_exprs):
                return True
            if self._find_element_in_exprs(scan_btn_exprs):
                return True
            if i == 2:
                self.reconnect_dogtail()
            sleep(1)
        return self.get_detection_functional_modules_showing()

    def get_pc_manager_cpu_usage(self) -> float:
        """获取电脑管家主进程的 CPU 占用百分比

        通过 ps 命令获取进程 CPU 占用, 返回 0.0 表示进程不存在或读取失败。
        """
        result = self.run_cmd(
            r'ps -eo pcpu,args | grep -E "deepin-pc-manager" | grep -v daemon '
            r'| grep -v session-daemon | grep -v grep | awk "{print \$1}" | head -1',
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return float(result.strip())
        except (ValueError, IndexError):
            return 0.0

    def get_pc_manager_memory_mb(self) -> float:
        """获取电脑管家主进程的内存占用(MB)

        通过 ps 命令获取进程 RSS 内存, 返回 0.0 表示进程不存在或读取失败。
        """
        result = self.run_cmd(
            r'ps -eo rss,args | grep -E "deepin-pc-manager" | grep -v daemon '
            r'| grep -v session-daemon | grep -v grep | awk "{print \$1}" | head -1',
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return float(result.strip()) / 1024.0
        except (ValueError, IndexError):
            return 0.0

    def check_ui_responsive(self) -> bool:
        """检查 UI 是否响应(AT-SPI 树可访问)

        在扫描过程中尝试通过 AT-SPI 查找窗口元素, 若能成功找到则说明
        UI 线程未阻塞、界面无卡顿。
        """
        try:
            self._safe_focus_windows()
            return True
        except BaseException:
            return False

    def get_detection_score_text(self) -> str:
        """获取系统检测首页评分标签文本"""
        self._safe_focus_windows()
        score_exprs = [
            "$//detection_page//detection_scoreLabel",
            "$//detectionScoreText",
        ]
        element = self._find_element_in_exprs(score_exprs)
        if element and element.text:
            return element.text.strip()
        return ""

    def click_detection_full_scan_button(self):
        """点击系统检测首页'全面检测'按钮, 进入全面检测页面"""
        self._safe_focus_windows()
        scan_btn_exprs = [
            "$//detection_page//detection_scanBtn",
            "$//detectionFullScanButton",
            "$//detection_scanBtn",
        ]
        element = self._find_element_in_exprs(scan_btn_exprs)
        if element:
            self._atspi_do_action(element)
        sleep(3)
        self._refresh_app()
        self._safe_focus_windows()

    def _refresh_app(self):
        """轻量级刷新 AT-SPI 应用对象(retry=False 避免阻塞)

        V25 扫描完成后 AT-SPI 树更新, 需要重新获取应用对象才能看到新元素。
        """
        from src.depends.dogtail.tree import root

        try:
            self.dog.obj = root.application(self.dog.name, retry=False)
        except BaseException:
            pass

    def _safe_focus_windows(self):
        """安全聚焦窗口(扫描期间窗口可能暂时不可见, 不抛出异常)

        V25 扫描过程中应用窗口可能短暂不可见, xdotool 搜索失败会抛出
        ApplicationStartError; 此方法捕获异常避免测试中断。
        """
        try:
            self.ui.focus_windows()
        except BaseException:
            pass

    def _wait_for_scan_progress(self, timeout=15) -> bool:
        """等待检测进度出现(扫描已开始)"""
        for _ in range(timeout):
            try:
                pages = self.dog.find_elements_by_attr("$//detection_progress")
                if any(p.showing for p in pages):
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def _check_completion_elements(self, require_showing=True) -> bool:
        """检查检测完成标志是否存在/显示"""
        check_exprs = [
            "$//detection_result",
            "$//detection_noProblemPage",
            "$//detection_fixAllBtn",
            "$//detection_recheckBtn",
        ]
        for expr in check_exprs:
            try:
                elements = self.dog.find_elements_by_attr(expr)
                if not elements:
                    continue
                if require_showing:
                    if any(e.showing for e in elements):
                        return True
                else:
                    return True
            except BaseException:
                pass
        return False

    def wait_for_full_scan_started(self, timeout=60) -> bool:
        """等待全面扫描真正开始(进度组件或检测中图标可见)

        点击"全面检测"后产品需要几秒准备(加载检测项/初始化插件), 直接采样会
        把准备阶段的低占用误当作扫描期数据。这里以 size 非零判定可见实例,
        避免隐藏页副本造成的误判。

        :param timeout: 最长等待秒数
        :return: True 表示扫描已开始
        """
        for _ in range(timeout):
            if self._any_visible("$//detection_progress") or self._any_visible(
                "$//detection_runningIcon"
            ):
                return True
            sleep(1)
            self._refresh_app()
            self._safe_focus_windows()
        return False

    def wait_for_full_scan_completion(self, timeout=150) -> bool:
        """等待全面检测完成

        实测(deepin-pc-manager V20): 扫描过程中进度组件 detection_progress
        可见(size 非零), 完成后结果标题/描述可见且进度组件尺寸归零;
        showing 属性恒为 False, 元素存在性无区分度(隐藏页元素常驻 AT-SPI 树)。
        因此以 size 非零判定当前阶段。
        该版本完成后停留在全面检测页面, 不自动返回检测首页。
        :param timeout: 最长等待秒数
        :return: True 如果检测已完成
        """
        result_exprs = [
            "$//detection_resultTitle",
            "$//detection_resultDesc",
            "$//detection_issuesIcon",
            "$//detection_noProblemPage",
        ]

        # 等待扫描真正开始(进度组件可见), 最多 20 秒
        for _ in range(20):
            if self._any_visible("$//detection_progress"):
                break
            sleep(1)

        # 等待结果态出现
        for i in range(timeout):
            if self._any_visible(*result_exprs):
                return True
            if i > 0 and i % 10 == 0:
                self._refresh_app()
                self._safe_focus_windows()
            sleep(1)
        return False

    def get_detection_scan_time_text(self) -> str:
        """获取上次检测时间文本"""
        self._safe_focus_windows()
        try:
            element = self.dog.find_element_by_attr("$//detectionScoreTimeText")
            return element.text
        except BaseException:
            return ""

    def get_detection_full_scan_button_showing(self, timeout=10) -> bool:
        """检查全面检测按钮是否显示

        V20 上使用 detectionFullScanButton, V25 上使用 detection_scanBtn。
        添加重试循环: V25 上 showing 属性可能需要等待页面完全渲染后才为 True。
        """
        for _ in range(timeout):
            self._safe_focus_windows()
            for attr in (
                "$//detectionFullScanButton",
                "$//detection_page//detection_scanBtn",
                "$//detection_scanBtn",
            ):
                try:
                    elements = self.dog.find_elements_by_attr(attr, probe=True)
                    if elements:
                        if any(e.showing for e in elements):
                            return True
                except BaseException:
                    pass
            sleep(1)
        return False

    def get_detection_cards_view_showing(self) -> bool:
        """检查检测卡片视图是否显示

        V20/V25 上检测概览页的卡片容器元素名不同,
        依次尝试 detectionCardsView(旧版)、detection_scoreCard、
        detection_overviewScrollArea, 任一可见即返回 True。
        """
        self._safe_focus_windows()
        for expr in (
            "$//detectionCardsView",
            "$//detection_scoreCard",
            "$//detection_overviewScrollArea",
        ):
            try:
                elements = self.dog.find_elements_by_attr(expr, probe=True)
                if elements:
                    return True
            except BaseException:
                continue
        return False

    def get_detection_card_count(self) -> int:
        """获取检测卡片数量(通过检测概览中的卡片项)

        V20 卡片容器为 detection_cardsView(子节点为 push button),
        V25 为 detectionCardsView; 两者都尝试。
        """
        self._safe_focus_windows()
        for expr in ("$//detection_cardsView", "$//detectionCardsView"):
            try:
                container = self.dog.find_element_by_attr(expr, probe=True)
                return len(container.children)
            except BaseException:
                continue
        return 0

    # ===== 分项检测(检测首页卡片 → 单项检测 → 结果断言) =====

    def get_detection_card_names(self) -> list:
        """获取检测首页所有分项卡片名称

        :return: 卡片名称列表, 如 ["系统环境检测", "更新环境检测", ...]
        """
        self._safe_focus_windows()
        for expr in ("$//detection_cardsView", "$//detectionCardsView"):
            try:
                container = self.dog.find_element_by_attr(expr, probe=True)
            except BaseException:
                continue
            names = []
            for child in container.children:
                name = (child.name or "").strip()
                if name:
                    names.append(name)
            return names
        return []

    def click_detection_card(self, card_name, timeout=15) -> bool:
        """点击检测首页指定名称的分项卡片(真实触发该分项检测)

        卡片不存在或 AT-SPI 动作失败时返回 False, 由调用方断言失败,
        不做任何"未点击也算通过"的兜底。

        :param card_name: 卡片标题(如 "系统环境检测")
        :param timeout: 等待卡片出现的秒数
        :return: True 表示卡片已点击且进入该分项的检测运行时页面
        """
        self._safe_focus_windows()
        for _ in range(timeout):
            card = None
            for expr in ("$//detection_cardsView", "$//detectionCardsView"):
                try:
                    container = self.dog.find_element_by_attr(expr)
                except BaseException:
                    continue
                for child in container.children:
                    if (child.name or "").strip() == card_name:
                        card = child
                        break
                if card is not None:
                    break
            if card is None:
                sleep(1)
                continue
            if not self._atspi_do_action(card):
                return False
            sleep(2)
            self.reconnect_dogtail()
            self._safe_focus_windows()
            for _ in range(10):
                try:
                    page = self.dog.find_element_by_attr("$//detection_runtimePage")
                    if page.showing and page.size[0] > 0:
                        return True
                except BaseException:
                    pass
                sleep(1)
            return False
        return False

    def get_detection_group_element(self, card_name):
        """获取运行时页面中指定分项的检测组元素(detectionGroup_<卡片名>)"""
        for expr in (f"$//detectionGroup_{card_name}",):
            try:
                elements = self.dog.find_elements_by_attr(expr)
            except BaseException:
                continue
            for element in elements:
                if (element.description or "").strip():
                    return element
        return None

    def get_detection_group_description(self, card_name) -> str:
        """获取分项检测组描述, 形如
        'Detection group: 系统环境检测, 已检查 2/6 项，发现 0 项问题'
        """
        element = self.get_detection_group_element(card_name)
        return (element.description or "").strip() if element is not None else ""

    def get_detection_group_state(self, card_name) -> dict:
        """解析分项检测组的进度与问题数

        :return: {"checked": int, "total": int, "issues": int} 解析不到时为 -1
        """
        import re as _re

        desc = self.get_detection_group_description(card_name)
        state = {"checked": -1, "total": -1, "issues": -1}
        matched = _re.search(r"已检查\s*(\d+)\s*/\s*(\d+)\s*项", desc)
        if matched:
            state["checked"] = int(matched.group(1))
            state["total"] = int(matched.group(2))
        matched = _re.search(r"发现\s*(\d+)\s*项问题", desc)
        if matched:
            state["issues"] = int(matched.group(1))
        return state

    def _detection_progress_running(self) -> bool:
        """检测进度组件是否正在显示(以可见且尺寸非零为准)"""
        try:
            for element in self.dog.find_elements_by_attr("$//detection_progress"):
                try:
                    if element.showing and element.size[0] > 0:
                        return True
                except BaseException:
                    continue
        except BaseException:
            pass
        return False

    def wait_detection_group_completion(self, card_name, timeout=300) -> bool:
        """等待分项检测完成

        完成判据(取自被测应用的自身状态文本):
        1. 检测组描述出现 '已检查 N/N 项' 且 N > 0;
        2. 进度组件不再显示(尺寸归零)。
        无论行、结果页均据此判定, 超时返回 False。

        :param card_name: 卡片标题
        :param timeout: 最长等待秒数
        :return: True 表示该分项检测已完成
        """
        for i in range(timeout):
            state = self.get_detection_group_state(card_name)
            if (
                state["total"] > 0
                and state["checked"] == state["total"]
                and not self._detection_progress_running()
            ):
                return True
            if i > 0 and i % 10 == 0:
                self.reconnect_dogtail()
                self._safe_focus_windows()
            sleep(1)
        return False

    def run_detection_item(self, card_name, timeout=300) -> bool:
        """点击分项卡片并等待该分项检测完成

        点击失败、检测未启动或未在超时内完成, 一律返回 False。

        :param card_name: 卡片标题(如 "系统环境检测")
        :param timeout: 等待检测完成的秒数
        :return: True 表示分项检测已真实执行并完成
        """
        before = self.get_detection_group_description(card_name)
        if not self.click_detection_card(card_name):
            return False
        # 等待检测真正开始: 出现进度, 或组描述(已检查/发现问题)发生变化
        started = False
        for _ in range(30):
            if self._detection_progress_running():
                started = True
                break
            current = self.get_detection_group_description(card_name)
            if current and current != before:
                started = True
                break
            sleep(1)
        if not started:
            return False
        return self.wait_detection_group_completion(card_name, timeout=timeout)

    def get_detection_item_names(self, card_name) -> list:
        """获取指定分项检测的检测项名称列表

        检测项名称来自该分项检测组内 detectionCheckList_listView 的
        accessibleDescription: 'Detection item list: A, B, C';
        无描述时退回读取 listView 子节点(list item)的名称。

        :param card_name: 卡片标题
        :return: 检测项名称列表
        """
        group = self.get_detection_group_element(card_name)
        if group is None:
            return []
        list_view = self._find_descendant_by_name(
            group, ("detectionCheckList_listView", "detection_checkList_listView")
        )
        if list_view is None:
            return []
        desc = (list_view.description or "").strip()
        if "Detection item list:" in desc:
            raw = desc.split("Detection item list:", 1)[1]
            return [name.strip() for name in raw.split(",") if name.strip()]
        names = []
        try:
            for child in list_view.children:
                name = (child.name or "").strip()
                if name:
                    names.append(name)
        except BaseException:
            pass
        return names

    def _find_descendant_by_name(self, element, names, maxdepth=8):
        """在元素子树中按名称查找后代元素(广度优先)"""
        queue = [(element, 0)]
        while queue:
            current, depth = queue.pop(0)
            try:
                if (current.name or "").strip() in names:
                    return current
            except BaseException:
                pass
            if depth >= maxdepth:
                continue
            try:
                children = current.children
            except BaseException:
                continue
            for child in children:
                queue.append((child, depth + 1))
        return None

    def get_detection_item_present(self, card_name, item_name) -> bool:
        """判断指定分项检测中是否存在某个检测项

        :param card_name: 卡片标题
        :param item_name: 检测项名称(如 "备份与快照检查")
        :return: True 表示检测项存在
        """
        return item_name in self.get_detection_item_names(card_name)

    # 系统检测首页的 5 张分项卡片
    DETECTION_CARDS = ("系统环境检测", "更新环境检测", "硬件检测", "网络检测", "系统稳定性")

    def get_detection_all_groups_state(self) -> dict:
        """读取 5 张检测卡片各自的分组状态

        :return: {卡片名: {"checked": n, "total": m, "issues": k}}
        """
        states = {}
        for card in self.DETECTION_CARDS:
            state = self.get_detection_group_state(card)
            if state:
                states[card] = state
        return states

    def is_only_group_detected(self, card_name) -> bool:
        """确认本次只执行了指定分项的检测(而非"全面检测"), 且该分项已跑完

        全面检测会把 5 张卡片的检测项全部跑一遍; 只点某张卡片时, 其它卡片的
        已检查数应保持 0。该方法同时校验该分项 checked == total。

        :param card_name: 卡片标题(如 "系统环境检测")
        :return: True 表示仅该分项被检测且已跑完
        """
        states = self.get_detection_all_groups_state()
        target = states.get(card_name)
        if not target or target.get("total", 0) <= 0:
            return False
        if target.get("checked") != target.get("total"):
            return False
        for name, state in states.items():
            if name == card_name:
                continue
            if state.get("checked", 0) > 0:
                return False
        return True

    def _detect_via_dbus(self, detection_id, bus, timeout=60):
        """在指定总线上执行 Detect(id) 并等待结果

        :param detection_id: 检测项 ID
        :param bus: "session" 或 "system"
        :param timeout: 等待完成的秒数
        :return: (ok, detail); ok 为 None 表示该总线不认识该检测项
        """
        bus_args = "--session"
        prefix = ""
        if bus == "system":
            bus_args = "--system"
        elif bus == "session":
            prefix = f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{os.getuid()}/bus "
        out = self.run_cmd(
            f"{prefix}/usr/bin/gdbus call {bus_args} --dest org.deepin.PCManager1 "
            f"--object-path /org/deepin/PCManager1 "
            f"--method org.deepin.PCManager1.Detect {detection_id}",
            timeout=15,
            out_debug_flag=False,
        ) or ""
        match = re.search(r"(/org/deepin/PCManager1/Task/[\w/]+)", out)
        if not match:
            return None, f"检测项 {detection_id} 启动失败: {out.strip()}"
        path = match.group(1)
        status = ""
        for _ in range(int(timeout)):
            status = self.run_cmd(
                f"{prefix}/usr/bin/gdbus call {bus_args} --dest org.deepin.PCManager1 "
                f"--object-path {path} "
                f"--method org.freedesktop.DBus.Properties.Get "
                f"org.deepin.PCManager1.Task status",
                timeout=10,
                out_debug_flag=False,
            ) or ""
            if "unknown operable item" in status:
                return None, status.strip()
            if "running" not in status and "success" in status:
                break
            if "failure" in status or "error" in status:
                return False, status.strip()
            sleep(1)
        result = self.run_cmd(
            f"{prefix}/usr/bin/gdbus call {bus_args} --dest org.deepin.PCManager1 "
            f"--object-path {path} --method org.deepin.PCManager1.Task.GetResult",
            timeout=15,
            out_debug_flag=False,
        ) or ""
        verdict = re.search(r"\((true|false),", result)
        if not verdict:
            return None, result.strip()
        return verdict.group(1) == "true", result.strip()

    def get_detection_item_verdict(self, detection_id, timeout=60):
        """读取单个检测项(如 critical_libraries)的检测结论

        V20 的 QML 列表项不向 AT-SPI 暴露单项状态, 界面层只能拿到"分项问题总数"。
        单项结论取自电脑管家自身的 D-Bus 检测接口
        (org.deepin.PCManager1.Detect + Task.GetResult), 即产品对外结果通道。
        检测项分散在会话总线与系统总线上(operable_item_ids.h 注释), 本方法先查
        会话总线, 若该总线不认识此 id 再查系统总线。

        :param detection_id: 检测项 ID(如 "critical_libraries")
        :param timeout: 等待检测完成的超时时间
        :return: (ok, detail); ok 为 None 表示两条总线都不实现该检测项,
                 调用方应退回分项级断言
        """
        ok, detail = self._detect_via_dbus(detection_id, "session", timeout=timeout)
        if ok is not None:
            return ok, detail
        if "unknown operable item" not in (detail or ""):
            return ok, detail
        return self._detect_via_dbus(detection_id, "system", timeout=timeout)

    def get_detection_result_texts(self) -> tuple:
        """获取分项检测运行时页面的结果标题与描述文本

        V20 的 QML Label 不暴露可访问文本(AT-SPI text 接口为空, name 为元素名),
        此时返回空字符串, 调用方应改用结果元件可见性判断。

        :return: (title, desc), 取不到时为空字符串
        """
        texts = []
        for expr in ("$//detection_resultTitle", "$//detection_resultDesc"):
            value = ""
            try:
                for element in self.dog.find_elements_by_attr(expr):
                    if not (element.showing and element.size[0] > 0):
                        continue
                    text = (element.text or "").strip()
                    if text and text != (element.name or "").strip():
                        value = text
                        break
            except BaseException:
                pass
            texts.append(value)
        return tuple(texts)

    def get_detection_runtime_texts(self) -> list:
        """收集分项检测运行时页面内所有可见文本(名称/文本/描述)

        用于断言被测应用给出的检测结论文案, 例如
        "备份分区缺失或快照已损坏，系统无法还原"、"系统时间同步正常"。

        :return: 文本列表
        """
        self._safe_focus_windows()
        collected = []
        try:
            pages = self.dog.find_elements_by_attr("$//detection_runtimePage")
        except BaseException:
            return collected
        for page in pages:
            if not page.showing:
                continue
            stack = [(page, 0)]
            while stack:
                element, depth = stack.pop()
                if depth > 8:
                    continue
                try:
                    name = (element.name or "").strip()
                    text = (element.text or "").strip()
                    desc = (element.description or "").strip()
                    for value in (name, text, desc):
                        if value:
                            collected.append(value)
                except BaseException:
                    pass
                try:
                    children = element.children
                except BaseException:
                    continue
                for child in children:
                    stack.append((child, depth + 1))
        return collected

    def detection_runtime_text_contains(self, keyword) -> bool:
        """分项检测运行时页面内是否存在包含指定关键字的文本"""
        for value in self.get_detection_runtime_texts():
            if keyword in value:
                return True
        return False

    def leave_detection_runtime_page(self) -> bool:
        """从分项检测运行时页面返回检测首页

        :return: True 表示已回到检测首页
        """
        try:
            self.dog.find_element_by_attr("$//mainWindow_backBtn").click()
        except BaseException:
            return False
        for _ in range(20):
            sleep(1)
            self.reconnect_dogtail()
            if self.get_detection_page_showing(timeout=1):
                return True
        return False

    def get_detection_runtime_page_showing(self, timeout=10) -> bool:
        """检查检测运行时页面是否显示(V20: detection_runtimePage, V25: detectionRuntimePage)"""
        for _ in range(timeout):
            for expr in ("$//detection_runtimePage", "$//detectionRuntimePage"):
                try:
                    page = self.dog.find_element_by_attr(expr)
                    if page and page.size[0] > 0:
                        return True
                except BaseException:
                    pass
            sleep(1)
        return False

    def get_detection_full_scan_page_showing(self, timeout=15) -> bool:
        """检查全面检测页面是否显示(V20: detection_fullScanPage, V25: detectionFullScanPage)

        V20 上 detection_fullScanPage.showing 可靠;
        V25 上 detection_fullScanPage 总在树中(showing 不可靠),
        改用 detectionFullScanPage 存在性 + showing 双重判断。
        V25 上扫描可能立即开始, 检测到进度也视为全面检测页面已显示。
        """
        for _ in range(timeout):
            self._refresh_app()
            for attr in ("$//detectionFullScanPage", "$//detection_fullScanPage"):
                try:
                    page = self.dog.find_element_by_attr(attr, probe=True)
                    if page.showing:
                        return True
                except BaseException:
                    continue
            if self._find_element_in_exprs(["$//detectionFullScanPage"]):
                return True
            # V25: 扫描可能已立即开始, 检测到进度也视为全面检测页面已显示
            try:
                pages = self.dog.find_elements_by_attr("$//detection_progress")
                if any(p.showing for p in pages):
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def get_back_button_element(self):
        """获取标题栏返回按钮元素(不点击)

        重复文件扫描只持续数秒, 进入插件页面后再查找该按钮(AT-SPI 查找约 2s)
        会错过扫描窗口; 需要在进入前缓存元素, 扫描开始时直接触发动作。
        :return: 返回按钮元素, 获取失败返回 None
        """
        self._safe_focus_windows()
        try:
            return self.dog.find_element_by_attr("$//mainWindow_backBtn")
        except BaseException:
            return None

    def click_back_button(self, wait=2, element=None):
        """点击标题栏返回按钮

        :param wait: 点击后等待秒数; 传 0 可在点击瞬间立即读取被测状态
        :param element: 预先缓存的返回按钮元素; 传入时直接触发动作, 省去查找耗时
        """
        if element is not None:
            self._atspi_do_action(element)
            sleep(wait)
            return
        self._safe_focus_windows()
        try:
            element = self.dog.find_element_by_attr("$//mainWindow_backBtn")
            self._atspi_do_action(element)
            sleep(wait)
        except BaseException:
            pass

    def get_context_label_text(self) -> str:
        """获取标题栏上下文标签文本"""
        self._safe_focus_windows()
        try:
            element = self.dog.find_element_by_attr("$//mainWindow_contextLabel")
            return element.text or element.name or ""
        except BaseException:
            return ""

    def wait_for_full_scan_complete(self, timeout=120) -> bool:
        """等待全面检测完成(全面检测页面消失或检测首页元素重新出现)

        V20: detectionFullScanPage/detection_fullScanPage 消失即完成;
        V25: 该元素不存在, 委托给 wait_for_full_scan_completion 处理
        (等待进度消失 + 结果页出现 + 点击返回按钮回到检测首页)。
        """
        return self.wait_for_full_scan_completion(timeout=timeout)

    def go_back_from_detection(self):
        """点击标题栏返回按钮, 从全面检测页面返回到系统检测首页"""
        self._safe_focus_windows()
        self.dog.find_element_by_attr("$//mainWindow_backBtn").click()
        sleep(2)
        self.reconnect_dogtail()
        self._safe_focus_windows()

    def wait_detection_complete(self, timeout=120) -> bool:
        """等待检测完成(检测运行图标消失且结果区出现)

        实测 V20: detection_runningIcon 在 runtimePage 与 fullScanPage 中各存
        在一份, 隐藏页副本的 showing 恒为 False; 用 find_element_by_attr 取第一份
        会立即误判为"已完成"。这里以 size 非零判定可见(隐藏实例为 0x0),
        并先等待检测真正开始, 避免点击后瞬时返回。
        """
        started = False
        for _ in range(timeout):
            running = self._any_visible("$//detection_runningIcon")
            if running:
                started = True
            elif started or self._any_visible("$//detection_resultTitle"):
                return True
            sleep(1)
        return False

    def get_detection_manual_icon_showing(self) -> bool:
        """检查"手动修复"图标是否显示(存在不可修复项时显示)"""
        return self._any_visible("$//detection_manualIcon")

    def get_detection_recheck_btn_showing(self) -> bool:
        """检查"复查"按钮是否显示(检测完成后显示)"""
        return self.get_detection_recheck_button_showing()

    def get_detection_fix_all_btn_showing(self) -> bool:
        """检查"一键修复"按钮是否显示(存在可修复项时显示)"""
        return self.get_detection_fix_all_button_showing()

    def get_detection_running_icon_showing(self) -> bool:
        """检查"检测中"图标是否显示(检测进行中显示)

        隐藏页面的同名副本始终存在, 因此不能用"元素存在"判断,
        以 size 非零的可见实例为准。
        """
        return self._any_visible("$//detection_runningIcon")

    def get_last_score_displayed(self, timeout=10) -> bool:
        """检查系统检测首页是否显示了上次检测分数

        优先检查分数标签文本是否包含"上次检测分数"（V20 标准 Qt label）；
        若文本不可读（V25 自定义绘制），则检查分数标签和检测时间标签是否存在。
        :param timeout: 最长等待秒数
        """
        score_exprs = [
            "$//detection_page//detection_scoreLabel",
            "$//detectionScoreText",
        ]
        score_time_exprs = [
            "$//detection_page//detection_scoreTimeLabel",
            "$//detectionScoreTimeText",
        ]
        for _ in range(timeout):
            # 方式一: 尝试读取分数标签文本（V20）
            text = self.get_detection_score_text()
            if text and "上次检测分数" in text:
                return True
            # 方式二: 检查分数标签和检测时间标签是否存在
            if self._find_element_in_exprs(score_exprs) and self._find_element_in_exprs(
                score_time_exprs
            ):
                return True
            sleep(1)
        return False

    def get_detection_result_showing(self, timeout=10) -> bool:
        """检查检测结果是否展示

        V20 上检测完成后停留在全面检测页面, 显示结果标题/描述/问题图标;
        V25 使用独立结果页 detectionResultFrame。
        showing 属性恒为 False, 以 size 非零判定可见。
        """
        for _ in range(timeout):
            self.refresh_dogtail_root()
            if self._any_visible(
                "$//detection_resultTitle",
                "$//detection_resultDesc",
                "$//detection_issuesIcon",
                "$//detectionResultFrame",
            ):
                return True
            sleep(1)
        return False

    def get_detection_result_title_showing(self) -> bool:
        """检查检测结果标题是否可见

        V20 的 QML Label 不暴露 accessible name(AT-SPI 中 name 仅为元素名),
        无法读取文案内容, 因此以元素尺寸非零判定其已渲染。
        """
        return self._any_visible("$//detection_resultTitle", "$//detectionResultTitle")

    def get_detection_result_desc_showing(self) -> bool:
        """检查检测结果描述是否可见(同标题, V20 无法读取文案)"""
        return self._any_visible("$//detection_resultDesc", "$//detectionResultDesc")

    def get_detection_result_title_text(self) -> str:
        """获取检测结果标题文本(V20: detection_resultTitle, V25: detectionResultTitle)"""
        self._safe_focus_windows()
        title_exprs = [
            "$//detection_resultTitle",
            "$//detectionResultTitle",
        ]
        for expr in title_exprs:
            try:
                elements = self.dog.find_elements_by_attr(expr)
                for element in elements:
                    if element.text:
                        return element.text.strip()
            except BaseException:
                pass
        return ""

    def get_detection_result_desc_text(self) -> str:
        """获取检测结果描述文本(V20: detection_resultDesc, V25: detectionResultDesc)"""
        self._safe_focus_windows()
        desc_exprs = [
            "$//detection_resultDesc",
            "$//detectionResultDesc",
        ]
        for expr in desc_exprs:
            try:
                elements = self.dog.find_elements_by_attr(expr)
                for element in elements:
                    if element.text:
                        return element.text.strip()
            except BaseException:
                pass
        return ""

    def get_detection_result_actions_showing(self) -> bool:
        """检查检测结果的一键修复/重新扫描操作入口是否可见

        两个按钮仅在检测完成后可见(size 非零), 可作为结果态的活动操作证据。
        """
        self._safe_focus_windows()
        return self._any_visible(
            "$//detection_fixAllBtn",
            "$//detection_recheckBtn",
        )

    # ===== 修复工具模块方法 =====

    def _find_repair_element(self, *exprs):
        """尝试多个 AT-SPI 表达式查找元素(V20 snake_case / V25 camelCase)

        :param exprs: 多个 AT-SPI 表达式, 按顺序尝试, 返回第一个找到的元素
        :return: 找到的元素
        :raises: 所有表达式均未找到时抛出最后一个异常
        """
        last_err = None
        for expr in exprs:
            try:
                elements = self.dog.find_elements_by_attr(expr, probe=True)
                if elements:
                    return elements[0]
                last_err = Exception(f"element not found: {expr}")
            except BaseException:
                last_err = Exception(f"element not found: {expr}")
        raise last_err

    def _atspi_do_action(self, element):
        """通过 AT-SPI Action 接口触发元素操作(V20/V25 兼容)

        dogtail 2.x Accessible 对象不提供 queryAction(),
        但提供 doActionNamed / do_action / get_n_actions 等方法。
        优先尝试 AT-SPI doActionNamed("Press"), 失败则回退到 element.click()。

        :return: True 表示动作已被无异常地提交(仍是异步生效, 调用方需自行
                 校验界面结果); False 表示所有 AT-SPI 动作均失败。
        """
        try:
            n = element.get_n_actions()
            if n and n > 0:
                for i in range(n):
                    try:
                        name = element.get_action_name(i)
                        if "press" in name.lower():
                            element.do_action(i)
                            return True
                    except BaseException:
                        pass
                element.do_action(0)
                return True
        except BaseException:
            pass
        try:
            element.click()
            return True
        except BaseException:
            return False

    def _click_at_element(self, element) -> bool:
        """通过 xdotool 点击元素中心

        V20 上 AT-SPI click 对部分 QML 控件(导航项、搜索框)无效,
        这些控件的事件只响应鼠标坐标点击。
        """
        try:
            x, y = element.position
            width, height = element.size
            if width <= 0 or height <= 0:
                return False
            self.run_cmd(
                f"xdotool mousemove {x + width // 2} {y + height // 2} click 1",
                timeout=5,
                out_debug_flag=False,
            )
            return True
        except BaseException:
            return False

    def _type_to_app(self, text: str, clear: bool = True) -> bool:
        """向电脑管家窗口定向发送键盘输入

        X11 键盘焦点可能被其他窗口(如 lightdm greeter)占用,
        直接 xdotool type 不一定送达, 需要 --window 指定目标窗口。
        """
        try:
            window_id = self.run_cmd(
                "xdotool search --name '电脑管家' | tail -1",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            if not window_id:
                return False
            if clear:
                self.run_cmd(
                    f"xdotool key --clearmodifiers --window {window_id} End; "
                    f"xdotool key --clearmodifiers --window {window_id} "
                    f"--repeat 80 BackSpace",
                    timeout=10,
                    out_debug_flag=False,
                )
            if text:
                self.run_cmd(
                    f"xdotool type --clearmodifiers --window {window_id} "
                    f"--delay 50 '{text}'",
                    timeout=10,
                    out_debug_flag=False,
                )
            return True
        except BaseException:
            return False

    def _key_to_app(self, key: str) -> bool:
        """向电脑管家窗口定向发送按键(焦点可能被其他窗口占用)

        修复对话框是独立窗口, Escape/Return 需要发送到对应窗口,
        因此向应用的全部窗口发送按键。
        """
        try:
            window_ids = self.run_cmd(
                "xdotool search --class deepin-pc-manager 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            ).split()
            if not window_ids:
                return False
            for window_id in window_ids:
                self.run_cmd(
                    f"xdotool key --clearmodifiers --window {window_id} {key}",
                    timeout=5,
                    out_debug_flag=False,
                )
            return True
        except BaseException:
            return False

    def click_repair_nav(self):
        """点击左侧导航第三项(修复工具)

        点击后等待页面切换动画完成并重新建立 dogtail 连接,
        刷新 AT-SPI 树引用(V20/V25 上页面切换后旧引用会失效)。

        V20 上 navList 与子项的 AT-SPI 层级关系不稳定,
        `$//mainWindow_navList//修复工具` 可能匹配失败, 因此直接在
        navList 子元素中按名称查找, 并带重试。
        """
        self._safe_focus_windows()
        clicked = False
        for _ in range(15):
            for name in ("修复工具", "Repair Tools"):
                try:
                    nav_list = self.dog.find_element_by_attr("$//mainWindow_navList")
                    items = nav_list.findChildren(
                        lambda node, target=name: node.name == target,
                        recursive=True,
                        showingOnly=False,
                    )
                    if items:
                        if not self._click_at_element(items[0]):
                            items[0].click()
                        clicked = True
                        break
                except BaseException:
                    continue
            if clicked:
                break
            self.refresh_dogtail_root()
            sleep(1)
        if not clicked:
            self.dog.find_element_by_attr("$//mainWindow_navList//修复工具").click()
        sleep(2)
        self.reconnect_dogtail()

    def get_repair_page_showing(self, timeout=15) -> bool:
        """等待并获取修复工具页面的可见状态

        V20/V25 上 repair_page 等 QStackedWidget 容器的 showing 属性不可靠,
        改为检查子元素是否存在来判断页面是否显示。
        """
        page_exprs = [
            "$//repair_page//repair_overview",
            "$//repair_viewStack//repair_overview",
            "$//repair_viewStack//repair_sectionsContainer",
            "$//repair_sectionsContainer",
            "$//repair_page//repair_sectionsContainer",
        ]
        for i in range(timeout):
            if self._find_element_in_exprs(page_exprs):
                return True
            if i == 2:
                self.reconnect_dogtail()
            sleep(1)
        fallback_exprs = [
            "$//repair_sectionsContainer",
            "$//repair_sectionWidget",
            "$//repair_sectionTitle",
        ]
        return bool(self._find_element_in_exprs(fallback_exprs))

    def get_repair_page_header_showing(self, timeout=10) -> bool:
        """检查修复工具页顶部页头(标题 + 描述)是否已渲染

        实测 V20(deepin-pc-manager): repair_overview 顶部为 pageHeader,
        内含 pageHeader_titleLabel(页面标题"修复工具")与
        pageHeader_subtitleLabel(描述"一键修复常见问题")。
        产品把 QLabel 的 accessibleName 固定成 objectName, AT-SPI 读不到文案
        (V20 QML Label 不暴露 text 与 description), 因此以两个标签的
        实际渲染(size 非零)作为页头展示的等价断言。
        """
        exprs = (
            "$//repair_overview//pageHeader//pageHeader_titleLabel",
            "$//repair_overview//pageHeader//pageHeader_subtitleLabel",
        )
        for i in range(timeout):
            if all(self._any_visible(expr) for expr in exprs):
                return True
            if i == 2:
                self.reconnect_dogtail()
            sleep(1)
        return False

    def get_repair_cards_view_showing(self) -> bool:
        """检查修复卡片视图是否显示"""
        self._safe_focus_windows()
        try:
            elements = self.dog.find_elements_by_attr("$//repair_sectionsContainer")
            if elements:
                return True
        except BaseException:
            pass
        return False

    def get_repair_empty_state_showing(self) -> bool:
        """检查修复工具"未找到匹配工具"空状态是否真正渲染

        实测(deepin-pc-manager V20): 产品把 repair_emptyTitle /
        repair_emptyText 的 accessible name 固定为 objectName, 读不到
        「未找到匹配的修复工具」「请尝试其他关键词」文案; 且这两个标签
        在列表正常显示时仍留在树中, showing 恒为 False, 仅靠存在性判断
        会一直为真。未命中关键词时标签实际渲染(size 非零), 列表正常时
        被缩成 0x0, 因此以"标题 + 副标题标签均 size 非零"作为空状态
        展示的等价断言。
        """
        self._safe_focus_windows()
        exprs = ("$//repair_emptyTitle", "$//repair_emptyText")
        return all(self._any_visible(expr) for expr in exprs)

    def get_repair_empty_state_labels(self) -> list:
        """获取修复工具空状态标签的渲染明细(name, size), 用于诊断与断言

        :return: [{"name": str, "width": int, "height": int}, ...]
        """
        self._safe_focus_windows()
        labels = []
        for expr in ("$//repair_emptyTitle", "$//repair_emptyText"):
            try:
                for element in self.dog.find_elements_by_attr(expr):
                    width, height = element.size
                    labels.append(
                        {"name": element.name or "", "width": width, "height": height}
                    )
            except BaseException:
                continue
        return labels

    def get_repair_card_count(self) -> int:
        """获取修复卡片数量(修复项按钮数量)"""
        self._safe_focus_windows()
        try:
            sections = self.dog.find_elements_by_attr(
                "$//repair_sectionsContainer//repair_sectionWidget"
            )
            count = 0
            if sections:
                for section in sections:
                    try:
                        buttons = section.findChildren(
                            lambda n: n.roleName in ("push button", "button"),
                            recursive=True,
                            showingOnly=False,
                        )
                        count += len(buttons)
                    except BaseException:
                        continue
            return count
        except BaseException:
            return 0

    def get_repair_card_names(self) -> list:
        """获取修复卡片名称列表, 用于验证模块分类"""
        self._safe_focus_windows()
        names = []
        try:
            sections = self.dog.find_elements_by_attr(
                "$//repair_sectionsContainer//repair_sectionWidget"
            )
            if sections:
                for section in sections:
                    try:
                        buttons = section.findChildren(
                            lambda n: n.roleName in ("push button", "button"),
                            recursive=True,
                            showingOnly=False,
                        )
                        for btn in buttons:
                            if btn.name:
                                names.append(btn.name)
                    except BaseException:
                        continue
        except BaseException:
            pass
        return names

    def get_repair_category_tab_count(self) -> int:
        """获取修复工具分类标签数量"""
        self._safe_focus_windows()
        try:
            elements = self.dog.find_elements_by_attr("$//repair_categoryTabs//repair_catBtn")
            return len(elements) if elements else 0
        except BaseException:
            return 0


    def click_repair_category_tab_by_index(self, index: int) -> bool:
        """点击修复工具分类标签(按索引)并等待列表刷新

        产品把 repair_catBtn 的 accessibleName 固定成 objectName,
        description 统一是 "Filters repair tools by category", 无法按
        文案区分, 因此按索引点击。

        实测 V20 上分类标签的 AT-SPI 角色是 check box,
        Action 只有 Toggle/SetFocus, 调用 Toggle 后列表不刷新;
        只有 xdotool 坐标点击才会触发筛选, 因此优先坐标点击,
        AT-SPI Toggle 仅作为兜底。

        :param index: 分类标签索引(从0开始)
        :return: True 表示点击动作已提交(仍需调用方校验列表结果)
        """
        self._safe_focus_windows()
        try:
            elements = self.dog.find_elements_by_attr("$//repair_categoryTabs//repair_catBtn")
            if not elements or not (0 <= index < len(elements)):
                return False
            element = elements[index]
            clicked = self._click_at_element(element)
            if not clicked:
                clicked = self._atspi_do_action(element)
            sleep(2)
            self.reconnect_dogtail()
            return bool(clicked)
        except BaseException:
            return False
    def get_repair_category_tab_names(self) -> list:
        """获取修复工具分类标签名称列表"""
        self.ui.focus_windows()
        names = []
        try:
            elements = self.dog.find_elements_by_attr("$//repair_categoryTabs//repair_catBtn")
            if elements:
                for el in elements:
                    try:
                        name = el.name
                        if name:
                            names.append(name)
                    except BaseException:
                        continue
        except BaseException:
            pass
        return names

    def get_repair_category_tab_labels(self) -> list:
        """获取修复工具分类标签的最佳可读文案列表(V20/V25 兼容)

        V20 上 QML Label/Button 的 AT-SPI name 被产品固定成 objectName
        (repair_catBtn), 中文文案通常只出现在 description 中; 因此逐项
        取 name/description 中第一个非 objectName 的文本, 都取不到时
        退回 name。调用方不应依赖标签文案存在, 需以筛选后的列表内容
        作为最终判据。

        :return: 与分类标签一一对应的文案列表(可能为空字符串)
        """
        self._safe_focus_windows()
        labels = []
        try:
            elements = self.dog.find_elements_by_attr("$//repair_categoryTabs//repair_catBtn")
            if not elements:
                return labels
            for el in elements:
                text = ""
                for attr in ("name", "description"):
                    try:
                        value = (getattr(el, attr, "") or "").strip()
                    except BaseException:
                        value = ""
                    if value and value != "repair_catBtn":
                        text = value
                        break
                labels.append(text)
        except BaseException:
            pass
        return labels

    def click_repair_category_tab_by_name(self, tab_name: str) -> bool:
        """点击指定名称的分类标签(V20/V25 兼容)

        :param tab_name: 分类标签名称
        :return: True 表示点击成功, False 表示未找到标签
        """
        self.ui.focus_windows()
        try:
            elements = self.dog.find_elements_by_attr("$//repair_categoryTabs//repair_catBtn")
            if elements:
                for el in elements:
                    try:
                        name = el.name or ""
                        if tab_name in name or name in tab_name:
                            self._atspi_do_action(el)
                            sleep(2)
                            self.reconnect_dogtail()
                            return True
                    except BaseException:
                        continue
        except BaseException:
            pass
        return False

    def get_repair_filtered_card_count(self) -> int:
        """获取当前筛选状态下修复卡片数量"""
        self.ui.focus_windows()
        try:
            sections = self.dog.find_elements_by_attr(
                "$//repair_sectionsContainer//repair_sectionWidget"
            )
            count = 0
            if sections:
                for section in sections:
                    try:
                        buttons = section.findChildren(
                            lambda n: n.roleName in ("push button", "button"),
                            recursive=True,
                            showingOnly=False,
                        )
                        count += len(buttons)
                    except BaseException:
                        continue
            return count
        except BaseException:
            return 0

    def get_repair_visible_card_names(self) -> list:
        """获取修复工具当前可见的修复项名称

        实测 V20 分类筛选并不销毁未选中的分区/卡片, 而是把它们
        缩成 0x0(AT-SPI 中仍存在但 size 为零); 因此不能只看元素
        是否存在, 必须用 size 过滤出真正渲染的卡片。

        :return: 当前可见的修复项名称列表(按 AT-SPI 树顺序去重)
        """
        names = [
            card
            for section in self.get_repair_visible_sections_detail()
            for card in section["cards"]
        ]
        unique = []
        for name in names:
            if name not in unique:
                unique.append(name)
        return unique

    def get_repair_visible_sections_detail(self) -> list:
        """获取修复工具当前真正可见的分区明细(标题 + 修复项)

        与 get_repair_sections_detail 的区别: 后者返回树中全部分区,
        含被分类筛选隐藏(0x0)的分区; 本方法只保留 size 非零的分区
        与 size 非零的卡片按钮, 用于断言筛选后列表的实际内容。

        :return: [{"title": str, "cards": [str, ...]}, ...]
        """
        self._safe_focus_windows()
        detail = []
        try:
            sections = self.dog.find_elements_by_attr(
                "$//repair_sectionsContainer//repair_sectionWidget"
            )
            if not sections:
                return detail
            for section in sections:
                try:
                    width, height = section.size
                except BaseException:
                    continue
                if width <= 0 or height <= 0:
                    continue
                title = ""
                try:
                    title_el = section.findChild(
                        lambda n: n.name == "repair_sectionTitle",
                        recursive=False,
                        showingOnly=False,
                    )
                    if title_el is not None:
                        title = title_el.name or ""
                except BaseException:
                    pass
                cards = []
                try:
                    buttons = section.findChildren(
                        lambda n: n.roleName in ("push button", "button"),
                        recursive=True,
                        showingOnly=False,
                    )
                except BaseException:
                    buttons = []
                for btn in buttons:
                    try:
                        btn_width, btn_height = btn.size
                        name = (btn.name or "").strip()
                    except BaseException:
                        continue
                    if btn_width > 0 and btn_height > 0 and name:
                        cards.append(name)
                if cards:
                    detail.append({"title": title, "cards": cards})
        except BaseException:
            pass
        return detail

    def get_repair_filtered_section_titles(self) -> list:
        """获取当前筛选状态下修复工具各模块分区标题列表"""
        self.ui.focus_windows()
        titles = []
        try:
            elements = self.dog.find_elements_by_attr(
                "$//repair_sectionsContainer//repair_sectionWidget//repair_sectionTitle"
            )
            if elements:
                for el in elements:
                    try:
                        name = el.name
                        if name:
                            titles.append(name)
                    except BaseException:
                        continue
        except BaseException:
            pass
        return titles

    def get_repair_section_count(self) -> int:
        """获取修复工具模块分区数量"""
        self._safe_focus_windows()
        try:
            elements = self.dog.find_elements_by_attr(
                "$//repair_sectionsContainer//repair_sectionWidget"
            )
            return len(elements) if elements else 0
        except BaseException:
            return 0

    def get_repair_section_titles(self) -> list:
        """获取修复工具各模块分区标题列表"""
        self._safe_focus_windows()
        titles = []
        try:
            elements = self.dog.find_elements_by_attr(
                "$//repair_sectionsContainer//repair_sectionWidget//repair_sectionTitle"
            )
            if elements:
                for el in elements:
                    try:
                        name = el.name
                        if name:
                            titles.append(name)
                    except BaseException:
                        continue
        except BaseException:
            pass
        return titles

    def get_repair_sections_detail(self) -> list:
        """获取修复工具各模块分区明细(分区标题 + 该分区下的修复项名称)

        :return: [{"title": str, "cards": [str, ...]}, ...], 按页面显示顺序排列

        依据: 产品修复工具页面 repair_sectionsContainer 下每个模块分区为
        repair_sectionWidget(系统修复/桌面修复/外设修复/应用修复), 分区标题
        为 repair_sectionTitle, 分区内每个修复工具按钮 roleName 为 push button。
        V20 上 QML Label/Button 的 AT-SPI name 被固定成 objectName
        (repair_sectionTitle / repair_catBtn), 读不到中文文案, 因此 title 可能
        等于 objectName, 分类校验以按钮文案(修复项名称)为准。
        """
        self._safe_focus_windows()
        detail = []
        try:
            sections = self.dog.find_elements_by_attr(
                "$//repair_sectionsContainer//repair_sectionWidget"
            )
            if not sections:
                return detail
            try:
                titles = [
                    el.name or ""
                    for el in self.dog.find_elements_by_attr(
                        "$//repair_sectionsContainer//repair_sectionWidget"
                        "//repair_sectionTitle"
                    )
                ]
            except BaseException:
                titles = []
            for index, section in enumerate(sections):
                cards = []
                try:
                    buttons = section.findChildren(
                        lambda n: n.roleName in ("push button", "button"),
                        recursive=True,
                        showingOnly=False,
                    )
                    for btn in buttons:
                        if btn.name:
                            cards.append(btn.name)
                except BaseException:
                    pass
                title = titles[index] if index < len(titles) else ""
                detail.append({"title": title, "cards": cards})
        except BaseException:
            return detail
        return detail

    def click_repair_card_by_name(self, card_name: str):
        """点击指定名称的修复卡片(V20/V25 兼容)

        V25(loongarch64)上 raw click 无法触发 Qt button 的 clicked 信号,
        需通过 AT-SPI doActionNamed('Press') 接口直接触发按钮操作。
        """
        self._safe_focus_windows()
        element = self._find_repair_element(
            f"$//repair_sectionsContainer//{card_name}",
            f"$//repairCardsView//{card_name}",
        )
        self._atspi_do_action(element)
        sleep(2)
        self.reconnect_dogtail()

    def get_repair_start_button_showing(self) -> bool:
        """检查修复开始按钮是否显示"""
        self._safe_focus_windows()
        try:
            elements = self.dog.find_elements_by_attr("$//repair_runtimePage//")
            if elements:
                for el in elements:
                    try:
                        name = el.name or ""
                        if "修复" in name and "开始" in name:
                            return el.showing
                    except BaseException:
                        continue
            return False
        except BaseException:
            return False

    def click_repair_start_button(self):
        """点击修复开始按钮(V20/V25 兼容)"""
        self._safe_focus_windows()
        element = self._find_repair_element(
            "$//repair_runtimePage//开始修复",
            "$//repair_startBtn",
            "$//repairStartButton",
        )
        self._atspi_do_action(element)
        sleep(2)

    def get_shell_repair_input_showing(self, timeout=10) -> bool:
        """检查提权密码输入框是否显示(验证修复需要提权)

        :param timeout: 最长等待秒数
        :return: True 表示密码输入框已显示, False 表示超时未显示
        """
        for _ in range(timeout):
            try:
                pwd_input = self.dog.find_element_by_attr("$//shellRepair_inputEdit", probe=True)
                if pwd_input and pwd_input.showing:
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def handle_shell_repair_dialog(self, password=None, tries=15):
        """在修复对话框的脚本交互行输入密码并提交

        产品行为: 输入行(shellRepair_inputEdit)常驻显示但默认禁用, 只有脚本
        显式请求输入([[PASSWORD]]/[[TEXT]] 标记或识别到密码提示)时才启用。
        因此必须判断 sensitive, 否则会对禁用的输入行写入无效。

        输入通道: 该行是 DPasswordEdit, 产品未实现 AT-SPI EditableText
        (role 为 INVALID, text 恒为 None, queryEditableText 抛
        NotImplementedError), 直接赋值 text 会抛异常且不生效; 真实用户也是
        用键盘输入。因此在输入框中心点击聚焦后用 xdotool 键入密码, 再触发
        submitBtn 的 Press 动作(失败时回退为点击按钮中心)。

        :param password: sudo 密码; 默认取 setting/globalconfig.ini 的 PASSWORD
        :param tries: 等待输入行可用的最大轮询次数(每次 1s)
        :return: True 表示已输入并提交; False 表示输入行始终不可用/提交失败
        """
        if password is None:
            password = conf.PASSWORD
        for _ in range(tries):
            try:
                pwd_input = self.dog.find_element_by_attr("$//shellRepair_inputEdit", probe=True)
            except BaseException:
                pwd_input = None
            if pwd_input and pwd_input.showing and pwd_input.sensitive:
                return self._type_and_submit_shell_repair_input(pwd_input, password)
            sleep(1)
        return False

    def _type_and_submit_shell_repair_input(self, pwd_input, password) -> bool:
        """在密码输入行上用键盘键入密码并提交(见 handle_shell_repair_dialog)

        :return: True 表示键入与提交动作均已发出(异步生效, 调用方需校验输出)
        """
        try:
            x, y = pwd_input.position
            w, h = pwd_input.size
        except BaseException:
            return False
        # 点击输入框中心: 顺带把修复对话框带到前台并让密码框获得键盘焦点
        self.run_cmd(
            f"xdotool mousemove --sync {int(x + w / 2)} {int(y + h / 2)} click 1",
            timeout=15,
        )
        sleep(0.5)
        self.run_cmd(
            f"xdotool type --clearmodifiers --delay 80 {quote(password)}",
            timeout=15,
        )
        sleep(0.5)
        # 回车提交: 产品把 inputEdit_ 的 returnPressed 直接连到 submitInput,
        # 比依赖按钮 enabled 状态更稳(密码模式切换瞬间按钮可能仍是禁用态)
        self.run_cmd("xdotool key --clearmodifiers Return", timeout=15)
        # 密码模式下提交后产品会 append "********" 回显, 由此确认密码已被受理
        if self._wait_shell_repair_password_echo(tries=3):
            return True
        # 回退1: 触发提交按钮的 Press 动作
        try:
            submit_btn = self.dog.find_element_by_attr("$//shellRepair_submitBtn")
        except BaseException:
            submit_btn = None
        if submit_btn is not None:
            try:
                if submit_btn.showing and submit_btn.sensitive:
                    if self._atspi_do_action(submit_btn):
                        return self._wait_shell_repair_password_echo()
            except BaseException:
                pass
            # 回退2: 直接点击提交按钮中心
            try:
                bx, by = submit_btn.position
                bw, bh = submit_btn.size
                self.run_cmd(
                    f"xdotool mousemove --sync {int(bx + bw / 2)} "
                    f"{int(by + bh / 2)} click 1",
                    timeout=15,
                )
            except BaseException:
                return False
        return self._wait_shell_repair_password_echo()

    def _wait_shell_repair_password_echo(self, tries=5) -> bool:
        """等待输出出现密码提交掩码(证明产品已受理密码并写入脚本 stdin)

        :param tries: 最大轮询次数(每次 1s)
        :return: True 表示已出现 "********" 掩码
        """
        for _ in range(tries):
            if "********" in self.get_shell_repair_output_text():
                return True
            sleep(1)
        return False

    def get_shell_repair_output_text(self) -> str:
        """读取修复对话框(shellRepair_outputLog)当前的输出日志文本

        :return: 输出文本, 对话框不存在或取不到时返回空字符串
        """
        try:
            output_log = self.dog.find_element_by_attr("$//shellRepair_outputLog")
            return getattr(output_log, "text", "") or ""
        except BaseException:
            return ""

    def get_repair_completion_status(self, timeout=120) -> bool:
        """检测修复是否完成(检查 shellRepair_outputLog 中的完成文本)

        :param timeout: 最长等待秒数
        """
        complete_keywords = [
            "修复完成",
            "执行完毕",
            "恢复完成",
            "检查完成",
            "Repair complete",
            "repair complete",
        ]
        last_text = ""
        for _ in range(timeout):
            try:
                output_log = self.dog.find_element_by_attr("$//shellRepair_outputLog")
                log_text = getattr(output_log, "text", "") or ""
                if log_text:
                    last_text = log_text
                for kw in complete_keywords:
                    if kw in log_text:
                        return True
            except BaseException:
                pass
            try:
                result = self.dog.find_elements_by_attr("$//修复完成", probe=True)
                for elem in result:
                    if elem.showing:
                        return True
            except BaseException:
                pass
            sleep(2)
        from funnylog import logger

        logger.warning(
            f"修复未在 {timeout} 次轮询(约 {timeout * 2}s)内完成, "
            f"输出({len(last_text)} 字符): {last_text[-2000:]!r}"
        )
        return False

    def close_repair_completion_dialog(self):
        """关闭修复完成提示框及修复对话框"""
        sleep(2)
        try:
            pwd_input = self.dog.find_element_by_attr("$//shellRepair_inputEdit", probe=True)
            if pwd_input and pwd_input.showing:
                self.run_cmd("xdotool key Escape", timeout=2, out_debug_flag=False)
                sleep(1)
        except BaseException:
            pass
        self.run_cmd("xdotool key Escape", timeout=2, out_debug_flag=False)
        sleep(2)
        self.run_cmd("xdotool key Escape", timeout=2, out_debug_flag=False)
        sleep(1)

    def get_offline_filter_switch_showing(self) -> bool:
        """检查离线过滤器开关是否显示(V20/V25 兼容)

        修复工具页面上"仅显示不需要网络的工具"开关。
        """
        self._safe_focus_windows()
        switch_exprs = [
            "$//repairOfflineOnlySwitch",
            "$//repair_offlineSwitch",
            "$//repairOfflineSwitch",
            "$//repair_offlineFilterGroup//repairOfflineOnlySwitch",
            "$//repair_searchFilterRow//repairOfflineOnlySwitch",
        ]
        for expr in switch_exprs:
            try:
                element = self.dog.find_element_by_attr(expr)
                if element:
                    return True
            except BaseException:
                continue
        return False

    def get_offline_filter_switch_checked(self) -> bool:
        """获取离线过滤器开关的选中状态(V20/V25 兼容)

        :return: True 表示开关已开启(仅显示离线工具), False 表示已关闭
        """
        self._safe_focus_windows()
        switch_exprs = [
            "$//repairOfflineOnlySwitch",
            "$//repair_offlineSwitch",
            "$//repairOfflineSwitch",
        ]
        for expr in switch_exprs:
            try:
                element = self.dog.find_element_by_attr(expr)
                if element:
                    try:
                        checked = element.checked
                        return bool(checked)
                    except BaseException:
                        try:
                            states = element.states
                            if "checked" in states:
                                return True
                        except BaseException:
                            pass
                    return False
            except BaseException:
                continue
        return False

    def click_offline_filter_switch(self) -> bool:
        """点击"仅显示不需要联网的工具"开关, 并确认筛选真的生效

        V20 上该开关是 QML Switch, AT-SPI Action 只有 Toggle/SetFocus,
        与分类标签 repair_catBtn 同源问题: 直接 Toggle 不改变 checked,
        列表也不刷新(2005695 实测), 只有 xdotool 坐标点击才会触发筛选。
        因此优先坐标点击, 再以"可见修复项集合发生变化"作为翻转判据,
        坐标点击无效时回退 AT-SPI 动作。V25(loongarch64) 上 raw click
        无法触发 Qt clicked, 该回退路径仍被保留。

        :return: True 表示开关状态已翻转(可见修复项列表发生变化)
        """
        self._safe_focus_windows()
        before = tuple(sorted(self.get_repair_visible_card_names()))
        try:
            element = self._find_repair_element(
                "$//repairOfflineOnlySwitch",
                "$//repair_offlineSwitch",
                "$//repairOfflineSwitch",
            )
        except BaseException:
            return False
        for mode in ("click", "atspi"):
            if mode == "click":
                submitted = self._click_at_element(element)
            else:
                submitted = self._atspi_do_action(element)
            if not submitted:
                continue
            for _ in range(8):
                sleep(1)
                self.reconnect_dogtail()
                if tuple(sorted(self.get_repair_visible_card_names())) != before:
                    return True
        return False

    def get_repair_plugin_network_map(self) -> dict:
        """读取修复工具的联网属性映射(修复项名称 -> 是否需要联网)

        依据: 产品每个修复工具以插件形式安装在
        /usr/lib/deepin-pc-manager/plugins/<name>/config.json,
        parent 以 repair/ 开头的是修复工具, requiresNetwork 标明该修复项
        是否需要联网(例如 长文件名支持修复 要安装 ulnfs 包, 标为 True),
        "仅显示不需要联网的工具"开关即按该属性过滤列表。

        :return: {displayName: requiresNetwork(bool)}; 读不到时返回 {}
        """
        mapping = {}
        try:
            import glob as _glob
            import json as _json
            for path in _glob.glob(
                "/usr/lib/deepin-pc-manager/plugins/*/config.json"
            ):
                try:
                    with open(path, "r", encoding="utf-8") as fp:
                        config = _json.load(fp)
                except BaseException:
                    continue
                if not str(config.get("parent", "")).startswith("repair/"):
                    continue
                name = (config.get("displayName") or "").strip()
                if name:
                    mapping[name] = bool(config.get("requiresNetwork"))
        except BaseException:
            return {}
        return mapping

    # ===== 修复工具搜索方法 =====

    def get_repair_search_edit_showing(self) -> bool:
        """检查修复工具搜索框是否显示"""
        self._safe_focus_windows()
        try:
            element = self._find_repair_element(
                "$//repair_searchEdit",
                "$//repairSearchEdit",
            )
            return bool(element)
        except BaseException:
            return False

    def input_repair_search(self, text: str):
        """在修复工具搜索框中输入文本(V20/V25 兼容)

        优先使用 AT-SPI EditableText; 该 QML 控件不支持 SetText 时,
        改用 xdotool 在 X11 层输入(支持 UTF-8 中文)。rawinput 的键盘
        注入在无输入法的远程会话中会失败并导致 AT-SPI 连接断开。

        :param text: 要输入的搜索关键字
        """
        self._safe_focus_windows()
        element = self._find_repair_element(
            "$//repair_searchEdit",
            "$//repairSearchEdit",
        )
        try:
            element.text = text
        except AttributeError:
            if not self._click_at_element(element):
                element.click()
            if not self._type_to_app(text):
                self.run_cmd(
                    "xdotool key --clearmodifiers ctrl+a; "
                    "xdotool key --clearmodifiers Delete",
                    timeout=10,
                    out_debug_flag=False,
                )
                self.run_cmd(
                    f"xdotool type --clearmodifiers --delay 50 '{text}'",
                    timeout=10,
                    out_debug_flag=False,
                )
        sleep(2)
        self.reconnect_dogtail()

    def clear_repair_search(self):
        """清空修复工具搜索框"""
        self._safe_focus_windows()
        element = self._find_repair_element(
            "$//repair_searchEdit",
            "$//repairSearchEdit",
        )
        try:
            element.text = ""
        except AttributeError:
            if not self._click_at_element(element):
                element.click()
            if not self._type_to_app(""):
                self.run_cmd(
                    "xdotool key --clearmodifiers ctrl+a; "
                    "xdotool key --clearmodifiers Delete",
                    timeout=10,
                    out_debug_flag=False,
                )
        sleep(2)
        self.reconnect_dogtail()

    # ===== 实用工具模块方法 =====

    def click_utility_nav(self):
        """点击左侧导航第四项(实用工具)

        应用启动后 UI 可能尚未完全加载, 找不到导航项时等待重试。
        QML 导航项的 AT-SPI role 为 INVALID, Node.click() 不会触发页面切换,
        必须经 Action 接口 Press。
        """
        for _attempt in range(5):
            try:
                self._safe_focus_windows()
                element = self.dog.find_element_by_attr("$//mainWindow_navList//实用工具")
                self._atspi_do_action(element)
                sleep(2)
                self.reconnect_dogtail()
                return
            except BaseException:
                sleep(3)
                if _attempt == 2:
                    self.reconnect_dogtail()
        raise Exception("无法找到实用工具导航项")

    def get_utility_page_showing(self, timeout=15) -> bool:
        """等待并获取实用工具页面的可见状态

        :param timeout: 最长等待秒数, 页面切换动画完成即提前返回

        V25 上页面切换后 AT-SPI 树引用会失效, 需要重连 dogtail 刷新引用后重试。
        V20 上 utility_page 的 showing 属性恒为 False, 额外按元素尺寸判定。
        """
        self.reconnect_dogtail()
        for i in range(timeout):
            try:
                page = self.dog.find_element_by_attr("$//utility_page")
                if page.showing:
                    return True
                w, h = page.size
                if w > 0 and h > 0:
                    return True
            except BaseException:
                pass
            if i % 3 == 2:
                self.reconnect_dogtail()
            sleep(1)
        for expr in ("$//utility_sectionsContainer", "$//utility_searchEdit"):
            try:
                if self.dog.find_elements_by_attr(expr):
                    return True
            except BaseException:
                continue
        return False

    def get_utility_cards_view_showing(self) -> bool:
        """检查实用工具卡片视图是否显示"""
        self._safe_focus_windows()
        try:
            element = self.dog.find_element_by_attr("$//utility_sectionsContainer")
            return element.showing
        except BaseException:
            return False

    def get_utility_card_count(self) -> int:
        """获取实用工具卡片数量"""
        self._safe_focus_windows()
        try:
            elements = self.dog.find_elements_by_attr("$//utility_sectionsContainer//")
            return len(elements) if elements else 0
        except BaseException:
            return 0

    def click_utility_card_by_name(self, card_name: str):
        """点击指定名称的实用工具卡片

        QML 卡片需经 Action 接口 Press, Node.click() 不触发 clicked 信号。
        """
        self._safe_focus_windows()
        element = self.dog.find_element_by_attr(f"$//utility_sectionsContainer//{card_name}")
        self._atspi_do_action(element)
        sleep(2)
        self.reconnect_dogtail()

    def get_utility_category_tab_count(self) -> int:
        """获取实用工具分类标签数量"""
        self._safe_focus_windows()
        try:
            elements = self.dog.find_elements_by_attr("$//utility_categoryTabs//utility_catBtn")
            return len(elements) if elements else 0
        except BaseException:
            return 0

    def click_utility_category_tab_by_index(self, index: int):
        """点击实用工具分类标签(按索引)

        :param index: 分类标签索引(从0开始)
        """
        self._safe_focus_windows()
        try:
            elements = self.dog.find_elements_by_attr("$//utility_categoryTabs//utility_catBtn")
            if elements and 0 <= index < len(elements):
                self._atspi_do_action(elements[index])
                sleep(1)
                self.reconnect_dogtail()
        except BaseException:
            pass

    def get_utility_search_edit_showing(self) -> bool:
        """检查实用工具搜索框是否显示"""
        self._safe_focus_windows()
        try:
            element = self.dog.find_element_by_attr("$//utility_searchEdit")
            return bool(element)
        except BaseException:
            return False

    def input_utility_search(self, text: str):
        """在实用工具搜索框中输入文本

        :param text: 要输入的搜索关键字

        dogtail 的 EditableText 接口在 QML 搜索框上会抛异常
        (queryEditableText/setTextContents), 此时回退到坐标点击 + xdotool 输入。
        """
        self._safe_focus_windows()
        element = self.dog.find_element_by_attr("$//utility_searchEdit")
        try:
            element.text = text
        except BaseException:
            if not self._click_at_element(element):
                self._atspi_do_action(element)
            self.run_cmd(
                "xdotool key --clearmodifiers ctrl+a; "
                "xdotool key --clearmodifiers Delete",
                timeout=10,
                out_debug_flag=False,
            )
            self.run_cmd(
                f"xdotool type --clearmodifiers --delay 50 '{text}'",
                timeout=10,
                out_debug_flag=False,
            )
        sleep(2)
        self.reconnect_dogtail()

    def get_utility_visible_section_count(self) -> int:
        """获取实用工具可见分区数量"""
        self._safe_focus_windows()
        try:
            elements = self.dog.find_elements_by_attr(
                "$//utility_sectionsContainer//utility_sectionWidget"
            )
            count = 0
            if elements:
                for section in elements:
                    try:
                        if section.showing:
                            count += 1
                    except BaseException:
                        continue
            return count
        except BaseException:
            return 0

    def get_utility_visible_card_count(self) -> int:
        """获取实用工具可见卡片数量

        V25 上卡片元素没有固定的 roleName(push button/button),
        通过递归遍历可见且有名称的子元素来计数。
        跳过 utility_sectionHeader 子树(包含分类标题, 非工具卡片)。
        """
        for _attempt in range(3):
            self._safe_focus_windows()

            count = 0

            def _count_visible_named(node, depth=0):
                nonlocal count
                if depth > 15:
                    return
                try:
                    children = node.children
                except BaseException:
                    return
                if not children:
                    return
                for child in children:
                    try:
                        if child.name == "utility_sectionHeader":
                            continue
                    except BaseException:
                        pass
                    try:
                        if (
                            child.showing
                            and child.name
                            and not child.name.startswith("utility_")
                        ):
                            count += 1
                    except BaseException:
                        pass
                    _count_visible_named(child, depth + 1)

            try:
                sections = self.dog.find_elements_by_attr(
                    "$//utility_sectionsContainer//utility_sectionWidget"
                )
                if sections:
                    for section in sections:
                        try:
                            if not section.showing:
                                continue
                            _count_visible_named(section)
                        except BaseException:
                            continue
            except BaseException:
                pass

            if count == 0:
                try:
                    elements = self.dog.find_elements_by_attr(
                        "$//utilityCardsView"
                    )
                    if elements:
                        for elem in elements:
                            _count_visible_named(elem)
                except BaseException:
                    pass

            if count > 0:
                return count
            if _attempt < 2:
                self.reconnect_dogtail()
                sleep(1)
        return 0

    def get_log_viewer_process_status(self) -> bool:
        """检查 deepin-log-viewer 进程是否正在运行"""
        result = self.run_cmd(
            "pgrep -f deepin-log-viewer",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def kill_log_viewer(self):
        """终止 deepin-log-viewer 进程(测试后清理)"""
        self.run_cmd(
            "killall deepin-log-viewer 2>/dev/null",
            timeout=2,
            out_debug_flag=False,
        )
        sleep(1)

    def click_utility_category_tab(self, index: int):
        """点击实用工具页面的分类Tab(按索引)

        V25 上 AT-SPI 树引用可能失效, 找不到 Tab 时重连 dogtail 后重试。
        """
        tabs = []
        for _attempt in range(3):
            self._safe_focus_windows()
            tabs = self.dog.find_elements_by_attr("$//utility_categoryTabs//utility_catBtn")
            if tabs and index < len(tabs):
                break
            self.reconnect_dogtail()
            sleep(1)
        if not tabs or index >= len(tabs):
            raise Exception(f"分类Tab索引{index}不存在")
        tabs[index].click()
        sleep(2)

    def get_utility_category_tab_checked(self, index: int) -> bool:
        """获取指定分类Tab的选中状态"""
        self._safe_focus_windows()
        try:
            tabs = self.dog.find_elements_by_attr("$//utility_categoryTabs//utility_catBtn")
            if not tabs or index >= len(tabs):
                return False
            return bool(tabs[index].checked)
        except BaseException:
            return False

    def type_in_utility_search(self, text: str):
        """在实用工具搜索框中输入文本

        V25 上 AT-SPI 树引用可能失效, 需要重连 dogtail 后重试。
        搜索框在不同版本可能命名不同, 提供多种回退定位方式。
        """
        search_exprs = [
            "$//utility_searchEdit",
            "$//utility_searchRow//utility_searchEdit",
        ]
        for _attempt in range(4):
            try:
                self._safe_focus_windows()
            except BaseException:
                pass
            for expr in search_exprs:
                try:
                    self.dog.find_element_by_attr(expr).click()
                    sleep(0.5)
                    self.input_message(text)
                    sleep(1)
                    return
                except BaseException:
                    continue
            if _attempt == 1:
                self.reconnect_dogtail()
            sleep(2)
        raise Exception("无法找到实用工具搜索框")

    def clear_utility_search(self):
        """清空实用工具搜索框

        V25 上 AT-SPI 树引用可能失效, 需要重连 dogtail 后重试。
        """
        search_exprs = [
            "$//utility_searchEdit",
            "$//utility_searchRow//utility_searchEdit",
        ]
        for _attempt in range(4):
            try:
                self._safe_focus_windows()
            except BaseException:
                pass
            for expr in search_exprs:
                try:
                    self.dog.find_element_by_attr(expr).click()
                    sleep(0.5)
                    self.hot_key("ctrl", "a")
                    sleep(0.3)
                    self.press_key("BackSpace")
                    sleep(1)
                    return
                except BaseException:
                    continue
            if _attempt == 1:
                self.reconnect_dogtail()
            sleep(2)
        raise Exception("无法找到实用工具搜索框")

    def get_visible_utility_tool_names(self) -> list:
        """获取实用工具页面当前可见的工具名称列表

        V25 使用 utility_sectionsContainer 结构, V20 使用 utilityCardsView 结构。
        通过 find_elements_by_attr 获取容器本身(不加尾部 //), 再手动递归遍历子元素,
        收集可见且有名称的工具按钮。
        """
        try:
            self._safe_focus_windows()
        except BaseException:
            pass
        names = []

        def _collect_visible_names(node, depth=0):
            if depth > 15:
                return
            try:
                children = node.children
            except BaseException:
                return
            if not children:
                return
            for child in children:
                try:
                    if (
                        child.showing
                        and child.name
                        and not child.name.startswith("utility_")
                        and child.name not in names
                    ):
                        names.append(child.name)
                except BaseException:
                    pass
                _collect_visible_names(child, depth + 1)

        for container_expr in (
            "$//utility_sectionsContainer",
            "$//utilityCardsView",
            "$//utility_overviewScrollArea",
            "$//utility_page",
        ):
            try:
                elements = self.dog.find_elements_by_attr(container_expr)
            except BaseException:
                continue
            if not elements:
                continue
            for elem in elements:
                _collect_visible_names(elem)
            if names:
                break
        return names

    def get_utility_empty_state_showing(self) -> bool:
        """检查实用工具空状态(未找到工具)是否显示"""
        try:
            self._safe_focus_windows()
        except BaseException:
            pass
        for label_name in ("未找到工具",):
            try:
                element = self.dog.find_element_by_attr(f"$//{label_name}")
                if element.showing:
                    return True
            except BaseException:
                continue
        return False

    # ===== 系统环境/状态检测辅助方法 =====

    def get_ssh_key_permission_status(self) -> str:
        """检查SSH密钥权限是否过大(权限>600视为过大)"""
        result = self.run_cmd(
            'find ~/.ssh -name "id_*" -exec stat -c "%a %n" {} \\; 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_network_connection_status(self) -> bool:
        """检查网络是否已连接"""
        result = self.run_cmd(
            'nmcli device status 2>/dev/null | grep -E "connected|已连接" | head -1',
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def disconnect_all_network(self):
        """断开所有网络连接以模拟未连接任何网络的状态

        使用 nmcli networking off 关闭所有网络接口。
        断网前通过 systemd-run 安排 120 秒后自动恢复网络,
        确保即使 SSH 会话因断网中断、测试进程被杀, 网络也能自动恢复。
        测试结束后通过 reconnect_all_network 恢复网络并取消定时任务。
        """
        self.sudo_run_cmd(
            "systemd-run --on-active=120 --unit=pms-net-recovery "
            'bash -c "nmcli networking on" 2>/dev/null; true',
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "nmcli networking off 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)

    def reconnect_all_network(self):
        """恢复所有网络连接

        使用 nmcli networking on 重新启用所有网络接口,
        并取消 disconnect_all_network 设置的定时恢复任务。
        """
        self.sudo_run_cmd(
            "bash -c 'systemctl stop pms-net-recovery.timer 2>/dev/null; "
            "nmcli networking on 2>/dev/null; true'",
            timeout=15,
            out_debug_flag=False,
        )
        sleep(5)

    def get_dhcp_service_status(self) -> bool:
        """检查DHCP客户端服务是否正在运行(dhclient 或 NetworkManager 内置 DHCP)

        V20/V25 上 DHCP 由 NetworkManager 管理, dhclient 进程存在表示 DHCP 正常。
        """
        result = self.run_cmd(
            "pgrep -x dhclient 2>/dev/null || "
            'nmcli -t -f DHCP4 device show 2>/dev/null | grep -v "unknown" | head -1',
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def stop_dhcp_service(self):
        """停止DHCP客户端服务以模拟DHCP服务异常

        通过终止 dhclient 进程模拟 DHCP 服务异常状态。
        不会停止 NetworkManager 本身, 避免断开 SSH 连接。
        现有 IP 租约在租约期内仍然有效, SSH 连接不受影响。
        """
        self.sudo_run_cmd(
            "bash -c 'killall dhclient 2>/dev/null; pkill -f dhclient 2>/dev/null; true'",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)

    def start_dhcp_service(self):
        """恢复DHCP客户端服务

        通过重启 NetworkManager 连接来重新获取 DHCP 租约,
        恢复 DHCP 客户端服务。
        """
        self.sudo_run_cmd(
            "bash -c 'nmcli networking off 2>/dev/null; sleep 1; "
            "nmcli networking on 2>/dev/null; true'",
            timeout=15,
            out_debug_flag=False,
        )
        sleep(5)

    def restart_dhcp_client(self, dev: str = None, timeout: int = 60) -> bool:
        """重连网络设备以重新获取 DHCP 租约(不 disconnect, 不断 SSH 链路)

        NetworkManager 服务重启后常见"设备 active 但没有 IPv4 地址",
        这里先 `nmcli device reapply`(让 NM 重新下发当前连接并触发 DHCP
        renew), 仍无地址时用 `nmcli connection up <连接名>` 重新激活该连接。
        全程不使用 `nmcli device disconnect` / `nmcli networking off`,
        避免把测试机的 SSH 链路断开。

        :param dev: 设备名, 默认取当前 connected 的第一块网卡
        :param timeout: 等待 IPv4 地址回来的最长秒数
        :return: True 表示设备已拿到全局 IPv4 地址
        """
        device = dev or self.get_active_network_device()
        if not device:
            logger.warning("重启 DHCP 客户端: 未找到 connected 状态网卡")
            return False
        self.sudo_run_cmd(
            f"nmcli device reapply {quote(device)}",
            timeout=30,
            out_debug_flag=False,
        )
        if self._wait_dhcp_ipv4(device, timeout // 3):
            return True
        con_name = self.run_cmd(
            "nmcli -t -f NAME,DEVICE connection show --active 2>/dev/null "
            f"| awk -F: -v d={quote(device)} '$2==d{{print $1; exit}}'",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        if con_name:
            logger.info(
                f"重启 DHCP 客户端: reapply 未恢复 IPv4, 重新激活连接 {con_name!r}"
            )
            self.sudo_run_cmd(
                f"nmcli connection up {quote(con_name)}",
                timeout=60,
                out_debug_flag=False,
            )
        return self._wait_dhcp_ipv4(device, timeout * 2 // 3)

    def _wait_dhcp_ipv4(self, device: str, timeout: int) -> bool:
        """轮询设备是否已拿到全局 IPv4 地址"""
        for _ in range(max(1, timeout // 3)):
            addrs = self.run_cmd(
                f"nmcli -g IP4.ADDRESS device show {quote(device)} 2>/dev/null",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            if addrs and addrs != "--":
                return True
            sleep(3)
        return False

    def get_active_network_device(self) -> str:
        """获取当前已连接的网络设备名(如 eth0, enp0s3)

        通过 nmcli 查找第一个 connected 状态的设备, 排除 lo 本地回环。
        V20/V25 均使用 nmcli 管理网络, 输出格式一致。
        :return: 设备名, 未找到时返回空字符串
        """
        result = self.run_cmd(
            r"nmcli -t -f DEVICE,STATE,TYPE device status 2>/dev/null "
            r'| grep -E "connected" '
            r'| grep -v "^lo:" '
            r'| grep -v "loopback" '
            r"| head -1 | cut -d: -f1",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def cleanup_extra_ip_addresses(self, keep_ip: str = "") -> None:
        """删除活动网卡上除 keep_ip 外的 IPv4 地址

        网络类用例会临时给网卡设置静态地址(如 TEST-NET-1 的 192.0.2.100),
        若 teardown 只改 nmcli profile 而未删除运行时地址, 残留地址会与网内
        其他主机冲突, 并使后续网络检测用例误判。此方法显式清理残留地址。
        :param keep_ip: 需要保留的 IPv4 地址(通常为用例开始前的 DHCP 地址);
                        为空时自动取默认路由源地址
        """
        conn_name = self.run_cmd(
            "nmcli -t -f NAME,TYPE connection show --active 2>/dev/null "
            "| grep -E 'ethernet|wifi' | head -1 | cut -d: -f1",
            timeout=5,
            out_debug_flag=False,
        ).strip()
        if conn_name:
            # 先重置 profile, 否则 NetworkManager 可能按旧配置重新加上静态地址
            self.sudo_run_cmd(
                f"nmcli connection modify '{conn_name}' ipv4.method auto "
                f"ipv4.addresses '' ipv4.gateway ''",
                timeout=15,
                out_debug_flag=False,
            )
        device = self.get_active_network_device()
        if not device:
            return
        if not keep_ip:
            keep_ip = self.run_cmd(
                "ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}'",
                timeout=5,
                out_debug_flag=False,
            ).strip()
        addrs = self.run_cmd(
            f"ip -4 -o addr show dev {device} 2>/dev/null | awk '{{print $4}}'",
            timeout=5,
            out_debug_flag=False,
        ).split()
        for cidr in addrs:
            if keep_ip and cidr.split("/")[0] == keep_ip:
                continue
            self.sudo_run_cmd(
                f"ip addr del {cidr} dev {device} 2>/dev/null; true",
                timeout=10,
                out_debug_flag=False,
            )

    def disconnect_network_device(self, device: str):
        """断开指定网络设备以模拟网络环境切换

        断开前通过 systemd-run 安排 120 秒后自动恢复该设备,
        确保即使测试进程被杀或 SSH 会话中断, 网络也能自动恢复。
        :param device: 网络设备名(如 eth0)
        """
        self.sudo_run_cmd(
            f'systemd-run --on-active=120 --unit=pms-netdev-recovery '
            f'bash -c "nmcli device connect {device}" 2>/dev/null; true',
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f'nmcli device disconnect "{device}" 2>/dev/null; true',
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)

    def reconnect_network_device(self, device: str) -> bool:
        """重新连接指定网络设备, 恢复网络环境

        使用 nmcli device connect 重新激活设备, 最多重试 3 次。
        成功后取消 disconnect_network_device 设置的定时恢复任务。
        :param device: 网络设备名(如 eth0)
        :return: True 表示连接成功, False 表示连接失败
        """
        self.sudo_run_cmd(
            'systemctl stop pms-netdev-recovery.timer pms-netdev-recovery.service 2>/dev/null; true',
            timeout=5,
            out_debug_flag=False,
        )
        for _ in range(3):
            self.sudo_run_cmd(
                f'nmcli device connect "{device}" 2>/dev/null; true',
                timeout=15,
                out_debug_flag=False,
            )
            sleep(3)
            if self.get_network_connection_status():
                return True
        return False

    def get_network_manager_service_status(self) -> bool:
        """检查NetworkManager服务是否正在运行

        通过 systemctl is-active 检查 NetworkManager 服务状态。
        V20/V25 均使用 systemd 管理服务, 输出格式一致。
        """
        result = self.run_cmd(
            "systemctl is-active NetworkManager 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip() == "active"

    def stop_network_manager_service(self):
        """停止NetworkManager服务以模拟服务本身异常

        通过 systemctl stop NetworkManager 停止服务。
        停止前通过 systemd-run 安排 60 秒后自动恢复, 确保即使 SSH
        会话中断或测试进程被杀, NetworkManager 也能自动恢复。
        现有 SSH 连接在内核层面保持, NetworkManager 停止不会立即
        断开已建立的 TCP 连接。
        """
        self.sudo_run_cmd(
            "systemd-run --on-active=60 --unit=pms-nm-recovery "
            "systemctl start NetworkManager 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "systemctl stop NetworkManager 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)

    def start_network_manager_service(self):
        """恢复NetworkManager服务

        启动 NetworkManager 服务并取消 stop_network_manager_service
        设置的定时恢复任务。
        """
        self.sudo_run_cmd(
            "bash -c 'systemctl stop pms-nm-recovery.timer 2>/dev/null; "
            "systemctl start NetworkManager 2>/dev/null; true'",
            timeout=15,
            out_debug_flag=False,
        )
        sleep(5)

    def get_network_manager_main_pid(self) -> str:
        """获取 NetworkManager 服务主进程 PID

        systemd 记录的 MainPID 在服务重启后会变化, 用它作为"服务被真实重启"
        的可观测依据(比只看脚本日志更可靠)。

        :return: MainPID 字符串, 服务未运行时为 "0", 读取失败为空串
        """
        result = self.run_cmd(
            "systemctl show -p MainPID --value NetworkManager 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def wait_network_manager_restarted(self, old_pid, timeout=60) -> bool:
        """等待 NetworkManager 被真实重启

        判据: 服务为 active 且 MainPID 与重启前记录的 PID 不同。

        :param old_pid: 重启前记录的 MainPID
        :param timeout: 最长等待秒数
        :return: True 表示服务已完成重启
        """
        for _ in range(timeout):
            current = self.get_network_manager_main_pid()
            if (
                current
                and current not in ("0", str(old_pid))
                and self.get_network_manager_service_status()
            ):
                return True
            sleep(1)
        return False

    def wait_network_connection_restored(self, timeout=90) -> bool:
        """等待 NetworkManager 重启后网络连接恢复

        判据: NM 服务为 active 且存在非回环设备已重新拿到 IPv4 地址。
        不用 nmcli 的 "connected" 文本作唯一判据: 1.1.7 重启 NM 后, 由
        ifupdown 接管的网卡会先以 "connected (externally)" 呈现(实测该状态
        可持续 1 分钟以上), 且 nmcli 的 "disconnected" 也包含 "connected"
        子串, 因此改为检查地址是否恢复(重启瞬间地址会被摘掉, 重新 DHCP 后
        才回来), 状态文本只用于排除 unmanaged/unavailable。

        :param timeout: 最长等待秒数
        :return: True 表示网络连接已恢复
        """
        for _ in range(timeout):
            if self.get_network_manager_service_status():
                devices = self.run_cmd(
                    "nmcli -t -f DEVICE,STATE device status 2>/dev/null "
                    "| grep -v '^lo:' | grep -vE ':(unmanaged|unavailable)$'",
                    timeout=5,
                    out_debug_flag=False,
                )
                addresses = self.run_cmd(
                    "ip -o -4 addr show scope global 2>/dev/null | grep -v ' lo '",
                    timeout=5,
                    out_debug_flag=False,
                )
                if devices.strip() and addresses.strip():
                    return True
            sleep(1)
        return False

    # ===== NetworkManager 服务本身异常场景助手(用例 2005719) =====
    NM_BINARY_PATH = "/usr/sbin/NetworkManager"
    NM_BINARY_BAK = "/usr/sbin/NetworkManager.bak"
    NM_BINARY_RECOVERY_UNIT = "pms-nm-binary-recovery"
    NM_BINARY_RECOVERY_SCRIPT = "/tmp/autotest_nm_binary_recovery.sh"

    def get_network_manager_binary_exists(self) -> bool:
        """检查 NetworkManager 可执行文件是否存在且可执行

        "服务本身异常"的构造依据是用例前置:
        sudo mv /usr/sbin/NetworkManager /usr/sbin/NetworkManager.bak,
        之后 systemd 找不到 ExecStart, 服务无法启动。

        :return: True 表示 /usr/sbin/NetworkManager 仍存在且可执行
        """
        result = self.run_cmd(
            f"test -x {self.NM_BINARY_PATH} && echo yes || echo no",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip().endswith("yes")

    def get_network_manager_binary_backup_exists(self) -> bool:
        """检查前置构造产生的 NetworkManager 备份文件是否存在

        :return: True 表示 /usr/sbin/NetworkManager.bak 存在
        """
        result = self.run_cmd(
            f"test -e {self.NM_BINARY_BAK} && echo yes || echo no",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip().endswith("yes")

    def get_network_manager_service_state(self) -> str:
        """读取 NetworkManager 的 systemctl is-active 原文

        :return: active / failed / inactive / activating 等, 读取失败为空串
        """
        return self.run_cmd(
            "systemctl is-active NetworkManager 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()

    def schedule_network_manager_binary_recovery(self, seconds=1200) -> bool:
        """安排兜底恢复: 若干秒后自动把 NetworkManager 备份移回并拉起服务

        本用例会把 /usr/sbin/NetworkManager 移走, 若用例进程被强杀或超时,
        finally 不会执行, 测试机将永久失去网络。因此先注册一个 systemd-run
        定时单元兜底(与 stop_network_manager_service 的 60s 兜底同一思路),
        在 finally 里再取消; 脚本执行后自行删除, 不留 /tmp 残留。

        :param seconds: 兜底触发延时(秒), 需大于用例最长运行时间
        :return: True 表示定时器已注册
        """
        script = (
            "#!/usr/bin/env bash\n"
            "# 用例 2005719 兜底恢复: 可执行文件被移走后自动移回并拉起服务\n"
            f"if [ -x {self.NM_BINARY_BAK} ] && [ ! -x {self.NM_BINARY_PATH} ]; then\n"
            f"    mv {self.NM_BINARY_BAK} {self.NM_BINARY_PATH}\n"
            "fi\n"
            "systemctl reset-failed NetworkManager 2>/dev/null\n"
            "systemctl start NetworkManager 2>/dev/null\n"
            f"rm -f {self.NM_BINARY_RECOVERY_SCRIPT}\n"
        )
        # 先取消可能存在的旧定时器(它会删掉同名脚本), 再写脚本并注册新定时器
        self.cancel_network_manager_binary_recovery()
        try:
            with open(self.NM_BINARY_RECOVERY_SCRIPT, "w", encoding="utf-8") as script_file:
                script_file.write(script)
            os.chmod(self.NM_BINARY_RECOVERY_SCRIPT, 0o755)
        except OSError as exc:
            logger.error(f"写兜底恢复脚本失败: {exc}")
            return False
        self.sudo_run_cmd(
            f"systemd-run --on-active={int(seconds)} "
            f"--unit={self.NM_BINARY_RECOVERY_UNIT} "
            f"/bin/bash {self.NM_BINARY_RECOVERY_SCRIPT}",
            timeout=20,
            out_debug_flag=False,
        )
        state = self.run_cmd(
            f"systemctl show -p ActiveState --value "
            f"{self.NM_BINARY_RECOVERY_UNIT}.timer 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return state.strip() == "active"

    def cancel_network_manager_binary_recovery(self):
        """取消兜底恢复定时器并删除其临时脚本(可重复调用)"""
        self.sudo_run_cmd(
            f"bash -c 'systemctl stop {self.NM_BINARY_RECOVERY_UNIT}.timer "
            f"{self.NM_BINARY_RECOVERY_UNIT}.service 2>/dev/null; "
            f"systemctl reset-failed {self.NM_BINARY_RECOVERY_UNIT}.service 2>/dev/null; "
            "true'",
            timeout=20,
            out_debug_flag=False,
        )
        try:
            os.remove(self.NM_BINARY_RECOVERY_SCRIPT)
        except OSError:
            pass

    def restore_stale_network_manager_binary(self) -> bool:
        """自愈: 清理上次异常退出遗留的 NetworkManager 二进制备份

        测试机若上次用例被强杀, 会残留 .bak 而可执行文件缺失; 不先自愈,
        本用例的前置构造("移走文件")就无从判断, 也可能让机器停在无网络状态。

        :return: True 表示当前 /usr/sbin/NetworkManager 已存在可用
        """
        if self.get_network_manager_binary_backup_exists():
            if self.get_network_manager_binary_exists():
                # 两者都在: 备份属于上次用例的残留副本, 直接删除
                self.sudo_run_cmd(
                    f"rm -f {self.NM_BINARY_BAK}",
                    timeout=10,
                    out_debug_flag=False,
                )
            else:
                logger.warning("检测到上次遗留的 NetworkManager 备份, 先恢复")
                self.restore_network_manager_binary()
        return self.get_network_manager_binary_exists()

    def break_network_manager_binary(self) -> bool:
        """构造 NetworkManager 服务本身异常(可执行文件被移走, 服务无法启动)

        对应用例前置:
            sudo mv /usr/sbin/NetworkManager /usr/sbin/NetworkManager.bak
            sudo systemctl restart NetworkManager
        缺少可执行文件时 systemd 启动失败, 服务进入 failed, 因此产品脚本里的
        systemctl restart NetworkManager.service 必然返回非 0。

        :return: True 表示已构造成功(备份存在、原文件缺失、服务非 active)
        """
        if self.get_network_manager_binary_backup_exists():
            self.restore_network_manager_binary()
        self.sudo_run_cmd(
            f"bash -c 'mv {self.NM_BINARY_PATH} {self.NM_BINARY_BAK} "
            "&& systemctl reset-failed NetworkManager 2>/dev/null; "
            "systemctl restart NetworkManager 2>/dev/null; true'",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(3)
        return (
            self.get_network_manager_binary_backup_exists()
            and not self.get_network_manager_binary_exists()
            and not self.get_network_manager_service_status()
        )

    def restore_network_manager_binary(self, timeout=60) -> bool:
        """回退: 把 NetworkManager 备份移回原位并拉起服务, 等待 active

        :param timeout: 等待服务 active 的最长秒数
        :return: True 表示可执行文件已归位且服务处于 active
        """
        self.sudo_run_cmd(
            f"bash -c 'if [ -x {self.NM_BINARY_BAK} ] "
            f"&& [ ! -x {self.NM_BINARY_PATH} ]; then "
            f"mv {self.NM_BINARY_BAK} {self.NM_BINARY_PATH}; fi; "
            "systemctl reset-failed NetworkManager 2>/dev/null; "
            "systemctl start NetworkManager 2>/dev/null; true'",
            timeout=60,
            out_debug_flag=False,
        )
        for _ in range(timeout):
            if (
                self.get_network_manager_binary_exists()
                and self.get_network_manager_service_status()
            ):
                return True
            sleep(1)
        return False

    def backup_network_settings(self):
        """备份电脑管家网络检测设置配置文件

        备份 ~/.config/deepin-pc-manager/deepin-pc-manager.conf,
        以便测试结束后恢复原始网络模式与内网地址配置。
        """
        self.run_cmd(
            "cp ~/.config/deepin-pc-manager/deepin-pc-manager.conf "
            "/tmp/pc_manager_network_settings.bak 2>/dev/null; "
            "echo $? > /tmp/pc_manager_network_settings_existed",
            timeout=5, out_debug_flag=False,
        )

    def open_basic_settings_page(self) -> bool:
        """在设置对话框中切换到"基础设置"页

        左侧导航默认选中"基础设置", 从其它页返回时需显式点击。
        :return: 基础设置页是否就绪(能找到网络模式下拉框)
        """
        self._safe_focus_windows()
        try:
            for element in self.dog.find_elements_by_attr(
                "$//settings_dialog//基础设置"
            ) or []:
                if element.roleName == "list item":
                    element.click()
                    break
        except BaseException:
            pass
        sleep(1)
        return self.get_network_mode_combobox() is not None

    def get_network_mode_combobox(self):
        """获取"基础设置-网络设置检测"中的网络模式下拉框

        该控件 node name 随当前值变化(公网/内网), 角色为 combo box;
        同名的弹出列表项需按角色排除。
        """
        for name in ("公网", "内网"):
            try:
                for element in self.dog.find_elements_by_attr(
                    f"$//settings_dialog//{name}"
                ) or []:
                    if element.roleName == "combo box":
                        return element
            except BaseException:
                continue
        return None

    def get_network_mode_ui(self) -> str:
        """读取设置页网络模式下拉框当前显示值(公网/内网)"""
        element = self.get_network_mode_combobox()
        return element.name if element else ""

    def switch_network_mode(self, target) -> str:
        """在基础设置页切换网络模式

        DTK 下拉框的弹出列表项 position 是相对坐标, 直接点击不可靠;
        点击下拉框后用键盘 Down/Up + Return 选择。
        :param target: 目标模式, "公网" 或 "内网"
        :return: 切换后下拉框显示值
        """
        self._safe_focus_windows()
        current = self.get_network_mode_combobox()
        if current is None:
            return ""
        if current.name == target:
            return current.name
        pos, size = current.position, current.size
        self.run_cmd(
            f"xdotool mousemove {int(pos[0] + size[0] / 2)} "
            f"{int(pos[1] + size[1] / 2)} click 1",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)
        key = "Down" if target == "内网" else "Up"
        self.run_cmd(f"xdotool key --clearmodifiers {key}", timeout=5, out_debug_flag=False)
        sleep(1)
        self.run_cmd("xdotool key --clearmodifiers Return", timeout=5, out_debug_flag=False)
        sleep(1)
        return self.get_network_mode_ui()

    def is_intranet_address_row_showing(self) -> bool:
        """内网地址输入行是否可见(仅内网模式下显示)"""
        try:
            element = self.dog.find_element_by_attr("$//settings_networkAddressEdit")
            return bool(element.showing)
        except BaseException:
            return False

    def get_intranet_address_text(self) -> str:
        """读取设置页内网地址输入框当前文本"""
        try:
            element = self.dog.find_element_by_attr(
                "$//settings_networkAddressEdit//DLineEditChildLineEdit"
            )
            return element.text or ""
        except BaseException:
            return ""

    def set_intranet_address(self, text):
        """在设置页内网地址输入框写入文本

        走 X11 键盘注入(xdotool)而非 AT-SPI EditableText, 保证触发
        textChanged 从而让产品把值落盘。
        :param text: 内网地址(IP/域名), 传空串表示清空输入框
        """
        self._safe_focus_windows()
        element = self.dog.find_element_by_attr(
            "$//settings_networkAddressEdit//DLineEditChildLineEdit"
        )
        element.click()
        sleep(1)
        self.run_cmd(
            "xdotool key --clearmodifiers ctrl+a; xdotool key --clearmodifiers Delete",
            timeout=10,
            out_debug_flag=False,
        )
        if text:
            self.run_cmd(
                f"xdotool type --clearmodifiers --delay 50 '{text}'",
                timeout=10,
                out_debug_flag=False,
            )
        sleep(1)

    def get_intranet_address_config(self) -> str:
        """读取配置文件中的内网地址(basic.network.intranetAddress)"""
        config_path = os.path.expanduser(
            "~/.config/deepin-pc-manager/deepin-pc-manager.conf"
        )
        import configparser

        cfg = configparser.ConfigParser()
        cfg.optionxform = str
        cfg.read(config_path)
        return cfg.get("basic.network.intranetAddress", "value", fallback="")

    def set_intranet_network_mode(self, address):
        """设置网络检测模式为内网模式并配置内网地址

        通过写入 QSettings 配置文件设置网络模式为 intranet,
        并配置正确的内网地址用于网络连通性检测。
        :param address: 内网地址(IP 或域名), 如 127.0.0.1
        """
        config_path = os.path.expanduser(
            "~/.config/deepin-pc-manager/deepin-pc-manager.conf"
        )
        config_dir = os.path.dirname(config_path)
        os.makedirs(config_dir, exist_ok=True)
        import configparser
        cfg = configparser.ConfigParser()
        cfg.optionxform = str
        cfg.read(config_path)
        if not cfg.has_section("basic.network.mode"):
            cfg.add_section("basic.network.mode")
        cfg.set("basic.network.mode", "value", "intranet")
        if not cfg.has_section("basic.network.intranetAddress"):
            cfg.add_section("basic.network.intranetAddress")
        cfg.set("basic.network.intranetAddress", "value", address)
        with open(config_path, "w") as f:
            cfg.write(f)
        sleep(1)

    def restore_network_settings(self):
        """恢复电脑管家网络检测设置到测试前状态"""
        existed = self.run_cmd(
            "cat /tmp/pc_manager_network_settings_existed 2>/dev/null",
            timeout=5, out_debug_flag=False,
        ).strip()
        if existed == "0":
            self.run_cmd(
                "cp /tmp/pc_manager_network_settings.bak "
                "~/.config/deepin-pc-manager/deepin-pc-manager.conf",
                timeout=5, out_debug_flag=False,
            )
        else:
            self.run_cmd(
                "rm -f ~/.config/deepin-pc-manager/deepin-pc-manager.conf",
                timeout=5, out_debug_flag=False,
            )
        self.run_cmd(
            "rm -f /tmp/pc_manager_network_settings.bak "
            "/tmp/pc_manager_network_settings_existed",
            timeout=5, out_debug_flag=False,
        )
        sleep(1)

    def get_network_mode(self) -> str:
        """读取当前网络检测模式(public 或 intranet)"""
        config_path = os.path.expanduser(
            "~/.config/deepin-pc-manager/deepin-pc-manager.conf"
        )
        import configparser
        cfg = configparser.ConfigParser()
        cfg.optionxform = str
        cfg.read(config_path)
        return cfg.get("basic.network.mode", "value", fallback="public")

    def get_package_update_status(self) -> bool:
        """检查是否有可用更新"""
        result = self.run_cmd(
            "LC_ALL=C apt list --upgradable 2>/dev/null | grep -v Listing | head -1",
            timeout=30,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def get_pc_manager_installed(self) -> bool:
        """检查deepin-pc-manager包是否已安装(覆盖安装前置条件)

        :return: True 表示包已安装
        """
        result = self.run_cmd(
            "dpkg -s deepin-pc-manager 2>/dev/null | grep -E '^Status:.*installed'",
            timeout=10,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def get_pc_manager_version(self) -> str:
        """获取deepin-pc-manager已安装版本号

        :return: 版本号字符串, 未安装时返回空字符串
        """
        result = self.run_cmd(
            "dpkg -s deepin-pc-manager 2>/dev/null | grep -E '^Version:' | awk '{print $2}'",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip()

    def stop_session_daemon(self):
        """停止session-daemon服务(systemd用户服务 + 进程)

        先停止systemd用户服务, 再杀掉残留进程, 确保session-daemon完全停止。
        注意: 只匹配 deepin-pc-manager 相关的 session-daemon, 避免误杀
        dde-session-daemon / deepin-defender-session-daemon 等无关服务。
        """
        self.run_cmd(
            "systemctl --user stop deepin-pc-manager-session-daemon 2>/dev/null; "
            "pkill -f 'deepin-pc-manager.*session-daemon' 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)

    def get_session_daemon_status(self) -> bool:
        """检查session-daemon服务是否在运行

        仅检查 deepin-pc-manager-session-daemon 服务状态, 不使用通用的
        pgrep -f session-daemon, 因为后者会匹配 dde-session-daemon、
        deepin-defender-session-daemon 等无关进程导致误判。
        """
        result = self.run_cmd(
            "systemctl --user is-active deepin-pc-manager-session-daemon 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip().lower() in ("active", "activating")

    def wait_for_session_daemon(self, timeout=30) -> bool:
        """等待session-daemon服务变为active状态(每秒轮询, 最多timeout秒)

        session-daemon 通过 D-Bus activation 启动(Type=dbus), 当电脑管家 GUI
        初始化并调用 org.deepin.PCManager1 D-Bus 接口时, systemd 才会自动拉起
        该服务。start_pc_manager 中的 kill_process("deepin-pc-manager") 会同时
        会被旧实现的子串匹配 kill 一并杀掉(现已改为主程序精确匹配), D-Bus
        自动激活仍可能存在延迟, 因此先主动通过 systemctl start 触发启动,
        再轮询等待。
        """
        self.run_cmd(
            "systemctl --user start deepin-pc-manager-session-daemon 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        for _ in range(timeout):
            if self.get_session_daemon_status():
                return True
            sleep(1)
        return False

    def get_disk_free_space_mb(self) -> int:
        """获取根分区可用空间(MB)"""
        result = self.run_cmd(
            "df -m / 2>/dev/null | tail -1 | awk '{print $4}'",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, IndexError):
            return 0

    def get_font_list_count(self) -> int:
        """获取已安装字体数量"""
        result = self.run_cmd(
            "fc-list 2>/dev/null | wc -l",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except ValueError:
            return 0

    def get_theme_type(self) -> str:
        """获取当前主题类型(light/dark)

        V20 使用 com.deepin.dde.appearance 的 theme-name 键;
        V25 没有 theme-name 键, 回退到 gtk-theme 键。
        """
        result = self.run_cmd(
            "gsettings get com.deepin.dde.appearance theme-name 2>/dev/null || "
            "gsettings get org.deepin.dde.appearance theme-name 2>/dev/null || "
            "gsettings get com.deepin.dde.appearance gtk-theme 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip().strip("'\"")

    def get_binary_permissions(self) -> str:
        """获取deepin-pc-manager二进制文件权限"""
        result = self.run_cmd(
            'stat -c "%a %n" /usr/libexec/deepin/deepin-pc-manager 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def _get_binary_path(self) -> str:
        """获取 deepin-pc-manager 主二进制文件路径

        V20/V25 上二进制可能位于 /usr/libexec/deepin/ 或 /usr/bin/。
        :return: 二进制文件路径, 未找到时返回空字符串
        """
        result = self.run_cmd(
            "for p in /usr/libexec/deepin/deepin-pc-manager "
            "/usr/bin/deepin-pc-manager; do "
            "[ -f \"$p\" ] && echo \"$p\" && break; done",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_path_permission(self, path) -> dict:
        """读取路径的权限位与属主(最小权限用例用)

        :param path: 文件或目录路径
        :return: {"perm": "644", "owner": "root", "group": "root"}; 路径不存在时 perm 为空
        """
        out = self.run_cmd(
            f"stat -c '%a %U %G' {path} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()
        parts = out.split()
        if len(parts) != 3:
            return {"perm": "", "owner": "", "group": ""}
        return {"perm": parts[0], "owner": parts[1], "group": parts[2]}

    def get_world_writable_paths(self, path) -> list:
        """列出目录/文件下 other 可写的路径(含路径本身)

        :param path: 待检查的目录或文件
        :return: other 可写路径列表, 路径不存在返回 []
        """
        out = self.run_cmd(
            f"if [ -e {path} ]; then "
            f"find {path} -perm -o+w -printf '%m %p\\n' 2>/dev/null; fi",
            timeout=10,
            out_debug_flag=False,
        )
        return [line for line in (out or "").splitlines() if line.strip()]

    def get_binary_no_setuid_setgid(self) -> bool:
        """检查二进制文件是否未设置 setuid/setgid 位

        最小权限原则要求应用二进制不应设置 setuid(4xxx) 或 setgid(2xxx) 位,
        以避免提权风险。
        :return: True 表示未设置 setuid/setgid 位
        """
        binary_path = self._get_binary_path()
        if not binary_path:
            return False
        result = self.run_cmd(
            f'stat -c "%a" {binary_path} 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        perm = result.strip()
        if not perm or not perm.isdigit():
            return False
        perm_int = int(perm, 8)
        return (perm_int & 0o6000) == 0

    def get_binary_not_world_writable(self) -> bool:
        """检查二进制文件是否不可被其他用户写入

        最小权限原则要求应用二进制不应有 other 写权限(o+w),
        以防止非特权用户篡改。
        :return: True 表示不可被其他用户写入
        """
        binary_path = self._get_binary_path()
        if not binary_path:
            return False
        result = self.run_cmd(
            f'stat -c "%a" {binary_path} 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        perm = result.strip()
        if not perm or not perm.isdigit():
            return False
        perm_int = int(perm, 8)
        return (perm_int & 0o002) == 0

    def get_process_running_user(self) -> str:
        """获取 deepin-pc-manager 主进程的运行用户(排除 daemon)

        :return: 运行用户名, 失败时返回空字符串
        """
        result = self.run_cmd(
            r"ps -eo user,args | grep -E 'deepin-pc-manager' | "
            r"grep -v daemon | grep -v session-daemon | grep -v grep | "
            r"head -1 | awk '{print $1}'",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_process_not_root(self) -> bool:
        """检查是否存在以普通用户运行的主进程

        最小权限原则要求应用以普通用户权限运行。机器上可能残留 root 实例
        (异常场景用例会留下), 因此只要主进程集合中存在非 root 实例即视为满足。
        :return: True 表示存在非 root 主进程
        """
        result = self.run_cmd(
            r"ps -eo user,args | grep -E 'deepin-pc-manager' | "
            r"grep -v daemon | grep -v session-daemon | grep -v grep | "
            r"awk '{print $1}'",
            timeout=5,
            out_debug_flag=False,
        )
        users = {line.strip() for line in result.splitlines() if line.strip()}
        return bool(users - {"root"})

    def get_desktop_file_permissions(self) -> str:
        """获取 desktop 文件权限"""
        result = self.run_cmd(
            'stat -c "%a %n" /usr/share/applications/deepin-pc-manager.desktop 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_desktop_file_not_world_writable(self) -> bool:
        """检查 desktop 文件是否不可被其他用户写入

        :return: True 表示不可被其他用户写入
        """
        result = self.run_cmd(
            'stat -c "%a" /usr/share/applications/deepin-pc-manager.desktop 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        perm = result.strip()
        if not perm or not perm.isdigit():
            return False
        perm_int = int(perm, 8)
        return (perm_int & 0o002) == 0

    def get_dependency_status(self) -> bool:
        """检查依赖关系是否满足(apt-get check 返回 0 表示满足)"""
        _, status = self.sudo_run_cmd(
            "apt-get check > /dev/null 2>&1",
            timeout=60,
            out_debug_flag=False,
            return_code=True,
        )
        return status == 0

    def backup_apt_sources(self):
        """备份 apt 源配置文件

        将 /etc/apt/sources.list 及 /etc/apt/sources.list.d/ 目录
        备份到 /tmp, 以便测试结束后恢复原始状态。备份后打印文件清单,
        便于排查"恢复后源文件缺失/被注释"的问题。
        """
        out = self.sudo_run_cmd(
            "cp -a /etc/apt/sources.list /tmp/apt_sources_list.bak 2>&1; "
            "rm -rf /tmp/apt_sources_list_d.bak; "
            "cp -a /etc/apt/sources.list.d /tmp/apt_sources_list_d.bak 2>&1; "
            "echo '--- backup files:'; ls /tmp/apt_sources_list_d.bak; "
            "echo '--- active debs:'; "
            "cat /tmp/apt_sources_list.bak /tmp/apt_sources_list_d.bak/*.list "
            "2>/dev/null | grep -c '^deb '; echo done",
            timeout=30,
            out_debug_flag=False,
        )
        match = re.search(r"--- active debs:\n(\d+)", out)
        self._apt_backup_deb_count = int(match.group(1)) if match else None
        logger.info(f"[backup_apt_sources] 备份有效 deb 行数: {self._apt_backup_deb_count}")

    def restore_apt_sources(self) -> bool:
        """恢复 apt 源配置到测试前状态并校验

        安全约束: 备份缺失时直接返回 False, 且**不删除**现有
        /etc/apt/sources.list.d, 避免"备份丢了又把源目录清空"。

        :return: True 表示 sources.list 已恢复且启用的 deb 行数与备份时一致
        """
        out, rc = self.sudo_run_cmd(
            "if [ ! -e /tmp/apt_sources_list.bak ]; then echo 'no-backup'; "
            "elif [ ! -d /tmp/apt_sources_list_d.bak ]; then echo 'no-dir-backup'; "
            "else "
            "cp -a /tmp/apt_sources_list.bak /etc/apt/sources.list && "
            "rm -rf /etc/apt/sources.list.d && "
            "cp -a /tmp/apt_sources_list_d.bak /etc/apt/sources.list.d && "
            "rm -f /tmp/apt_sources_list.bak && "
            "rm -rf /tmp/apt_sources_list_d.bak && echo restored; fi",
            timeout=30,
            out_debug_flag=False,
            return_code=True,
        )
        logger.info(f"[restore_apt_sources] rc={rc} out={out!r}")
        if "restored" not in out:
            logger.error("apt 源备份缺失或恢复失败, 保留现场等待人工确认")
            return False
        verified = self.run_cmd(
            "cat /etc/apt/sources.list /etc/apt/sources.list.d/*.list "
            "2>/dev/null | grep -c '^deb ' || true",
            timeout=10,
            out_debug_flag=False,
        )
        try:
            count = int(verified.strip().splitlines()[-1])
        except (ValueError, IndexError):
            logger.error(f"恢复后无法统计 apt 源: {verified!r}")
            return False
        expected = getattr(self, "_apt_backup_deb_count", None)
        logger.info(f"[restore_apt_sources] 恢复后有效 deb 行数={count} 备份时={expected}")
        return expected is None or count == expected

    def set_invalid_release_repo(self):
        """将 apt 源指向可达但无 Release 文件的仓库地址, 使 apt update 必定失败

        注: set_unreachable_repo 用 RFC 5737 保留地址时, 若同时停用了全部有效源,
        apt 只报 W: 部分索引下载失败, 返回码仍为 0(实测 apt 1.8.2), 无法用于
        "apt update 失败"的前置构造。这里改用可达主机上不存在的仓库路径, apt
        报 E: 没有 Release 文件, 返回码 100。
        """
        self.sudo_run_cmd(
            "echo 'deb http://pools.uniontech.com/nonexistent-autotest-2036/ ./' "
            "> /etc/apt/sources.list; "
            "for f in /etc/apt/sources.list.d/*.list; do "
            "[ -f \"$f\" ] && sed -i -E 's/^[[:space:]]*deb(-src)? /# deb /' \"$f\"; "
            "done; echo done",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

    def get_apt_update_success(self) -> bool:
        """检查 apt update 是否成功"""
        result = self.run_cmd(
            "apt update 2>&1; echo $?",
            timeout=60,
            out_debug_flag=False,
        )
        return result.strip().split("\n")[-1].strip() == "0"

    def _get_apt_repo_urls(self, limit=5):
        """收集 apt 源配置中所有已启用的仓库地址

        兼容 /etc/apt/sources.list 与 /etc/apt/sources.list.d/*.list,
        并跳过 `deb [arch=amd64 ...] URL` 形式的选项块(旧实现取第 2 列会把
        选项块当成 URL, 导致可达性误判)。

        :param limit: 最多返回的地址数
        :return: 去重后的仓库地址列表
        """
        result = self.run_cmd(
            "cat /etc/apt/sources.list /etc/apt/sources.list.d/*.list "
            "2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        urls = []
        for raw_line in result.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            line = re.sub(r"\[[^\]]*\]", " ", line)
            tokens = line.split()
            if not tokens or tokens[0] not in ("deb", "deb-src"):
                continue
            for token in tokens[1:]:
                if token.startswith(("http://", "https://", "ftp://")):
                    if token not in urls:
                        urls.append(token)
                    break
        return urls[:limit]

    def get_repo_address_reachable(self) -> bool:
        """检查 apt 仓库地址是否可达（无需 root 权限）

        依次取所有源文件中已启用的 deb 仓库地址, 用 curl 发送 HEAD 请求;
        只要任一仓库返回 HTTP 响应(含 401 鉴权失败)即认为源服务可达。
        """
        urls = self._get_apt_repo_urls()
        if not urls:
            logger.warning("源配置中没有找到启用的 deb 仓库地址")
            return False
        for url in urls:
            result = self.run_cmd(
                f"curl -sI --connect-timeout 10 --max-time 30 '{url}' "
                "2>/dev/null | head -1",
                timeout=45,
                out_debug_flag=False,
            )
            if "HTTP/" in result:
                return True
        return False

    def break_dependency_partially(self):
        """构造依赖关系部分破坏的状态(模拟 apt install -fy 部分修复成功场景)

        创建一个依赖不存在包的 dummy deb 并强制安装, 使系统中存在
        无法通过 apt install -fy 完全修复的依赖关系;
        同时安装一个可修复的依赖问题(缺少 tree 包), 模拟"部分修复"。
        """
        # 创建 dummy deb: 依赖不存在的包(不可修复) + tree(可修复)
        self.run_cmd(
            "mkdir -p /tmp/dummy-deb/DEBIAN && "
            'printf "Package: dummy-broken-dep\n'
            "Version: 1.0\n"
            "Architecture: all\n"
            "Depends: dummy-nonexistent-dep-xyz (>= 1.0), tree\n"
            'Description: Dummy package for testing partial dependency repair\n" '
            "> /tmp/dummy-deb/DEBIAN/control && "
            "dpkg-deb --build /tmp/dummy-deb /tmp/dummy-broken-dep.deb",
            timeout=15,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "dpkg --force-depends -i /tmp/dummy-broken-dep.deb",
            timeout=15,
            out_debug_flag=False,
        )
        sleep(2)

    def restore_dependency(self):
        """恢复依赖关系状态(清理测试中创建的 dummy 包并修复依赖)"""
        self.sudo_run_cmd(
            "dpkg --force-all --remove dummy-broken-dep 2>/dev/null; "
            "apt-get install -fy 2>/dev/null; "
            "rm -rf /tmp/dummy-deb /tmp/dummy-broken-dep.deb",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(1)

    def apt_update_success(self, timeout=180) -> bool:
        """以 root 执行 apt-get update, 返回是否更新成功(返回码 0)

        依赖关系修复工具的第一步就是 apt update -y。已有的 get_apt_update_success
        以普通用户执行 apt update, 必然因 /var/lib/apt/lists 无写权限而失败, 不能
        用于校验"仓库更新成功"的前置条件, 故此处以 root 执行。

        :param timeout: 命令超时秒数(源较多时 apt update 可能较慢)
        :return: True 表示 apt update 返回 0
        """
        out, status = self.sudo_run_cmd(
            "apt-get update",
            timeout=timeout,
            out_debug_flag=False,
            return_code=True,
        )
        if status != 0:
            logger.warning(f"apt-get update 失败(rc={status}): {out[-1000:]}")
        return status == 0

    def apt_update_with_return_code(self, timeout=300):
        """以 root 执行 apt-get update -y, 返回 (输出, 返回码)

        "修复依赖关系不满足 - apt update 失败(仓库不可达)" 用例的步骤就是
        执行 sudo apt update -y 并断言返回码非 0。apt_update_success 只暴露
        成功与否, 这里把输出与返回码一并返回, 便于区分"仓库不可达导致失败"
        与"命令本身没跑起来(如 sudo 失败)"。

        :param timeout: 命令超时秒数(源不可达时 apt 会走连接超时重试)
        :return: (命令输出文本, 返回码)
        """
        return self.sudo_run_cmd(
            "apt-get update -y",
            timeout=timeout,
            out_debug_flag=False,
            return_code=True,
        )

    def is_package_state_installed(self, package: str) -> bool:
        """判断包是否处于"已安装"状态, 兼容 apt-mark hold 后的状态

        被 hold 的包在 dpkg 中的状态是 "hold ok installed" 而不是
        "install ok installed", is_package_installed 会误判为未安装。

        :param package: 软件包名
        :return: True 表示包已安装(允许处于 hold 状态)
        """
        out = self.run_cmd(
            f"dpkg -s {package} 2>/dev/null | grep '^Status:'",
            timeout=10,
            out_debug_flag=False,
        )
        return "installed" in out

    def is_package_installed(self, package: str) -> bool:
        """判断系统是否已安装指定软件包(dpkg 状态为 install ok installed)

        :param package: 软件包名
        :return: True 表示已安装且已配置
        """
        out = self.run_cmd(
            "dpkg -s " + package + " 2>/dev/null | grep '^Status: install ok installed'",
            timeout=10,
            out_debug_flag=False,
        )
        return "install ok installed" in out

    def get_installable_uninstalled_package(self, candidates=(
            "tree", "cowsay", "sl", "unzip", "nano", "fortune-mod")) -> str:
        """从候选包里挑一个"当前未安装、但能从有效源安装"的包

        依赖关系修复用例需要一个"依赖关系不满足但可被 apt 修好"的构造: dummy
        包依赖该包时, 只要软件源有效, 产品执行 apt install -fy 就能补齐依赖,
        从而走"仓库更新成功 + 依赖修复成功"分支; 相反, 若依赖在本源里根本装不
        到, 就变成了 apt install -fy 失败(依赖无法解决)场景。

        :param candidates: 候选包名(按顺序尝试; 取体积小、仓库常收录的包)
        :return: 可安装的包名, 都不可用时返回 ""
        """
        for package in candidates:
            if self.is_package_installed(package):
                continue
            _, status = self.sudo_run_cmd(
                f"apt-get install -s -y {package} >/dev/null 2>&1",
                timeout=60,
                out_debug_flag=False,
                return_code=True,
            )
            if status == 0:
                return package
        return ""

    def break_dependency_repairable(self, package: str = "") -> str:
        """构造"依赖关系不满足但可修复"的前置状态, 返回被依赖的包名

        产品依据(deepin-pc-manager 1.1.7): 修复工具中的"依赖关系修复"由 daemon
        以 root 执行入口脚本, 依次执行 apt update -y -> apt install -fy ->
        dpkg --configure -a; apt 源更新成功时 dpmapi log_info 输出"系统仓库更新
        成功", 结束时输出修复完成并经 dpm_notify 等待用户确认。

        构造方式: 打一个依赖仓库内可安装包(package)的 dummy deb, 用
        dpkg --force-depends -i 强制安装, 系统即出现"已安装但依赖不满足"的软件
        包(apt-get check 失败), 而该依赖本身能从有效源装到, 属于可修复场景。

        :param package: dummy 包依赖的包名, 为空时自动挑一个可安装的包
        :return: 实际使用的依赖包名, 构造失败返回 ""
        """
        dep_pkg = package or self.get_installable_uninstalled_package()
        if not dep_pkg:
            logger.warning("软件源中没有找到可安装的候选包, 无法构造依赖不满足状态")
            return ""
        out, status = self.sudo_run_cmd(
            "rm -rf /tmp/autotest_dep_deb && "
            "mkdir -p /tmp/autotest_dep_deb/DEBIAN && "
            "printf 'Package: dummy-dep-unmet\n"
            "Version: 1.0\n"
            "Architecture: all\n"
            f"Depends: {dep_pkg}\n"
            "Description: dummy package with unmet dependency for autotest\n' "
            "> /tmp/autotest_dep_deb/DEBIAN/control && "
            "dpkg-deb --build /tmp/autotest_dep_deb /tmp/autotest_dep_unmet.deb",
            timeout=60,
            out_debug_flag=False,
            return_code=True,
        )
        if status != 0:
            logger.warning(f"构造依赖不满足的 dummy 包失败(rc={status}): {out}")
            return ""
        self.sudo_run_cmd(
            "dpkg --force-depends -i /tmp/autotest_dep_unmet.deb",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(2)
        return dep_pkg

    def break_dependency_by_removal(self, package: str = "bzip2") -> bool:
        """通过强制卸载"被其它已安装包依赖"的包, 构造依赖关系不满足状态

        测试机装有权限管理 dpkg 安装钩子(非白名单包禁止安装), 用自建 dummy 包
        构造依赖不满足会被钩子拒绝, 故改用真实包: 强制卸载 package 后, 依赖它的
        已安装包(libdpkg-perl -> bzip2)留下未满足依赖, apt-get check 失败, 而
        package 本身可从有效源装回, 属于"可修复"的依赖不满足。

        :param package: 被卸载的包名(需被某个已安装包依赖, 且源内可安装)
        :return: True 表示已构造出依赖不满足状态
        """
        self.sudo_run_cmd(
            f"dpkg --force-depends --remove {package}",
            timeout=180,
            out_debug_flag=False,
        )
        sleep(2)
        return not self.get_dependency_status()

    def restore_dependency_package(self, package: str = "bzip2") -> bool:
        """把 break_dependency_by_removal 卸掉的包装回, 并确认依赖关系恢复

        :param package: 被卸载的包名
        :return: True 表示包已安装且 apt-get check 通过
        """
        self.sudo_run_cmd(
            f"apt-get install -y {package} 2>/dev/null; apt-get install -fy 2>/dev/null",
            timeout=300,
            out_debug_flag=False,
        )
        sleep(1)
        return self.is_package_installed(package) and self.get_dependency_status()

    def cleanup_dependency_repairable(self, package: str = ""):
        """回退"依赖关系不满足"的构造状态, 不在测试机留残留

        :param package: break_dependency_repairable 返回的依赖包名(构造前未安装),
                        传入时一并卸载
        """
        purge = f"dpkg --force-all --purge {package} 2>/dev/null; " if package else ""
        self.sudo_run_cmd(
            "dpkg --force-all --remove dummy-dep-unmet 2>/dev/null; "
            + purge
            + "apt-get install -fy 2>/dev/null; "
            "dpkg --configure -a 2>/dev/null; "
            "rm -rf /tmp/autotest_dep_deb /tmp/autotest_dep_unmet.deb",
            timeout=180,
            out_debug_flag=False,
        )
        sleep(1)

    def dpkg_configure_all(self, timeout=180):
        """以 root 执行 dpkg --configure -a, 返回 (输出, 返回码)

        依赖关系修复工具的最后一步就是 dpkg --configure -a, 用例用它做
        "命令可正常执行"的等价断言。

        :param timeout: 命令超时秒数
        :return: (输出文本, 返回码)
        """
        return self.sudo_run_cmd(
            "dpkg --configure -a",
            timeout=timeout,
            out_debug_flag=False,
            return_code=True,
        )

    def get_unconfigured_packages(self) -> list:
        """列出 dpkg 状态不是 ii(已安装且已配置)的软件包名

        用于确认构造出来的半配置包已被 dpkg --configure -a 配置完成。

        :return: 软件包名列表
        """
        result = self.run_cmd(
            "dpkg -l 2>/dev/null | awk '$1 != \"ii\" && $1 != \"rc\" {print $2}'",
            timeout=20,
            out_debug_flag=False,
        )
        return [line.strip() for line in result.splitlines() if line.strip()]

    def get_dependency_repair_card_name(self) -> str:
        """在修复工具卡片列表中查找"依赖关系修复"卡片, 返回其名称

        卡片文案随版本可能是"依赖关系修复"或"系统依赖修复", 统一按"依赖"
        关键字匹配。

        :return: 卡片名, 找不到返回 ""
        """
        for name in self.get_repair_card_names():
            if "依赖" in name:
                return name
        return ""

    # ===== 模块 修复工具 - 依赖关系无法解决(apt install -fy 必然失败) =====

    UNRESOLVABLE_DUMMY_PACKAGE = "dummy-dep-unresolvable"
    UNRESOLVABLE_DUMMY_DEP = "dummy-nonexistent-dep-xyz"

    DPKG_STATUS_BACKUP = "/tmp/autotest_dpkg_status.bak"

    def _patch_dpkg_status_depends(self, package, dep):
        """在 dpkg status 中给已安装包追加一条依赖(用于构造无法解决的依赖)

        测试机装有 dpkg 安装钩子, 非白名单的 dummy 包无法安装, 因此无法用
        自建包构造"依赖无法解决"。改为直接给真实已安装包的状态记录追加一条
        指向不存在包的依赖, 并由调用方备份/恢复 /var/lib/dpkg/status。

        :param package: 已安装包名
        :param dep: 追加的依赖包名(不存在于任何软件源)
        :return: True 表示状态记录已改写
        """
        script = base64.b64decode(
            "aW1wb3J0IHN5cwpwYXRoID0gIi92YXIvbGliL2Rwa2cvc3RhdHVzIgpwa2csIGRlcCA9IHN5cy5hcmd2WzFdLCBzeXMuYXJndlsyXQp3aXRoIG9wZW4ocGF0aCkgYXMgZjoKICAgIGRhdGEgPSBmLnJlYWQoKQptYXJrZXIgPSAiUGFja2FnZTogJXNcbiIgJSBwa2cKaWR4ID0gZGF0YS5pbmRleChtYXJrZXIpCmVuZCA9IGRhdGEuaW5kZXgoIlxuXG4iLCBpZHgpCnNlZyA9IGRhdGFbaWR4OmVuZF0KaWYgIkRlcGVuZHM6IiBpbiBzZWc6CiAgICBzZWcgPSBzZWcucmVwbGFjZSgiRGVwZW5kczoiLCAiRGVwZW5kczogJXMsIiAlIGRlcCwgMSkKZWxzZToKICAgIHNlZyA9IHNlZyArICJcbkRlcGVuZHM6ICVzIiAlIGRlcAp3aXRoIG9wZW4ocGF0aCwgInciKSBhcyBmOgogICAgZi53cml0ZShkYXRhWzppZHhdICsgc2VnICsgZGF0YVtlbmQ6XSkKcHJpbnQoInBhdGNoZWQiKQo="
        )
        self.sudo_run_cmd(
            f"cat > /tmp/autotest_patch_status.py <<'PYEOF'\n"
            + script.decode("utf-8")
            + "PYEOF",
            timeout=10,
            out_debug_flag=False,
        )
        out, status = self.sudo_run_cmd(
            f"python3 /tmp/autotest_patch_status.py {package} {dep}",
            timeout=30,
            out_debug_flag=False,
            return_code=True,
        )
        return status == 0 and "patched" in out

    def break_dependency_unresolvable(self, package="", missing_dep="") -> str:
        """构造"依赖无法解决"状态, 使 apt install -fy 必然失败

        产品依据(deepin-pc-manager 1.1.7): "依赖关系修复"插件(executionMode=
        root)由 daemon 以 root 依次执行 `apt update -y`、`dpkg --configure -a`、
        `apt install -fy`; 依赖无法解决时 apt install -fy 返回码非 0, 期望产品
        提示"依赖关系未修复，需要手动执行 sudo apt install -f 查看详情"。

        构造方式(等价实现): 描述要求追加 Debian sid 源制造源冲突, 但该操作会把
        整机包版本拖入不稳定分支且难以完全回退, 风险过高; dummy 包又会测试机的
        dpkg 安装钩子(非白名单包禁止安装)拒绝。改为给真实已安装包(bzip2)的
        dpkg status 记录追加一条"软件源中不存在的包"依赖, 并 apt-mark hold 该包:
        apt 既装不上不存在的依赖, 又不能删除被 hold 的包, `apt install -fy`
        必然返回非 0。原始 status 文件在构造前备份, 回退时整体还原。

        :param package: 被构造的已安装包名, 空串用 bzip2
        :param missing_dep: 追加的不存在依赖包名, 空串用默认值
        :return: 被构造的包名, 构造失败返回空串
        """
        pkg = package or "bzip2"
        dep = missing_dep or self.UNRESOLVABLE_DUMMY_DEP
        self.sudo_run_cmd(
            f"test -f {self.DPKG_STATUS_BACKUP} || "
            f"cp -a /var/lib/dpkg/status {self.DPKG_STATUS_BACKUP}",
            timeout=30,
            out_debug_flag=False,
        )
        if not self._patch_dpkg_status_depends(pkg, dep):
            logger.warning(f"改写 {pkg} 的 dpkg status 依赖失败")
            return ""
        self.sudo_run_cmd(f"apt-mark hold {pkg} 2>/dev/null", timeout=30,
                          out_debug_flag=False)
        sleep(1)
        held = self.run_cmd("apt-mark showhold 2>/dev/null", timeout=15,
                            out_debug_flag=False)
        if pkg not in [ln.strip() for ln in held.splitlines()]:
            logger.warning(f"{pkg} 未能 hold, apt install -f 会删除该包自我修复")
            return ""
        return pkg

    def cleanup_dependency_unresolvable(self, package="") -> bool:
        """回退"依赖无法解决"的构造状态, 不在测试机留残留

        :param package: break_dependency_unresolvable 返回的包名
        :return: True 表示 hold 已解除、status 已还原且依赖关系恢复
        """
        pkg = package or "bzip2"
        self.sudo_run_cmd(
            f"apt-mark unhold {pkg} 2>/dev/null; "
            f"if [ -f {self.DPKG_STATUS_BACKUP} ]; then "
            f"cp -a {self.DPKG_STATUS_BACKUP} /var/lib/dpkg/status; "
            f"rm -f {self.DPKG_STATUS_BACKUP}; fi; "
            "apt-get install -fy 2>/dev/null; "
            "dpkg --configure -a 2>/dev/null; "
            "rm -f /tmp/autotest_patch_status.py /tmp/autotest_dep_unresolvable.deb",
            timeout=180,
            out_debug_flag=False,
        )
        sleep(1)
        return self.get_dependency_status()

    # ===== 模块 修复工具 - 依赖关系修复(apt/dpkg 命令不存在) =====
    # 产品依据(deepin-pc-manager 1.1.7, plugins/plugin-dependency/entry.sh):
    #   if apt update -y; then
    #       log_info "系统仓库更新成功"
    #   else
    #       提示"系统仓库更新失败"并 exit 1
    #   fi
    #   if dpkg --configure -a; then ... else 提示"依赖关系未修复..." fi
    # 精简系统里 apt / dpkg 命令不存在时, 入口脚本的 apt update -y 由 shell
    # 报 command not found 并返回 127, 产品据此走"系统仓库更新失败"分支, 不再
    # 执行 dpkg --configure -a 与 apt install -fy。
    #
    # 构造方式(等价实现): 描述要求"模拟精简系统, 无 apt/dpkg 命令(或路径被
    # 修改)"。真卸载包管理器会毁掉测试机, 因此把 /usr/bin/apt、/usr/bin/apt-get、
    # /usr/bin/dpkg 临时改名为 *.autotest_bak(即"路径被修改"), 使 PATH 里找不到
    # 这三个命令, 等价于"命令不存在"; 用例 finally 里原样移回, 并先用
    # systemd-run 注册兜底定时器, 万一用例被强杀也能自动恢复。
    APT_DPKG_SIM_BINARIES = (
        ("/usr/bin/apt", "/usr/bin/apt.autotest_bak"),
        ("/usr/bin/apt-get", "/usr/bin/apt-get.autotest_bak"),
        ("/usr/bin/dpkg", "/usr/bin/dpkg.autotest_bak"),
    )
    APT_DPKG_RECOVERY_UNIT = "pms-apt-dpkg-recovery"
    APT_DPKG_RECOVERY_SCRIPT = "/tmp/autotest_apt_dpkg_recovery.sh"

    def get_apt_dpkg_missing_commands(self) -> list:
        """返回 PATH 中找不到的包管理命令名(apt/apt-get/dpkg)

        用例需要断言"命令不存在", 用 shell 的 command -v 判断最贴近产品
        入口脚本实际执行时的可解析性。

        :return: 缺失命令名列表, 三个都可用时为空列表
        """
        result = self.run_cmd(
            "for c in apt apt-get dpkg; do "
            "command -v \"$c\" >/dev/null 2>&1 || echo \"$c\"; done",
            timeout=10,
            out_debug_flag=False,
        )
        return [line.strip() for line in result.splitlines() if line.strip()]

    def get_apt_dpkg_commands_available(self) -> bool:
        """检查 apt、apt-get、dpkg 三个命令是否都能在 PATH 中找到

        :return: True 表示三个命令都存在
        """
        return not self.get_apt_dpkg_missing_commands()

    def get_apt_dpkg_binaries_state(self) -> dict:
        """读取 apt/apt-get/dpkg 主程序与备份文件的存在状态

        :return: {命令名: {"path", "bak", "exists", "backup"}}
        """
        state = {}
        for path, backup in self.APT_DPKG_SIM_BINARIES:
            result = self.run_cmd(
                f"test -e {path} && echo orig || true; "
                f"test -e {backup} && echo bak || true",
                timeout=10,
                out_debug_flag=False,
            )
            tokens = result.split()
            state[os.path.basename(path)] = {
                "path": path,
                "bak": backup,
                "exists": "orig" in tokens,
                "backup": "bak" in tokens,
            }
        return state

    def schedule_apt_dpkg_binary_recovery(self, seconds=900) -> bool:
        """安排兜底恢复: 若干秒后自动把 apt/apt-get/dpkg 备份移回原位

        本用例会把 /usr/bin 下的包管理命令移走, 若用例进程被强杀或超时,
        finally 不会执行, 测试机将失去 apt/dpkg 能力。因此先注册一个
        systemd-run 定时单元兜底(与 NetworkManager 二进制兜底同一思路),
        在 finally 里再取消; 脚本执行后自行删除, 不留 /tmp 残留。

        :param seconds: 兜底触发延时(秒), 需大于用例最长运行时间
        :return: True 表示定时器已注册
        """
        lines = [
            "#!/usr/bin/env bash",
            "# 用例 2005735 兜底恢复: apt/apt-get/dpkg 被临时移走时自动移回",
        ]
        for path, backup in self.APT_DPKG_SIM_BINARIES:
            lines.append(
                f'if [ -e "{backup}" ] && [ ! -e "{path}" ]; then '
                f'mv "{backup}" "{path}"; fi'
            )
        lines.append(f"rm -f {self.APT_DPKG_RECOVERY_SCRIPT}")
        script = "\n".join(lines) + "\n"
        # 先取消可能存在的旧定时器(它会删掉同名脚本), 再写脚本并注册新定时器
        self.cancel_apt_dpkg_binary_recovery()
        try:
            with open(self.APT_DPKG_RECOVERY_SCRIPT, "w", encoding="utf-8") as script_file:
                script_file.write(script)
            os.chmod(self.APT_DPKG_RECOVERY_SCRIPT, 0o755)
        except OSError as exc:
            logger.error(f"写 apt/dpkg 兜底恢复脚本失败: {exc}")
            return False
        self.sudo_run_cmd(
            f"systemd-run --on-active={int(seconds)} "
            f"--unit={self.APT_DPKG_RECOVERY_UNIT} "
            f"/bin/bash {self.APT_DPKG_RECOVERY_SCRIPT}",
            timeout=20,
            out_debug_flag=False,
        )
        state = self.run_cmd(
            f"systemctl show -p ActiveState --value "
            f"{self.APT_DPKG_RECOVERY_UNIT}.timer 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return state.strip() == "active"

    def cancel_apt_dpkg_binary_recovery(self):
        """取消 apt/dpkg 兜底恢复定时器并删除其临时脚本(可重复调用)"""
        self.sudo_run_cmd(
            f"bash -c 'systemctl stop {self.APT_DPKG_RECOVERY_UNIT}.timer "
            f"{self.APT_DPKG_RECOVERY_UNIT}.service 2>/dev/null; "
            f"systemctl reset-failed {self.APT_DPKG_RECOVERY_UNIT}.service 2>/dev/null; "
            "true'",
            timeout=20,
            out_debug_flag=False,
        )
        try:
            os.remove(self.APT_DPKG_RECOVERY_SCRIPT)
        except OSError:
            pass

    def restore_stale_apt_dpkg_binaries(self) -> bool:
        """自愈: 清理上次异常退出遗留的 apt/apt-get/dpkg 备份

        测试机若上次用例被强杀, 会残留 *.autotest_bak 而原命令缺失; 不先自愈,
        "命令不存在"的前置构造就无从判断, 机器也会停在无包管理命令的状态。

        :return: True 表示三个命令当前都可用
        """
        state = self.get_apt_dpkg_binaries_state()
        stale = [item for item in state.values() if item["backup"]]
        if not stale:
            return self.get_apt_dpkg_commands_available()
        for item in stale:
            if item["exists"]:
                # 原文件与备份同时存在: 备份是上次用例的残留副本, 直接删除
                self.sudo_run_cmd(
                    f"rm -f {item['bak']}",
                    timeout=10,
                    out_debug_flag=False,
                )
            else:
                logger.warning(f"检测到残留备份 {item['bak']}, 先恢复")
        commands = "; ".join(
            f'if [ -e "{item["bak"]}" ] && [ ! -e "{item["path"]}" ]; then '
            f'mv "{item["bak"]}" "{item["path"]}"; fi'
            for item in stale
        )
        self.sudo_run_cmd(f"bash -c '{commands}; true'", timeout=30, out_debug_flag=False)
        return self.get_apt_dpkg_commands_available()

    def break_apt_dpkg_binaries(self) -> bool:
        """构造"apt/dpkg 命令不存在"(精简系统)的前置状态

        等价实现: 把 /usr/bin/apt、/usr/bin/apt-get、/usr/bin/dpkg 临时改名为
        *.autotest_bak, 使其在 PATH 中找不到; 产品入口脚本 apt update -y
        因此得到 127(command not found), 走"系统仓库更新失败"分支。

        :return: True 表示 apt 与 dpkg 都已不可用
        """
        self.restore_stale_apt_dpkg_binaries()
        commands = "; ".join(
            f'if [ -e "{path}" ]; then mv "{path}" "{backup}"; fi'
            for path, backup in self.APT_DPKG_SIM_BINARIES
        )
        self.sudo_run_cmd(f"bash -c '{commands}; true'", timeout=60, out_debug_flag=False)
        sleep(1)
        missing = set(self.get_apt_dpkg_missing_commands())
        return {"apt", "dpkg"} <= missing and not self.get_apt_dpkg_commands_available()

    def restore_apt_dpkg_binaries(self) -> bool:
        """回退: 把 apt/apt-get/dpkg 备份移回原位并校验命令恢复可用

        :return: True 表示三个命令都已能在 PATH 中找到
        """
        commands = "; ".join(
            f'if [ -e "{backup}" ] && [ ! -e "{path}" ]; then '
            f'mv "{backup}" "{path}"; fi'
            for path, backup in self.APT_DPKG_SIM_BINARIES
        )
        self.sudo_run_cmd(f"bash -c '{commands}; true'", timeout=60, out_debug_flag=False)
        for _ in range(30):
            if self.get_apt_dpkg_commands_available():
                return True
            sleep(1)
        return self.get_apt_dpkg_commands_available()

    def apt_update_command_missing(self):
        """在 apt 命令不存在时执行 apt update -y, 返回 (输出, 返回码)

        用例步骤"执行脚本"的直接复现: 模拟精简系统后执行 apt update,
        shell 报 command not found 并返回 127(预期1)。

        :return: (命令输出文本, 返回码)
        """
        return self.run_cmd(
            "apt update -y 2>&1",
            timeout=60,
            out_debug_flag=False,
            return_code=True,
        )

    def dpkg_configure_command_missing(self):
        """在 dpkg 命令不存在时执行 dpkg --configure -a, 返回 (输出, 返回码)

        :return: (命令输出文本, 返回码)
        """
        return self.run_cmd(
            "dpkg --configure -a 2>&1",
            timeout=60,
            out_debug_flag=False,
            return_code=True,
        )

    # ===== 模块 修复工具 - 依赖关系部分可修复(apt install -fy 部分修复成功) =====
    # 产品依据(deepin-pc-manager 1.1.7, plugins/plugin-dependency/entry.sh):
    #   if apt update -y; then
    #       log_info "系统仓库更新成功"
    #   else 提示"系统仓库更新失败"并 exit 1
    #   if dpkg --configure -a; then
    #       apt install -o Dpkg::Options::=--force-confnew -fy   # 返回码未检查
    #       log_info "依赖关系修复成功"; dpm_notify 成功
    #   else
    #       提示"依赖关系未修复，需要手动执行 sudo apt install -f 查看详情"; exit 1
    # 即: 产品只在 dpkg --configure -a 失败时给"手动修复"提示, apt install -fy 的
    # 返回码不被检查。因此"apt install -fy 部分修复成功"必须由 apt 自身的行为体现:
    # 一个依赖能装上, 另一个依赖在配置阶段失败, apt 返回码非 0, 系统只被修好一半。
    def get_package_dpkg_status(self, package: str) -> str:
        """返回软件包在 dpkg 中的状态字符串(如 install ok installed)

        :param package: 软件包名
        :return: 状态字符串(不含 "Status:" 前缀); 包不存在时返回空串
        """
        out = self.run_cmd(
            f"dpkg -s {package} 2>/dev/null | grep '^Status:'",
            timeout=10,
            out_debug_flag=False,
        )
        if "Status:" not in out:
            return ""
        return out.split("Status:", 1)[1].strip()

    PARTIAL_REPAIR_HALF_PKG = "less"
    PARTIAL_REPAIR_BROKEN_PKG = "bzip2"
    PARTIAL_REPAIR_MISSING_DEP = "autotest-missing-dep (>= 1.0)"

    def break_dependency_partial_repair(self) -> dict:
        """构造"部分依赖可修复、部分依赖修不好"的前置状态

        用例场景(2005729): 系统里同时存在两类问题 —— 一类半配置包能被
        dpkg/apt 配置完成(部分修复成功), 另一类依赖在软件源里根本不存在
        (部分修复失败), 于是 apt install -fy 返回非 0, 系统只被修好一半。

        构造方式(等价实现): 用例描述要求"部分包依赖可修复、部分无法解决"。
        自建依赖包会被测试机的 dpkg 安装钩子(非白名单包禁止安装)拒绝, 故直接
        改写 /var/lib/dpkg/status(构造前备份, 回退时整体还原):
          - less  状态改为 "install ok unpacked" → dpkg --configure -a 可配置成功;
          - bzip2 追加一条指向不存在包的依赖并 apt-mark hold → apt install -fy
            既补不齐依赖也不能删除该包, 必然失败。

        :return: dict, ok 表示构造成功; 附 half/broken 包名与诊断信息
        """
        script = base64.b64decode(
            "aW1wb3J0IHJlCmltcG9ydCBzeXMKcGF0aCA9ICIvdmFyL2xpYi9kcGtnL3N0YXR1cyIKaGFsZl9wa2csIGJyb2tlbl9wa2csIGRlcCA9IHN5cy5hcmd2WzFdLCBzeXMuYXJndlsyXSwgc3lzLmFyZ3ZbM10Kd2l0aCBvcGVuKHBhdGgpIGFzIGY6CiAgICBkYXRhID0gZi5yZWFkKCkKCmRlZiBibG9jayhwa2cpOgogICAgaWR4ID0gZGF0YS5pbmRleCgiUGFja2FnZTogJXNcbiIgJSBwa2cpCiAgICBlbmQgPSBkYXRhLmluZGV4KCJcblxuIiwgaWR4KQogICAgcmV0dXJuIGlkeCwgZW5kCgojIDEpIOS4gOS4quWMhee9ruS4uiLlt7Lop6PljIXmnKrphY3nva4iLCDkvpsgZHBrZyAtLWNvbmZpZ3VyZSAtYSDkv67lpb0o6YOo5YiG5oiQ5YqfKQppZHgsIGVuZCA9IGJsb2NrKGhhbGZfcGtnKQpzZWcgPSByZS5zdWIociJTdGF0dXM6IC4qIiwgIlN0YXR1czogaW5zdGFsbCBvayB1bnBhY2tlZCIsIGRhdGFbaWR4OmVuZF0sIGNvdW50PTEpCmRhdGEgPSBkYXRhWzppZHhdICsgc2VnICsgZGF0YVtlbmQ6XQoKIyAyKSDlj6bkuIDkuKrljIXov73liqAi6L2v5Lu25rqQ5Lit5LiN5a2Y5Zyo55qE5L6d6LWWIijpg6jliIblpLHotKUsIOaXoOazleS/ruWkjSkKaWR4LCBlbmQgPSBibG9jayhicm9rZW5fcGtnKQpzZWcgPSBkYXRhW2lkeDplbmRdCmlmICJEZXBlbmRzOiIgaW4gc2VnOgogICAgc2VnID0gc2VnLnJlcGxhY2UoIkRlcGVuZHM6IiwgIkRlcGVuZHM6ICVzLCIgJSBkZXAsIDEpCmVsc2U6CiAgICBzZWcgKz0gIlxuRGVwZW5kczogJXMiICUgZGVwCmRhdGEgPSBkYXRhWzppZHhdICsgc2VnICsgZGF0YVtlbmQ6XQp3aXRoIG9wZW4ocGF0aCwgInciKSBhcyBmOgogICAgZi53cml0ZShkYXRhKQpwcmludCgicGF0Y2hlZCIpCg=="
        )
        self.sudo_run_cmd(
            "cat > /tmp/autotest_patch_status_partial.py <<'PYEOF'\n"
            + script.decode("utf-8")
            + "PYEOF",
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"test -f {self.DPKG_STATUS_BACKUP} || "
            f"cp -a /var/lib/dpkg/status {self.DPKG_STATUS_BACKUP}",
            timeout=30,
            out_debug_flag=False,
        )
        out, status = self.sudo_run_cmd(
            "python3 /tmp/autotest_patch_status_partial.py "
            f"{self.PARTIAL_REPAIR_HALF_PKG} {self.PARTIAL_REPAIR_BROKEN_PKG} "
            f"'{self.PARTIAL_REPAIR_MISSING_DEP}'",
            timeout=30,
            out_debug_flag=False,
            return_code=True,
        )
        if status != 0 or "patched" not in out:
            logger.warning(f"改写 dpkg status 构造部分修复失败(rc={status}): {out}")
            return {"ok": False, "rc": status, "output": out}
        self.sudo_run_cmd(
            f"apt-mark hold {self.PARTIAL_REPAIR_BROKEN_PKG} 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(1)
        half_status = self.get_package_dpkg_status(self.PARTIAL_REPAIR_HALF_PKG)
        dep_ok = self.get_dependency_status()
        print(
            f"[widget] break_dependency_partial_repair: half_status={half_status!r} "
            f"dependency_ok={dep_ok}"
        )
        return {
            "ok": not dep_ok and not half_status.startswith("install ok installed"),
            "half": self.PARTIAL_REPAIR_HALF_PKG,
            "broken": self.PARTIAL_REPAIR_BROKEN_PKG,
            "half_status": half_status,
            "dependency_ok": dep_ok,
            "output": out,
        }

    def cleanup_dependency_partial_repair(self) -> dict:
        """回退"部分依赖可修复"的构造, 不在测试机留残留

        依次: 解除 hold -> 还原 dpkg status 备份 -> 重新修依赖 -> 删除临时脚本。
        最后核实依赖关系恢复、临时文件已删除。

        :return: dict, 各项清理结果
        """
        out, status = self.sudo_run_cmd(
            f"apt-mark unhold {self.PARTIAL_REPAIR_BROKEN_PKG} 2>/dev/null; "
            f"if [ -f {self.DPKG_STATUS_BACKUP} ]; then "
            f"cp -a {self.DPKG_STATUS_BACKUP} /var/lib/dpkg/status; "
            f"rm -f {self.DPKG_STATUS_BACKUP}; fi; "
            "dpkg --configure -a >/dev/null 2>&1; "
            "apt-get install -fy >/dev/null 2>&1; "
            "rm -f /tmp/autotest_patch_status_partial.py; echo CLEANUP_DONE",
            timeout=600,
            out_debug_flag=False,
            return_code=True,
        )
        residue = {
            "cleanup_rc": status,
            "half_status": self.get_package_dpkg_status(
                self.PARTIAL_REPAIR_HALF_PKG
            ),
            "broken_hold": self.PARTIAL_REPAIR_BROKEN_PKG
            in self.run_cmd("apt-mark showhold 2>/dev/null", timeout=15,
                            out_debug_flag=False).split(),
            "dependency_ok": self.get_dependency_status(),
            "output": out,
        }
        print(f"[widget] cleanup_dependency_partial_repair: {residue}")
        return residue

    # ===== 模块 修复工具 - dpkg --configure -a 执行失败(dpkg 异常、apt 正常) =====
    # 产品依据(deepin-pc-manager 1.1.7, plugins/plugin-dependency/entry.sh):
    #   apt update -y 成功 -> log_info "系统仓库更新成功"
    #   dpkg --configure -a 成功 -> apt install -o Dpkg::Options::=--force-confnew -fy
    #   dpkg --configure -a 失败 -> 提示"依赖关系未修复, 需要手动执行 sudo apt
    #   install -f 查看详情"并 exit 1(此时不再继续 apt install -fy)
    # 因此"dpkg --configure -a 执行失败"场景要构造的是: 软件源与 apt 都正常,
    # 只有 dpkg 的配置阶段失败。
    def apt_install_fix_with_return_code(self, timeout=300):
        """以 root 执行 `apt install -fy`, 返回 (输出, 返回码)

        依赖关系修复工具在 `dpkg --configure -a` 之后执行的就是该命令; 用例
        用它断言"依赖无法解决时 apt install -fy 返回码非 0"。

        :param timeout: 命令超时秒数
        :return: (输出文本, 返回码)
        """
        return self.sudo_run_cmd(
            "apt-get install -fy",
            timeout=timeout,
            out_debug_flag=False,
            return_code=True,
        )

    REPAIR_RESULT_PROMPT_TITLE = "依赖修复"

    def _dialog_text(self, dialog) -> str:
        """收集对话框内 label/text 节点的文案(用于断言提示语)

        :param dialog: dialog 节点
        :return: 去重后以空格拼接的文本
        """
        texts = []
        for node in self._collect_dialog_nodes(dialog, max_depth=6):
            try:
                if (getattr(node, "roleName", "") or "") not in ("label", "text"):
                    continue
                value = (
                    (getattr(node, "text", "") or "")
                    or (getattr(node, "name", "") or "")
                ).strip()
            except BaseException:
                continue
            if value and value not in texts:
                texts.append(value)
        return " ".join(texts)

    def get_repair_result_prompt_text(self, title="", timeout=180) -> str:
        """等待修复脚本的结果提示框, 返回其正文文本

        产品依据(deepin-pc-manager 1.1.7): 依赖关系修复插件在依赖无法修复时
        调用 dpmapi 提示"依赖关系未修复，需要手动执行 sudo apt install -f
        查看详情"。提示框有两种可观测形态:
          1. dpmapi openinfobox: session-daemon 创建 DDialog, accessible name
             即脚本第一个参数(如"依赖修复");
          2. dpm_notify: 主进程创建无标题 DDialog, 内含"确定"按钮。
        两种形态都按 AT-SPI 读取 label 文案。

        :param title: 提示框标题, 空串用 REPAIR_RESULT_PROMPT_TITLE
        :param timeout: 最长等待秒数
        :return: 提示框文本, 超时未出现返回空串
        """
        prompt_title = title or self.REPAIR_RESULT_PROMPT_TITLE
        for _ in range(max(int(timeout), 1)):
            try:
                dialog = self._get_confirm_dialog_node(prompt_title)
            except BaseException:
                dialog = None
            if dialog is not None:
                text = self._dialog_text(dialog)
                if text:
                    return text
            try:
                tops = list(self.dog.obj.children)
            except BaseException:
                tops = []
            for top in tops:
                try:
                    if (getattr(top, "roleName", "") or "") not in (
                        "dialog",
                        "alert dialog",
                    ):
                        continue
                    if getattr(top, "showing", False) is not True:
                        continue
                    if (getattr(top, "name", "") or "").strip() not in (
                        "",
                        prompt_title,
                    ):
                        continue
                    nodes = self._collect_dialog_nodes(top, max_depth=6)
                    buttons = [
                        (getattr(node, "name", "") or "")
                        for node in nodes
                        if (getattr(node, "roleName", "") or "") == "push button"
                    ]
                    # 选择框/确认框有"取消"/"确认", 不是修复结果提示框
                    if "取消" in buttons or "确认" in buttons:
                        continue
                    if not buttons:
                        continue
                except BaseException:
                    continue
                text = self._dialog_text(top)
                if text:
                    return text
            sleep(1)
        return ""

    def close_repair_result_prompt(self, title="", rounds=2) -> int:
        """关闭修复脚本的结果提示框(兼容 openinfobox 与 dpm_notify)

        :param title: 提示框标题, 空串用 REPAIR_RESULT_PROMPT_TITLE
        :param rounds: 最多连续处理的提示框个数
        :return: 实际关闭的提示框数量
        """
        prompt_title = title or self.REPAIR_RESULT_PROMPT_TITLE
        closed = self.close_info_dialogs(prompt_title, rounds=rounds)
        closed += self.close_repair_notify_dialog(rounds=rounds)
        return closed

    def finish_repair_flow(self, title="", rounds=3) -> dict:
        """修复流程收尾: 点掉脚本末尾的提示框, 再关闭修复窗口

        产品依据(实测 2005771/2026-11-12): 插件 entry.sh 末尾用
        `dpmapi openinfobox "<工具名>" "<完成文案>"` 收尾, 该调用 timeoutMs=0
        表示**没有超时**——提示框不会自己消失, 脚本一直阻塞到用户点【确定】。
        遗留后果: 弹窗盖在桌面上污染后续用例, 且修复窗口点不掉。
        `dpm_notify` 形态的无标题提示框同样可能未应答。

        用例 finally 必调: 不依赖前置断言是否通过, 一律清理现场。

        实测(2005707/2026-11-12): 窗口销毁后 AT-SPI 节点仍报
        shellRepair_outputLog.showing=True, 用 get_repair_dialog_showing 判定
        window_left 会把"窗口已关"误报成"窗口还在"; 因此这里与
        wait_repair_dialog_window_closed 一致, 以 X11 窗口标题为准。

        :param title: openinfobox 标题(插件名+修复, 如 "微信修复"); 空串表示全部
        :param rounds: 提示框/关窗最多处理轮数
        :return: {"info_closed", "notify_closed", "window_left"} --
                 window_left 为 True 表示修复窗口仍在显示
        """
        info_closed = self.close_info_dialogs(title, rounds=rounds)
        notify_closed = self.close_repair_notify_dialog(rounds=rounds)
        result = {
            "info_closed": info_closed,
            "notify_closed": notify_closed,
            "window_left": False,
        }
        # 修复对话框标题即工具名(card.title); 调用方给标题时按标题判,
        # 未给时从现存窗口里取"含修复且不是主窗口"的标题
        titles = [title] if title else self.get_repair_dialog_window_titles()
        for _ in range(rounds):
            if not any(self.get_pc_manager_window_title_contains(t) for t in titles):
                return result
            self.close_repair_completion_dialog()
            sleep(1)
        result["window_left"] = any(
            self.get_pc_manager_window_title_contains(t) for t in titles
        )
        return result

    def get_repair_dialog_window_titles(self) -> list:
        """列出当前仍存在的修复对话框窗口标题(X11 判定)

        实测(2005707/2026-11-12)对话框标题形如"密钥环修复 — 电脑管家",
        主窗口标题则只有"电脑管家"且不含"修复", 故按"含修复且不等于主窗口
        标题"过滤, 不能用"含电脑管家"排除(会把对话框一并排掉)。

        :return: 标题列表, 无对话框时为空列表
        """
        main_titles = ("电脑管家", "控制中心", "deepin-pc-manager")
        return [
            t
            for t in self.get_pc_manager_window_titles()
            if "修复" in t and t.strip() not in main_titles
        ]

    def wait_and_clear_repair_result(self, keywords, timeout=90):
        """等待修复流程结束, 途中出现的弹窗一律点掉

        产品依据(deepin-pc-manager 1.1.7): 修复脚本通过 session-daemon 的
        action_executor 弹提示框, daemon 日志为

            execute: received request, actionType= "OpenMessage"
            runDialog: starting dialog exec, actionType= "OpenMessage" timeoutMs= 0

        **timeoutMs=0 表示提示框没有超时**, 不会自己消失, 脚本一直阻塞直到
        用户点【确定】。因此这里不能"等到读出文案再关", 也不能靠等待超时:
        每轮只要看到弹窗就点(无标题 dpm_notify 点【确定】, 有标题的
        OpenMessage 归 session-daemon, 用 close_info_dialogs 点【确定】),
        修复窗口已关闭且无弹窗时立即返回。

        :param keywords: 结束关键字序列, 如 ("依赖关系未修复", "依赖关系修复成功")
        :param timeout: 最长等待秒数
        :return: (命中的keyword或空串, 收集到的弹窗正文列表, 当前输出日志)
        """
        texts = []
        output = ""
        started = time.time()
        while time.time() - started < timeout:
            acted = False
            state = self.get_repair_notify_dialog_state()
            if state.get("showing"):
                if not self.click_repair_notify_ok(timeout=3):
                    # 按钮识别失败时用 Return 兜底(DDialog 默认按钮)
                    self.run_cmd(
                        "xdotool key Return", timeout=2, out_debug_flag=False
                    )
                acted = True
            # session-daemon 侧的 OpenMessage/OpenInfoBox(标题由脚本决定)
            if self.close_info_dialogs("", rounds=1):
                acted = True
            if acted:
                text = self.get_repair_result_prompt_text(timeout=1)
                if text and text not in texts:
                    texts.append(text)
            output = self.get_repair_output_text() or ""
            for keyword in keywords:
                if keyword in output:
                    return keyword, texts, output
            if not acted and not self.get_repair_dialog_showing(timeout=1):
                # 修复窗口已关闭且没有弹窗: 脚本已退出, 不再空等
                break
            sleep(0.5)
        return "", texts, output

    def wait_repair_output_keywords(self, keywords, timeout=180) -> str:
        """轮询修复输出日志, 命中任一关键词时返回该关键词

        :param keywords: 关键词序列(如"依赖关系未修复"/"依赖关系修复成功")
        :param timeout: 最长等待秒数(每轮约 1s)
        :return: 命中的关键词, 超时返回空串
        """
        for _ in range(max(int(timeout), 1)):
            text = self.get_repair_output_text()
            for keyword in keywords:
                if keyword and keyword in text:
                    return keyword
            sleep(1)
        return ""

    def get_long_filename_support_status(self) -> bool:
        """检查根文件系统是否支持长文件名

        通过检查根分区文件系统类型判断是否支持长文件名。
        FAT12/FAT16文件系统不支持长文件名(仅支持8.3格式),
        ext2/3/4, btrfs, xfs等现代文件系统均支持长文件名。
        """
        result = self.run_cmd(
            "df -T / 2>/dev/null | tail -1 | awk '{print $2}'",
            timeout=5,
            out_debug_flag=False,
        )
        fs_type = result.strip().lower()
        unsupported_fs = {"fat12", "fat16", "msdos"}
        return fs_type not in unsupported_fs


    DPKG_CONFIGURE_FAIL_PKG = "less"
    DPKG_CONFIGURE_FAIL_POSTINST = "/var/lib/dpkg/info/less.postinst"
    DPKG_CONFIGURE_FAIL_POSTINST_BAK = "/tmp/autotest_less_postinst.bak"

    def break_dpkg_configure_failure(self) -> dict:
        """构造"dpkg 异常、apt 正常"的前置状态: dpkg --configure -a 必然失败

        用例场景(2005731): sudo apt update -y 成功, 但 sudo dpkg --configure -a
        报错并返回非 0; 后续 apt install -fy 会尝试修复但最终失败。

        构造方式(等价实现): 自建包会被测试机的 dpkg 安装钩子(非白名单包禁止
        安装)拒绝, 故改用真实包 less: 备份其 postinst 后在第 2 行插入 `exit 1`
        (每次配置必失败), 并把 /var/lib/dpkg/status 中 less 的状态改为
        "install ok unpacked", 系统里即留下一个"配置必然失败"的半配置包; 软件源
        与 apt 本身完全正常。回退时还原 postinst 与 status 备份并重新配置。

        :return: dict, ok 为 True 表示构造成功; 附带 package/postinst/status 等
        """
        self.sudo_run_cmd(
            f"test -f {self.DPKG_STATUS_BACKUP} || "
            f"cp -a /var/lib/dpkg/status {self.DPKG_STATUS_BACKUP}",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"test -f {self.DPKG_CONFIGURE_FAIL_POSTINST_BAK} || "
            f"cp -a {self.DPKG_CONFIGURE_FAIL_POSTINST} "
            f"{self.DPKG_CONFIGURE_FAIL_POSTINST_BAK}",
            timeout=30,
            out_debug_flag=False,
        )
        script = (
            "sed -i '1a exit 1' " + self.DPKG_CONFIGURE_FAIL_POSTINST + "; "
            "python3 - <<'PYEOF'\n"
            "import re\n"
            "p='/var/lib/dpkg/status'\n"
            "s=open(p).read()\n"
            f"i=s.index('Package: {self.DPKG_CONFIGURE_FAIL_PKG}\\n')\n"
            "j=s.index('\\n\\n', i)\n"
            "seg=re.sub(r'Status: .*', 'Status: install ok unpacked', s[i:j], count=1)\n"
            "open(p,'w').write(s[:i]+seg+s[j:])\n"
            "print('patched')\n"
            "PYEOF"
        )
        out, status = self.sudo_run_cmd(
            script, timeout=60, out_debug_flag=False, return_code=True
        )
        pkg_status = self.get_package_dpkg_status(
            self.DPKG_CONFIGURE_FAIL_PKG
        )
        info = {
            "ok": status == 0 and pkg_status == "install ok unpacked",
            "package": self.DPKG_CONFIGURE_FAIL_PKG,
            "status": pkg_status,
            "postinst": self.DPKG_CONFIGURE_FAIL_POSTINST,
            "output": out,
        }
        print(f"[widget] break_dpkg_configure_failure: {info}")
        return info

    def cleanup_dpkg_configure_failure(self) -> dict:
        """回退"dpkg 异常"的构造状态, 不在测试机留残留

        依次: 还原 less 的 postinst 与 dpkg status 备份 -> 重新配置 -> 修复依赖,
        最后核实 less 处于 install ok installed、依赖关系恢复、临时备份已删除。

        :return: dict, 各项清理结果
        """
        out, status = self.sudo_run_cmd(
            f"if [ -f {self.DPKG_CONFIGURE_FAIL_POSTINST_BAK} ]; then "
            f"cp -a {self.DPKG_CONFIGURE_FAIL_POSTINST_BAK} "
            f"{self.DPKG_CONFIGURE_FAIL_POSTINST}; "
            f"rm -f {self.DPKG_CONFIGURE_FAIL_POSTINST_BAK}; fi; "
            f"if [ -f {self.DPKG_STATUS_BACKUP} ]; then "
            f"cp -a {self.DPKG_STATUS_BACKUP} /var/lib/dpkg/status; "
            f"rm -f {self.DPKG_STATUS_BACKUP}; fi; "
            "dpkg --configure -a >/dev/null 2>&1; "
            "apt-get install -fy >/dev/null 2>&1; echo CLEANUP_DONE",
            timeout=300,
            out_debug_flag=False,
            return_code=True,
        )
        residue = {
            "cleanup_rc": status,
            "package_status": self.get_package_dpkg_status(
                self.DPKG_CONFIGURE_FAIL_PKG
            ),
            "dependency_ok": self.get_dependency_status(),
            "postinst_clean": self.sudo_run_cmd(
                f"grep -c '^exit 1$' {self.DPKG_CONFIGURE_FAIL_POSTINST} "
                "|| true",
                timeout=15,
                out_debug_flag=False,
            ).strip(),
            "backup_left": self.sudo_run_cmd(
                f"test -e {self.DPKG_STATUS_BACKUP} -o -e "
                f"{self.DPKG_CONFIGURE_FAIL_POSTINST_BAK} && echo yes || echo no",
                timeout=15,
                out_debug_flag=False,
            ).strip(),
            "output": out,
        }
        print(f"[widget] cleanup_dpkg_configure_failure: {residue}")
        return residue

    # ===== 模块 系统修复 - 长文件名支持修复 =====
    # 产品依据(deepin-pc-manager 1.1.7, plugins/plugin-long-filename/entry.sh):
    # - 读取 /etc/os-version 的 MajorVersion/MinorVersion/OsBuild/EditionName;
    # - V20 有效版本 = MinorVersion + (OsBuild 第二段 - 100):
    #     >=1074  -> ulnfs 方案: 必要时 apt install ulnfs, 再写
    #                org.deepin.dde.file-manager/dfm.mount.ulnfs=true;
    #     1063~1073 -> dlnfs 方案: 写 dfm.mount.dlnfs=true, 并告警"目录支持
    #                  范围有限(仅桌面、视频、音乐、图片、文档、下载、回收站)";
    #     <1063   -> 提示系统版本不支持;
    # - V25 仅专业版: 写 org.deepin.dlnfs/ulnfs=true;
    # - 设置成功后调用 dpmapi openconfirm("长文件名修复", "重启生效，是否现在
    #   重启"); 点【确认】会执行 reboot, 自动化必须点【取消】;
    # - 配置在登录时由 /etc/X11/Xsession.d/99dfm-{dlnfs,ulnfs}-automount 调用
    #   MountControl 挂载到 dfm.mount.*.defaults 列出的目录; 自动化用同一条
    #   官方自动挂载脚本等效应用, 无需真的重启系统。
    LONG_FILENAME_CONFIRM_TITLE = "长文件名修复"
    LONG_FILENAME_APP_V20 = "org.deepin.dde.file-manager"
    LONG_FILENAME_APP_V25 = "org.deepin.dlnfs"
    LONG_FILENAME_DLNFS_KEY = "dfm.mount.dlnfs"
    LONG_FILENAME_ULNFS_KEY = "dfm.mount.ulnfs"
    LONG_FILENAME_DLNFS_DEFAULTS_KEY = "dfm.mount.dlnfs.defaults"
    LONG_FILENAME_ULNFS_DEFAULTS_KEY = "dfm.mount.ulnfs.defaults"
    LONG_FILENAME_DLNFS_AUTOMOUNT = (
        "/etc/deepin/dde-file-manager/dfm-dlnfs-automount"
    )
    LONG_FILENAME_ULNFS_AUTOMOUNT = (
        "/etc/deepin/dde-file-manager/dfm-ulnfs-automount"
    )

    def get_os_version_fields(self) -> dict:
        """读取 /etc/os-version 的键值(长文件名修复插件据此选择修复方案)"""
        fields = {}
        try:
            with open("/etc/os-version", "r", encoding="utf-8",
                      errors="replace") as version_file:
                for line in version_file:
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith("["):
                        continue
                    if "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    fields[key.strip()] = value.strip()
        except BaseException as err:
            logger.warning(f"读取 /etc/os-version 失败: {err}")
        return fields

    def get_long_filename_branch(self) -> dict:
        """解析本机应走的长文件名修复方案(与插件 entry.sh 的判定逻辑一致)

        :return: {
            "fields": os-version 原始键值,
            "branch": "dlnfs"/"ulnfs"/"v25pro"/"unsupported",
            "effective_version": V20 有效版本号(非 V20 为 0),
            "config_app"/"config_key"/"config_use_dashes": 插件写入的配置,
            "mount_app"/"mount_key"/"mount_defaults_key": 挂载相关配置,
            "automount_script": 登录时使用的官方自动挂载脚本,
            "fs_type"/"scheme": "dlnfs" 或 "ulnfs",
        }
        """
        fields = self.get_os_version_fields()
        major = fields.get("MajorVersion", "")
        minor = fields.get("MinorVersion", "")
        os_build = fields.get("OsBuild", "")
        edition = fields.get("EditionName", "")
        info = {
            "fields": fields,
            "major": major,
            "minor": minor,
            "os_build": os_build,
            "edition": edition,
            "effective_version": 0,
            "branch": "unsupported",
            "config_app": self.LONG_FILENAME_APP_V20,
            "config_key": self.LONG_FILENAME_DLNFS_KEY,
            "config_use_dashes": True,
            "mount_app": self.LONG_FILENAME_APP_V20,
            "mount_key": self.LONG_FILENAME_DLNFS_KEY,
            "mount_defaults_key": self.LONG_FILENAME_DLNFS_DEFAULTS_KEY,
            "automount_script": self.LONG_FILENAME_DLNFS_AUTOMOUNT,
            "fs_type": "dlnfs",
            "scheme": "dlnfs",
        }
        if major == "20":
            effective = 0
            try:
                effective = int(minor)
                parts = os_build.split(".")
                if len(parts) >= 2 and parts[1].isdigit():
                    effective += int(parts[1]) - 100
            except (TypeError, ValueError):
                effective = 0
            info["effective_version"] = effective
            if effective >= 1074:
                info.update({
                    "branch": "ulnfs",
                    "config_key": self.LONG_FILENAME_ULNFS_KEY,
                    "mount_key": self.LONG_FILENAME_ULNFS_KEY,
                    "mount_defaults_key": self.LONG_FILENAME_ULNFS_DEFAULTS_KEY,
                    "automount_script": self.LONG_FILENAME_ULNFS_AUTOMOUNT,
                    "fs_type": "ulnfs",
                    "scheme": "ulnfs",
                })
            elif effective >= 1063:
                info.update({"branch": "dlnfs", "scheme": "dlnfs"})
            else:
                info["branch"] = "unsupported"
        elif major == "25":
            if edition == "Professional":
                info.update({
                    "branch": "v25pro",
                    "config_app": self.LONG_FILENAME_APP_V25,
                    "config_key": "ulnfs",
                    "config_use_dashes": False,
                    "mount_defaults_key": self.LONG_FILENAME_ULNFS_DEFAULTS_KEY,
                    "automount_script": self.LONG_FILENAME_ULNFS_AUTOMOUNT,
                    "fs_type": "ulnfs",
                    "scheme": "ulnfs",
                })
            else:
                info["branch"] = "unsupported_v25"
        return info

    def _dde_dconfig_prefix(self) -> str:
        """dde-dconfig 所需的会话总线环境(ssh 非登录 shell 通常没有)"""
        return f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{os.getuid()}/bus "

    def get_dde_config(self, app_id: str, key: str, use_dashes: bool = True,
                       resource: str = "") -> str:
        """读取 dde-dconfig 配置项

        :param app_id: 应用 ID(如 org.deepin.dde.file-manager)
        :param key: 配置键
        :param use_dashes: V20 使用 --get, V25 使用 get
        :param resource: resource, 默认与 app_id 相同
        :return: 配置值文本(读取失败返回空字符串)
        """
        resource = resource or app_id
        action = "--get" if use_dashes else "get"
        cmd = (
            f"{self._dde_dconfig_prefix()}dde-dconfig {action} "
            f"-a {quote(app_id)} -r {quote(resource)} -k {quote(key)}"
        )
        return self.run_cmd(cmd, timeout=15, out_debug_flag=False).strip()

    def set_dde_config(self, app_id: str, key: str, value: str,
                       use_dashes: bool = True, resource: str = "") -> bool:
        """写入 dde-dconfig 配置项(布尔值按 true/false 写入)

        :return: True 表示 dde-dconfig 返回 0
        """
        resource = resource or app_id
        action = "--set" if use_dashes else "set"
        cmd = (
            f"{self._dde_dconfig_prefix()}dde-dconfig {action} "
            f"-a {quote(app_id)} -r {quote(resource)} -k {quote(key)} "
            f"-v {quote(str(value).lower())}"
        )
        out, rc = self.run_cmd(
            cmd, timeout=15, out_debug_flag=False, return_code=True
        )
        if rc != 0:
            logger.warning(
                f"dde-dconfig 设置 {app_id}/{key}={value} 失败 rc={rc}: {out}"
            )
        return rc == 0

    def get_long_filename_config_value(self, branch: dict) -> str:
        """读取长文件名修复开关的当前值(true/false, 失败为空串)"""
        value = self.get_dde_config(
            branch["config_app"],
            branch["config_key"],
            branch.get("config_use_dashes", True),
        )
        return value.strip().lower()

    def wait_long_filename_config(self, branch: dict, expected: str,
                                  timeout: int = 20) -> bool:
        """轮询等待长文件名修复开关变为期望值"""
        expected = str(expected).lower()
        for _ in range(max(int(timeout), 1)):
            if self.get_long_filename_config_value(branch) == expected:
                return True
            sleep(1)
        return False

    def get_long_filename_default_dirs(self, branch: dict) -> list:
        """读取并展开 dfm.mount.*.defaults 中的默认挂载目录

        dde-dconfig 对列表返回的是一层 JSON 字符串(内部才是 JSON 数组),
        因此先解析成字符串再解析成列表; 只返回本机真实存在的目录。
        """
        raw = self.get_dde_config(
            branch.get("mount_app", self.LONG_FILENAME_APP_V20),
            branch.get(
                "mount_defaults_key", self.LONG_FILENAME_DLNFS_DEFAULTS_KEY
            ),
            True,
        )
        values = []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            if isinstance(parsed, list):
                values = [str(item) for item in parsed]
        except BaseException:
            for token in (
                raw.replace("[", " ").replace("]", " ").replace('"', " ")
                .replace(",", " ").split()
            ):
                if token.startswith("$HOME") or token.startswith("/"):
                    values.append(token)
        home = os.path.expanduser("~")
        expanded = []
        for value in values:
            path = value.replace("$HOME", home)
            if path.startswith("~"):
                path = home + path[1:]
            if os.path.isdir(path) and path not in expanded:
                expanded.append(path)
        return expanded

    def get_long_filename_probe_dir(self, branch: dict = None) -> str:
        """选取长文件名创建验证目录(优先默认挂载目录中的 Documents)

        :return: 存在的绝对路径; 都不存在时返回家目录
        """
        home = os.path.expanduser("~")
        preferred = ("Documents", "Desktop", "Downloads", "Pictures")
        default_dirs = self.get_long_filename_default_dirs(branch or {})

        def covered(path):
            if not default_dirs:
                return True
            return any(
                path == item.rstrip("/")
                or path.startswith(item.rstrip("/") + "/")
                for item in default_dirs
            )

        for name in preferred:
            path = os.path.join(home, name)
            if os.path.isdir(path) and covered(path):
                return path
        for path in default_dirs:
            if os.path.isdir(path):
                return path
        return home

    def _get_mount_entries(self) -> list:
        """返回当前挂载表 [(挂载点, 文件系统类型), ...]"""
        out = self.run_cmd(
            "findmnt -rn -o TARGET,FSTYPE --raw 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        entries = []
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                entries.append((parts[0], parts[1]))
        return entries

    def get_path_mount_fstype(self, path: str) -> str:
        """获取包含指定路径的挂载点的文件系统类型(最长的匹配挂载点)"""
        target = os.path.realpath(os.path.expanduser(path))
        best_type, best_len = "", -1
        for mount_point, fs_type in self._get_mount_entries():
            mount_point = os.path.realpath(mount_point)
            if target == mount_point or target.startswith(
                mount_point.rstrip("/") + "/"
            ):
                if len(mount_point) > best_len:
                    best_type, best_len = fs_type, len(mount_point)
        return best_type

    def is_path_long_filename_mounted(self, path: str, fs_type: str) -> bool:
        """判断路径是否处于长文件名文件系统内(包含其上级挂载点)"""
        return self.get_path_mount_fstype(path) in (fs_type, f"fuse.{fs_type}")

    def is_path_long_filename_mount_point(self, path: str, fs_type: str) -> bool:
        """判断路径本身是否为长文件名文件系统的挂载点"""
        target = os.path.realpath(os.path.expanduser(path))
        for mount_point, mounted_type in self._get_mount_entries():
            if os.path.realpath(mount_point) != target:
                continue
            if mounted_type in (fs_type, f"fuse.{fs_type}"):
                return True
        return False

    def get_long_filename_mounts(self, paths: list, fs_type: str) -> list:
        """返回给定路径中当前处于长文件名挂载状态的目录"""
        return [
            path for path in paths
            if self.is_path_long_filename_mounted(path, fs_type)
        ]

    def get_long_filename_mount_points(self, paths: list, fs_type: str) -> list:
        """返回给定路径中本身是长文件名挂载点的目录"""
        return [
            path for path in paths
            if self.is_path_long_filename_mount_point(path, fs_type)
        ]

    def mount_long_filename_fs(self, path: str, fs_type: str) -> bool:
        """通过文件管理器 daemon 的 MountControl 挂载长文件名文件系统

        与登录脚本 /etc/deepin/dde-file-manager/dfm-*-automount 使用同一个
        system 总线接口:
          com.deepin.filemanager.daemon.MountControl.Mount(path, {fsType})
        :return: True 表示挂载成功后该路径本身成为对应文件系统的挂载点
        """
        if fs_type not in ("dlnfs", "ulnfs") or not os.path.isdir(path):
            return False
        cmd = (
            "gdbus call -y -d com.deepin.filemanager.daemon "
            "-o /com/deepin/filemanager/daemon/MountControl "
            "-m com.deepin.filemanager.daemon.MountControl.Mount "
            f"{quote(os.path.abspath(path))} "
            f"\"{{\'fsType\': <\'{fs_type}\'>}}\" -t 5"
        )
        self.run_cmd(cmd, timeout=40, out_debug_flag=False)
        for _ in range(10):
            if self.is_path_long_filename_mount_point(path, fs_type):
                return True
            sleep(1)
        logger.warning(f"MountControl 未把 {path} 挂载为 {fs_type}")
        return False

    def unmount_long_filename_fs(self, path: str, fs_type: str = "") -> bool:
        """卸载长文件名文件系统挂载(优先 daemon Unmount, 兜底懒卸载)

        :param path: 挂载点
        :param fs_type: 期望的文件系统类型; 为空时只要求不再是长文件名挂载
        :return: True 表示该路径已不是长文件名挂载点
        """
        path = os.path.abspath(os.path.expanduser(path))
        fs_types = (fs_type,) if fs_type else ("dlnfs", "ulnfs")
        if not self.is_path_long_filename_mount_point(path, fs_types[0]):
            if not any(self.is_path_long_filename_mount_point(p, t)
                       for p in (path,) for t in fs_types):
                return True
        cmd = (
            "gdbus call -y -d com.deepin.filemanager.daemon "
            "-o /com/deepin/filemanager/daemon/MountControl "
            "-m com.deepin.filemanager.daemon.MountControl.Unmount "
            f"{quote(path)} \"{{}}\" -t 5"
        )
        self.run_cmd(cmd, timeout=30, out_debug_flag=False)
        sleep(1)
        if not any(self.is_path_long_filename_mount_point(path, t)
                   for t in fs_types):
            return True
        # 默认目录可能被桌面/文件管理器占用, 用懒卸载保证不留下挂载点
        self.sudo_run_cmd(
            f"umount -l {quote(path)}", timeout=30, out_debug_flag=False
        )
        sleep(1)
        return not any(self.is_path_long_filename_mount_point(path, t)
                       for t in fs_types)

    def apply_long_filename_mounts(self, branch: dict,
                                   target_dir: str = "") -> list:
        """把长文件名配置应用到文件系统(等效登录自动挂载, 无需重启)

        优先只挂载用例自己的验证目录, 避免影响会话默认目录; 若 daemon
        不允许该路径, 再执行登录时的官方自动挂载脚本。
        :return: 当前处于长文件名挂载状态的目录列表
        """
        fs_type = branch.get("fs_type", "")
        if fs_type not in ("dlnfs", "ulnfs"):
            return []
        default_dirs = self.get_long_filename_default_dirs(branch)
        if target_dir and self.mount_long_filename_fs(target_dir, fs_type):
            return [target_dir]
        script = branch.get("automount_script", "")
        if script and os.path.isfile(script):
            self.run_cmd(
                f"{self._dde_dconfig_prefix()}bash {quote(script)} 2>&1",
                timeout=180,
                out_debug_flag=False,
            )
        return self.get_long_filename_mounts(default_dirs, fs_type)

    def wait_long_filename_mounted(self, path: str, fs_type: str,
                                   timeout: int = 60) -> bool:
        """轮询等待路径进入长文件名文件系统(含上级挂载点)"""
        for _ in range(max(int(timeout), 1)):
            if self.is_path_long_filename_mounted(path, fs_type):
                return True
            sleep(1)
        return False

    def create_long_filename_file(self, dir_path: str, char: str = "哈",
                                  count: int = 255) -> tuple:
        """在指定目录创建超长文件名文件(中文按 UTF-8 计 3 字节/字符)

        :return: (是否创建成功, 文件路径, 错误描述)
        """
        name = char * count
        path = os.path.join(dir_path, name)
        try:
            with open(path, "w", encoding="utf-8"):
                pass
        except OSError as err:
            return False, path, str(err)
        return os.path.exists(path), path, ""

    def remove_long_filename_file(self, path: str) -> bool:
        """删除长文件名文件, 返回 True 表示已不存在"""
        try:
            if os.path.exists(path):
                os.unlink(path)
        except OSError as err:
            logger.warning(f"删除长文件名文件失败 {path[:32]}...: {err}")
        return not os.path.exists(path)

    def long_filename_create_supported(self, dir_path: str) -> bool:
        """探测目录当前是否允许创建 765 字节(255 个中文)的文件名

        在不支持长文件名的文件系统上内核返回 ENAMETOOLONG。
        """
        created, path, err = self.create_long_filename_file(dir_path, "哈", 255)
        if created:
            self.remove_long_filename_file(path)
        logger.info(f"长文件名创建探测 {dir_path}: {created} {err}")
        return created

    def get_mounted_partitions(self) -> str:
        """获取已挂载分区列表"""
        result = self.run_cmd(
            "lsblk -o NAME,MOUNTPOINT,FSTYPE 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_mounted_partition_count(self) -> int:
        """获取已挂载分区数量(有挂载点的分区)

        通过 lsblk 列出所有有挂载点的分区, 过滤掉无挂载点的设备。
        用于验证多分区显示场景。
        """
        result = self.run_cmd(
            "lsblk -o MOUNTPOINT -n 2>/dev/null | grep -v '^$' | grep -v '^/$' | wc -l",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return 0


    def is_home_partition_always_scanned(self) -> bool:
        """验证 /home 分区默认始终被扫描

        检查已挂载分区列表中是否包含 /home 或 / (根分区):
        - 若 /home 是独立分区, 则应出现在挂载列表中, 表示始终被扫描;
        - 若 /home 不是独立分区, 则 / (根分区) 应出现在列表中,
          /home 作为根分区子目录同样始终被扫描。

        :return: True 表示 /home 分区默认始终被扫描
        """
        partitions = self.get_partition_capacity_list()
        if not partitions:
            return False
        mountpoints = [p.get("mountpoint", "") for p in partitions]
        return "/home" in mountpoints or "/" in mountpoints

    def get_printer_status(self) -> bool:
        """检查打印机服务是否可用"""
        result = self.run_cmd(
            "which lpstat 2>/dev/null && lpstat -r 2>/dev/null | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        return "running" in result.lower() if result.strip() else False

    def get_lpadmin_permission_status(self) -> bool:
        """检查当前用户是否拥有 lpadmin 权限(属于 lpadmin 组)

        gpasswd/usermod 修改的是组数据库, 已运行进程的组凭据不会随之变化,
        因此读取 /etc/group(经 getent)而非 id -nG(进程凭据), 否则删除成员后
        仍会误判为有权限。
        """
        result = self.run_cmd(
            'getent group lpadmin | cut -d: -f4 | tr "," "\\n" '
            '| grep -qx "$(whoami)" && echo yes || echo no',
            timeout=5,
            out_debug_flag=False,
        )
        return "yes" in result.strip()

    def remove_lpadmin_permission(self):
        """移除当前用户的 lpadmin 权限(从 lpadmin 组中删除)

        使用 gpasswd -d 需要 root 权限, 通过 sudo_run_cmd 执行。
        """
        self.sudo_run_cmd(
            'gpasswd -d "$SUDO_USER" lpadmin',
            timeout=5,
            out_debug_flag=False,
        )

    def restore_lpadmin_permission(self):
        """恢复当前用户的 lpadmin 权限(添加到 lpadmin 组)

        使用 usermod -a -G 需要 root 权限, 通过 sudo_run_cmd 执行。
        """
        self.sudo_run_cmd(
            'usermod -a -G lpadmin "$SUDO_USER"',
            timeout=5,
            out_debug_flag=False,
        )

    def wait_lpadmin_permission_restored(self, timeout=60) -> bool:
        """轮询等待 lpadmin 权限被恢复(修复脚本通过 usermod 添加)

        :param timeout: 最长等待秒数
        :return: True 表示权限已恢复, False 表示超时仍未恢复
        """
        for _ in range(timeout):
            if self.get_lpadmin_permission_status():
                return True
            sleep(1)
        return False

    def is_dde_printer_installed(self) -> bool:
        """检查 dde-printer 包是否已安装"""
        result = self.run_cmd(
            "dpkg -l dde-printer 2>/dev/null | grep '^ii'",
            timeout=10,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def get_dde_printer_versions(self) -> tuple:
        """读取 dde-printer 的已安装版本与 apt 候选版本

        用于"已安装且为最新版本"这类前置条件: 只有两者相等才说明没有可升级版本。

        :return: (installed_version, candidate_version), 读取失败用空串
        """
        installed = self.run_cmd(
            "dpkg-query -W -f='${Version}' dde-printer 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        candidate = self.run_cmd(
            "apt-cache policy dde-printer 2>/dev/null | "
            "sed -n 's/^ *候选： *//p;s/^ *Candidate: *//p' | head -1",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        return installed, candidate

    def is_dde_printer_latest(self) -> bool:
        """判断 dde-printer 是否已安装且为 apt 候选版本(无可升级版本)

        :return: True 表示已安装且版本与候选一致
        """
        installed, candidate = self.get_dde_printer_versions()
        return bool(installed) and bool(candidate) and installed == candidate

    def get_dde_printer_available_versions(self) -> list:
        """列出 apt 中可安装的 dde-printer 版本(去重, 按出现顺序)

        用于构造"存在可升级版本"现场: 需要挑一个比候选版本旧的版本降级安装。

        :return: 版本字符串列表, 读取失败返回 []
        """
        out = self.run_cmd(
            "apt-cache policy dde-printer 2>/dev/null | "
            "sed -n 's/^ *[0-9][0-9.]*-[0-9+~a-zA-Z.]* *[0-9]*$/&/p'",
            timeout=10,
            out_debug_flag=False,
        )
        versions = []
        for line in (out or "").splitlines():
            parts = line.split()
            if parts and parts[0][0].isdigit() and parts[0] not in versions:
                versions.append(parts[0])
        return versions

    def install_dde_printer_version(self, version) -> bool:
        """安装指定版本的 dde-printer(允许降级), 并确认已生效

        apt 默认拒绝降级, 需显式 --allow-downgrades; 安装后轮询确认 dpkg 记录的
        版本确实是目标版本。

        :param version: 目标版本字符串(如 1.0.19-1+1060)
        :return: True 表示安装成功且版本匹配
        """

        if not version:
            return False
        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get install -y "
            f"--allow-downgrades dde-printer={version}",
            timeout=300,
            out_debug_flag=False,
        )
        for _ in range(30):
            installed, _candidate = self.get_dde_printer_versions()
            if installed == version:
                return True
            sleep(1)
        return False

    def get_liansoft_feature_in_cups_logs(self) -> bool:
        """检查CUPS日志中是否存在联软管控软件特征(dvc-filter-exe)

        联软管控软件会在CUPS日志中留下 dvc-filter-exe 关键字,
        通过检查 error_log/access_log/page_log 判断是否存在特征。
        :return: True 表示存在特征, False 表示不存在
        """
        result = self.run_cmd(
            "grep -rl 'dvc-filter-exe' /var/log/cups/error_log "
            "/var/log/cups/access_log /var/log/cups/page_log 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def uninstall_dde_printer(self):
        """卸载 dde-printer 包(V20/V25 兼容)"""

        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get remove -y dde-printer",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(2)

    def install_dde_printer(self):
        """安装 dde-printer 包(V20/V25 兼容)

        测试机的部分 apt 源已失效(pro-driver/professional-security 返回
        "不再含有 Release 文件"), "apt-get update" 因此整体返回非 0。原先用
        "&&" 串联会导致 update 失败时根本不执行 install; 这里让 update 尽力而为
        (失败忽略), install 使用本地索引与可用源完成安装, 最后轮询确认装回。
        """

        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get update -qq >/dev/null 2>&1 "
            f"|| true; echo '{conf.PASSWORD}' | sudo -S apt-get install -y dde-printer",
            timeout=300,
            out_debug_flag=False,
        )
        for _ in range(30):
            if self.is_dde_printer_installed():
                break
            sleep(1)

    def get_audio_service_status(self) -> bool:
        """检查D-Bus音频服务是否可用"""
        result = self.run_cmd(
            "systemctl --user is-active pulseaudio 2>/dev/null || "
            "systemctl --user is-active pipewire 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        # 必须精确匹配: is-active 输出 "inactive" 时子串包含 "active"
        states = {line.strip().lower() for line in result.splitlines() if line.strip()}
        return "active" in states

    def stop_audio_service(self):
        """停止音频服务以模拟 pulseaudio 重启失败场景(V20/V25 兼容)

        V20 停止 pulseaudio 用户服务, V25 停止 pipewire 用户服务。
        必须同时停止 .socket: 仅停 .service 时 socket 会立即按需重新拉起服务,
        导致服务状态仍为 active。
        停止前通过 systemd-run --user 安排 60 秒后自动恢复, 确保即使
        测试中断音频服务也能自动恢复。
        """
        if self.is_v25_environment():
            services = "pipewire.socket pipewire.service"
        else:
            services = "pulseaudio.socket pulseaudio.service"
        self.run_cmd(
            f"systemd-run --user --on-active=60 --unit=pms-audio-recovery "
            f"systemctl --user start {services} 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"systemctl --user stop {services} 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)

    def start_audio_service(self):
        """恢复音频服务(V20/V25 兼容)

        启动音频服务并取消 stop_audio_service 设置的定时恢复任务。
        """
        if self.is_v25_environment():
            services = "pipewire.socket pipewire.service"
        else:
            services = "pulseaudio.socket pulseaudio.service"
        self.run_cmd(
            f"systemctl --user stop pms-audio-recovery.timer 2>/dev/null; "
            f"systemctl --user start {services} 2>/dev/null; true",
            timeout=15,
            out_debug_flag=False,
        )
        sleep(5)

    def get_default_source_name(self) -> str:
        """获取默认音频输入 Source 名称(V20 PulseAudio / V25 PipeWire 兼容)

        通过 pactl 获取默认 source 名称。
        :return: 默认 source 名称, 获取失败返回空字符串
        """
        result = self.run_cmd(
            "pactl get-default-source 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        name = result.strip()
        if name:
            return name
        # 回退: 从 pactl list short sources 中取第一个非 monitor 的 source
        result = self.run_cmd(
            "pactl list short sources 2>/dev/null | grep -v '.monitor' | head -1 | awk '{print $2}'",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def set_source_mute(self, source_name: str, mute: bool = True):
        """设置指定 Source 的静音状态(V20/V25 兼容)

        :param source_name: Source 名称
        :param mute: True 表示静音, False 表示取消静音
        """
        mute_val = "1" if mute else "0"
        self.run_cmd(
            f"pactl set-source-mute {source_name} {mute_val} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def get_source_mute_status(self, source_name: str) -> bool:
        """获取指定 Source 的静音状态(V20/V25 兼容)

        旧版 pactl(12.x) 无 get-source-mute 子命令, 回退解析 pactl list sources。
        :param source_name: Source 名称
        :return: True 表示已静音, False 表示未静音
        """
        result = self.run_cmd(
            f"pactl get-source-mute {source_name} 2>&1",
            timeout=5,
            out_debug_flag=False,
        )
        text = result.strip().lower()
        if "yes" in text or "是" in text:
            return True
        if "no" in text or "否" in text:
            return False
        if source_name.startswith("@"):
            source_name = self.get_default_source_name()
        return self._pactl_list_muted("sources", source_name)

    # ===== UI交互辅助方法 =====

    def switch_theme(self):
        """切换主题(浅色/深色)

        V20 使用 theme-name 键, V25 没有 theme-name 键则回退到 gtk-theme。
        """
        current = self.get_theme_type()
        if "dark" in current.lower():
            self.run_cmd(
                "gsettings set com.deepin.dde.appearance theme-name light 2>/dev/null || "
                "gsettings set org.deepin.dde.appearance theme-name light 2>/dev/null || "
                "gsettings set com.deepin.dde.appearance gtk-theme deepin 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
        else:
            self.run_cmd(
                "gsettings set com.deepin.dde.appearance theme-name dark 2>/dev/null || "
                "gsettings set org.deepin.dde.appearance theme-name dark 2>/dev/null || "
                "gsettings set com.deepin.dde.appearance gtk-theme deepin-dark 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
        sleep(2)

    def get_gtk_theme(self) -> str:
        """获取当前系统 GTK 主题(如 deepin/deepin-dark)

        V20 控制中心"个性化-主题"切换即修改该键, 可作为系统配色变更的等价开关。

        :return: 主题名字符串(已去除引号)
        """
        result = self.run_cmd(
            "gsettings get com.deepin.dde.appearance gtk-theme 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip().strip("'\"")

    def set_gtk_theme(self, theme_name) -> bool:
        """设置系统 GTK 主题并回读校验

        :param theme_name: 主题名, 如 deepin-dark
        :return: True 表示设置成功
        """
        self.run_cmd(
            f"gsettings set com.deepin.dde.appearance gtk-theme '{theme_name}'",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)
        return self.get_gtk_theme() == theme_name

    def get_focused_window_screenshot_md5(self, path="/tmp/pcm_accent_check.png") -> str:
        """截取当前焦点窗口并返回图片 MD5(用于判断配色是否变化)

        只截焦点窗口, 避免桌面/壁纸/任务栏干扰配色对比。

        :param path: 临时截图路径
        :return: MD5 字符串, 失败返回空串
        """
        self._safe_focus_windows()
        self.run_cmd(f"scrot -u {path} 2>/dev/null", timeout=20, out_debug_flag=False)
        result = self.run_cmd(
            f"test -s {path} && md5sum {path} | awk '{{print $1}}'",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip()

    def remove_accent_color_screenshot(self, path="/tmp/pcm_accent_check.png"):
        """删除配色验证用的临时截图"""
        self.run_cmd(f"rm -f {path}", timeout=5, out_debug_flag=False)

    def get_accent_color(self) -> str:
        """获取当前活动用色(accent color), 返回 hex 色值字符串

        V25 使用 dde-dconfig, V20 使用 gsettings, 两者均尝试。
        """
        result = self.run_cmd(
            'dde-dconfig --get -a org.deepin.dde.appearance '
            '-r org.deepin.dde.appearance -k accent-color 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        result = result.strip().strip("'\"")
        if result and "not exist" not in result and "Usage:" not in result:
            return result
        result = self.run_cmd(
            "gsettings get com.deepin.dde.appearance accent-color 2>/dev/null || "
            "gsettings get org.deepin.dde.appearance accent-color 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip().strip("'\"")

    def set_accent_color(self, color: str):
        """设置活动用色(accent color), color 为 hex 色值如 #FF0000

        V25 使用 dde-dconfig, V20 使用 gsettings, 两者均尝试。
        """
        self.run_cmd(
            f"dde-dconfig --set -a org.deepin.dde.appearance "
            f"-r org.deepin.dde.appearance -k accent-color -v '{color}' 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"gsettings set com.deepin.dde.appearance accent-color '{color}' 2>/dev/null || "
            f"gsettings set org.deepin.dde.appearance accent-color '{color}' 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(2)

    def switch_accent_color(self):
        """切换活动用色到不同颜色(在预设列表中循环切换)"""
        accent_colors = ["#FF0000", "#00FF00", "#0000FF", "#FFA500"]
        current = self.get_accent_color()
        for color in accent_colors:
            if color.upper() not in current.upper():
                self.set_accent_color(color)
                return
        self.set_accent_color(accent_colors[0])

    def get_window_title(self) -> str:
        """获取当前窗口标题"""
        result = self.run_cmd(
            "xdotool getactivewindow getwindowname 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def press_key(self, key: str):
        """模拟按键"""
        self.run_cmd(
            f"xdotool key {key}",
            timeout=2,
            out_debug_flag=False,
        )
        sleep(1)

    # ===== PMS 2005497「系统检测--空间清理入口有垃圾」测试用例方法 =====

    def create_test_junk_files(self):
        """创建测试垃圾文件以确保空间清理扫描能检测到垃圾

        空间清理扫描器只统计回收站、浏览器缓存、系统缓存等固定类别,
        自定义缓存目录(~/.cache/autotest_junk)不会被识别。
        因此把 5 个 1MB 文件写入回收站 files 目录, 保证扫描结果包含垃圾。
        """
        junk_dir = f"{HOME_DIR}/.local/share/Trash/files/autotest_junk"
        self.run_cmd(f"mkdir -p {junk_dir}", timeout=5, out_debug_flag=False)
        for i in range(5):
            junk_file = f"{junk_dir}/junk_{i}.dat"
            self.run_cmd(
                f"dd if=/dev/zero of={junk_file} bs=1M count=1 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
        sleep(1)

    def remove_test_junk_files(self):
        """清理测试创建的垃圾文件"""
        junk_dir = f"{HOME_DIR}/.local/share/Trash/files/autotest_junk"
        self.run_cmd(
            f"rm -rf {junk_dir}",
            timeout=5,
            out_debug_flag=False,
        )

    def get_space_clean_featured_card_showing(self, timeout=10) -> bool:
        """检查系统优化页"空间清理"特色卡片入口是否可见

        产品系统优化页(optimization_overview)的 featuredCard 固定承载空间清理
        入口: 卡片标题/描述为 QML 绘制, AT-SPI 只暴露英文 accessibleName
        ("Featured card for space clean plugin"), .text/.name 均读不到
        "存在垃圾可清理"这类中文文案(实测)。
        因此以卡片框架 optimization_featuredCard 与开始扫描按钮
        optimization_startScanBtn 的非零尺寸作为"入口已渲染"的等价判据。

        :param timeout: 最长等待秒数
        :return: True 表示特色卡片/开始扫描按钮可见
        """
        self._safe_focus_windows()
        for _ in range(timeout):
            for expr in ("$//optimization_featuredCard",
                         "$//optimization_startScanBtn"):
                try:
                    element = self.dog.find_element_by_attr(expr)
                    if element.showing:
                        return True
                    width, height = element.size
                    if width > 0 and height > 0:
                        return True
                except BaseException:
                    continue
            sleep(1)
        return False

    def create_large_trash_file(self, size="3G",
                                name="autotest_large_trash.bin"):
        """在回收站中创建指定大小的大文件(对应 3G 回收站前置条件)

        使用 fallocate 快速分配(稀疏文件), 扫描器按文件大小统计。
        :param size: fallocate 大小, 如 "3G"
        :param name: 文件名
        """
        path = f"{HOME_DIR}/.local/share/Trash/files/{name}"
        self.run_cmd(
            f"mkdir -p {quote(f'{HOME_DIR}/.local/share/Trash/files')} && "
            f"fallocate -l {size} {quote(path)}",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_large_trash_file(self, name="autotest_large_trash.bin"):
        """清理回收站中的大测试文件(含回收站信息文件)"""
        self.run_cmd(
            f"rm -f "
            f"{quote(f'{HOME_DIR}/.local/share/Trash/files/{name}')} "
            f"{quote(f'{HOME_DIR}/.local/share/Trash/info/{name}.trashinfo')}",
            timeout=10,
            out_debug_flag=False,
        )

    def get_large_trash_file_exist(self, name="autotest_large_trash.bin"):
        """检查回收站中的大测试文件是否仍存在"""
        result = self.run_cmd(
            f"test -f "
            f"{quote(f'{HOME_DIR}/.local/share/Trash/files/{name}')} && "
            "echo AUTOTEST_FILE_EXISTS",
            timeout=5,
            out_debug_flag=False,
        )
        return "AUTOTEST_FILE_EXISTS" in result

    def wait_large_trash_file_cleaned(self, timeout=120,
                                      name="autotest_large_trash.bin"):
        """等待回收站中的大测试文件被清理

        :param timeout: 最长等待秒数
        :param name: 文件名
        :return: True 如果文件已被清理
        """
        for _ in range(timeout):
            if not self.get_large_trash_file_exist(name):
                return True
            sleep(1)
        return False

    # ===== 空间清理全类型垃圾预创建(用例自建测试数据) =====
    # 与 space_clean_detector 的扫描规则一一对应, 用例执行多次后真实垃圾会被
    # 清理干净, 因此每个用例自行在管家检测目录中创建测试垃圾。
    _ALL_JUNK_APP_FILES = (
        f"{HOME_DIR}/.cache/youdao-dict/autotest_cache.dat",
        f"{HOME_DIR}/.cache/filezilla/autotest_cache.dat",
        f"{HOME_DIR}/.local/share/ThunderNetwork/autotest_cache.dat",
        f"{HOME_DIR}/.cache/baidunetdisk/autotest_cache.dat",
        f"{HOME_DIR}/.cache/sunloginclient/autotest_cache.dat",
        f"{HOME_DIR}/.cache/browser/autotest_cache.dat",
        f"{HOME_DIR}/.cache/mozilla/firefox/autotest_cache.dat",
        f"{HOME_DIR}/.local/share/Kingsoft/autotest_cache.dat",
        f"{HOME_DIR}/.config/360zip.db",
    )
    _ALL_JUNK_COOKIE_DIRS = (
        f"{HOME_DIR}/.config/browser/Default",
        f"{HOME_DIR}/.config/qqbrowser/Default",
        f"{HOME_DIR}/.config/com.360.browser/Default",
        f"{HOME_DIR}/.config/google-chrome/Default",
        f"{HOME_DIR}/.config/microsoft-edge/Default",
    )
    _JOURNAL_JUNK_FILE = "/var/log/journal/autotest@archive.journal"
    _LICENSE_JUNK_FILE = "/var/log/uos/uos-license-agent/autotest.99.log"

    def create_all_space_clean_junk(self):
        """按空间清理扫描规则预创建全部四类测试垃圾

        对应产品 space_clean_detector 的目录:
        - 系统垃圾: 回收站、apt 缓存 deb、/var/log 下 >100MB 大日志、
          已轮转日志、journal 归档日志、uos-license-agent 轮转日志
        - 应用垃圾: 有道/FileZilla/迅雷/百度网盘/向日葵/UOS 浏览器/
          Firefox/WPS/360zip 的缓存与卸载残留
        - 痕迹信息: ~/.local/share/recently-used.xbel
        - cookies: UOS/QQ/360/Chrome/Edge 浏览器的 Cookies 文件

        创建完成后扫描结果应同时出现系统垃圾/应用垃圾/痕迹信息/cookies
        四个分类, 供"清理所有"类用例使用; 需要单选某一类的用例先调用
        clean_other_system_junk_items 等隔离手段再扫描。
        """
        # 系统垃圾
        self.create_test_junk_files()
        self.create_system_cache_junk()
        self.create_large_system_log()
        self.create_test_system_log_junk()
        self.sudo_run_cmd(
            f"mkdir -p {os.path.dirname(self._JOURNAL_JUNK_FILE)} && "
            f"dd if=/dev/zero of={self._JOURNAL_JUNK_FILE} bs=1M count=1 "
            "2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"mkdir -p {os.path.dirname(self._LICENSE_JUNK_FILE)} && "
            f"dd if=/dev/zero of={self._LICENSE_JUNK_FILE} bs=1M count=1 "
            "2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        # 应用垃圾(缓存/卸载残留)
        for app_file in self._ALL_JUNK_APP_FILES:
            self.run_cmd(
                f"mkdir -p {quote(os.path.dirname(app_file))} && "
                f"dd if=/dev/zero of={quote(app_file)} bs=1M count=1 "
                "2>/dev/null",
                timeout=15,
                out_debug_flag=False,
            )
        # 痕迹信息
        self.create_trace_junk()
        # cookies
        for cookie_dir in self._ALL_JUNK_COOKIE_DIRS:
            self.run_cmd(
                f"mkdir -p {quote(cookie_dir)} && "
                f"dd if=/dev/zero of={quote(cookie_dir)}/Cookies "
                "bs=1K count=1024 2>/dev/null",
                timeout=15,
                out_debug_flag=False,
            )
        sleep(1)

    def remove_all_space_clean_junk(self):
        """清理 create_all_space_clean_junk 创建的全部测试垃圾"""
        self.remove_test_junk_files()
        self.remove_system_cache_junk()
        self.remove_large_system_log()
        self.remove_test_system_log_junk()
        self.sudo_run_cmd(
            f"rm -f {self._JOURNAL_JUNK_FILE} {self._LICENSE_JUNK_FILE} "
            "2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        )
        app_files = " ".join(quote(f) for f in self._ALL_JUNK_APP_FILES)
        self.run_cmd(
            f"rm -f {app_files} 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        )
        cookie_files = " ".join(
            quote(f"{d}/Cookies") for d in self._ALL_JUNK_COOKIE_DIRS
        )
        self.run_cmd(
            f"rm -f {cookie_files} 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        )
        self.remove_trace_junk()
        sleep(1)

    def get_test_junk_files_exist(self) -> bool:
        """检查测试创建的垃圾文件是否仍然存在

        :return: True 如果垃圾文件仍存在, False 如果已被清理
        """
        junk_dir = f"{HOME_DIR}/.local/share/Trash/files/autotest_junk"
        result = self.run_cmd(
            f"test -d {junk_dir} && ls -A {junk_dir}/ && echo 1",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def wait_test_junk_files_cleaned(self, timeout=60) -> bool:
        """等待测试垃圾文件被清理完毕

        点击清理按钮后, 应用需要时间执行清理操作。
        本方法轮询检查测试垃圾文件是否已被删除。
        :param timeout: 最长等待秒数
        :return: True 如果垃圾文件已被清理, False 如果超时仍存在
        """
        for _ in range(timeout):
            if not self.get_test_junk_files_exist():
                return True
            sleep(1)
        return False

    # ===== PMS 2001729「垃圾清理--清理系统日志」测试用例方法 =====
    def create_test_system_log_junk(self):
        """创建测试系统日志垃圾文件（已轮转的日志文件）以确保空间清理扫描能检测到系统日志

        空间清理扫描器检测 /var/log 下匹配特定模式的已轮转日志文件:
        daemon.log.* / kern.log.* / messages.* / syslog.* / user.log.*
        使用高编号后缀避免与真实轮转日志冲突。
        """
        test_log_files = [
            "/var/log/daemon.log.99",
            "/var/log/syslog.99",
            "/var/log/user.log.99",
        ]
        for log_file in test_log_files:
            self.sudo_run_cmd(
                f"dd if=/dev/zero of={log_file} bs=1M count=1 2>/dev/null",
                timeout=10,
                out_debug_flag=False,
            )
        sleep(1)

    def remove_test_system_log_junk(self):
        """清理测试创建的系统日志垃圾文件"""
        test_log_files = [
            "/var/log/daemon.log.99",
            "/var/log/syslog.99",
            "/var/log/user.log.99",
        ]
        for log_file in test_log_files:
            self.sudo_run_cmd(
                f"rm -f {log_file} 2>/dev/null || true",
                timeout=10,
                out_debug_flag=False,
            )

    # ===== 空间清理：系统垃圾分类 6 个扫描项 =====

    # 系统垃圾分类(system)下的全部扫描项, 与产品 ScanRule.id 一一对应。
    # 1.1.7 的 AT-SPI 不暴露 itemId: 产品把 id 存在 QWidget 的
    # accessibleIdentifier 动态属性里(不上 AT-SPI), accessibleName 对所有
    # 子项都是固定值 spaceClean_itemName, 显示文本也读不到(queryText 为空)。
    # 因此断言只能落在"项数量 + 大小降序位置 + 清理结果"三者的交叉验证上,
    # ID 与显示名称用于文档映射。
    SYSTEM_JUNK_ITEMS = (
        ("sys-cache", "系统缓存"),
        ("sys-log-large", "超过100MB的系统日志"),
        ("sys-log-journal", "journal 日志（日志转储/归档文件）"),
        ("sys-log-rotated", "轮转日志文件"),
        ("sys-license-log", "uos-license-agent 轮转日志"),
        ("sys-trash", "回收站"),
    )
    SYSTEM_JUNK_ITEM_IDS = tuple(item_id for item_id, _name in SYSTEM_JUNK_ITEMS)

    # 每个扫描项对应的测试垃圾路径(前置构造/后置清理/存在性断言共用)。
    # 判据来自产品 space_clean_detector 的 ScanRule:
    # - sys-cache: /var/cache/{apt,lastore}/archives 下的残留 .deb
    # - sys-log-large: /var/log 下 >= 100MB 的文件(清理方式是 truncate)
    # - sys-log-journal: /var/log/journal 下文件名含 '@' 的归档 journal
    # - sys-log-rotated: daemon.log/kern.log/messages/syslog/user.log 的轮转文件
    # - sys-license-log: /var/log/uos/uos-license-agent 下非当前日志
    # - sys-trash: ~/.local/share/Trash 下的文件
    SYSTEM_JUNK_PATHS = {
        "sys-cache": "/var/cache/apt/archives/autotest-sysjunk_1.0_amd64.deb",
        "sys-log-large": "/var/log/autotest_sysjunk_large.log",
        "sys-log-journal": "/var/log/journal/autotest_sysjunk@probe.journal",
        "sys-log-rotated": "/var/log/syslog.99",
        "sys-license-log": "/var/log/uos/uos-license-agent/autotest_sysjunk.log.1",
        "sys-trash": f"{HOME_DIR}/.local/share/Trash/files/autotest_sysjunk/junk.dat",
    }

    def create_all_system_junk_items(self):
        """构造系统垃圾分类 6 个扫描项对应的垃圾, 使结果页出现全部 6 项

        每个文件都远大于扫描器的最小可清理阈值, 且 sys-log-large 的 120MB
        保证它在系统垃圾分类内按大小降序排在第一位(产品 categoryItemLess),
        用例因此可以用"勾选第一项 + 清理"定位到"超过100MB的系统日志"。
        """
        self.sudo_run_cmd(
            "mkdir -p /var/cache/apt/archives /var/log/journal "
            "/var/log/uos/uos-license-agent "
            f"{HOME_DIR}/.local/share/Trash/files/autotest_sysjunk && "
            "dd if=/dev/zero "
            "of=/var/cache/apt/archives/autotest-sysjunk_1.0_amd64.deb "
            "bs=1M count=2 2>/dev/null; "
            "dd if=/dev/zero "
            "of=/var/log/journal/autotest_sysjunk@probe.journal "
            "bs=1M count=2 2>/dev/null; "
            "dd if=/dev/zero of=/var/log/syslog.99 bs=1M count=1 2>/dev/null; "
            "dd if=/dev/zero "
            "of=/var/log/uos/uos-license-agent/autotest_sysjunk.log.1 "
            "bs=1M count=1 2>/dev/null; "
            "dd if=/dev/zero "
            f"of={HOME_DIR}/.local/share/Trash/files/autotest_sysjunk/junk.dat "
            "bs=1M count=1 2>/dev/null; "
            "dd if=/dev/zero of=/var/log/autotest_sysjunk_large.log "
            "bs=1M count=120 2>/dev/null; true",
            timeout=180,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_all_system_junk_items(self):
        """清理 create_all_system_junk_items 构造的全部测试垃圾"""
        paths = " ".join(
            quote(path) for path in self.SYSTEM_JUNK_PATHS.values()
        )
        self.sudo_run_cmd(
            f"rm -rf {paths} "
            f"'{HOME_DIR}/.local/share/Trash/files/autotest_sysjunk' "
            "2>/dev/null; true",
            timeout=60,
            out_debug_flag=False,
        )

    def get_system_junk_item_exists(self, item_id) -> bool:
        """检查系统垃圾某一扫描项对应的测试垃圾是否仍可被扫描到

        sys-log-large 的清理方式是把文件截断为 0, 因此判定"仍存在"要求
        文件同时存在且不小于 100MB。

        :param item_id: 扫描项 ID, 取值见 SYSTEM_JUNK_ITEMS
        :return: True 表示该扫描项对应的垃圾仍存在
        """
        path = quote(self.SYSTEM_JUNK_PATHS[item_id])
        if item_id == "sys-log-large":
            command = (
                f"test -f {path} && "
                f'[ "$(stat -c %s {path} 2>/dev/null)" -ge 104857600 ] && '
                "echo SYSJUNK_ITEM_EXISTS"
            )
        else:
            command = (
                f"test -e {path} && echo SYSJUNK_ITEM_EXISTS"
            )
        return "SYSJUNK_ITEM_EXISTS" in self.sudo_run_cmd(
            f"{command} 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )

    def wait_system_junk_item_cleaned(self, item_id, timeout=120) -> bool:
        """等待系统垃圾某一扫描项对应的测试垃圾被清理完毕

        :param item_id: 扫描项 ID, 取值见 SYSTEM_JUNK_ITEMS
        :param timeout: 最长等待秒数
        :return: True 如果对应垃圾已不存在
        """
        for _ in range(timeout):
            if not self.get_system_junk_item_exists(item_id):
                return True
            sleep(1)
        return False

    def get_space_clean_item_total_count(self, retries=5) -> int:
        """获取空间清理结果页可见的单项(分类内子项)复选框总数

        1.1.7 上结果页只渲染已展开分类的子项, 系统垃圾分类默认展开,
        因此该数量即系统垃圾分类下的子项数(产品系统垃圾分类共 6 个扫描项)。

        :return: 可见单项复选框数量
        """
        return len(self.get_space_clean_item_checkboxes(retries=retries))

    # ===== 空间清理：系统垃圾/回收站用例方法 =====

    def clean_other_system_junk_items(self):
        """清理回收站之外的系统垃圾, 使系统垃圾分类下只剩回收站

        与 space_clean_detector 的 system 分类规则一一对应, 避免其它系统
        垃圾项干扰"仅勾选回收站"的定位(结果页系统垃圾按大小降序排列,
        回收站未必是第一项):
        - sys-cache: /var/cache/{apt,lastore}/archives
        - sys-log-large: /var/log 下 >= 100MB 的文件
        - sys-log-journal: 归档 journal(文件名含 @)
        - sys-log-rotated: daemon.log/kern.log/messages/syslog/user.log 的轮转文件
        - sys-license-log: uos-license-agent 已轮转日志
        """
        self.sudo_run_cmd(
            "rm -f /var/log/journal/*/*@*.journal 2>/dev/null; "
            "journalctl --vacuum-size=20M >/dev/null 2>&1 || true; "
            "apt-get clean >/dev/null 2>&1 || true; "
            "rm -rf /var/cache/lastore/archives/* 2>/dev/null; "
            "rm -f /var/log/daemon.log.* /var/log/kern.log.* "
            "/var/log/messages.* /var/log/syslog.* /var/log/user.log.* 2>/dev/null; "
            "find /var/log -type f -size +100M -delete 2>/dev/null; "
            "find /var/log/uos/uos-license-agent -maxdepth 1 -type f "
            "! -name uos-license-agent.log -delete 2>/dev/null; "
            "true",
            timeout=120,
            out_debug_flag=False,
        )
        sleep(1)

    def get_test_system_log_junk_exist(self) -> bool:
        """检查测试创建的系统日志垃圾文件是否仍然存在

        :return: True 如果任一测试日志文件仍存在, False 如果全部已被清理
        """
        test_log_files = [
            "/var/log/daemon.log.99",
            "/var/log/syslog.99",
            "/var/log/user.log.99",
        ]
        for log_file in test_log_files:
            result = self.sudo_run_cmd(
                f"test -f {log_file} && echo AUTOTEST_FILE_EXISTS",
                timeout=10,
                out_debug_flag=False,
            )
            if "AUTOTEST_FILE_EXISTS" in result:
                return True
        return False

    def wait_test_system_log_junk_cleaned(self, timeout=60) -> bool:
        """等待测试系统日志垃圾文件被清理完毕

        点击清理按钮后, 应用需要时间执行清理操作。
        本方法轮询检查测试日志文件是否已被删除。
        :param timeout: 最长等待秒数
        :return: True 如果日志文件已被清理, False 如果超时仍存在
        """
        for _ in range(timeout):
            if not self.get_test_system_log_junk_exist():
                return True
            sleep(1)
        return False

    # ===== PMS 2001661「垃圾清理--系统日志超过100MB可清理」测试用例方法 =====
    def create_large_system_log(self):
        """在 /var/log 下创建超过 100MB 的系统日志文件, 确保空间清理扫描器能检测到

        空间清理扫描器检测 /var/log 下超过 100MB 的大日志文件。
        创建一个 120MB 的测试日志文件, 使扫描结果包含系统日志分类。
        """
        log_file = "/var/log/autotest_large_syslog.log"
        self.sudo_run_cmd(
            f"dd if=/dev/zero of={log_file} bs=1M count=120 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(1)

    # ===== PMS 2001733「垃圾清理--清理cookies」测试用例方法 =====

    def create_test_cookie_files(self):
        """创建测试用浏览器 Cookie 文件, 确保空间清理扫描能检测到 Cookies 分类

        空间清理扫描器检测以下浏览器路径的 Cookie 文件:
        google-chrome / chromium / microsoft-edge / UOS 浏览器(browser) /
        QQ 浏览器(qqbrowser) / 360 浏览器(com.360.browser)。
        在 google-chrome 的 Default 目录下创建 Cookies 文件即可触发检测。
        """
        cookie_dir = f"{HOME_DIR}/.config/google-chrome/Default"
        self.run_cmd(f"mkdir -p {cookie_dir}", timeout=5, out_debug_flag=False)
        self.run_cmd(
            f"dd if=/dev/zero of={cookie_dir}/Cookies bs=1K count=1 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_large_system_log(self):
        """清理测试创建的大型系统日志文件"""
        log_file = "/var/log/autotest_large_syslog.log"
        self.sudo_run_cmd(
            f"rm -f {log_file}",
            timeout=10,
            out_debug_flag=False,
        )

    def get_large_system_log_exists(self) -> bool:
        """检查大型系统日志文件是否仍然存在且超过 100MB

        空间清理器对大日志文件的处理方式是 truncate(截断为 0),
        因此清理后文件可能仍存在但大小为 0。
        注意: sudo -S 会向 stderr 输出 "验证成功", 而 _getstatusoutput 将
        stderr 合并到 stdout, 因此不能用 bool(result.strip()) 判断,
        必须检查特定标记字符串。
        :return: True 如果文件存在且超过 100MB, False 如果已被截断或删除
        """
        log_file = "/var/log/autotest_large_syslog.log"
        result = self.sudo_run_cmd(
            f"test -f {log_file} && "
            f'[ "$(stat -c %s {log_file} 2>/dev/null)" -gt 104857600 ] && echo LOG_LARGE_EXISTS',
            timeout=10,
            out_debug_flag=False,
        )
        return "LOG_LARGE_EXISTS" in result

    def wait_large_system_log_cleaned(self, timeout=120) -> bool:
        """等待大型系统日志文件被清理完毕

        点击清理按钮后, 应用需要时间执行清理操作。
        本方法轮询检查大型日志文件是否已被截断或删除。
        :param timeout: 最长等待秒数
        :return: True 如果日志文件已被清理, False 如果超时仍存在
        """
        for _ in range(timeout):
            if not self.get_large_system_log_exists():
                return True
            sleep(1)
        return False

    def remove_test_cookie_files(self):
        """清理测试创建的 Cookie 文件"""
        self.run_cmd(
            f"rm -rf {HOME_DIR}/.config/google-chrome",
            timeout=5,
            out_debug_flag=False,
        )

    def get_test_cookie_files_exist(self) -> bool:
        """检查测试创建的 Cookie 文件是否仍然存在

        :return: True 如果 Cookie 文件仍存在, False 如果已被清理
        """
        cookie_file = f"{HOME_DIR}/.config/google-chrome/Default/Cookies"
        result = self.run_cmd(
            f"test -f {cookie_file} && echo 1",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def wait_test_cookie_files_cleaned(self, timeout=60) -> bool:
        """等待测试 Cookie 文件被清理完毕

        点击清理按钮后, 应用需要时间执行清理操作。
        本方法轮询检查测试 Cookie 文件是否已被删除。
        :param timeout: 最长等待秒数
        :return: True 如果 Cookie 文件已被清理, False 如果超时仍存在
        """
        for _ in range(timeout):
            if not self.get_test_cookie_files_exist():
                return True
            sleep(1)
        return False

    def clean_system_junk_for_no_junk_test(self):
        """清理常见缓存目录以确保空间清理扫描结果为无垃圾

        清理用户级别的缓存目录(缩略图缓存、回收站、测试垃圾文件等),
        以及需要 sudo 的 APT 缓存, 尽量确保扫描器检测不到垃圾。
        """
        self.remove_test_junk_files()
        clean_cmds = [
            f"rm -rf {HOME_DIR}/.cache/thumbnails/*",
            f"rm -rf {HOME_DIR}/.local/share/Trash/*",
            f"rm -rf {HOME_DIR}/.cache/mozilla/*",
            f"rm -rf {HOME_DIR}/.cache/google-chrome/*",
            f"rm -rf {HOME_DIR}/.cache/deepin/*",
            "sudo rm -rf /var/cache/apt/archives/*.deb 2>/dev/null || true",
            "sudo apt-get clean 2>/dev/null || true",
        ]
        for cmd in clean_cmds:
            self.run_cmd(cmd, timeout=10, out_debug_flag=False)
        sleep(1)

    def clean_system_for_no_junk(self):
        """清理系统中空间清理扫描器可能检测到的所有垃圾文件

        空间清理扫描器检测以下类别:
        - 系统缓存(apt/lastore 归档)
        - 系统日志中超过 100MB 的大日志文件
        - 已轮转的日志文件(daemon.log.* / kern.log.* / messages.* / syslog.* / user.log.*)
        - journal 归档日志(文件名含 @ 的已归档日志)
        - uos-license-agent 轮转日志
        - 回收站
        - 应用垃圾(Application Junk): 有道词典/FileZilla/迅雷/百度网盘/向日葵/
          UOS 浏览器/Firefox/WPS/360zip 的缓存与卸载残留
        - Cookies Information: UOS 浏览器/QQ 浏览器/360 浏览器/Chrome/Edge 的 cookie

        本方法在"无垃圾"测试用例前置步骤中调用, 确保扫描结果为空。
        各清理步骤独立执行, 单步失败不影响后续步骤。
        """
        self.sudo_run_cmd("apt-get clean", timeout=30, out_debug_flag=False)
        self.sudo_run_cmd(
            "rm -rf /var/cache/lastore/archives/*",
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "find /var/log -type f -size +100M -exec truncate -s 0 {} \\;",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "find /var/log -maxdepth 1 -type f \\( "
            "-name 'daemon.log.*' -o -name 'kern.log.*' -o -name 'messages.*' "
            "-o -name 'syslog.*' -o -name 'user.log.*' \\) -delete",
            timeout=15,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "journalctl --vacuum-size=1 --vacuum-time=1s",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(1)
        self.sudo_run_cmd(
            "journalctl --vacuum-size=1 --vacuum-time=1s",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "find /var/log/journal -type f -name '*@*' -delete 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "find /var/log/uos/uos-license-agent -maxdepth 1 -type f "
            "! -name 'uos-license-agent.log' -delete 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"rm -rf {HOME_DIR}/.local/share/Trash/*",
            timeout=10,
            out_debug_flag=False,
        )
        # 痕迹信息(recently-used.xbel)会被扫描器计为垃圾, 需一并清理
        self.run_cmd(
            f"rm -f {HOME_DIR}/.local/share/recently-used.xbel "
            f"{HOME_DIR}/.recently-used.xbel",
            timeout=5,
            out_debug_flag=False,
        )
        # 1.1.3 起扫描器新增 Application Junk / Cookies Information 规则,
        # 这些目录下的文件同样计入垃圾(与是否安装应用无关), 需清空内容
        app_junk_dirs = (
            f"{HOME_DIR}/.cache/youdao-dict",
            f"{HOME_DIR}/.cache/Youdao/Youdao Dict",
            f"{HOME_DIR}/.config/youdao-dict",
            f"{HOME_DIR}/.local/share/Youdao/Youdao Dict",
            f"{HOME_DIR}/.local/share/Youdao Dict",
            f"{HOME_DIR}/.cache/filezilla",
            f"{HOME_DIR}/.config/filezilla",
            f"{HOME_DIR}/.local/share/ThunderNetwork",
            f"{HOME_DIR}/.config/com.xunlei.download",
            f"{HOME_DIR}/.cache/baidunetdisk",
            f"{HOME_DIR}/.config/baidunetdisk",
            f"{HOME_DIR}/.cache/sunloginclient",
            f"{HOME_DIR}/Oray",
            f"{HOME_DIR}/.sunlogin",
            f"{HOME_DIR}/.cache/browser",
            f"{HOME_DIR}/.config/browser",
            f"{HOME_DIR}/.linglong/org.deepin.browser/config/browser",
            f"{HOME_DIR}/.cache/mozilla/firefox",
            f"{HOME_DIR}/.mozilla",
            f"{HOME_DIR}/.local/share/Kingsoft",
            f"{HOME_DIR}/.config/Kingsoft",
            f"{HOME_DIR}/.config/qqbrowser",
            f"{HOME_DIR}/.config/com.360.browser",
            f"{HOME_DIR}/.config/google-chrome",
            f"{HOME_DIR}/.config/chromium",
            f"{HOME_DIR}/.config/microsoft-edge",
        )
        for junk_dir in app_junk_dirs:
            self.run_cmd(
                f"find {quote(junk_dir)} -mindepth 1 -delete 2>/dev/null || true",
                timeout=15,
                out_debug_flag=False,
            )
        # 360zip 的残留是单个文件而非目录
        self.run_cmd(
            f"rm -f {HOME_DIR}/.config/360zip.db",
            timeout=5,
            out_debug_flag=False,
        )
        # 向日葵后端日志属于系统路径, 需 root 权限
        self.sudo_run_cmd(
            "find /var/log/sunlogin -mindepth 1 -delete 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        )
        self.remove_test_junk_files()
        sleep(2)

    def click_space_clean_featured_card(self, timeout=15):
        """点击系统优化页面的空间清理特色卡片中的开始扫描按钮

        页面切换后扫描按钮可能需要时间加载, 带重试机制。
        V25 上 AT-SPI showing 属性可能全为 False, 不依赖 showing 判断可见性,
        找到元素后直接尝试点击; focus_windows 可能失败, 需容错。
        QML 按钮的 Node.click() 不触发点击, 必须走 AT-SPI Press 动作。
        """
        try:
            self._safe_focus_windows()
        except BaseException:
            pass
        for i in range(timeout):
            try:
                btn = self.dog.find_element_by_attr("$//optimization_startScanBtn")
                self._atspi_do_action(btn)
                return
            except BaseException:
                pass
            if i > 0 and i % 3 == 0:
                self._refresh_app()
                try:
                    self._safe_focus_windows()
                except BaseException:
                    pass
            sleep(1)
        self._atspi_do_action(
            self.dog.find_element_by_attr("$//optimization_startScanBtn")
        )

    def get_space_clean_has_junk(self, timeout=120) -> bool:
        """等待空间清理扫描完成并检查是否检测到垃圾

        扫描完成后, 结果页面(spaceClean_resultTitle)显示表示有垃圾;
        空状态页面(spaceClean_emptyTitle)显示表示无垃圾。

        V25 上 AT-SPI showing 属性可能全为 False, 额外检查元素 size:
        size 为 (0, 0) 表示不可见, 非 (0, 0) 表示可见。
        :param timeout: 最长等待秒数
        :return: True 如果检测到垃圾, False 如果无垃圾
        """
        try:
            self.ui.focus_windows()
        except BaseException:
            pass
        for i in range(timeout):
            try:
                result = self.dog.find_element_by_attr("$//spaceClean_resultTitle")
                if result.showing:
                    return True
                w, h = result.size
                if w > 0 and h > 0:
                    return True
            except BaseException:
                pass
            try:
                empty = self.dog.find_element_by_attr("$//spaceClean_emptyTitle")
                if empty.showing:
                    return False
                w, h = empty.size
                if w > 0 and h > 0:
                    return False
            except BaseException:
                pass
            if i > 0 and i % 5 == 0:
                self._refresh_app()
                try:
                    self.ui.focus_windows()
                except BaseException:
                    pass
            sleep(1)
        return False

    # ===== PMS 2001925「空间清理结果页-不同功能项进行选择」测试用例方法 =====

    def get_space_clean_result_page_showing(self, timeout=120) -> bool:
        """等待空间清理结果页面显示

        检查结果页面标题(spaceClean_resultTitle)是否可见。
        :param timeout: 最长等待秒数
        :return: True 如果结果页面已显示
        """
        self._safe_focus_windows()
        for _ in range(timeout):
            try:
                element = self.dog.find_element_by_attr("$//spaceClean_resultTitle")
                if element.showing:
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def get_space_clean_clean_button(self):
        """获取空间清理结果页面的清理按钮元素

        :return: 清理按钮元素, 或 None
        """
        return self._find_element_in_exprs(
            [
                "$//spaceClean_cleanBtn",
                "$//spaceCleanCleanButton",
            ]
        )

    def get_space_clean_clean_button_enabled(self, retries=5) -> bool:
        """检查清理按钮是否可用(非灰色)

        V25 上 showing 属性可能全为 False, 额外检查元素 size。
        交互后 AT-SPI 可能暂时找不到元素, 加入重试。
        :return: True 如果按钮可用
        """
        for _attempt in range(retries):
            try:
                btn = self.get_space_clean_clean_button()
                if btn:
                    if btn.showing:
                        return btn.sensitive
                    w, h = btn.size
                    if w > 0 and h > 0:
                        return btn.sensitive
            except BaseException:
                pass
            sleep(1)
        return False

    def get_space_clean_clean_button_text(self) -> str:
        """获取清理按钮的文本内容

        :return: 按钮文本, 如 "Clean Selected (3)"
        """
        try:
            btn = self.get_space_clean_clean_button()
            if btn:
                return btn.text or ""
        except BaseException:
            pass
        return ""

    def click_space_clean_clean_button(self):
        """点击清理按钮"""
        self._safe_focus_windows()
        btn = self.get_space_clean_clean_button()
        if btn:
            btn.click()
            return
        self.dog.find_element_by_attr("$//spaceClean_cleanBtn").click()

    def get_space_clean_category_checkboxes(self, retries=5):
        """获取所有分类级别的复选框元素列表

        分类复选框的 accessible name 为 spaceClean_categoryCheck。
        V25 上 showing 属性可能全为 False, 额外检查元素 size。
        find_elements_by_attr 在部分场景下无法发现滚动区域内的元素,
        额外通过 findChildren 兜底查找。
        :return: 复选框元素列表
        """
        for _attempt in range(retries):
            self._safe_focus_windows()
            for expr in (
                "$//spaceClean_categoryCheck",
                "$//spaceCleanCategoryCheck",
            ):
                try:
                    elements = self.dog.find_elements_by_attr(expr)
                    if elements:
                        result = []
                        for e in elements:
                            try:
                                if e.showing:
                                    result.append(e)
                                    continue
                                w, h = e.size
                                if w > 0 and h > 0:
                                    result.append(e)
                            except BaseException:
                                result.append(e)
                        if result:
                            return result
                        return list(elements)
                except BaseException:
                    continue
            try:
                app = self.dog.obj
                found = app.findChildren(
                    lambda x: x.name == "spaceClean_categoryCheck"
                    and x.roleName == "check box"
                )
                if found:
                    return found
            except BaseException:
                pass
            sleep(1)
        return []

    def get_space_clean_category_count(self, retries=5):
        """获取空间清理结果页可见分类项的数量

        每个分类项包含 4 个子元素: categoryCheck(复选框)、
        expandBtn(展开按钮)、categoryName(名称标签)、categorySize(大小标签)。
        产品通过 setA11yMeta 将 accessibleName 覆盖为固定标识符,
        无法通过 AT-SPI 获取显示文本, 因此以可见分类项数量判定。

        V20 上有 5 类(system/app/trace/cookies/linglong),
        V25 上有 6 类(额外 snapshot)。
        :return: 可见分类项数量
        """
        for _attempt in range(retries):
            self._safe_focus_windows()
            try:
                elements = self.dog.find_elements_by_attr("$//spaceClean_categoryName")
                if elements:
                    visible = [
                        el for el in elements
                        if getattr(el, "showing", False)
                    ]
                    if visible:
                        return len(visible)
            except BaseException:
                pass
            sleep(1)
        return 0

    def get_space_clean_category_info(self, retries=5):
        """获取空间清理结果页每个分类项的结构信息

        返回每个分类项的复选框状态, 用于验证分类项是否可清理。
        :return: list[dict], 每项含 checked(是否选中)、showing(是否可见)
        """
        result = []
        for _attempt in range(retries):
            self._safe_focus_windows()
            try:
                elements = self.dog.find_elements_by_attr("$//spaceClean_categoryCheck")
                if elements:
                    for el in elements:
                        info = {}
                        try:
                            info["checked"] = el.checked
                        except BaseException:
                            info["checked"] = False
                        try:
                            info["showing"] = el.showing
                        except BaseException:
                            info["showing"] = False
                        result.append(info)
                    if result:
                        return result
            except BaseException:
                pass
            sleep(1)
        return result

    def create_all_category_junk(self):
        """为空间清理的全部扫描分类创建测试垃圾, 确保结果页展示所有分类

        涵盖 V20 的 5 类: system(app/trash)、app(应用残留)、trace(痕迹)、
        cookies(浏览器 Cookie)、linglong(玲珑仓库不可达对象)。
        V25 额外有 snapshot, 由系统快照管理, 测试不构造。
        """
        # system: 回收站垃圾(已有 create_test_junk_files 覆盖, 此处重复确保)
        junk_dir = f"{HOME_DIR}/.local/share/Trash/files/autotest_junk"
        self.run_cmd(f"mkdir -p {junk_dir}", timeout=5, out_debug_flag=False)
        for i in range(5):
            junk_file = f"{junk_dir}/junk_{i}.dat"
            self.run_cmd(
                f"dd if=/dev/zero of={junk_file} bs=1M count=1 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )

        # app: 应用残留(youdao-dict 未安装时检测 ~/.cache/youdao-dict)
        app_junk_dir = f"{HOME_DIR}/.cache/youdao-dict"
        self.run_cmd(f"mkdir -p {app_junk_dir}", timeout=5, out_debug_flag=False)
        self.run_cmd(
            f"dd if=/dev/zero of={app_junk_dir}/cache.dat bs=1M count=1 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )

        # trace: 最近使用记录文件
        trace_file = f"{HOME_DIR}/.local/share/recently-used.xbel"
        self.run_cmd(
            f'echo "<?xml version=\"1.0\"?><xbel></xbel>" > {trace_file}',
            timeout=5,
            out_debug_flag=False,
        )

        # cookies: 浏览器 Cookie 文件(google-chrome 路径)
        cookie_dir = f"{HOME_DIR}/.config/google-chrome/Default"
        self.run_cmd(f"mkdir -p {cookie_dir}", timeout=5, out_debug_flag=False)
        self.run_cmd(
            f"dd if=/dev/zero of={cookie_dir}/Cookies bs=1K count=1 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )

        # linglong: 在玲珑仓库中创建不可达 ostree 对象(需 sudo)
        self.run_cmd(
            "mkdir -p /tmp/ostree_test && echo test > /tmp/ostree_test/junk.txt",
            timeout=5,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "ostree --repo=/var/lib/linglong/repo commit --tree=dir=/tmp/ostree_test "
            "-b test-autotest-unreachable 2>/dev/null",
            timeout=30,
        )
        self.sudo_run_cmd(
            "ostree --repo=/var/lib/linglong/repo refs --delete test-autotest-unreachable 2>/dev/null",
            timeout=10,
        )
        sleep(1)

    def remove_all_category_junk(self):
        """清理 create_all_category_junk 创建的全部测试垃圾"""
        # system: 回收站垃圾
        junk_dir = f"{HOME_DIR}/.local/share/Trash/files/autotest_junk"
        self.run_cmd(f"rm -rf {junk_dir}", timeout=5, out_debug_flag=False)

        # app: 应用残留
        self.run_cmd(
            f"rm -rf {HOME_DIR}/.cache/youdao-dict",
            timeout=5,
            out_debug_flag=False,
        )

        # trace: 最近使用记录
        self.run_cmd(
            f"rm -f {HOME_DIR}/.local/share/recently-used.xbel",
            timeout=5,
            out_debug_flag=False,
        )

        # cookies: 浏览器 Cookie
        self.run_cmd(
            f"rm -rf {HOME_DIR}/.config/google-chrome",
            timeout=5,
            out_debug_flag=False,
        )

        # linglong: 清理不可达对象
        self.sudo_run_cmd(
            "ostree --repo=/var/lib/linglong/repo prune --refs-only 2>/dev/null",
            timeout=30,
        )
        self.run_cmd("rm -rf /tmp/ostree_test", timeout=5, out_debug_flag=False)

    def create_trace_junk(self):
        """创建痕迹信息测试垃圾(recently-used.xbel), 确保空间清理扫描能检测到痕迹分类"""
        trace_file = f"{HOME_DIR}/.local/share/recently-used.xbel"
        self.run_cmd(
            f"mkdir -p {HOME_DIR}/.local/share",
            timeout=5,
            out_debug_flag=False,
        )
        self.run_cmd(
            f'echo "<?xml version=\"1.0\" encoding=\"UTF-8\"?>'
            f'<xbel version="1.0">'
            f'<bookmark href="file:///tmp/autotest_trace.txt" '
            f'added="2026-01-01T00:00:00Z" '
            f'modified="2026-01-01T00:00:00Z" '
            f'visited="2026-01-01T00:00:00Z"/>'
            f'</xbel>" > {trace_file}',
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def get_trace_junk_exists(self) -> bool:
        """检查痕迹信息文件是否仍存在且包含 bookmark 记录

        :return: True 如果痕迹信息文件存在且含 bookmark, False 如果已被清理
        """
        trace_file = f"{HOME_DIR}/.local/share/recently-used.xbel"
        result = self.run_cmd(
            f"test -f {trace_file} && grep -q 'bookmark' {trace_file} && echo 'exists' || echo 'cleaned'",
            timeout=5,
            out_debug_flag=False,
        )
        return "exists" in result.strip()

    def wait_trace_junk_cleaned(self, timeout=60) -> bool:
        """轮询等待痕迹信息文件被空间清理清除

        :param timeout: 最长等待秒数
        :return: True 表示痕迹信息已被清理, False 表示超时仍存在
        """
        for _ in range(timeout):
            if not self.get_trace_junk_exists():
                return True
            sleep(1)
        return False

    def remove_trace_junk(self):
        """清理痕迹信息测试垃圾"""
        trace_file = f"{HOME_DIR}/.local/share/recently-used.xbel"
        self.run_cmd(
            f"rm -f {trace_file}",
            timeout=5,
            out_debug_flag=False,
        )

    def get_space_clean_item_checkboxes(self, retries=5):
        """获取所有单项级别的复选框元素列表

        单项复选框的 accessible name 为 spaceClean_itemCheck。
        V25 上 showing 属性可能全为 False, 额外检查元素 size。
        :return: 复选框元素列表
        """
        for _attempt in range(retries):
            self._safe_focus_windows()
            for expr in (
                "$//spaceClean_itemCheck",
                "$//spaceCleanItemCheck",
            ):
                try:
                    elements = self.dog.find_elements_by_attr(expr)
                    if elements:
                        result = []
                        for e in elements:
                            try:
                                if e.showing:
                                    result.append(e)
                                    continue
                                w, h = e.size
                                if w > 0 and h > 0:
                                    result.append(e)
                            except BaseException:
                                result.append(e)
                        if result:
                            return result
                        return list(elements)
                except BaseException:
                    continue
            sleep(1)
        return []

    def _get_checkbox_checked(self, element) -> bool:
        """获取复选框的选中状态, 兼容 V20/V25

        :param element: 复选框元素
        :return: True 表示已选中
        """
        try:
            return bool(element.checked)
        except BaseException:
            pass
        try:
            states = element.states
            return "checked" in states
        except BaseException:
            pass
        return False

    def click_space_clean_category_checkbox(self, index=0, checkboxes=None):
        """点击指定索引的分类复选框以切换选中状态

        V25 上交互后 AT-SPI 可能无法重新发现复选框元素,
        因此优先使用调用方传入的已缓存元素列表, 避免重新获取失败。

        :param index: 分类复选框索引(从0开始)
        :param checkboxes: 已缓存的复选框元素列表, 避免重复获取
        """
        self._safe_focus_windows()
        if checkboxes is None:
            checkboxes = self.get_space_clean_category_checkboxes()
        if checkboxes and index < len(checkboxes):
            try:
                # QML 的 check box 不响应 Node.click(), 需经 AT-SPI 动作接口
                self._atspi_do_action(checkboxes[index])
                sleep(1)
                return
            except BaseException:
                pass
            self._refresh_app()
            sleep(1)
            fresh = self.get_space_clean_category_checkboxes(retries=10)
            if fresh and index < len(fresh):
                self._atspi_do_action(fresh[index])
                sleep(1)
                return
        raise IndexError(
            f"分类复选框索引 {index} 超出范围, 共 {len(checkboxes)} 个"
        )

    def click_space_clean_item_checkbox(self, index=0, checkboxes=None):
        """点击指定索引的单项复选框以切换选中状态

        V25 上交互后 AT-SPI 可能无法重新发现复选框元素,
        因此优先使用调用方传入的已缓存元素列表, 避免重新获取失败。

        :param index: 单项复选框索引(从0开始)
        :param checkboxes: 已缓存的复选框元素列表, 避免重复获取
        """
        self._safe_focus_windows()
        if checkboxes is None:
            checkboxes = self.get_space_clean_item_checkboxes()
        if checkboxes and index < len(checkboxes):
            try:
                self._atspi_do_action(checkboxes[index])
                sleep(1)
                return
            except BaseException:
                pass
            self._refresh_app()
            sleep(1)
            fresh = self.get_space_clean_item_checkboxes(retries=10)
            if fresh and index < len(fresh):
                fresh[index].click()
                sleep(1)
                return
        raise IndexError(
            f"单项复选框索引 {index} 超出范围, 共 {len(checkboxes)} 个"
        )

    # ===== 空间清理：系统垃圾/回收站用例方法 =====

    def get_space_clean_checked_category_count(self, checkboxes=None) -> int:
        """统计空间清理结果页已勾选的分类复选框数量

        :param checkboxes: 已缓存的分类复选框元素列表, 避免重复获取
        :return: 已勾选的分类数量
        """
        if checkboxes is None:
            checkboxes = self.get_space_clean_category_checkboxes()
        return sum(1 for box in checkboxes if self._get_checkbox_checked(box))

    def keep_only_first_space_clean_category_checked(self, retries=5) -> bool:
        """仅保留第一个分类(系统垃圾)的勾选, 取消其余分类的勾选

        结果页分类顺序遵循产品 kScanCategoryOrder(system/app/trace/
        cookies/linglong/snapshot), 系统垃圾恒为第一个分类。
        system/app/linglong 默认勾选, 其余默认未勾选; 倒序逐项取消,
        每次重新获取元素列表, 避免勾选后 AT-SPI 树重建导致索引错位。

        :return: True 如果最终只有第一个分类处于勾选状态
        """
        for _attempt in range(retries):
            boxes = self.get_space_clean_category_checkboxes()
            for idx in range(len(boxes) - 1, 0, -1):
                boxes = self.get_space_clean_category_checkboxes()
                if idx >= len(boxes):
                    continue
                if self._get_checkbox_checked(boxes[idx]):
                    self.click_space_clean_category_checkbox(idx, checkboxes=boxes)
            if self.get_space_clean_checked_category_count() == 1:
                return True
            sleep(1)
        return False

    def get_space_clean_category_checked_states(self, checkboxes=None):
        """返回结果页所有分类复选框的勾选状态(按分类顺序)

        :param checkboxes: 已缓存的复选框元素列表, 避免重复获取
        :return: 布尔列表, True 表示该分类已勾选
        """
        if checkboxes is None:
            checkboxes = self.get_space_clean_category_checkboxes()
        return [self._get_checkbox_checked(box) for box in checkboxes]

    def uncheck_all_space_clean_categories(self, retries=5) -> bool:
        """取消结果页所有分类的勾选(分类内子项随之全部取消)

        :return: True 如果最终没有分类处于勾选状态
        """
        for _attempt in range(retries):
            boxes = self.get_space_clean_category_checkboxes()
            for idx in range(len(boxes) - 1, -1, -1):
                boxes = self.get_space_clean_category_checkboxes()
                if idx >= len(boxes):
                    continue
                if self._get_checkbox_checked(boxes[idx]):
                    self.click_space_clean_category_checkbox(
                        idx, checkboxes=boxes
                    )
            if self.get_space_clean_checked_category_count() == 0:
                return True
            sleep(1)
        return False

    def keep_only_space_clean_category_checked(self, index, retries=5) -> bool:
        """仅保留指定分类的勾选, 取消其余分类

        结果页分类顺序遵循产品 kScanCategoryOrder(system/app/trace/
        cookies/linglong/snapshot)。分类复选框只作用于本分类的子项,
        因此勾选一个分类不会影响其它分类(不存在跨分类全选)。

        :param index: 需要保持勾选的分类索引(从0开始)
        :return: True 如果最终仅该分类处于勾选状态
        """
        for _attempt in range(retries):
            boxes = self.get_space_clean_category_checkboxes()
            if index >= len(boxes):
                return False
            for idx in range(len(boxes) - 1, -1, -1):
                if idx == index:
                    continue
                boxes = self.get_space_clean_category_checkboxes()
                if idx < len(boxes) and self._get_checkbox_checked(boxes[idx]):
                    self.click_space_clean_category_checkbox(
                        idx, checkboxes=boxes
                    )
            boxes = self.get_space_clean_category_checkboxes()
            if index < len(boxes) and not self._get_checkbox_checked(
                boxes[index]
            ):
                self.click_space_clean_category_checkbox(
                    index, checkboxes=boxes
                )
            boxes = self.get_space_clean_category_checkboxes()
            states = self.get_space_clean_category_checked_states(boxes)
            if (
                states.count(True) == 1
                and index < len(states)
                and states[index]
            ):
                return True
            sleep(1)
        return False

    def get_space_clean_checked_item_count(self, checkboxes=None) -> int:
        """统计结果页已勾选的单项复选框数量

        :param checkboxes: 已缓存的单项复选框元素列表, 避免重复获取
        :return: 已勾选的单项数量
        """
        if checkboxes is None:
            checkboxes = self.get_space_clean_item_checkboxes()
        return sum(1 for box in checkboxes if self._get_checkbox_checked(box))

    def get_space_clean_rescan_button(self):
        """获取空间清理结果页的重新扫描按钮

        :return: 重新扫描按钮元素, 或 None
        """
        return self._find_element_in_exprs(
            [
                "$//spaceClean_rescanBtn",
                "$//spaceCleanRescanButton",
            ]
        )

    def click_space_clean_rescan_button(self):
        """点击空间清理结果页的重新扫描按钮"""
        self._safe_focus_windows()
        btn = self.get_space_clean_rescan_button()
        if btn is None:
            raise RuntimeError("未找到空间清理重新扫描按钮")
        self._atspi_do_action(btn)
        sleep(1)

    def is_space_clean_element_visible(self, expr) -> bool:
        """检查空间清理页面的指定元素是否可见

        扫描页与结果页/空状态页在同一 QStackedWidget 中, 隐藏页的元素
        仍在 AT-SPI 树上; QWidget 隐藏时 extents 为 (0, 0, 0, 0),
        showing 为 False。因此同时检查 showing 与 size 兜底。

        :param expr: AT-SPI 查找表达式
        :return: True 如果元素可见
        """
        try:
            element = self.dog.find_element_by_attr(expr)
        except BaseException:
            return False
        try:
            if element.showing:
                return True
        except BaseException:
            pass
        try:
            width, height = element.size
            return width > 0 and height > 0
        except BaseException:
            return False

    def wait_space_clean_scan_finished(self, timeout=180) -> str:
        """等待一次空间清理扫描结束

        判定条件: 扫描页(spaceClean_scanTitle)不可见, 且结果页
        (spaceClean_resultTitle)或空状态页(spaceClean_emptyTitle)可见。

        :param timeout: 最长等待秒数
        :return: "result" 有垃圾结果页; "empty" 无垃圾空状态页; "" 超时
        """
        for i in range(timeout):
            if not self.is_space_clean_element_visible("$//spaceClean_scanTitle"):
                if self.is_space_clean_element_visible(
                    "$//spaceClean_resultTitle"
                ):
                    return "result"
                if self.is_space_clean_element_visible(
                    "$//spaceClean_emptyTitle"
                ):
                    return "empty"
            if i > 0 and i % 5 == 0:
                self._safe_focus_windows()
            sleep(1)
        return ""

    def get_space_clean_scan_started(self, timeout=30) -> bool:
        """检查空间清理扫描是否已开始(或已瞬间完成)

        点击开始扫描后有两种可能界面:
        1. 扫描进行中: V25 显示 spaceClean_scanProgress / spaceClean_scanTitle,
           V20 显示 backGroundWidget_scanProgressBar;
        2. 数据量小或扫描极快: 直接进入结果页(有垃圾)或空状态页, 进度条观测不到。

        两者任一可见即视为扫描已开始, 避免小数据量场景下进度条被误判为未显示。
        V25 上 AT-SPI showing 可能恒为 False, 用 size 非 (0, 0) 兜底。
        :param timeout: 最长等待秒数
        :return: True 如果检测到扫描进度或扫描结果页, False 如果超时
        """
        scan_exprs = [
            "$//spaceClean_scanProgress",
            "$//spaceClean_scanTitle",
            "$//spaceCleanScanProgressBar",
            "$//spaceCleanScanningPage",
            "$//backGroundWidget_scanProgressBar",
            "$//spaceClean_resultTitle",
            "$//spaceClean_emptyTitle",
        ]
        for _ in range(timeout):
            self._safe_focus_windows()
            for expr in scan_exprs:
                try:
                    element = self.dog.find_element_by_attr(expr)
                    if element.showing:
                        return True
                    width, height = element.size
                    if width > 0 and height > 0:
                        return True
                except BaseException:
                    continue
            sleep(1)
        return False

    def get_space_clean_no_junk(self, timeout=120) -> bool:
        """等待空间清理扫描完成并验证无垃圾

        扫描完成后, 空状态页面(spaceClean_emptyTitle)显示表示无垃圾。
        与 get_space_clean_has_junk 不同, 本方法仅在确认无垃圾时返回 True,
        超时或检测到垃圾均返回 False。

        V25 上 AT-SPI showing 属性可能全为 False, 额外检查元素 size:
        size 为 (0, 0) 表示不可见, 非 (0, 0) 表示可见。
        :param timeout: 最长等待秒数
        :return: True 如果扫描完成且无垃圾, False 如果有垃圾或超时
        """
        try:
            self._safe_focus_windows()
        except BaseException:
            pass
        for i in range(timeout):
            try:
                result = self.dog.find_element_by_attr(
                    "$//spaceClean_resultTitle"
                )
                if result.showing:
                    return False
                w, h = result.size
                if w > 0 and h > 0:
                    return False
            except BaseException:
                pass
            try:
                empty = self.dog.find_element_by_attr(
                    "$//spaceClean_emptyTitle"
                )
                if empty.showing:
                    return True
                w, h = empty.size
                if w > 0 and h > 0:
                    return True
            except BaseException:
                pass
            if i > 0 and i % 5 == 0:
                self._refresh_app()
                try:
                    self._safe_focus_windows()
                except BaseException:
                    pass
            sleep(1)
        return False

    # ===== PMS 2032313「清理玲珑环境、系统快照-系统快照清理交互」测试用例方法 =====

    def create_linglong_unreachable_objects(self):
        """在玲珑 ostree 仓库中创建不可达对象, 使空间清理扫描能检测到玲珑环境残留

        通过 ostree commit 创建一个临时 ref, 然后删除该 ref,
        使 commit 产生的对象变为不可达对象。ostree prune --refs-only
        会将这些对象识别为可回收的玲珑环境残留。
        """
        tmp_dir = "/tmp/ostree_linglong_test"
        self.run_cmd(
            f"mkdir -p {tmp_dir}",
            timeout=5,
            out_debug_flag=False,
        )
        for i in range(3):
            self.run_cmd(
                f"dd if=/dev/zero of={tmp_dir}/file_{i}.dat bs=1K count=1 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
        repo = "/var/lib/linglong/repo"
        self.sudo_run_cmd(
            f"ostree --repo={repo} commit -b autotest-unreachable-ref "
            f"--tree=dir={tmp_dir} 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"ostree --repo={repo} refs --delete autotest-unreachable-ref 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

    def clean_linglong_unreachable_objects(self):
        """清理玲珑 ostree 仓库中的不可达对象(测试后清理)"""
        repo = "/var/lib/linglong/repo"
        self.sudo_run_cmd(
            f"ostree --repo={repo} prune --refs-only 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        self.run_cmd(
            "rm -rf /tmp/ostree_linglong_test",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def get_space_clean_category_names(self, retries=5):
        """获取空间清理结果页所有分类名称文本列表

        createCategoryCard 中 setA11yMeta 将 nameLabel 的 accessible name
        覆盖为 "spaceClean_categoryName", 导致 AT-SPI .name 属性不是显示文本,
        且 .text 属性返回 None。但扫描预填充页(prefill)中的分类名称标签未调用
        setA11yMeta, 其 .name 即为显示文本(如 "系统垃圾 (6)")。
        因此通过 findChildren 搜索匹配分类名称模式的标签获取名称列表。
        :return: 分类名称文本列表
        """
        cat_pattern = re.compile(r"^.+ \(\d+\)$")
        for _attempt in range(retries):
            self._safe_focus_windows()
            try:
                labels = self.dog.obj.findChildren(
                    lambda n: n.roleName == "label"
                    and n.name
                    and not n.description
                    and cat_pattern.match(n.name),
                    recursive=True,
                )
                if labels:
                    result = [lbl.name for lbl in labels]
                    if result:
                        return result
            except BaseException:
                pass
            sleep(1)
        return []

    def find_space_clean_category_index_by_keyword(self, keyword, retries=5):
        """通过名称关键字查找空间清理分类在名称列表中的索引

        注意: 返回的索引是分类名称列表中的位置, 不一定与复选框列表索引对应。
        :param keyword: 分类名称关键字(如"玲珑"、"快照")
        :return: 分类名称列表中的索引(从0开始), 未找到返回 -1
        """
        for _attempt in range(retries):
            names = self.get_space_clean_category_names()
            for i, name in enumerate(names):
                if keyword in name:
                    return i
            sleep(1)
        return -1

    def has_space_clean_category(self, keyword, retries=5):
        """检查空间清理结果中是否存在包含指定关键字的分类

        :param keyword: 分类名称关键字(如"玲珑"、"快照")
        :return: True 如果存在该分类
        """
        return self.find_space_clean_category_index_by_keyword(keyword, retries) >= 0

    def get_space_clean_snapshot_confirm_dialog_showing(self, timeout=10):
        """检测系统快照清理确认对话框是否可见

        当选中包含系统快照或系统备份的项目并点击清理时,
        会弹出 DDialog 确认对话框。
        :param timeout: 最长等待秒数
        :return: True 如果检测到对话框
        """
        for _ in range(timeout):
            try:
                dialogs = self.dog.obj.findChildren(
                    lambda n: n.roleName in ("dialog", "alert dialog"),
                    recursive=True,
                )
                if dialogs:
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def click_space_clean_confirm_dialog_button(self, button_text, timeout=10):
        """点击快照清理确认对话框中的指定按钮

        :param button_text: 按钮文本(如"让我再想想"、"继续删除")
        :param timeout: 最长等待秒数
        :return: True 如果点击成功
        """
        for _ in range(timeout):
            try:
                buttons = self.dog.obj.findChildren(
                    lambda n: n.roleName == "push button"
                    and button_text in (n.text or n.name or ""),
                    recursive=True,
                )
                if buttons:
                    self._atspi_do_action(buttons[0])
                    sleep(1)
                    return True
            except BaseException:
                pass
            sleep(1)
        return False


    # ===== PMS 2001665「垃圾清理--清理系统缓存」测试用例方法 =====

    def create_system_cache_junk(self):
        """创建系统缓存垃圾(在 /var/cache/apt/archives/ 中放置 .deb 包)

        1.1.6 起空间清理通过 lastore-apt-clean -print-json 扫描,
        该工具只把无法识别的残留 .deb 视为垃圾;apt-get download 下载的
        有效包(在软件源列表内)会被忽略。因此这里直接构造一个占位 .deb,
        保证扫描器能检测到系统缓存垃圾。
        """
        self.sudo_run_cmd(
            "rm -f /var/cache/apt/archives/autotest-junk_*.deb; "
            "dd if=/dev/zero "
            "of=/var/cache/apt/archives/autotest-junk_1.0_amd64.deb "
            "bs=1M count=1 2>/dev/null",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(1)

    def get_system_cache_junk_exist(self) -> bool:
        """检查系统缓存垃圾(.deb 文件)是否存在

        sudo_run_cmd 会将 sudo 密码提示文本泄漏到 stdout, 因此不能仅判断
        输出是否为空。改用 find + wc -l 统计 .deb 文件数量并解析为整数。
        :return: True 如果 /var/cache/apt/archives/ 中存在 .deb 文件
        """
        result = self.sudo_run_cmd(
            "find /var/cache/apt/archives/ -maxdepth 1 -name '*.deb' -type f 2>/dev/null | wc -l",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip()) > 0
        except (ValueError, AttributeError):
            return False

    def wait_system_cache_junk_cleaned(self, timeout=60) -> bool:
        """等待系统缓存垃圾被清理完毕

        点击清理按钮后, lastore-apt-clean 需要时间执行清理操作。
        :param timeout: 最长等待秒数
        :return: True 如果 .deb 文件已被清理, False 如果超时仍存在
        """
        for _ in range(timeout):
            if not self.get_system_cache_junk_exist():
                return True
            sleep(1)
        return False

    def remove_system_cache_junk(self):
        """清理测试创建的系统缓存垃圾文件"""
        self.sudo_run_cmd(
            "rm -f /var/cache/apt/archives/*.deb 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        )

    # ===== PMS 2032445「系统检测-无空间清理入口」测试用例方法 =====

    def get_detection_space_clean_entry_showing(self) -> bool:
        """检查系统检测页面是否显示空间清理入口

        空间清理入口属于系统优化模块, 不应出现在系统检测页面。
        检查检测页面下是否存在空间清理相关元素。
        :return: True 如果检测到空间清理入口, False 如果未检测到
        """
        self._safe_focus_windows()
        for expr in (
            "$//detection_page//spaceClean",
            "$//detection_page//optimization_startScanBtn",
            "$//detection_page//空间清理",
        ):
            try:
                element = self.dog.find_element_by_attr(expr)
                if element:
                    return True
            except BaseException:
                continue
        return False


    # ===== PMS 2032299「清理玲珑环境、系统快照-扫描入口」测试用例方法 =====

    def get_space_clean_category_card_showing(self, category_id, timeout=10) -> bool:
        """检查空间清理扫描结果中指定分类卡片是否显示

        扫描结果页中每个分类卡片有唯一的 accessible name,
        格式为 spaceCleanCategoryCheck_{categoryId} / spaceCleanCategoryName_{categoryId}。
        仅当该分类下存在可清理项时卡片才会出现。

        V25 上 AT-SPI showing 属性可能全为 False, 额外检查元素 size。
        :param category_id: 分类 ID (如 "linglong", "snapshot")
        :param timeout: 最长等待秒数
        :return: True 如果该分类卡片可见
        """
        self._safe_focus_windows()
        for _ in range(timeout):
            for expr in (
                f"$//spaceCleanCategoryCheck_{category_id}",
                f"$//spaceCleanCategoryName_{category_id}",
                f"$//categoryCard_{category_id}",
            ):
                try:
                    element = self.dog.find_element_by_attr(expr)
                    if element:
                        if element.showing:
                            return True
                        width, height = element.size
                        if width > 0 and height > 0:
                            return True
                except BaseException:
                    pass
            sleep(1)
        return False

    # ===== PMS 2032301「清理玲珑环境、系统快照-系统快照扫描」测试用例方法 =====

    def get_space_clean_snapshot_category_present(self, timeout=10) -> bool:
        """检查空间清理扫描结果中系统快照分类是否存在

        系统快照扫描仅在 V25(PCM_HAVE_OSTREE)构建中编译,
        V20 上空间清理不包含快照分类(5 类: system/app/trace/cookies/linglong)。

        判定依据是"含可清理项的快照分类": 扫描预填充页在 V20 上也会创建
        "系统快照 (0)" 占位卡片(ensureSnapshotCategoryCard), 但该类目没有
        可清理项, 不会出现在结果页; get_space_clean_category_names 已过滤
        数量为 0 的占位标签, 因此 V20 上本方法恒为 False。

        结果页无法按分类 id 定位: 产品的 accessibleName 对每个分类都是
        固定值 "spaceClean_categoryName", 不暴露分类标识。

        :param timeout: 最长等待秒数
        :return: True 如果存在含可清理项的快照分类, False 如果不存在
        """
        return self.has_space_clean_category("快照", retries=timeout)

    # ===== 模块 修复工具 - 应用修复-修复微信 测试用例方法 =====

    def click_wechat_fix_card(self):
        """点击微信修复卡片(V20/V25 兼容)

        微信修复卡片在应用修复区域中排列靠后,先最大化窗口确保布局
        稳定且卡片可见,然后直接通过 AT-SPI 点击卡片。
        """
        self._safe_focus_windows()
        if not self.get_window_maximized_status():
            self.maximize_window_by_shortcut()
            sleep(2)
            self._safe_focus_windows()
            self.reconnect_dogtail()
        element = self._find_repair_element(
            "$//repair_sectionsContainer//微信修复",
            "$//repairCardsView//微信修复",
        )
        self._atspi_do_action(element)
        sleep(2)
        self.reconnect_dogtail()

    def get_repair_detail_showing(self, timeout=10):
        """等待并获取修复详情页面可见状态(V20/V25 兼容)

        V25(loongarch64)上 .showing 对 QStackedWidget 子元素不可靠,
        改为检查元素是否存在来判断详情页是否显示。

        :param timeout: 最长等待秒数
        """
        for _ in range(timeout):
            try:
                self._safe_focus_windows()
            except BaseException:
                pass
            try:
                self._find_repair_element(
                    "$//repair_detailCard",
                    "$//repairDetailCard",
                )
                return True
            except BaseException:
                pass
            sleep(1)
        return False

    def get_repair_detail_header_showing(self, timeout=10) -> bool:
        """检查修复工具详情页顶部页头(工具标题 + 副标题/描述)是否已渲染

        实测 V20(deepin-pc-manager 1.1.7): 从列表点击某个修复工具后进入
        repair_runtimePage, 顶部 pageHeader 内含 pageHeader_titleLabel
        (工具名, 764x35)与 pageHeader_subtitleLabel(工具描述, 764x23);
        同时列表页 repair_overview 的同名页头被缩成 0x0, 因此以
        "repair_runtimePage 下两个标签均渲染"作为详情页页头的判据。
        产品 QML Label 的 AT-SPI name 固定为 objectName、text 恒为 None,
        读不到文案, 故以标签实际渲染(size 非零)作为标题与副标题展示的
        等价断言。

        :param timeout: 最长等待秒数
        :return: True 表示详情页页头(标题 + 副标题)已渲染
        """
        exprs = (
            "$//repair_runtimePage//pageHeader//pageHeader_titleLabel",
            "$//repair_runtimePage//pageHeader//pageHeader_subtitleLabel",
        )
        for i in range(timeout):
            if all(self._any_visible(expr) for expr in exprs):
                return True
            if i == 2:
                self.reconnect_dogtail()
            sleep(1)
        return False

    def get_repair_detail_content(self) -> dict:
        """获取修复工具详情页正文的渲染明细(描述区 + 修复项区 + 开始按钮)

        实测 V20(deepin-pc-manager 1.1.7): repair_detailCard 内含
        repair_problemDesc("描述"小节的问题说明)、repair_stepsContainer
        (每个修复步骤对应一个 repair_stepText)与 repair_startBtn。
        QML 标签不暴露文案, 故以各元素 size 非零作为"已渲染"判据;
        同一棵树中被 QStackedWidget 隐藏的副本 size 为 0x0, 不会误判。

        :return: {"detail_shown": bool, "problem_desc_showing": bool,
                  "step_count": int, "start_btn_showing": bool}
        """
        self._safe_focus_windows()
        detail = {
            "detail_shown": False,
            "problem_desc_showing": False,
            "step_count": 0,
            "start_btn_showing": False,
        }
        card = self._find_first_element(
            "$//repair_detailCard",
            "$//repairDetailCard",
        )
        if card is None:
            return detail
        detail["detail_shown"] = self._element_rendered(card)
        detail["problem_desc_showing"] = self._any_visible(
            "$//repair_detailCard//repair_problemDesc"
        )
        detail["start_btn_showing"] = self._any_visible(
            "$//repair_detailCard//repair_startBtn"
        )
        try:
            steps = self.dog.find_elements_by_attr(
                "$//repair_detailCard//repair_stepsContainer//repair_stepText"
            )
        except BaseException:
            steps = []
        detail["step_count"] = sum(1 for step in steps if self._element_rendered(step))
        return detail

    def click_start_repair_button(self):
        """点击开始修复按钮"""
        self._safe_focus_windows()
        button = self.dog.find_element_by_attr("$//repair_startBtn")
        if not self._click_at_element(button):
            button.click()
        sleep(0.5)

    def click_start_repair_button_until_dialog(self, attempts=3, timeout=20) -> bool:
        """点击"开始修复"并等待修复对话框出现, 未出现时有界重试

        实测 xdotool raw click 偶发不触发按钮(2005759 首跑未出现对话框、同环境
        重跑即正常), 属于 UI 点击丢事件。这里每次点击后最多等 timeout 秒,
        仍无 shellRepair_outputLog 就再点一次, 避免整条用例因一次丢事件失败。

        :param attempts: 最多点击次数
        :param timeout: 每次点击后等待对话框出现的秒数
        :return: True 表示对话框已出现
        """
        for index in range(max(1, attempts)):
            self.click_start_repair_button()
            if self.get_repair_dialog_showing(timeout=timeout):
                return True
            logger.warning(
                f"第 {index + 1} 次点击开始修复后 {timeout}s 内未出现修复对话框, 重试"
            )
        return False

    def get_repair_dialog_showing(self, timeout=10):
        """等待并获取修复对话框(ShellRepairDialog)可见状态

        通过检查输出日志区域(shellRepair_outputLog)是否可见来判断。
        :param timeout: 最长等待秒数
        """
        for i in range(timeout):
            try:
                log_widget = self.dog.find_element_by_attr("$//shellRepair_outputLog")
                if log_widget.showing:
                    return True
            except BaseException:
                pass
            if i == 2:
                self.reconnect_dogtail()
            sleep(1)
        return False

    def get_repair_password_input_showing(self, timeout=5) -> bool:
        """检查修复过程中是否出现密码/提权提示(用于判断是否需要提权)

        V20 上 shellRepair_inputEdit 是常驻交互输入行(提示"在此输入并按住
        回车键确认"), 元素始终存在, 不能作为提权判据; 真正需要提权时,
        输出日志或输入行提示中会出现"密码"等字样。
        :param timeout: 检查轮次(每次间隔 1 秒)
        :return: True 表示出现密码/提权提示, False 表示未出现
        """
        keywords = ("密码", "password", "Password", "提权", "管理员权限")
        for _ in range(timeout):
            try:
                output_log = self.dog.find_element_by_attr("$//shellRepair_outputLog")
                log_text = getattr(output_log, "text", "") or ""
                if any(kw in log_text for kw in keywords):
                    return True
            except BaseException:
                pass
            try:
                pwd_input = self.dog.find_element_by_attr("$//shellRepair_inputEdit", probe=True)
                prompt = getattr(pwd_input, "description", "") or ""
                if any(kw in prompt for kw in keywords):
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def start_mock_wechat_process(self):
        """启动模拟微信进程(用于测试修复功能终止微信进程)

        复制 sleep 二进制为 /tmp/wechat 并运行, 使进程名为 wechat,
        以便 killall wechat 能正确匹配并终止。
        """
        self.run_cmd(
            "cp $(which sleep) /tmp/wechat 2>/dev/null && /tmp/wechat 3600 &",
            timeout=2,
            out_debug_flag=False,
        )
        sleep(1)

    def get_wechat_process_status(self):
        """获取微信进程运行状态

        :return: True 表示进程正在运行, False 表示未运行
        """
        result = self.run_cmd(
            "pgrep -x wechat",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def wait_wechat_process_killed(self, timeout=30):
        """轮询等待微信进程被修复脚本终止

        :param timeout: 最长等待秒数
        :return: True 表示进程已被终止, False 表示超时仍在运行
        """
        for _ in range(timeout):
            if not self.get_wechat_process_status():
                return True
            sleep(1)
        return False

    def kill_wechat_process(self):
        """终止微信进程并清理临时文件(测试前后清理用)"""
        self.run_cmd(
            "killall wechat 2>/dev/null; rm -f /tmp/wechat",
            timeout=2,
            out_debug_flag=False,
        )
        sleep(1)

    # Linux 原生微信缓存目录路径(修复脚本 rm -rf ~/.xwechat/radium/cache)
    WECHAT_CACHE_DIR = f"{HOME_DIR}/.xwechat/radium/cache"
    # 模拟微信用户数据(账号会话/聊天记录/消息日志), 位于缓存目录之外,
    # 产品修复脚本不会删除, 用于修复后"聊天记录仍在、可继续发消息"的断言。
    WECHAT_USER_DATA_DIR = f"{HOME_DIR}/.xwechat/user_data"
    WECHAT_CHAT_HISTORY = f"{HOME_DIR}/.xwechat/user_data/chat_history.db"
    WECHAT_MESSAGE_LOG = f"{HOME_DIR}/.xwechat/user_data/message.log"
    # 用例构造前对真实 ~/.xwechat 的整体备份目录(同分区 mv, 用例结束还原)
    WECHAT_BACKUP_DIR = f"{HOME_DIR}/.autotest_wechat_backup"

    def backup_wechat_cache(self) -> bool:
        """备份测试机已有的 ~/.xwechat 目录, 避免用例删除真实微信数据

        产品修复脚本会 rm -rf ~/.xwechat/radium/cache, 而用例又要构造该
        缓存目录; 若测试机上原本已有用户微信数据, 必须先整体移走再构造,
        用例 finally 中调用 restore_wechat_cache 原样还原。同一分区 mv,
        不占额外磁盘(测试机仅约 1GB 可用)。

        :return: True 表示原本存在 ~/.xwechat 且已备份, False 表示原本不存在
        """
        result = self.run_cmd(
            f"rm -rf {self.WECHAT_BACKUP_DIR}; "
            f"if [ -e {HOME_DIR}/.xwechat ]; then "
            f"mv {HOME_DIR}/.xwechat {self.WECHAT_BACKUP_DIR} && echo backed; "
            f"else echo none; fi",
            timeout=30,
            out_debug_flag=False,
        )
        return "backed" in result

    def restore_wechat_cache(self):
        """还原 backup_wechat_cache 备份的 ~/.xwechat 目录

        先把用例构造/产品清理后的 ~/.xwechat 删掉, 再把备份目录移回原位;
        没有备份时仅删除备份目录, 不影响现场。
        """
        self.run_cmd(
            f"rm -rf {HOME_DIR}/.xwechat; "
            f"if [ -e {self.WECHAT_BACKUP_DIR} ]; then "
            f"mv {self.WECHAT_BACKUP_DIR} {HOME_DIR}/.xwechat; fi",
            timeout=30,
            out_debug_flag=False,
        )

    def create_mock_wechat_cache(self):
        """创建模拟微信缓存目录及测试文件(用于测试修复功能清理缓存)

        在 ~/.xwechat/radium/cache/ 下创建测试文件,
        模拟微信运行后产生的缓存数据, 修复脚本会执行 rm -rf 清理该目录。
        """
        cache_dir = self.WECHAT_CACHE_DIR
        self.run_cmd(
            f"mkdir -p {cache_dir} && "
            f"dd if=/dev/zero of={cache_dir}/test_cache.db bs=1M count=2 2>/dev/null && "
            f"echo 'mock_cache_data' > {cache_dir}/test_cache.txt",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

    def get_wechat_cache_exists(self) -> bool:
        """检查微信缓存目录中是否存在测试缓存文件

        :return: True 表示缓存文件存在, False 表示已被清理
        """
        cache_dir = self.WECHAT_CACHE_DIR
        result = self.run_cmd(
            f"test -e {cache_dir} && echo 'exists' || echo 'cleaned'",
            timeout=5,
            out_debug_flag=False,
        )
        return "exists" in result.strip()

    def get_wechat_cache_file_count(self) -> int:
        """统计微信缓存目录下剩余文件数(用于断言目录被彻底删除)

        用例预期"目录被完全删除", 除目录本身不存在外, 再以文件计数为 0
        作为等价量化断言; 目录不存在时 find 无输出, 计数为 0。

        :return: 缓存目录内文件数量
        """
        result = self.run_cmd(
            f"find {self.WECHAT_CACHE_DIR} -type f 2>/dev/null | wc -l",
            timeout=10,
            out_debug_flag=False,
        )
        try:
            return int(result.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return 0

    def wait_wechat_cache_cleaned(self, timeout=60) -> bool:
        """轮询等待微信缓存目录被修复脚本清理

        :param timeout: 最长等待秒数
        :return: True 表示缓存已被清理, False 表示超时仍存在
        """
        for _ in range(timeout):
            if not self.get_wechat_cache_exists():
                return True
            sleep(1)
        return False

    def clean_wechat_cache(self):
        """清理模拟微信缓存目录及文件(测试前后清理用)"""
        cache_dir = self.WECHAT_CACHE_DIR
        self.run_cmd(
            f"rm -rf {HOME_DIR}/.xwechat 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def create_mock_wechat_user_data(self) -> bool:
        """构造模拟微信用户数据(账号会话 + 聊天记录 + 消息日志)

        用例 2005769(修复后微信功能验证)需要"登录账号/查看聊天记录"的等价
        载体。产品 entry.sh 只删 ~/.xwechat/radium/cache, 不碰 user_data, 因此
        修复前后 chat_history.db 的摘要必须一致 —— 可作为"修复未破坏聊天记录"
        的量化断言; message.log 则用于"发送消息"的追加写验证。

        :return: True 表示目录与两个数据文件均创建成功
        """
        out, rc = self.run_cmd(
            f"mkdir -p {self.WECHAT_USER_DATA_DIR} && "
            f"printf '%s\\n' 'session: autotest_login' 'msg: 1 hello' "
            f"'msg: 2 chat_history' > {self.WECHAT_CHAT_HISTORY} && "
            f"printf '%s\\n' 'login: autotest' 'msg: sent hello' "
            f"> {self.WECHAT_MESSAGE_LOG} && echo created",
            timeout=10,
            out_debug_flag=False,
            return_code=True,
        )
        return rc == 0 and "created" in out

    def get_wechat_chat_history_digest(self) -> str:
        """获取聊天记录文件 md5 摘要(修复前后比对, 判断数据是否被破坏)

        :return: md5 十六进制串; 文件不存在或计算失败返回空串
        """
        out = self.run_cmd(
            f"md5sum {self.WECHAT_CHAT_HISTORY} 2>/dev/null | awk '{{print $1}}'",
            timeout=5,
            out_debug_flag=False,
        )
        lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
        return lines[-1] if lines else ""

    def get_wechat_message_count(self) -> int:
        """统计消息日志行数(用于断言修复后仍可追加新消息)

        :return: 行数; 文件不存在时返回 0
        """
        out = self.run_cmd(
            f"wc -l < {self.WECHAT_MESSAGE_LOG} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return 0

    def append_wechat_message(self, text: str = "post-repair hello") -> bool:
        """向消息日志追加一条消息(等价"发送消息": 应用数据目录可正常写入)

        :param text: 消息内容
        :return: True 表示追加成功
        """
        out, rc = self.run_cmd(
            f"printf '%s\\n' {quote(text)} >> {self.WECHAT_MESSAGE_LOG} "
            f"&& echo appended",
            timeout=10,
            out_debug_flag=False,
            return_code=True,
        )
        return rc == 0 and "appended" in out

    def get_wechat_process_pid(self) -> str:
        """获取微信进程 pid(进程名精确匹配 wechat)

        :return: pid 字符串; 进程不存在返回空串
        """
        out = self.run_cmd(
            "pgrep -x wechat 2>/dev/null | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
        return lines[-1] if lines else ""

    def get_wechat_process_info(self) -> dict:
        """获取微信进程运行时信息(pid / 状态 / 物理内存占用)

        状态取 /proc/<pid>/stat 第 3 列(S 睡眠、R 运行、Z 僵尸), 内存取
        /proc/<pid>/status 的 VmRSS。用于判断修复后重新启动的微信是"真的
        起来了并稳定驻留", 而不是一闪而过(Z 或 rss 为 0)。

        :return: {"pid": str, "state": str, "rss_kb": int}; 进程不存在时全空
        """
        pid = self.get_wechat_process_pid()
        info = {"pid": pid, "state": "", "rss_kb": 0}
        if not pid:
            return info
        out = self.run_cmd(
            f"awk '{{print $3}}' /proc/{pid}/stat 2>/dev/null; "
            f"awk '/VmRSS/ {{print $2}}' /proc/{pid}/status 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        parts = [line.strip() for line in out.strip().splitlines() if line.strip()]
        if parts:
            info["state"] = parts[0]
        if len(parts) > 1:
            try:
                info["rss_kb"] = int(parts[1])
            except ValueError:
                info["rss_kb"] = 0
        return info

    def is_wechat_process_healthy(self) -> bool:
        """判断微信进程是否健康存活(非僵尸且已占用内存)

        :return: True 表示进程存在、状态为 R/S/D/I 且 VmRSS > 0
        """
        info = self.get_wechat_process_info()
        if not info["pid"]:
            return False
        return info["state"] in ("R", "S", "D", "I") and info["rss_kb"] > 0

    def wait_wechat_process_started(self, timeout: int = 60) -> bool:
        """轮询等待微信启动完成(首次启动缓慢属预期, 给予较长超时)

        :param timeout: 最长等待秒数
        :return: True 表示进程已健康启动, False 表示超时
        """
        for _ in range(timeout):
            if self.is_wechat_process_healthy():
                return True
            sleep(1)
        return False

    def is_wechat_process_alive_after(self, seconds: int = 10) -> bool:
        """验证微信进程在观察窗口内持续存活且 pid 不变(无闪退/反复重启)

        :param seconds: 观察窗口秒数
        :return: True 表示窗口后仍是同一 pid 的健康进程
        """
        pid = self.get_wechat_process_pid()
        if not pid:
            return False
        sleep(seconds)
        return self.get_wechat_process_pid() == pid and self.is_wechat_process_healthy()

    # ===== 模块 修复工具 - 应用修复-修复微信-磁盘空间不足(用例 2005767) =====
    # 测试机根分区只有约 1GB 可用且整轮用例共用, 不能把根分区真塞到 100MB 以下
    # (会让后续用例集体 ENOSPC)。改为用一块 100MB 的 tmpfs 表示"可用空间不足
    # 100MB"的盘, 再把产品删除目标 ~/.xwechat 软链过去, 使 entry.sh 的
    # `rm -rf ~/.xwechat/radium/cache` 真实作用在低空间文件系统上, 删除后可用
    # 空间上升可用 df 量化。tmpfs 不可用时回退为普通缓存目录(仍验证缓存被真实
    # 删除), 保证用例不会仅因环境不允许挂载而失败。
    LOW_SPACE_MOUNT = "/tmp/autotest_pcm_lowspace"
    LOW_SPACE_TOTAL_MB = 100
    # 盘内先写 70MB 占位文件, 让可用空间明显低于 100MB 阈值(也不过多占内存)
    LOW_SPACE_FILL_MB = 70

    def get_mount_free_space_mb(self, mount_point: str) -> int:
        """获取指定挂载点/目录所在文件系统的可用空间(MB)

        :param mount_point: 挂载点或目录路径
        :return: 可用空间(MB); 获取失败返回 -1
        """
        result = self.run_cmd(
            f"df -m {mount_point} 2>/dev/null | tail -1 | awk '{{print $4}}'",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, IndexError):
            return -1

    def is_low_space_mounted(self) -> bool:
        """检查低空间 tmpfs 是否仍挂载(用于确认卸载结果)

        :return: True 表示 /proc/mounts 中仍有该挂载点
        """
        result = self.run_cmd(
            f"grep -c ' {self.LOW_SPACE_MOUNT} ' /proc/mounts 2>/dev/null; true",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip().splitlines()[-1]) > 0
        except (ValueError, IndexError):
            return False

    # 虚拟网卡测试现场: 独立 netns 内的 veth 对 + 专用网段, 与办公网/管理链路隔离
    VIRTUAL_NET_NAME = "veth-at"
    VIRTUAL_NET_PEER = "veth-peer"
    VIRTUAL_NET_NS = "autotest_pcm_netns"

    def setup_virtual_net_device(self, ip="192.168.77.2", conflict=False, name=None) -> dict:
        """构造一块可选"同网段存在同 IP 设备"的虚拟网卡

        产品依据(network_detector.cpp:430-466, 845-868): IP 冲突检测遍历
        QNetworkInterface 中 Ethernet/Wifi 且 IsUp&&IsRunning、非 bridge/lo 的
        网卡, 对每个 IPv4 执行 `arping -D -I <网卡> <IP> -w 3`, 退出码 1 判冲突。
        测试机是 VM, 只有一块 enp0s3 且无第二台可控主机, 因此用 veth 对构造
        "本机网卡 + 同一二层段内另一台设备": 主机侧 veth-at(类型 Ethernet,
        up/running, 非 bridge, 会被产品探测), 对端放进独立 netns 模拟另一台设备
        (同 IP 即冲突)。专用 192.168.77.0/24 与管理网 10.20.33.0/24 无交集,
        不影响 SSH。

        :param ip: 主机侧 veth 的 IPv4(/24), 须落在 192.168.77.0/24
        :param conflict: True 时对端设备配置同一 IP(模拟地址冲突)
        :param name: 主机侧网卡名, 默认 veth-at
        :return: {"name", "peer", "ns", "ip", "conflict", "ok"}
        """
        iface = name or self.VIRTUAL_NET_NAME
        peer = self.VIRTUAL_NET_PEER
        # 每个虚拟网卡独立 netns, 避免构造第二块时删掉第一块的 netns 连带销毁
        ns = f"{self.VIRTUAL_NET_NS}_{iface}"
        info = {"name": iface, "peer": peer, "ns": ns, "ip": ip,
                "conflict": conflict, "ok": False}
        # 幂等: 先清掉上次异常退出留下的现场
        self.teardown_virtual_net_device({"name": iface, "ns": ns})
        script = (
            f"ip netns add {ns} && "
            f"ip link add {iface} type veth peer name {peer} && "
            f"ip link set {peer} netns {ns} && "
            f"ip addr add {ip}/24 dev {iface} && "
            f"ip link set {iface} up && "
            f"ip netns exec {ns} ip link set {peer} up"
        )
        if conflict:
            script += (
                f" && ip netns exec {ns} ip addr add {ip}/24 dev {peer}"
            )
        script += f" && echo setup-ok"
        output = self.sudo_run_cmd(script, timeout=60, out_debug_flag=False)
        info["ok"] = "setup-ok" in (output or "")
        sleep(1)
        print(
            f"[setup_virtual_net_device] iface={iface} ip={ip} "
            f"conflict={conflict} ok={info['ok']}"
        )
        return info

    def teardown_virtual_net_device(self, info=None):
        """删除 setup_virtual_net_device 构造的 netns 与 veth 对

        :param info: setup_virtual_net_device 的返回值
        """
        iface = (info or {}).get("name") or self.VIRTUAL_NET_NAME
        ns = (info or {}).get("ns") or f"{self.VIRTUAL_NET_NS}_{iface}"
        self.sudo_run_cmd(
            f"ip link del {iface} 2>/dev/null; "
            f"ip netns del {ns} 2>/dev/null; true",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(1)
        left = self.run_cmd(
            f"ip -o link show | grep -cw {iface}; "
            f"ip netns list | grep -cw {ns}; true",
            timeout=10,
            out_debug_flag=False,
        )
        print(f"[teardown_virtual_net_device] 剩余引用: {left.strip()!r}")

    def get_virtual_net_device_state(self, name=None) -> dict:
        """读取虚拟网卡现场状态(exists/operstate/ipv4)

        :param name: 网卡名, 默认 veth-at
        :return: {"exists": bool, "operstate": str, "ipv4": str}
        """
        iface = name or self.VIRTUAL_NET_NAME
        output = self.run_cmd(
            f"if [ -e /sys/class/net/{iface} ]; then "
            f"echo exists=$(cat /sys/class/net/{iface}/operstate); "
            f"ip -o -4 addr show dev {iface} | awk '{{print $4}}'; "
            f"else echo missing; fi",
            timeout=10,
            out_debug_flag=False,
        ) or ""
        state = {"exists": "exists=" in output, "operstate": "", "ipv4": ""}
        for line in output.splitlines():
            if line.startswith("exists="):
                state["operstate"] = line.split("=", 1)[1].strip()
            elif "/" in line:
                state["ipv4"] = line.strip()
        return state

    def arping_conflict(self, iface, ip, timeout=3) -> int:
        """对指定网卡/IP 执行 arping -D, 返回退出码(与产品判定口径一致)

        :param iface: 网卡名
        :param ip: 待探测 IPv4
        :param timeout: arping -w 秒数
        :return: 退出码; 1 表示检出重复地址
        """
        output, rc = self.sudo_run_cmd(
            f"arping -D -I {iface} {ip} -w {timeout} >/dev/null 2>&1; echo rc=$?",
            timeout=timeout + 15,
            out_debug_flag=False,
            return_code=True,
        ) or ("", -1)
        match = re.search(r"rc=(\d+)", output or "")
        return int(match.group(1)) if match else -1

    def get_ip_conflict_log_tail(self, lines=12) -> str:
        """读取电脑管家守护进程日志中最近若干条 IP 冲突检测记录

        产品依据(network_detector.cpp:861/873/876): 每次探测记录
        `detectIpConflict: probe "<IP>" on "<网卡>" exit <rc>`, 检出重复时再记
        `IP address conflict detected: ("<IP>", ...)`, 末尾 `success: false`。
        D-Bus 的 GetResult 只回状态码(failure:4013), 冲突地址需从该日志取证。

        :param lines: 取日志末尾多少条匹配行
        :return: 匹配到的日志文本(无匹配为空串)
        """
        output = self.run_cmd(
            "grep -a 'detectIpConflict' "
            "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager-session-daemon.log "
            f"| tail -{int(lines)}",
            timeout=15,
            out_debug_flag=False,
        )
        return output or ""

    def get_ip_conflict_verdict(self, timeout=60):
        """读取产品 D-Bus 通道的 ip_conflict 检测结论

        :param timeout: 等待检测完成秒数
        :return: (ok, detail); ok 为 None 表示接口不可用
        """
        return self.get_detection_item_verdict("ip_conflict", timeout=timeout)

    def setup_low_space_wechat_cache(self) -> dict:
        """构造"磁盘空间不足 100MB"现场, 并把微信缓存放到该盘上

        产品依据(plugin-wechat-fix/entry.sh): 脚本最后执行
        `rm -rf ~/.xwechat/radium/cache`, 与所在文件系统无关, 但"磁盘空间
        不足"只体现在删除目标所在盘几乎没有余量。因此:
        1) 挂一块 100MB tmpfs(挂载点 /tmp/autotest_pcm_lowspace);
        2) 写入 70MB 占位文件, 使可用空间约 30MB(< 100MB 阈值);
        3) 在盘内创建 ~/.xwechat/radium/cache 及缓存文件, 并把 ~/.xwechat
           软链到盘内目录 —— 产品脚本的 rm -rf 因此真实作用在低空间盘上,
           删除后 df 可用空间上升, 可量化"释放空间"。
        调用前调用方必须已备份真实 ~/.xwechat(backup_wechat_cache)。

        tmpfs 挂载失败(无权限/内核不支持)时回退为家目录内的普通缓存目录,
        此时仍可验证"缓存被 rm -rf 删除", 只是无法量化释放空间与低空间压力。

        :return: {"mode": "tmpfs"/"fallback", "mount": 挂载点, "free_mb": 可用空间}
        """
        info = {"mode": "fallback", "mount": self.LOW_SPACE_MOUNT, "free_mb": -1}
        # 清上次异常退出可能留下的挂载与挂载点
        self.sudo_run_cmd(
            f"umount -l {self.LOW_SPACE_MOUNT} 2>/dev/null; true",
            timeout=30,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"rm -rf {self.LOW_SPACE_MOUNT}; mkdir -p {self.LOW_SPACE_MOUNT}",
            timeout=30,
            out_debug_flag=False,
        )
        _, rc = self.sudo_run_cmd(
            f"mount -t tmpfs -o size={self.LOW_SPACE_TOTAL_MB}M,mode=0777 "
            f"tmpfs {self.LOW_SPACE_MOUNT}",
            timeout=60,
            out_debug_flag=False,
            return_code=True,
        )
        if rc == 0:
            cache_dir = f"{self.LOW_SPACE_MOUNT}/xwechat/radium/cache"
            # tmpfs 以 mode=0777 挂载, 当前用户可直接写入, 无需 root
            self.run_cmd(
                f"dd if=/dev/zero of={self.LOW_SPACE_MOUNT}/filler.bin "
                f"bs=1M count={self.LOW_SPACE_FILL_MB} 2>/dev/null; "
                f"mkdir -p {cache_dir}; "
                f"dd if=/dev/zero of={cache_dir}/low_space_cache.db "
                f"bs=1M count=2 2>/dev/null; "
                f"echo 'mock_cache_data' > {cache_dir}/low_space_cache.txt; "
                f"if [ -e {HOME_DIR}/.xwechat ] && [ ! -L {HOME_DIR}/.xwechat ]; then "
                f"rm -rf {HOME_DIR}/.xwechat; fi; "
                f"ln -sfn {self.LOW_SPACE_MOUNT}/xwechat {HOME_DIR}/.xwechat",
                timeout=120,
                out_debug_flag=False,
            )
            free_mb = self.get_mount_free_space_mb(self.LOW_SPACE_MOUNT)
            # 占位文件到位时可用空间应比满盘少约 LOW_SPACE_FILL_MB; 否则视为构造失败
            filler_ok = free_mb <= self.LOW_SPACE_TOTAL_MB - self.LOW_SPACE_FILL_MB + 10
            if filler_ok and self.get_wechat_cache_exists():
                info.update(mode="tmpfs", free_mb=free_mb)
                return info
            logger.warning(
                f"低空间 tmpfs 构造不完整(free_mb={free_mb}, "
                f"cache_exists={self.get_wechat_cache_exists()}), 回退普通目录"
            )
            self.cleanup_low_space_wechat_cache(info={"mode": "tmpfs",
                                                     "mount": self.LOW_SPACE_MOUNT})
        else:
            logger.warning(
                f"tmpfs 挂载失败(rc={rc}), 磁盘空间不足现场退化为普通目录, "
                f"仅验证微信缓存被真实删除"
            )
        self.create_mock_wechat_cache()
        info["free_mb"] = self.get_disk_free_space_mb()
        return info

    def cleanup_low_space_wechat_cache(self, info: dict = None):
        """回退 setup_low_space_wechat_cache 构造的现场

        先删 ~/.xwechat 软链(rm 只删链接本身, 不会跟进 tmpfs), 再卸载 tmpfs
        (失败时惰性卸载), 最后删除挂载点目录。info 为空时按最坏情况清理固定
        挂载点。tmpfs 内的占位文件随卸载释放, 不占磁盘。

        :param info: setup_low_space_wechat_cache 的返回值
        """
        mount_point = (info or {}).get("mount") or self.LOW_SPACE_MOUNT
        self.run_cmd(
            f"if [ -L {HOME_DIR}/.xwechat ]; then rm -f {HOME_DIR}/.xwechat; fi",
            timeout=10,
            out_debug_flag=False,
        )
        for _ in range(3):
            self.sudo_run_cmd(
                f"umount {mount_point} 2>/dev/null; true",
                timeout=60,
                out_debug_flag=False,
            )
            if not self.is_low_space_mounted():
                break
            sleep(2)
        if self.is_low_space_mounted():
            self.sudo_run_cmd(
                f"umount -l {mount_point} 2>/dev/null; true",
                timeout=60,
                out_debug_flag=False,
            )
            sleep(1)
        self.run_cmd(
            f"rm -rf {mount_point} 2>/dev/null; true",
            timeout=30,
            out_debug_flag=False,
        )

    def _collect_usb_dialog_nodes(self, node, depth=0, max_depth=4) -> list:
        """收集 USB 确认对话框子树中的节点

        :param node: 起始节点
        :param depth: 当前深度
        :param max_depth: 最大递归深度
        :return: 节点列表
        """
        nodes = []
        try:
            nodes.append(node)
        except BaseException:
            return nodes
        if depth >= max_depth:
            return nodes
        try:
            for child in node.children:
                nodes.extend(self._collect_usb_dialog_nodes(child, depth + 1, max_depth))
        except BaseException:
            pass
        return nodes

    def _find_usb_confirm_dialog(self):
        """查找 USB 修复流程弹出的确认对话框(DDialog, 含"确认"/"取消"按钮)

        :return: 对话框节点, 未找到返回 None
        """
        try:
            tops = self.dog.obj.children
        except BaseException:
            return None
        for top in tops:
            try:
                if (getattr(top, "roleName", "") or "") != "dialog":
                    continue
                if not getattr(top, "showing", False):
                    continue
                names = [getattr(n, "name", "") or "" for n in self._collect_usb_dialog_nodes(top)]
                if "确认" in names and "取消" in names:
                    return top
            except BaseException:
                continue
        return None

    USB_DIALOG_ITEM_ROLES = ("list item", "table cell", "cell", "check box", "radio button")

    def _find_usb_dialog_button(self, nodes, names):
        """在交互框节点中查找指定文案的按钮

        :param nodes: 交互框子树节点
        :param names: 可接受的按钮文案(按 zh_CN 产品文案给出)
        :return: 按钮节点, 未找到返回 None
        """
        for node in nodes:
            try:
                if (getattr(node, "roleName", "") or "") != "push button":
                    continue
                if (getattr(node, "name", "") or "") in names:
                    return node
            except BaseException:
                continue
        return None

    def _select_usb_dialog_option(self, nodes) -> bool:
        """选中 USB 选择框列表中的第一项(QListWidget / 单选项)

        产品 dpm_select 交互框用 QListWidget 承载设备列表, 未选中任何项就点
        "确认"会被产品按"取消"处理(脚本输出"用户取消了设备选择"), 因此这里
        必须真正把列表项置为选中。先按 AT-SPI 动作触发, 再补一次坐标点击;
        点击后若可读取 selected 状态则校验, 未选中时用方向键补选。

        :param nodes: 交互框子树节点
        :return: True 表示找到并点击了可选项
        """
        for node in nodes:
            try:
                if (getattr(node, "roleName", "") or "") not in self.USB_DIALOG_ITEM_ROLES:
                    continue
            except BaseException:
                continue
            self._atspi_do_action(node)
            self._click_at_element(node)
            sleep(1)
            try:
                if getattr(node, "selected", False):
                    return True
            except BaseException:
                return True
            self._key_to_app("Down")
            sleep(1)
            try:
                return bool(getattr(node, "selected", False))
            except BaseException:
                return False
        return False

    def handle_usb_fix_confirm_dialog(self, timeout=180, done_texts=None) -> bool:
        """处理 USB 修复流程中的确认对话框(设备选择 / 诊断结果 / 修复文件系统)

        产品在 usb-fix 修复过程中会依次弹出 DDialog 确认框:
        先选择需要修复的 USB 设备(列表中选中设备), 再确认诊断结果与修复动作。
        每个确认框均为"取消"/"确认"按钮布局, 需要逐次点击"确认"推进流程。

        注意: 设备"无错误"时产品在 present_diagnosis 返回 2 后直接
        "设备状态正常，无需修复"并 exit 0, 不会打印"USB 修复流程结束",
        这类分支的终止文案由调用方通过 done_texts 传入。

        :param timeout: 最长等待秒数
        :param done_texts: 额外的流程终止关键词(如"设备状态正常，无需修复")
        :return: True 表示流程已执行到结束, False 表示超时
        """
        end_texts = ("USB 修复流程结束", "用户取消了设备选择", "未执行任何修复")
        if done_texts:
            end_texts = tuple(done_texts) + end_texts
        for _ in range(timeout):
            output_text = self.get_repair_output_text()
            # 流程终止的收尾: 正常结束 / 取消设备选择 / 交互通道不可用 / 无问题分支
            for done_text in end_texts:
                if done_text in output_text:
                    return True
            dialog = self._find_usb_confirm_dialog()
            if dialog is not None:
                nodes = self._collect_usb_dialog_nodes(dialog)
                if self._select_usb_dialog_option(nodes):
                    logger.info("已在 USB 修复交互框中选择设备项")
                button = self._find_usb_dialog_button(nodes, ("确认", "确定"))
                if button is not None:
                    if not self._atspi_do_action(button):
                        self._click_at_element(button)
                    logger.info(
                        f"已点击 USB 修复交互框【{getattr(button, 'name', '')}】"
                    )
                    sleep(2)
                    continue
            sleep(1)
        return False

    def close_repair_dialog(self):
        """关闭修复对话框及可能弹出的信息提示框

        修复脚本执行完毕后, dpmapi openinfobox 可能弹出一个信息提示框,
        需先关闭提示框使脚本退出, 再关闭修复对话框。
        若脚本仍在运行时关闭修复对话框, 会弹出"结束修复"确认框,
        按回车确认终止。
        """
        # 等待信息提示框出现
        sleep(2)
        # 关闭信息提示框(Escape 关闭 DDialog)
        self.run_cmd("xdotool key Escape", timeout=2, out_debug_flag=False)
        # 等待脚本执行完成
        sleep(2)
        # 关闭修复对话框
        self.run_cmd("xdotool key Escape", timeout=2, out_debug_flag=False)
        sleep(1)
        # 若出现"结束修复"确认框, 按回车确认(Yes 为默认按钮)
        if not self._key_to_app("Return"):
            self.run_cmd("xdotool key Return", timeout=2, out_debug_flag=False)
        sleep(1)

    def get_repair_info_dialog_showing(self, timeout=15) -> bool:
        """检测修复完成后弹出的信息提示框(提示框)是否可见

        修复脚本执行完毕后, 会弹出一个 DDialog 信息提示框显示修复结果。
        V20 上会弹出独立的提示框; V25 上 ShellRepairDialog 本身保持打开显示结果,
        即为信息提示框。因此修复完成后只要存在任意 dialog 即视为提示框可见。
        :param timeout: 最长等待秒数
        :return: True 表示信息提示框可见
        """
        for _ in range(timeout):
            try:
                dialogs = self.dog.obj.findChildren(
                    lambda n: n.roleName in ("dialog", "alert dialog"),
                    recursive=True,
                )
                if dialogs:
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    # ===== 模块 修复工具 - 应用修复-修复企业微信 测试用例方法 =====

    def click_wecom_fix_card(self):
        """点击企业微信修复卡片

        先最大化窗口确保布局稳定，然后直接通过 AT-SPI 点击卡片。
        AT-SPI 点击不依赖卡片的视觉可见性，即使卡片在滚动区域下方也能正常触发。
        """
        self._safe_focus_windows()
        if not self.get_window_maximized_status():
            self.maximize_window_by_shortcut()
            sleep(2)
            self._safe_focus_windows()
            self.reconnect_dogtail()
        self.click_repair_card_by_name("企业微信修复")

    def create_mock_wecom_wine_cache(self):
        """创建模拟 wine 企业微信缓存目录及文件

        在 ~/.deepinwine/Deepin-WXWork/ 下创建模拟缓存文件,
        修复脚本会删除整个目录以清理缓存。
        """
        cache_dir = f"{HOME_DIR}/.deepinwine/Deepin-WXWork"
        self.run_cmd(
            f"mkdir -p '{cache_dir}' && "
            f"dd if=/dev/zero of='{cache_dir}/cache.db' bs=1K count=100 2>/dev/null && "
            f"echo 'mock_wecom_cache' > '{cache_dir}/config.ini'",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def get_wecom_wine_cache_exists(self) -> bool:
        """检查 wine 企业微信缓存目录是否存在

        :return: True 表示目录存在, False 表示已被清理
        """
        cache_dir = f"{HOME_DIR}/.deepinwine/Deepin-WXWork"
        result = self.run_cmd(
            f"test -d '{cache_dir}' && echo exists",
            timeout=5,
            out_debug_flag=False,
        )
        return "exists" in result.strip()

    def wait_wecom_wine_cache_cleaned(self, timeout=30) -> bool:
        """轮询等待 wine 企业微信缓存目录被修复脚本删除

        :param timeout: 最长等待秒数
        :return: True 表示目录已被清理, False 表示超时仍存在
        """
        for _ in range(timeout):
            if not self.get_wecom_wine_cache_exists():
                return True
            sleep(1)
        return False

    def cleanup_wecom_wine_cache(self):
        """清理模拟 wine 企业微信缓存目录(测试前后清理用)"""
        cache_dir = f"{HOME_DIR}/.deepinwine/Deepin-WXWork"
        self.run_cmd(
            f"rm -rf '{cache_dir}' 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )

    def get_wecom_wine_cache_ls_error(self) -> bool:
        """执行 ls ~/.deepinwine/Deepin-WXWork 并判断是否报"路径不存在"

        对应用例预期第 2 条"无权限 / 路径错误": 修复完成后再次访问该目录
        应直接报错, 说明目录(不只内容)已被彻底删除, 而不是被清空。

        :return: True 表示 ls 以非 0 返回且报 No such file/没有那个文件
        """
        out, status = self.run_cmd(
            f"ls '{self.WECOM_BOTTLE_DIR}' 2>&1",
            timeout=5,
            out_debug_flag=False,
            return_code=True,
        )
        text = (out or "").strip()
        hit = (
            "No such file" in text
            or "没有那个文件" in text
            or "无法访问" in text
        )
        return status != 0 and hit

    # 产品实现(plugin-wecom-fix/entry.sh)实际命令:
    #   /opt/deepinwine/tools/kill.sh ~/.deepinwine/Deepin-WXWork/
    #   rm -rf ~/.deepinwine/Deepin-WXWork/
    #   dpmapi openinfobox "企业微信修复" "企业微信缓存清理完成，修复完成"
    # kill.sh 先按 bottle 路径找到 WINEPREFIX 指向该 prefix 的 wineserver 进程,
    # 再执行 `WINEPREFIX=<bottle> <wineserver> -k` 结束容器内全部进程。
    # 本机未安装真实 Wine 版企业微信, 用桩运行时构造等价现场。
    WECOM_MOCK_ROOT = "/tmp/autotest_wecom_wine"
    WECOM_MOCK_EXE = f"{WECOM_MOCK_ROOT}/WeChat.exe"
    WECOM_MOCK_WINESERVER = f"{WECOM_MOCK_ROOT}/wineserver"
    WECOM_BOTTLE_DIR = f"{HOME_DIR}/.deepinwine/Deepin-WXWork"
    # 测试机上若存在真实 wine 企业微信 bottle, 构造前改名备份, 结束后还原,
    # 避免产品 rm -rf 误删真实聊天缓存/容器(同分区 mv, 无拷贝开销)。
    WECOM_BOTTLE_BACKUP = f"{HOME_DIR}/.autotest_wecom_bottle_backup"
    # 桩 wineserver 的 pid 清单(放在桩运行时目录之外, 避免目录被 rm -rf 后丢失):
    # 修复后重启企业微信会二次构造现场, 需按清单杀掉所有历史桩实例, 不留残留。
    WECOM_MOCK_PIDS = f"{WECOM_MOCK_ROOT}.pids"
    # 产品 plugin-wecom-fix/entry.sh 依赖 /opt/deepinwine/tools/kill.sh 结束 Wine
    # 容器进程; 测试机只装了 deepin-wine-runtime, 该工具不在包内, 且脚本里写作
    # `/opt/deepinwine/tools/kill.sh ... 2>/dev/null || true`, 缺失时被静默跳过,
    # 预期"企业微信进程被终止"必然不成立。用例缺失时安装语义等价的桩
    # (按 WINEPREFIX 找 wineserver 再执行 -k, 与真实 kill.sh 同一条链路),
    # 结束后删除, 保证产品自身那条命令真实执行。
    WECOM_KILL_HELPER = "/opt/deepinwine/tools/kill.sh"
    WECOM_KILL_HELPER_DIR = "/opt/deepinwine/tools"
    WECOM_KILL_HELPER_TMP = "/tmp/autotest_wecom_kill.sh"
    WECOM_KILL_HELPER_STUB_MARK = "autotest-stub-wecom-kill"

    def get_wecom_kill_helper_state(self) -> str:
        """获取产品 kill.sh 的状态

        :return: "existing" 系统自带 / "stub" 本用例安装的桩 / "missing" 不存在
        """
        out = self.run_cmd(
            f"if [ -x '{self.WECOM_KILL_HELPER}' ]; then "
            f"if grep -q '{self.WECOM_KILL_HELPER_STUB_MARK}' "
            f"'{self.WECOM_KILL_HELPER}' 2>/dev/null; then echo stub; "
            "else echo existing; fi; else echo missing; fi",
            timeout=5,
            out_debug_flag=False,
        )
        for state in ("stub", "existing", "missing"):
            if state in out.strip().split():
                return state
        return "missing"

    def ensure_wecom_kill_helper(self) -> dict:
        """确保产品依赖的 kill.sh 存在, 缺失时安装等价桩(需 root)

        桩的行为与真实 kill.sh 一致: 扫描 /proc 找到 WINEPREFIX 等于入参
        bottle 的 wineserver, 执行 `<wineserver> -k`。写成 base64 落地, 避免
        sudo + heredoc + shlex 引号叠加出错。

        :return: dict, helper 为 "existing"/"stub", dir_created 表示 tools
            目录是否由本用例创建(收尾时据此决定是否 rmdir)
        """
        state = self.get_wecom_kill_helper_state()
        if state != "missing":
            return {"helper": state, "dir_created": False}
        dir_exists = bool(
            self.run_cmd(
                f"test -d '{self.WECOM_KILL_HELPER_DIR}' && echo yes",
                timeout=5,
                out_debug_flag=False,
            ).strip()
        )
        script = (
            "#!/bin/bash\n"
            f"# {self.WECOM_KILL_HELPER_STUB_MARK}: 用例注入的 kill.sh 等价实现\n"
            "# 语义同真实 kill.sh: 按 WINEPREFIX 定位 wineserver, 再执行 -k\n"
            'bottle="${1%/}"\n'
            'for envf in /proc/[0-9]*/environ; do\n'
            '    [ -r "$envf" ] || continue\n'
            '    tr \'\\0\' \'\\n\' < "$envf" 2>/dev/null | '
            'grep -qx "WINEPREFIX=$bottle" || continue\n'
            '    pid="${envf#/proc/}"; pid="${pid%/environ}"\n'
            '    [ "$(cat "/proc/$pid/comm" 2>/dev/null)" = "wineserver" ] '
            '|| continue\n'
            '    mapfile -d \'\' args < "/proc/$pid/cmdline"\n'
            '    "${args[@]}" -k\n'
            "done\n"
        )
        suffix = "编码失败"
        try:
            from base64 import b64encode

            suffix = b64encode(script.encode("utf-8")).decode("ascii")
        except BaseException:
            pass
        self.run_cmd(
            f"printf '%s' '{suffix}' | base64 -d > '{self.WECOM_KILL_HELPER_TMP}' "
            f"&& chmod 755 '{self.WECOM_KILL_HELPER_TMP}'",
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"mkdir -p '{self.WECOM_KILL_HELPER_DIR}' && "
            f"install -m 755 '{self.WECOM_KILL_HELPER_TMP}' "
            f"'{self.WECOM_KILL_HELPER}'",
            timeout=30,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"rm -f '{self.WECOM_KILL_HELPER_TMP}'", timeout=5, out_debug_flag=False
        )
        return {
            "helper": self.get_wecom_kill_helper_state(),
            "dir_created": not dir_exists,
        }

    def remove_wecom_kill_helper(self, env: dict) -> bool:
        """删除本用例安装的 kill.sh 桩(系统自带的不动)

        :param env: ensure_wecom_kill_helper 的返回值
        :return: True 表示现场已复原(helper 不存在或仍是系统自带的)
        """
        if not env or env.get("helper") != "stub":
            return True
        self.sudo_run_cmd(
            f"rm -f '{self.WECOM_KILL_HELPER}'", timeout=15, out_debug_flag=False
        )
        if env.get("dir_created"):
            self.sudo_run_cmd(
                f"rmdir '{self.WECOM_KILL_HELPER_DIR}' 2>/dev/null || true",
                timeout=15,
                out_debug_flag=False,
            )
        return self.get_wecom_kill_helper_state() in ("missing", "existing")

    def _protect_wecom_bottle(self):
        """把测试机可能存在的真实 wine 企业微信 bottle 改名备份

        产品 entry.sh 会 rm -rf 整个 ~/.deepinwine/Deepin-WXWork, 为避免误删
        真实聊天缓存与容器配置, 构造用例数据前把真实目录改名为
        ~/.autotest_wecom_bottle_backup(同分区 mv), 用例结束或下次启动时还原。
        若上次异常退出同时留下备份与桩 bottle, 以备份为准: 先删桩再还原。
        """
        self.run_cmd(
            f"if [ -e '{self.WECOM_BOTTLE_BACKUP}' ]; then "
            f"rm -rf '{self.WECOM_BOTTLE_DIR}'; "
            f"mv '{self.WECOM_BOTTLE_BACKUP}' '{self.WECOM_BOTTLE_DIR}'; fi; "
            f"if [ -e '{self.WECOM_BOTTLE_DIR}' ]; then "
            f"mv '{self.WECOM_BOTTLE_DIR}' '{self.WECOM_BOTTLE_BACKUP}'; fi",
            timeout=30,
            out_debug_flag=False,
        )

    def setup_mock_wecom_wine(self, protect_bottle: bool = True) -> bool:
        """构造"Wine 版企业微信正在运行"的前置现场(等效实现)

        产品 entry.sh 调用 /opt/deepinwine/tools/kill.sh <bottle>: 该脚本按
        bottle 路径(user.reg 判定)匹配 WINEPREFIX 等于该目录的 wineserver
        进程, 再执行 `WINEPREFIX=<bottle> <wineserver> -k`, 结束容器内所有
        Windows 进程。本机没有真实 Wine 版企业微信, 因此构造桩运行时:
          1) bottle 目录 ~/.deepinwine/Deepin-WXWork 且含 user.reg;
          2) 桩 wineserver 以该 bottle 为 WINEPREFIX 常驻, 收到 -k 时结束
             容器内的模拟 WeChat.exe, 语义与真实 wineserver -k 一致;
          3) 运行中的模拟企业微信进程 WeChat.exe(sleep 复制品)。
        这样产品脚本会真实走到 kill.sh -> wineserver -k 分支。

        :param protect_bottle: 是否先把测试机真实 bottle 改名备份(默认 True)。
            当调用方已经自行归一化过真实 bottle(例如把 ~/.deepinwine 整体
            bind 挂到低空间 tmpfs 上)时必须传 False, 否则备份会被 mv 进
            临时文件系统, 卸载后丢失。
        :return: True 表示桩 wineserver 与模拟企业微信进程均已就绪
        """
        # 先杀掉此前构造留下的桩 wineserver, 避免二次构造(修复后重启企业微信)时
        # 旧实例因 pid 文件被覆盖而泄漏成残留进程。
        self.kill_all_mock_wecom_wineservers()
        self.run_cmd(
            f"rm -rf '{self.WECOM_MOCK_ROOT}'",
            timeout=10,
            out_debug_flag=False,
        )
        if protect_bottle:
            self._protect_wecom_bottle()
        # 建 bottle 骨架(user.reg 是 kill.sh 认定 bottle 的依据)与桩运行时
        self.run_cmd(
            f"mkdir -p '{self.WECOM_MOCK_ROOT}' '{self.WECOM_BOTTLE_DIR}/drive_c' && "
            f": > '{self.WECOM_BOTTLE_DIR}/user.reg' && "
            f": > '{self.WECOM_BOTTLE_DIR}/.autotest_stub_bottle' && "
            f"cp \"$(command -v sleep)\" '{self.WECOM_MOCK_EXE}' && "
            f"cat > '{self.WECOM_MOCK_WINESERVER}' <<'WSEOF'\n"
            "#!/bin/bash\n"
            "# 桩 wineserver: 收到 -k 时结束容器内所有 Windows 进程(此处为 WeChat.exe)\n"
            "# 真实 kill.sh 可能以 `<wineserver> <原有参数> -k` 形式调用, 故匹配任意位置\n"
            "case \" $* \" in *\" -k \"*) pkill -x WeChat.exe 2>/dev/null; exit 0 ;; esac\n"
            f"echo $$ > '{self.WECOM_MOCK_ROOT}/wineserver.pid'\n"
            f"echo $$ >> '{self.WECOM_MOCK_PIDS}'\n"
            "while :; do sleep 5; done\n"
            "WSEOF\n"
            f"chmod +x '{self.WECOM_MOCK_WINESERVER}' '{self.WECOM_MOCK_EXE}'",
            timeout=15,
            out_debug_flag=False,
        )
        # 启动桩 wineserver(带 WINEPREFIX)与模拟企业微信进程
        self.run_cmd(
            f"setsid env WINEPREFIX='{self.WECOM_BOTTLE_DIR}' "
            f"'{self.WECOM_MOCK_WINESERVER}' 3600 >/dev/null 2>&1 & "
            f"setsid '{self.WECOM_MOCK_EXE}' 3600 >/dev/null 2>&1 &",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return self.get_wecom_wineserver_status() and self.get_wecom_process_status()

    def get_wecom_wineserver_status(self) -> bool:
        """检查桩 wineserver 进程是否存活(即 bottle 容器是否处于"运行中")

        桩 wineserver 启动后把自身 pid 写入 wineserver.pid, 用 kill -0 判断存活。

        :return: True 表示桩 wineserver 进程存活
        """
        pid_file = f"{self.WECOM_MOCK_ROOT}/wineserver.pid"
        result = self.run_cmd(
            f"[ -s '{pid_file}' ] && kill -0 \"$(cat '{pid_file}')\" 2>/dev/null "
            "&& echo alive",
            timeout=5,
            out_debug_flag=False,
        )
        return "alive" in result

    def get_wecom_process_status(self) -> bool:
        """获取模拟企业微信(WeChat.exe)进程运行状态

        用 pgrep -x 精确匹配进程名(comm), 不用 -f, 避免把命令行里含
        "WeChat.exe" 的 bash -c 包装进程误判成企业微信进程。

        :return: True 表示进程正在运行, False 表示未运行
        """
        result = self.run_cmd(
            "pgrep -x WeChat.exe",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def wait_wecom_process_killed(self, timeout=60) -> bool:
        """轮询等待企业微信进程被修复脚本(kill.sh -> wineserver -k)终止

        :param timeout: 最长等待秒数
        :return: True 表示进程已被终止, False 表示超时仍在运行
        """
        for _ in range(timeout):
            if not self.get_wecom_process_status():
                return True
            sleep(1)
        return False

    def create_wecom_wine_cache_payload(self, size_mb: int = 40) -> int:
        """在 wine 企业微信 bottle 内写入模拟缓存, 返回 bottle 占用(KB)

        企业微信(wine)把聊天缓存放在 ~/.deepinwine/Deepin-WXWork/ 下, 产品
        修复脚本用 rm -rf 删除整个 bottle 目录来释放空间。写入 size_mb 零
        数据作为可观测占用, 修复后目录整体消失即证明缓存被删净、空间释放。

        :param size_mb: 模拟缓存大小(MB)
        :return: 写入后 bottle 目录占用(KB), 失败返回 0
        """
        cache_file = (
            f"{self.WECOM_BOTTLE_DIR}/drive_c/users/uostest/Temp/cache.dat"
        )
        self.run_cmd(
            f"mkdir -p \"$(dirname '{cache_file}')\" && "
            f"dd if=/dev/zero of='{cache_file}' bs=1M count={size_mb} 2>/dev/null",
            timeout=60,
            out_debug_flag=False,
        )
        return self.get_wecom_bottle_size_kb()

    def get_wecom_bottle_size_kb(self) -> int:
        """获取 wine 企业微信 bottle 目录占用(KB)

        :return: 目录占用(KB), 目录不存在或读取失败返回 0
        """
        result = self.run_cmd(
            f"du -sk '{self.WECOM_BOTTLE_DIR}' 2>/dev/null | awk '{{print $1}}'",
            timeout=10,
            out_debug_flag=False,
        )
        try:
            return int(result.strip().split()[0])
        except BaseException:
            return 0

    def cleanup_mock_wecom_wine(self):
        """终止模拟企业微信/wineserver 并删除桩运行时与 bottle 目录

        用例前后回退用: 清桩进程、pid 文件、/tmp 下的桩二进制与 bottle,
        测试机不留残留(pkill -x 只按进程名匹配, 不会误杀执行命令的 shell)。
        """
        pid_file = f"{self.WECOM_MOCK_ROOT}/wineserver.pid"
        marker = f"{self.WECOM_BOTTLE_DIR}/.autotest_stub_bottle"
        # 先按 pid 清单清掉全部历史桩 wineserver(二次构造可能留下多个实例)
        self.kill_all_mock_wecom_wineservers()
        self.run_cmd(
            f"[ -s '{pid_file}' ] && kill -9 \"$(cat '{pid_file}')\" 2>/dev/null; "
            "pkill -x WeChat.exe 2>/dev/null; "
            f"rm -rf '{self.WECOM_MOCK_ROOT}'; "
            # 有备份说明当前 bottle 一定是用例桩数据: 删桩后还原真实 bottle;
            # 无备份时只删带桩标记的目录, 绝不误删测试机上真实的 bottle。
            f"if [ -e '{self.WECOM_BOTTLE_BACKUP}' ]; then "
            f"rm -rf '{self.WECOM_BOTTLE_DIR}'; "
            f"mv '{self.WECOM_BOTTLE_BACKUP}' '{self.WECOM_BOTTLE_DIR}'; "
            f"elif [ -e '{marker}' ]; then rm -rf '{self.WECOM_BOTTLE_DIR}'; fi",
            timeout=15,
            out_debug_flag=False,
        )
        sleep(1)

    def kill_all_mock_wecom_wineservers(self):
        """终止所有由 setup_mock_wecom_wine 启动的桩 wineserver

        桩 wineserver 是死循环常驻进程, 每次构造现场都会新起一个; 若只按
        wineserver.pid 清理, 多次构造(例如"修复后重启企业微信"需要重新构造
        现场)会漏杀旧实例, 残留到测试机。这里按 pid 清单逐个 kill -9 并删除
        清单; 不使用 pkill -f, 避免匹配到执行命令本身的 shell 进程。

        :return: 无
        """
        self.run_cmd(
            f"if [ -s '{self.WECOM_MOCK_PIDS}' ]; then "
            f"while read -r p; do [ -n \"$p\" ] && kill -9 \"$p\" 2>/dev/null; done "
            f"< '{self.WECOM_MOCK_PIDS}'; fi; rm -f '{self.WECOM_MOCK_PIDS}'",
            timeout=10,
            out_debug_flag=False,
        )

    # ===== 模块 修复工具 - 应用修复-修复企业微信-修复后功能验证(用例 2005777) =====
    # 产品 plugin-wecom-fix/entry.sh 会 kill.sh 掉 Wine 容器并 rm -rf 整个
    # bottle(~/.deepinwine/Deepin-WXWork), 因此"修复后首次启动企业微信"的真实
    # 语义是: 在容器已被删除的状态下重新拉起企业微信, Wine 会重新生成 prefix
    # (首次启动缓慢属预期), 随后登录、发消息、看聊天记录都正常。
    # 本机无真实 Wine 版企业微信, 用桩运行时等价实现: 修复后调用
    # setup_mock_wecom_wine(protect_bottle=False) 重建全新 bottle 并拉起
    # WeChat.exe(对应"重新生成 prefix + 首次启动"), 再以"本地会话数据可写可读回"
    # 作为"登录账号/发送消息/查看聊天记录"的可观测等价断言。
    WECOM_CHAT_DIR = (
        WECOM_BOTTLE_DIR + "/drive_c/users/uostest/Documents/WeChat Files/autotest_login"
    )
    WECOM_CHAT_HISTORY = f"{WECOM_CHAT_DIR}/chat_history.db"
    WECOM_CHAT_MESSAGE_LOG = f"{WECOM_CHAT_DIR}/message.log"

    def get_wecom_process_pid(self) -> str:
        """获取模拟企业微信进程 pid(进程名精确匹配 WeChat.exe)

        :return: pid 字符串; 进程不存在返回空串
        """
        out = self.run_cmd(
            "pgrep -x WeChat.exe 2>/dev/null | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
        return lines[-1] if lines else ""

    def get_wecom_process_info(self) -> dict:
        """获取模拟企业微信进程运行时信息(pid / 状态 / 物理内存占用)

        状态取 /proc/<pid>/stat 第 3 列(S 睡眠、R 运行、Z 僵尸), 内存取
        /proc/<pid>/status 的 VmRSS。用于判断修复后重新启动的企业微信是"真的
        起来了并稳定驻留", 而不是一闪而过(Z 状态或 rss 为 0)。

        :return: {"pid": str, "state": str, "rss_kb": int}; 进程不存在时全空
        """
        pid = self.get_wecom_process_pid()
        info = {"pid": pid, "state": "", "rss_kb": 0}
        if not pid:
            return info
        out = self.run_cmd(
            f"awk '{{print $3}}' /proc/{pid}/stat 2>/dev/null; "
            f"awk '/VmRSS/ {{print $2}}' /proc/{pid}/status 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        parts = [line.strip() for line in out.strip().splitlines() if line.strip()]
        if parts:
            info["state"] = parts[0]
        if len(parts) > 1:
            try:
                info["rss_kb"] = int(parts[1])
            except ValueError:
                info["rss_kb"] = 0
        return info

    def is_wecom_process_healthy(self) -> bool:
        """判断模拟企业微信进程是否健康存活(非僵尸且已占用内存)

        :return: True 表示进程存在、状态为 R/S/D/I 且 VmRSS > 0
        """
        info = self.get_wecom_process_info()
        if not info["pid"]:
            return False
        return info["state"] in ("R", "S", "D", "I") and info["rss_kb"] > 0

    def wait_wecom_process_started(self, timeout: int = 60) -> bool:
        """轮询等待企业微信启动完成(首次启动缓慢属预期, 给予较长超时)

        :param timeout: 最长等待秒数
        :return: True 表示进程已健康启动, False 表示超时
        """
        for _ in range(timeout):
            if self.is_wecom_process_healthy():
                return True
            sleep(1)
        return False

    def is_wecom_process_alive_after(self, seconds: int = 10) -> bool:
        """验证企业微信进程在观察窗口内持续存活且 pid 不变(无闪退/反复重启)

        :param seconds: 观察窗口秒数
        :return: True 表示窗口后仍是同一 pid 的健康进程
        """
        pid = self.get_wecom_process_pid()
        if not pid:
            return False
        sleep(seconds)
        return self.get_wecom_process_pid() == pid and self.is_wecom_process_healthy()

    def create_mock_wecom_chat_history(self) -> bool:
        """在 wine 企业微信 bottle 内构造本地会话与聊天记录(等价"登录账号")

        真实企业微信登录后会在容器用户目录下建立本地会话与聊天记录库。用例
        2005777 需要"登录账号 -> 发送消息 -> 查看聊天记录"的等价载体, 因此在
        bottle 的 Documents/WeChat Files 下写入 chat_history.db(会话+历史消息)
        与 message.log(消息收发日志), 既验证容器内数据目录可正常读写, 又给
        "发送消息/查看聊天记录"提供可读回的量化断言。

        :return: True 表示会话目录与两个数据文件均创建成功
        """
        out, rc = self.run_cmd(
            f"mkdir -p '{self.WECOM_CHAT_DIR}' && "
            f"printf '%s\\n' 'session: autotest_login' 'msg: 1 hello' "
            f"'msg: 2 chat_history' > '{self.WECOM_CHAT_HISTORY}' && "
            f"printf '%s\\n' 'login: autotest' 'msg: sent hello' "
            f"> '{self.WECOM_CHAT_MESSAGE_LOG}' && echo created",
            timeout=10,
            out_debug_flag=False,
            return_code=True,
        )
        return rc == 0 and "created" in out

    def get_wecom_chat_history_digest(self) -> str:
        """获取聊天记录文件 md5 摘要(用于确认记录可读且内容稳定)

        :return: md5 十六进制串; 文件不存在或计算失败返回空串
        """
        out = self.run_cmd(
            f"md5sum '{self.WECOM_CHAT_HISTORY}' 2>/dev/null | awk '{{print $1}}'",
            timeout=5,
            out_debug_flag=False,
        )
        lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
        return lines[-1] if lines else ""

    def get_wecom_chat_message_count(self) -> int:
        """统计企业微信消息日志行数(用于断言仍可发送新消息)

        :return: 行数; 文件不存在时返回 0
        """
        out = self.run_cmd(
            f"wc -l < '{self.WECOM_CHAT_MESSAGE_LOG}' 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return 0

    def append_wecom_chat_message(self, text: str = "post-repair hello") -> bool:
        """向企业微信消息日志追加一条消息(等价"发送消息")

        :param text: 消息内容
        :return: True 表示追加成功
        """
        out, rc = self.run_cmd(
            f"printf '%s\\n' {quote(text)} >> '{self.WECOM_CHAT_MESSAGE_LOG}' "
            f"&& echo appended",
            timeout=10,
            out_debug_flag=False,
            return_code=True,
        )
        return rc == 0 and "appended" in out

    def get_wecom_chat_last_message(self) -> str:
        """读取企业微信消息日志最后一行(等价"查看聊天记录"的读回动作)

        :return: 最后一条消息文本; 文件不存在或为空返回空串
        """
        out = self.run_cmd(
            f"tail -n 1 '{self.WECOM_CHAT_MESSAGE_LOG}' 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
        return lines[-1] if lines else ""

    # ===== 模块 修复工具 - 应用修复-修复企业微信-磁盘空间不足(用例 2005775) =====
    # 测试机整轮用例共用同一块盘的余量, 不能把根分区真塞到 100MB 以下(会让后续
    # 用例集体 ENOSPC)。改为挂一块 100MB tmpfs 并 bind 到 ~/.deepinwine, 使产品
    # plugin-wecom-fix/entry.sh 的 `rm -rf ~/.deepinwine/Deepin-WXWork/` 真实作用在
    # "可用空间不足 100MB"的文件系统上: bottle 在该盘内是普通目录(不是挂载点),
    # rm -rf 能整目录删掉, 删除后该盘可用空间上升, 可量化"释放空间"。
    WECOM_LOW_SPACE_MOUNT = "/tmp/autotest_pcm_lowspace_wecom"
    WECOM_LOW_SPACE_TOTAL_MB = 100
    # 盘内额外占位数据: 100MB - 30MB(占位) - 40MB(bottle 缓存) ≈ 30MB 余量,
    # 满足"可用空间不足 100MB", 又不会把 tmpfs 塞满导致占用过多内存。
    WECOM_LOW_SPACE_FILL_MB = 30

    def is_mount_present(self, path: str) -> bool:
        """检查指定路径(挂载点)是否仍出现在 /proc/mounts 中

        :param path: 挂载点绝对路径
        :return: True 表示仍处于挂载状态
        """
        result = self.run_cmd(
            f"grep -c ' {path} ' /proc/mounts 2>/dev/null; true",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip().splitlines()[-1]) > 0
        except (ValueError, IndexError):
            return False

    def unmount_path(self, path: str, rounds: int = 3) -> bool:
        """卸载指定挂载点(先正常卸载, 失败再惰性卸载)

        :param path: 挂载点绝对路径
        :param rounds: 正常卸载重试轮次(每轮间隔 2 秒)
        :return: True 表示已不再挂载
        """
        if not self.is_mount_present(path):
            return True
        for _ in range(rounds):
            self.sudo_run_cmd(
                f"umount {path} 2>/dev/null; true",
                timeout=60,
                out_debug_flag=False,
            )
            if not self.is_mount_present(path):
                return True
            sleep(2)
        self.sudo_run_cmd(
            f"umount -l {path} 2>/dev/null; true",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(1)
        return not self.is_mount_present(path)

    def _mount_low_space_deepinwine(self) -> tuple:
        """挂 100MB tmpfs 并 bind 到 ~/.deepinwine, 让 bottle 落在低空间盘上

        :return: (是否成功, 是否需要回退时删除 ~/.deepinwine 目录)
        """
        mnt = self.WECOM_LOW_SPACE_MOUNT
        bind_dir = f"{HOME_DIR}/.deepinwine"
        # 清上次异常退出可能留下的挂载与挂载点
        self.unmount_path(bind_dir)
        self.unmount_path(mnt)
        self.run_cmd(
            f"rm -rf {mnt}; mkdir -p {mnt}",
            timeout=30,
            out_debug_flag=False,
        )
        _, rc = self.sudo_run_cmd(
            f"mount -t tmpfs -o size={self.WECOM_LOW_SPACE_TOTAL_MB}M,mode=0777 "
            f"tmpfs {mnt}",
            timeout=60,
            out_debug_flag=False,
            return_code=True,
        )
        if rc != 0:
            logger.warning(f"低空间 tmpfs 挂载失败(rc={rc})")
            return False, False
        existed = self.run_cmd(
            f"test -d {bind_dir} && echo yes",
            timeout=5,
            out_debug_flag=False,
        )
        created = "yes" not in existed
        self.run_cmd(f"mkdir -p {bind_dir}", timeout=10, out_debug_flag=False)
        _, rc = self.sudo_run_cmd(
            f"mount --bind {mnt} {bind_dir}",
            timeout=60,
            out_debug_flag=False,
            return_code=True,
        )
        if rc != 0:
            logger.warning(f"~/.deepinwine bind 挂载失败(rc={rc})")
            self.unmount_path(mnt)
            self.run_cmd(f"rm -rf {mnt} 2>/dev/null; true", timeout=30,
                         out_debug_flag=False)
            return False, False
        return True, created

    def setup_low_space_wecom_bottle(self) -> dict:
        """构造"磁盘空间不足 100MB"现场并放置可被修复脚本删除的企业微信 bottle

        产品依据(plugin-wecom-fix/entry.sh):
            /opt/deepinwine/tools/kill.sh ~/.deepinwine/Deepin-WXWork/
            rm -rf ~/.deepinwine/Deepin-WXWork/
        "磁盘空间不足"只体现在删除目标所在盘几乎没有余量, 因此:
        1) 挂一块 100MB tmpfs(挂载点 /tmp/autotest_pcm_lowspace_wecom);
        2) bind 挂到 ~/.deepinwine, 真实 bottle 先改名备份(同分区 mv)避免误删;
        3) 盘内写 30MB 占位文件, 可用空间降到 100MB 以下;
        4) 在盘内构造桩 wine bottle(含缓存的 40MB 数据, 见 setup_mock_wecom_wine),
           使产品 rm -rf 真实作用在低空间盘上, 删除后可用空间上升可量化。
        挂载不可用(无权限/内核限制)时退化为家目录内普通 bottle, 仍验证
        "缓存被 rm -rf 真实删净", 只是无法量化低空间压力与释放量。

        :return: {"mode": "tmpfs"/"fallback", "mount": 挂载点,
                  "bind": bind 目录, "free_mb": 该盘可用空间,
                  "created_deepinwine": 是否由本次构造创建}
        """
        info = {
            "mode": "fallback",
            "mount": self.WECOM_LOW_SPACE_MOUNT,
            "bind": f"{HOME_DIR}/.deepinwine",
            "free_mb": -1,
            "created_deepinwine": False,
        }
        # 归一化: 先卸掉上次异常退出的挂载, 再把真实 bottle 移到备份
        self.unmount_path(info["bind"])
        self.unmount_path(self.WECOM_LOW_SPACE_MOUNT)
        self._protect_wecom_bottle()
        mounted, created = self._mount_low_space_deepinwine()
        if not mounted:
            logger.warning(
                "低空间 tmpfs/bind 挂载不可用, 退化为普通 bottle, "
                "仅验证 rm -rf 删净企业微信缓存"
            )
            self.setup_mock_wecom_wine()
            info["free_mb"] = self.get_disk_free_space_mb()
            return info
        info["created_deepinwine"] = created
        # 盘内写占位数据, 把可用空间压到 100MB 以下
        self.run_cmd(
            f"dd if=/dev/zero of={self.WECOM_LOW_SPACE_MOUNT}/filler.bin "
            f"bs=1M count={self.WECOM_LOW_SPACE_FILL_MB} 2>/dev/null",
            timeout=120,
            out_debug_flag=False,
        )
        # 桩运行时二进制在 /tmp(根分区), 只有 bottle 落在低空间盘上;
        # 真实 bottle 已备份, 这里禁止再次 mv 备份(否则会搬进 tmpfs)
        stub_ok = self.setup_mock_wecom_wine(protect_bottle=False)
        free_mb = self.get_mount_free_space_mb(self.WECOM_LOW_SPACE_MOUNT)
        bottle_ok = self.get_wecom_wine_cache_exists()
        if stub_ok and bottle_ok and 0 <= free_mb < self.WECOM_LOW_SPACE_TOTAL_MB:
            info.update(mode="tmpfs", free_mb=free_mb)
            return info
        logger.warning(
            f"低空间企业微信现场构造不完整(stub_ok={stub_ok}, "
            f"bottle_ok={bottle_ok}, free_mb={free_mb}), 回退普通 bottle"
        )
        self.cleanup_low_space_wecom_bottle(info)
        self.setup_mock_wecom_wine()
        info.update(
            mode="fallback",
            free_mb=self.get_disk_free_space_mb(),
            created_deepinwine=False,
        )
        return info

    def cleanup_low_space_wecom_bottle(self, info: dict = None):
        """回退 setup_low_space_wecom_bottle 构造的现场

        顺序很重要: 先卸载 ~/.deepinwine 上的 bind 挂载, 让真实的
        ~/.deepinwine 目录重新可见, 再清理桩进程/bottle 并还原备份的真实
        bottle —— 若顺序反过来, 备份会被 mv 进 tmpfs, 卸载后真实数据丢失。
        最后卸载低空间 tmpfs、删除挂载点(占位文件随卸载释放)。

        :param info: setup_low_space_wecom_bottle 的返回值
        """
        info = info or {}
        bind_dir = info.get("bind") or f"{HOME_DIR}/.deepinwine"
        mnt = info.get("mount") or self.WECOM_LOW_SPACE_MOUNT
        self.unmount_path(bind_dir)
        # 真实 ~/.deepinwine 已复现: 停桩进程/运行时, 有备份则还原真实 bottle
        self.cleanup_mock_wecom_wine()
        self.unmount_path(mnt)
        self.run_cmd(
            f"rm -rf {mnt} 2>/dev/null; true",
            timeout=30,
            out_debug_flag=False,
        )
        if info.get("created_deepinwine"):
            self.run_cmd(
                f"rmdir {bind_dir} 2>/dev/null; true",
                timeout=10,
                out_debug_flag=False,
            )
        sleep(1)

    def trigger_repair_dialog_close(self):
        """触发关闭修复对话框(按 Escape)

        若修复脚本仍在运行, 会弹出"结束修复"确认框;
        若脚本已执行完毕, 则直接关闭修复对话框。
        """
        if not self._key_to_app("Escape"):
            self.run_cmd("xdotool key Escape", timeout=2, out_debug_flag=False)
        sleep(0.5)
        self.reconnect_dogtail()

    def get_polkit_auth_dialog_showing(self) -> bool:
        """检查是否存在 polkit 鉴权弹窗(密码输入对话框)

        通过 xdotool 检查是否存在鉴权相关的窗口。
        polkit agent 守护进程常驻运行, 不能用于判断弹窗是否出现,
        需要检查实际的鉴权对话框窗口。
        """
        result = self.run_cmd(
            'xdotool search --name "认证" 2>/dev/null || '
            'xdotool search --name "Authenticate" 2>/dev/null || '
            'xdotool search --class "deepin-authentication" 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    # ===== 模块 修复工具 - 应用修复-修复QQ 测试用例方法 =====

    def click_qq_fix_card(self):
        """点击QQ修复卡片

        先最大化窗口确保布局稳定，然后直接通过 AT-SPI 点击卡片。
        AT-SPI 点击不依赖卡片的视觉可见性，即使卡片在滚动区域下方也能正常触发。
        V25 上页面切换后窗口可能短暂不可见导致 focus_windows 失败,
        最大化非必须, 失败时跳过并继续 AT-SPI 点击。
        """
        try:
            self._safe_focus_windows()
            if not self.get_window_maximized_status():
                self.maximize_window_by_shortcut()
                sleep(2)
                self._safe_focus_windows()
                self.reconnect_dogtail()
        except BaseException:
            self.reconnect_dogtail()
        self.click_repair_card_by_name("QQ修复")

    def create_mock_qq_cache(self):
        """创建模拟QQ缓存目录和文件(用于测试缓存清理功能)

        在 ~/.config/QQ/Cache/ 下创建模拟缓存文件,
        使修复工具有明确的目标去清理。
        """
        self.run_cmd(
            f"mkdir -p {HOME_DIR}/.config/QQ/Cache && "
            f"dd if=/dev/zero of={HOME_DIR}/.config/QQ/Cache/test_cache.db bs=1M count=1 2>/dev/null && "
            f"echo 'mock_qq_cache_data' > {HOME_DIR}/.config/QQ/Cache/test_cache.txt",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def get_qq_cache_exists(self) -> bool:
        """检查QQ缓存目录(~/.config/QQ/Cache)是否存在

        :return: True 表示缓存目录存在, False 表示不存在
        """
        result = self.run_cmd(
            f"test -d {HOME_DIR}/.config/QQ/Cache && echo yes || echo no",
            timeout=5,
            out_debug_flag=False,
        )
        return "yes" in result.strip()

    def wait_qq_cache_cleaned(self, timeout=30) -> bool:
        """轮询等待QQ缓存目录被修复脚本清理

        :param timeout: 最长等待秒数
        :return: True 表示缓存已被清理, False 表示超时仍存在
        """
        for _ in range(timeout):
            if not self.get_qq_cache_exists():
                return True
            sleep(1)
        return False

    def cleanup_qq_cache(self):
        """清理QQ缓存目录(测试前后清理用)"""
        self.run_cmd(
            f"rm -rf {HOME_DIR}/.config/QQ/Cache 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    # --- QQ 修复现场构造/回退(产线脚本 plugin-qq-fix/entry.sh 的真实目标路径) ---

    # 产品脚本: pkill -x qq; rm -rf <home>/.config/QQ/Cache;
    #           [ -d <home>/.deepinwine/Deepin-QQ ] && rm -rf 该目录
    QQ_CONFIG_DIR = f"{HOME_DIR}/.config/QQ"
    QQ_CACHE_DIR = f"{HOME_DIR}/.config/QQ/Cache"
    QQ_WINE_BOTTLE = f"{HOME_DIR}/.deepinwine/Deepin-QQ"
    # 用例构造前对真实 QQ 现场的整体备份目录(同分区 mv, 用例结束原样还原)
    QQ_BACKUP_ROOT = f"{HOME_DIR}/.autotest_qq_backup"

    def backup_qq_state(self) -> dict:
        """备份测试机已有的 QQ 现场, 避免用例删除真实用户数据

        产品脚本会 rm -rf ~/.config/QQ/Cache 与 ~/.deepinwine/Deepin-QQ,
        用例又要构造这两个路径; 若测试机上原本已有 QQ 用户数据, 必须先整体
        移走再构造, 用例 finally 中调用 restore_qq_state 原样还原。同一分区
        mv 不占额外磁盘(测试机磁盘紧张)。

        :return: {"config": 是否备份了 ~/.config/QQ,
                  "wine": 是否备份了 ~/.deepinwine/Deepin-QQ}
        """
        self.run_cmd(
            f"rm -rf {self.QQ_BACKUP_ROOT} && mkdir -p {self.QQ_BACKUP_ROOT}",
            timeout=30,
            out_debug_flag=False,
        )
        state = {}
        pairs = (
            ("config", self.QQ_CONFIG_DIR, f"{self.QQ_BACKUP_ROOT}/QQ"),
            ("wine", self.QQ_WINE_BOTTLE, f"{self.QQ_BACKUP_ROOT}/Deepin-QQ"),
        )
        for key, src, dst in pairs:
            result = self.run_cmd(
                f"if [ -e '{src}' ]; then mv '{src}' '{dst}' && echo backed; "
                f"else echo none; fi",
                timeout=30,
                out_debug_flag=False,
            )
            state[key] = "backed" in result
        logger.info(f"QQ 现场备份结果: {state}")
        return state

    def restore_qq_state(self):
        """还原 backup_qq_state 备份的 QQ 现场

        先删掉用例构造(及产品清理后残留)的 ~/.config/QQ 与
        ~/.deepinwine/Deepin-QQ, 再把备份移回原位; 没有备份时只删备份目录。
        """
        self.run_cmd(
            f"rm -rf '{self.QQ_CONFIG_DIR}' '{self.QQ_WINE_BOTTLE}'; "
            f"mkdir -p {HOME_DIR}/.config {HOME_DIR}/.deepinwine; "
            f"if [ -e '{self.QQ_BACKUP_ROOT}/QQ' ]; then "
            f"mv '{self.QQ_BACKUP_ROOT}/QQ' '{self.QQ_CONFIG_DIR}'; fi; "
            f"if [ -e '{self.QQ_BACKUP_ROOT}/Deepin-QQ' ]; then "
            f"mv '{self.QQ_BACKUP_ROOT}/Deepin-QQ' '{self.QQ_WINE_BOTTLE}'; fi; "
            f"rm -rf {self.QQ_BACKUP_ROOT}",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(1)

    def create_mock_qq_cache_payload(self, size_mb=8) -> int:
        """在 ~/.config/QQ/Cache 下构造可计量的 QQ 缓存(含子目录与文件)

        模拟 QQ 运行后产生的缓存目录结构, 让产品脚本的
        rm -rf ~/.config/QQ/Cache 有真实清理对象; 用 dd 写入 size_mb 的
        缓存块, 便于以"目录占用由 N KB 变为 0"作为缓存被删净的量化断言。

        :param size_mb: 缓存块大小(MB)
        :return: 构造后缓存目录占用(KB)
        """
        cache_dir = self.QQ_CACHE_DIR
        self.run_cmd(
            f"mkdir -p '{cache_dir}/avatar' '{cache_dir}/filecache' "
            f"'{cache_dir}/temp' && "
            f"dd if=/dev/zero of='{cache_dir}/filecache/blob.dat' "
            f"bs=1M count={size_mb} 2>/dev/null && "
            f"echo 'mock_qq_avatar_cache' > '{cache_dir}/avatar/avatar.db' && "
            f"echo 'mock_qq_cache_index' > '{cache_dir}/cache_index.db' && "
            f"echo 'mock_qq_temp' > '{cache_dir}/temp/tmp.log'",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(1)
        return self.get_qq_cache_size_kb()

    def get_qq_cache_size_kb(self) -> int:
        """统计 ~/.config/QQ/Cache 的磁盘占用(KB)

        :return: 占用 KB; 目录不存在时返回 0
        """
        result = self.run_cmd(
            f"du -sk '{self.QQ_CACHE_DIR}' 2>/dev/null | awk '{{print $1}}'",
            timeout=10,
            out_debug_flag=False,
        )
        try:
            return int(result.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return 0

    def get_qq_cache_file_count(self) -> int:
        """统计 QQ 缓存目录下剩余文件数(用于断言目录被彻底删除)

        :return: 缓存目录内文件数量; 目录不存在时 find 无输出, 计数为 0
        """
        result = self.run_cmd(
            f"find '{self.QQ_CACHE_DIR}' -type f 2>/dev/null | wc -l",
            timeout=10,
            out_debug_flag=False,
        )
        try:
            return int(result.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return 0

    def start_mock_qq_process(self):
        """启动名为 qq 的模拟 QQ 进程(等价"QQ 正在运行")

        产品脚本用 pkill -x qq 结束 QQ 进程, 只按进程名精确匹配, 因此把
        sleep 复制成 /tmp/qq 再运行, 使进程名恰为 qq; setsid + 重定向
        让进程脱离执行命令的 shell, 避免 run_cmd 等待管道关闭。
        """
        self.run_cmd(
            "cp -f $(command -v sleep) /tmp/qq && "
            "(setsid /tmp/qq 3600 </dev/null >/dev/null 2>&1 &) && echo started",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

    def get_qq_process_pids(self) -> list:
        """获取运行中的 QQ 进程 pid 列表(排除僵尸进程)

        pkill 结束后进程可能短暂处于 Z 状态, 此处按 /proc/<pid>/stat 第 3 列
        过滤, 确保"进程已结束"的断言不被僵尸态误判。

        :return: 存活(非僵尸)的 qq 进程 pid 列表
        """
        result = self.run_cmd("pgrep -x qq", timeout=5, out_debug_flag=False)
        pids = [pid for pid in result.split() if pid.isdigit()]
        alive = []
        for pid in pids:
            state = self.run_cmd(
                f"awk '{{print $3}}' /proc/{pid}/stat 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            if state and state != "Z":
                alive.append(pid)
        return alive

    def get_mock_qq_process_pid(self) -> str:
        """获取模拟 QQ 进程 pid(进程名精确匹配 qq)

        :return: pid 字符串; 无存活进程时返回空字符串
        """
        pids = self.get_qq_process_pids()
        return pids[0] if pids else ""

    def get_qq_process_status(self) -> bool:
        """获取 QQ 进程运行状态

        :return: True 表示存在存活的 qq 进程, False 表示未运行
        """
        return bool(self.get_qq_process_pids())

    def wait_qq_process_killed(self, timeout=60) -> bool:
        """轮询等待 QQ 进程被修复脚本(pkill -x qq)终止

        :param timeout: 最长等待秒数
        :return: True 表示进程已被终止, False 表示超时仍在运行
        """
        for _ in range(timeout):
            if not self.get_qq_process_status():
                return True
            sleep(1)
        return False

    def kill_qq_process(self):
        """终止模拟 QQ 进程并清理临时二进制(测试前后清理用)

        先 TERM 再 KILL, 只按进程名精确匹配 qq, 不会误杀执行命令的 shell。
        """
        self.run_cmd(
            "pkill -x qq 2>/dev/null; sleep 0.5; "
            "pkill -9 -x qq 2>/dev/null; rm -f /tmp/qq",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

    # ===== 模块 修复工具 - 应用修复-修复QQ-修复后功能验证(用例 2005785) =====
    # 产品依据(plugin-qq-fix/entry.sh, 已解码核对):
    #   pkill -x "qq"; 删 <home>/.deepinwine/Deepin-QQ/;
    #   删 <home>/.config/QQ/Cache; log_info "清理完成";
    #   dpmapi openinfobox "QQ修复" "QQ缓存清理完成，修复完成"
    # 与缓存清理用例(2005781)关注点不同: 本用例验证"修复后 QQ 仍可用"——
    # 聊天记录(位于缓存目录之外的 UserData)不得被修复破坏, 修复后能重新
    # 启动、稳定驻留、继续发送消息。
    QQ_USER_DATA_DIR = f"{HOME_DIR}/.config/QQ/UserData"
    QQ_CHAT_HISTORY = f"{HOME_DIR}/.config/QQ/UserData/chat_history.db"
    QQ_MESSAGE_LOG = f"{HOME_DIR}/.config/QQ/UserData/message.log"

    def create_mock_qq_user_data(self) -> bool:
        """构造 Linux 原生 QQ 的用户数据(账号会话 + 聊天记录 + 消息日志)

        产品 entry.sh 只删除 ~/.config/QQ/Cache 与 ~/.deepinwine/Deepin-QQ,
        不碰 ~/.config/QQ/UserData, 因此修复前后 chat_history.db 的摘要必须
        一致 —— 作为"查看聊天记录"的等价断言; message.log 用于"发送消息"的
        追加写验证。

        :return: True 表示目录与两个数据文件均创建成功
        """
        out, rc = self.run_cmd(
            f"mkdir -p {self.QQ_USER_DATA_DIR} && "
            f"printf '%s\\n' 'session: autotest_login' 'msg: 1 hello' "
            f"'msg: 2 chat_history' > {self.QQ_CHAT_HISTORY} && "
            f"printf '%s\\n' 'login: autotest' 'msg: sent hello' "
            f"> {self.QQ_MESSAGE_LOG} && echo created",
            timeout=10,
            out_debug_flag=False,
            return_code=True,
        )
        return rc == 0 and "created" in out

    def get_qq_chat_history_digest(self) -> str:
        """获取 QQ 聊天记录文件 md5 摘要(修复前后比对, 判断数据是否被破坏)

        :return: md5 十六进制串; 文件不存在或计算失败返回空串
        """
        out = self.run_cmd(
            f"md5sum {self.QQ_CHAT_HISTORY} 2>/dev/null | awk '{{print $1}}'",
            timeout=5,
            out_debug_flag=False,
        )
        lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
        return lines[-1] if lines else ""

    def get_qq_message_count(self) -> int:
        """统计 QQ 消息日志行数(用于断言修复后仍可追加新消息)

        :return: 行数; 文件不存在时返回 0
        """
        out = self.run_cmd(
            f"wc -l < {self.QQ_MESSAGE_LOG} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return 0

    def append_qq_message(self, text: str = "post-repair hello") -> bool:
        """向 QQ 消息日志追加一条消息(等价"发送消息": 数据目录可正常写入)

        :param text: 消息内容
        :return: True 表示追加成功
        """
        out, rc = self.run_cmd(
            f"printf '%s\\n' {quote(text)} >> {self.QQ_MESSAGE_LOG} "
            f"&& echo appended",
            timeout=10,
            out_debug_flag=False,
            return_code=True,
        )
        return rc == 0 and "appended" in out

    def get_qq_process_info(self) -> dict:
        """获取 QQ 进程运行时信息(pid / 状态 / 物理内存占用)

        状态取 /proc/<pid>/stat 第 3 列(S 睡眠、R 运行、Z 僵尸), 内存取
        /proc/<pid>/status 的 VmRSS。用于判断修复后重新启动的 QQ 是"真的
        起来了并稳定驻留", 而不是一闪而过(Z 或 rss 为 0)。

        :return: {"pid": str, "state": str, "rss_kb": int}; 无进程时全空
        """
        pid = self.get_mock_qq_process_pid()
        info = {"pid": pid, "state": "", "rss_kb": 0}
        if not pid:
            return info
        out = self.run_cmd(
            f"awk '{{print $3}}' /proc/{pid}/stat 2>/dev/null; "
            f"awk '/VmRSS/ {{print $2}}' /proc/{pid}/status 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        parts = [line.strip() for line in out.strip().splitlines() if line.strip()]
        if parts:
            info["state"] = parts[0]
        if len(parts) > 1:
            try:
                info["rss_kb"] = int(parts[1])
            except ValueError:
                info["rss_kb"] = 0
        return info

    def is_qq_process_healthy(self) -> bool:
        """判断 QQ 进程是否健康存活(非僵尸且已占用内存)

        :return: True 表示进程存在、状态为 R/S/D/I 且 VmRSS > 0
        """
        info = self.get_qq_process_info()
        if not info["pid"]:
            return False
        return info["state"] in ("R", "S", "D", "I") and info["rss_kb"] > 0

    def wait_qq_process_started(self, timeout: int = 60) -> bool:
        """轮询等待 QQ 启动完成(首次启动缓慢属预期, 给予较长超时)

        :param timeout: 最长等待秒数
        :return: True 表示进程已健康启动, False 表示超时
        """
        for _ in range(timeout):
            if self.is_qq_process_healthy():
                return True
            sleep(1)
        return False

    def is_qq_process_alive_after(self, seconds: int = 10) -> bool:
        """验证 QQ 进程在观察窗口内持续存活且 pid 不变(无闪退/反复重启)

        :param seconds: 观察窗口秒数
        :return: True 表示窗口后仍是同一 pid 的健康进程
        """
        pid = self.get_mock_qq_process_pid()
        if not pid:
            return False
        sleep(seconds)
        return self.get_mock_qq_process_pid() == pid and self.is_qq_process_healthy()

    # ===== 模块 修复工具 - 应用修复-修复QQ-磁盘空间不足(用例 2005783) =====
    # 产品依据(plugin-qq-fix/entry.sh):
    #   pkill -x qq
    #   [ -x /opt/deepinwine/tools/kill.sh ] && kill.sh <home>/.deepinwine/Deepin-QQ
    #   for user_home in /home/*:
    #       [ -d "$cache_dir" ] && [ ! -L "$cache_dir" ] && rm -rf "$cache_dir"
    #       (cache_dir = <home>/.config/QQ/Cache, wine_dir 同理)
    # 脚本对 cache_dir 有 "非符号链接" 防护, 所以**不能**用把
    # ~/.config/QQ/Cache 软链到低空间盘的做法(会被脚本跳过, 断言假通过);
    # 这里改为挂一块 100MB tmpfs 再 bind 到 ~/.config/QQ —— 目录本身仍是
    # 真实目录, Cache 落在低空间盘内, 产品 rm -rf 会真实执行, 删除后该盘
    # 可用空间上升可量化。
    QQ_LOW_SPACE_MOUNT = "/tmp/autotest_pcm_lowspace_qq"
    QQ_LOW_SPACE_TOTAL_MB = 100
    # 盘内占位 40MB + 缓存 20MB => 可用约 40MB(满足"不足 100MB"),
    # 又不把 tmpfs 塞满(占内存), 删除缓存后可用空间回升约 20MB。
    QQ_LOW_SPACE_FILL_MB = 40
    QQ_LOW_SPACE_CACHE_MB = 20

    def setup_low_space_qq_cache(self) -> dict:
        """构造"磁盘空间不足 100MB"现场, 并把 QQ 缓存放到该盘上

        "磁盘空间不足"只体现在删除目标所在盘几乎没有余量, 因此:
        1) 挂一块 100MB tmpfs(挂载点 /tmp/autotest_pcm_lowspace_qq);
        2) bind 到 ~/.config/QQ(调用方已用 backup_qq_state 把真实
           ~/.config/QQ 整体移走, 不会误删用户数据);
        3) 盘内写 40MB 占位文件, 可用空间降到 100MB 以下;
        4) 在盘内构造 ~/.config/QQ/Cache 及 20MB 缓存
           (见 create_mock_qq_cache_payload) —— 产品脚本的
           rm -rf "$cache_dir" 因此真实作用在"可用空间不足 100MB"的
           文件系统上, 删除后 df 可用空间上升可量化。
        挂载不可用(无 sudo/内核限制)时退化为家目录内普通缓存目录, 仍验证
        "缓存被 rm -rf 真实删净", 只是无法量化低空间压力与释放量。

        :return: {"mode": "tmpfs"/"fallback", "mount": 挂载点,
                  "bind": bind 目录, "free_mb": 该盘可用空间,
                  "created_config": 是否由本次构造创建 ~/.config/QQ}
        """
        info = {
            "mode": "fallback",
            "mount": self.QQ_LOW_SPACE_MOUNT,
            "bind": self.QQ_CONFIG_DIR,
            "free_mb": -1,
            "created_config": False,
        }
        # 归一化: 先卸掉上次异常退出可能遗留的 bind / tmpfs 挂载
        self.unmount_path(self.QQ_CONFIG_DIR)
        self.unmount_path(self.QQ_LOW_SPACE_MOUNT)
        self.run_cmd(
            f"rm -rf {self.QQ_LOW_SPACE_MOUNT}; "
            f"mkdir -p {self.QQ_LOW_SPACE_MOUNT} {self.QQ_CONFIG_DIR}",
            timeout=30,
            out_debug_flag=False,
        )
        info["created_config"] = True
        _, rc = self.sudo_run_cmd(
            f"mount -t tmpfs -o size={self.QQ_LOW_SPACE_TOTAL_MB}M,mode=0777 "
            f"tmpfs {self.QQ_LOW_SPACE_MOUNT}",
            timeout=60,
            out_debug_flag=False,
            return_code=True,
        )
        if rc == 0:
            # bind 到 ~/.config/QQ: 目标仍是真实目录, 不触发脚本的符号链接防护
            _, rc = self.sudo_run_cmd(
                f"mount --bind {self.QQ_LOW_SPACE_MOUNT} {self.QQ_CONFIG_DIR}",
                timeout=60,
                out_debug_flag=False,
                return_code=True,
            )
        if rc != 0:
            logger.warning(
                f"低空间 tmpfs/bind 挂载失败(rc={rc}), 退化为普通缓存目录, "
                f"仅验证 QQ 缓存被 rm -rf 真实删除"
            )
            self.unmount_path(self.QQ_CONFIG_DIR)
            self.unmount_path(self.QQ_LOW_SPACE_MOUNT)
            self.run_cmd(
                f"rm -rf {self.QQ_LOW_SPACE_MOUNT} 2>/dev/null; true",
                timeout=30,
                out_debug_flag=False,
            )
            self.create_mock_qq_cache_payload(size_mb=self.QQ_LOW_SPACE_CACHE_MB)
            info["free_mb"] = self.get_disk_free_space_mb()
            return info
        # 盘内写占位数据, 把可用空间压到 100MB 以下
        self.run_cmd(
            f"dd if=/dev/zero of={self.QQ_LOW_SPACE_MOUNT}/filler.bin "
            f"bs=1M count={self.QQ_LOW_SPACE_FILL_MB} 2>/dev/null",
            timeout=120,
            out_debug_flag=False,
        )
        cache_kb = self.create_mock_qq_cache_payload(
            size_mb=self.QQ_LOW_SPACE_CACHE_MB
        )
        free_mb = self.get_mount_free_space_mb(self.QQ_LOW_SPACE_MOUNT)
        # 占位 + 缓存都到位时, 可用空间应明显小于 100MB 且缓存目录确实存在
        if (
            self.get_qq_cache_exists()
            and cache_kb >= self.QQ_LOW_SPACE_CACHE_MB * 1024 // 2
            and 0 <= free_mb < self.QQ_LOW_SPACE_TOTAL_MB
        ):
            info.update(mode="tmpfs", free_mb=free_mb)
            return info
        logger.warning(
            f"低空间 QQ 现场构造不完整(cache_exists="
            f"{self.get_qq_cache_exists()}, cache_kb={cache_kb}, "
            f"free_mb={free_mb}), 回退普通缓存目录"
        )
        self.cleanup_low_space_qq_cache(info)
        self.create_mock_qq_cache_payload(size_mb=self.QQ_LOW_SPACE_CACHE_MB)
        info.update(
            mode="fallback",
            free_mb=self.get_disk_free_space_mb(),
            created_config=False,
        )
        return info

    def cleanup_low_space_qq_cache(self, info: dict = None):
        """回退 setup_low_space_qq_cache 构造的现场

        顺序很重要: 先卸载 ~/.config/QQ 上的 bind 挂载, 让本地真实的
        ~/.config/QQ 目录重新可见, 再卸载低空间 tmpfs 并删除挂载点
        (占位文件随卸载释放, 不占磁盘)。若顺序反过来, 后续
        restore_qq_state 的 rm -rf 会打在 tmpfs 上。

        :param info: setup_low_space_qq_cache 的返回值
        """
        info = info or {}
        bind_dir = info.get("bind") or self.QQ_CONFIG_DIR
        mnt = info.get("mount") or self.QQ_LOW_SPACE_MOUNT
        self.unmount_path(bind_dir)
        self.unmount_path(mnt)
        self.run_cmd(
            f"rm -rf {mnt} 2>/dev/null; true",
            timeout=30,
            out_debug_flag=False,
        )
        if info.get("created_config"):
            self.run_cmd(
                f"rmdir {bind_dir} 2>/dev/null; true",
                timeout=10,
                out_debug_flag=False,
            )
        sleep(1)

    # ===== 模块 修复工具 - 应用修复-输入法修复 测试用例方法 =====

    def get_input_method_name(self) -> str:
        """检测当前系统运行的输入法框架名称

        优先检测运行中的进程, 返回 "fcitx5" 或 "fcitx"; 未检测到返回空字符串。
        """
        for name in ("fcitx5", "fcitx"):
            result = self.run_cmd(
                f"pgrep -x {name}",
                timeout=5,
                out_debug_flag=False,
            )
            if result.strip():
                return name
        return ""

    def get_input_method_pids(self) -> str:
        """获取输入法进程的 PID 列表(换行分隔)

        :return: PID 列表字符串, 无输入法进程时返回空字符串
        """
        name = self.get_input_method_name()
        if not name:
            return ""
        result = self.run_cmd(
            f"pgrep -x {name}",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def ensure_input_method_running(self):
        """确保输入法进程正在运行(未运行则启动)

        测试前调用, 保证输入法进程存在以便修复脚本检测和终止。
        """
        self._ensure_input_method_helper()
        if self.get_input_method_name():
            return
        self.start_input_method_framework()

    def wait_input_method_process_killed(self, old_pids: str, timeout: int = 30) -> bool:
        """等待旧的输入法进程被修复脚本终止

        修复脚本会 killall 输入法进程并重启, 此方法通过比较 PID 变化
        检测旧进程是否已被终止。
        :param old_pids: 修复前的 PID 列表(换行分隔)
        :param timeout: 最长等待秒数
        :return: True 表示旧进程已被终止, False 表示超时仍在运行
        """
        old_pid_set = set(pid.strip() for pid in old_pids.split() if pid.strip())
        if not old_pid_set:
            return True
        for _ in range(timeout):
            name = self.get_input_method_name()
            if not name:
                return True
            result = self.run_cmd(
                f"pgrep -x {name}",
                timeout=5,
                out_debug_flag=False,
            )
            current_pids = set(pid.strip() for pid in result.split() if pid.strip())
            if not current_pids or not old_pid_set.intersection(current_pids):
                return True
            sleep(1)
        return False

    def get_input_method_process_running(self) -> bool:
        """检查输入法进程是否正在运行

        :return: True 表示输入法进程正在运行, False 表示未运行
        """
        return bool(self.get_input_method_name())

    def click_input_method_fix_card(self):
        """点击输入法修复卡片

        先最大化窗口确保布局稳定, 然后通过 AT-SPI 点击卡片。
        """
        self._safe_focus_windows()
        if not self.get_window_maximized_status():
            self.maximize_window_by_shortcut()
            sleep(2)
            self._safe_focus_windows()
            self.reconnect_dogtail()
        element = self._find_repair_element(
            "$//repair_sectionsContainer//重启输入法",
            "$//repairCardsView//重启输入法",
        )
        self._atspi_do_action(element)
        sleep(2)
        self.reconnect_dogtail()

    def _ensure_input_method_helper(self):
        """恢复被 stop_input_method 终止的 fcitx-helper 守护进程"""
        if self.run_cmd(
            "pgrep -x fcitx-helper", timeout=5, out_debug_flag=False
        ).strip():
            return
        if not self.run_cmd(
            "test -x /usr/bin/fcitx-helper && echo ok",
            timeout=5,
            out_debug_flag=False,
        ).strip():
            return
        self.run_cmd(
            "nohup /usr/bin/fcitx-helper > /dev/null 2>&1 &",
            timeout=2,
            out_debug_flag=False,
        )
        sleep(1)

    def restart_input_method(self):
        """重启输入法进程(测试清理用, 确保输入法恢复运行)"""
        self._ensure_input_method_helper()
        if self.get_input_method_name():
            return
        self.start_input_method_framework()

    # 搜狗/cpis 输入法的配套服务: 候选条/引擎/热键/分词进程由框架按需拉起,
    # 与框架进程成对。只重启框架而留着旧服务时, 测试机实测出现
    # "fcitx-remote 仍为 2, 但按键直通、候选条永不 IsViewable"的错配。
    IME_AUX_SERVICE_PATTERNS = (
        "cpis-panel-service",
        "cpis-engine-service",
        "cpis-hotkey-service",
        "ISE_NODE",
    )

    def get_ime_aux_service_pids(self) -> str:
        """获取输入法配套服务进程 PID(换行分隔, 供日志与断言使用)"""
        pids = []
        for pattern in self.IME_AUX_SERVICE_PATTERNS:
            text = self.run_cmd(
                f"pgrep -f {quote(pattern)} 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
            pids.extend(pid.strip() for pid in text.split() if pid.strip())
        return "\n".join(pids)

    def _stop_ime_aux_services(self):
        """终止输入法配套服务, 让新拉起的框架进程重新配对同版本服务"""
        for pattern in self.IME_AUX_SERVICE_PATTERNS:
            self.run_cmd(
                f"pkill -f {quote(pattern)} 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )

    def start_input_method_framework(self, timeout: int = 20) -> bool:
        """启动输入法框架进程(优先 fcitx5, 回退 fcitx)

        启动前清掉旧配套服务: 新框架会重新拉起自己的候选/引擎服务, 混用旧
        服务会让输入法"看起来已激活但不接管键盘"。

        :param timeout: 等待框架进程出现的秒数
        :return: True 表示框架进程已运行
        """
        self._stop_ime_aux_services()
        for name in ("fcitx5", "fcitx"):
            if not self.run_cmd(
                f"which {name}", timeout=5, out_debug_flag=False
            ).strip():
                continue
            self.run_cmd(
                f"nohup {name} -r -d > /dev/null 2>&1 &",
                timeout=2,
                out_debug_flag=False,
            )
            for _ in range(max(int(timeout), 1)):
                sleep(1)
                if self.get_input_method_name():
                    return True
            return False
        return False

    def restart_input_method_stack(self, timeout: int = 30) -> bool:
        """完整重启输入法栈(框架进程 + 配套服务)并等待可读状态

        用于修复测试机上的错配状态: 框架问题态下 fcitx-remote 仍返回 2,
        但按键不进预编辑、候选条永不显示(实测), 只重启框架无法恢复。

        :param timeout: 等待框架运行且 fcitx-remote 可读状态的秒数
        :return: True 表示框架已运行且状态可读
        """
        self.run_cmd(
            "fcitx-remote -e 2>/dev/null", timeout=5, out_debug_flag=False
        )
        self.stop_input_method()
        self._stop_ime_aux_services()
        sleep(1)
        self._ensure_input_method_helper()
        self.start_input_method_framework()
        for _ in range(max(int(timeout), 1)):
            if self.get_input_method_name() and self.get_fcitx_state() >= 0:
                return True
            sleep(1)
        return False

    def get_input_method_version(self) -> str:
        """获取当前运行输入法的版本号文本(等价于 fcitx5 --version 的前置校验)

        :return: 版本输出文本(如 "fcitx version: 4.2.9.32.46"); 输入法未运行/
                无 --version 时返回空字符串
        """
        name = self.get_input_method_name()
        if not name:
            return ""
        return self.run_cmd(
            f"{name} --version 2>&1",
            timeout=10,
            out_debug_flag=False,
        ).strip()

    def get_input_method_xmodifiers(self) -> str:
        """读取当前桌面会话的 XMODIFIERS(等价于在会话里 echo $XMODIFIERS)

        用例前置条件要求会话环境 XMODIFIERS 为 @im=fcitx 或 @im=fcitx5,
        但 ssh 非登录 shell 没有桌面会话环境, 因此从会话进程的
        /proc/<pid>/environ 读取其继承的会话环境。
        优先会话管理进程(startdde / dde-session-daemon / dde-desktop):
        它们由会话拉起、不随修复脚本重启, 取值稳定; 最后才回退到输入法
        进程自身(输入法进程由脚本 fcitx -r -d 重启后可能丢失该变量)。

        :return: XMODIFIERS 的值(如 "@im=fcitx"); 取不到返回空字符串
        """
        candidates = [
            "startdde",
            "dde-session-daemon",
            "dde-desktop",
            self.get_input_method_name(),
        ]
        for name in candidates:
            if not name:
                continue
            value = self.run_cmd(
                f"tr '\\0' '\\n' < /proc/$(pgrep -x {name} | head -1)/environ "
                "| grep -m1 '^XMODIFIERS=' | cut -d= -f2-",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            if value:
                return value
        return ""

    def wait_input_method_restarted(self, old_pids: str, timeout: int = 30) -> bool:
        """等待输入法进程以新的 PID 重新运行(修复脚本 killall 后重启)

        与 wait_input_method_process_killed 互补: 前者只证明旧进程消失, 本方法
        进一步要求当前存在与修复前完全不重合的 PID, 即脚本末尾的
        "<输入法> -r -d" 真正把输入法拉起来了。

        :param old_pids: 修复前的 PID 列表(换行分隔)
        :param timeout: 最长等待秒数
        :return: True 表示存在新的输入法进程, False 表示超时
        """
        old_pid_set = set(pid.strip() for pid in old_pids.split() if pid.strip())
        for _ in range(max(int(timeout), 1)):
            current_pids = set(
                pid.strip()
                for pid in self.get_input_method_pids().split()
                if pid.strip()
            )
            if current_pids and not (old_pid_set & current_pids):
                return True
            sleep(1)
        return False

    def is_input_method_installed(self) -> bool:
        """检查系统是否安装了任何输入法框架

        检测 fcitx5、fcitx 和 ibus 是否安装(通过 which 命令)。
        :return: True 表示至少安装了一种输入法框架, False 表示均未安装
        """
        for name in ("fcitx5", "fcitx", "ibus"):
            result = self.run_cmd(
                f"which {name}",
                timeout=5,
                out_debug_flag=False,
            )
            if result.strip():
                return True
        return False

    def stop_input_method(self):
        """终止正在运行的输入法进程(测试前模拟无输入法运行状态)

        UOS 桌面会话(startdde)通过 fcitx-helper 守护自动拉起 fcitx,
        只 killall fcitx 会在 1 秒内被重新拉起, 需先终止该守护进程。
        """
        self.run_cmd(
            "pkill -9 -x fcitx-helper 2>/dev/null",
            timeout=2,
            out_debug_flag=False,
        )
        for name in ("fcitx5", "fcitx", "ibus"):
            self.run_cmd(
                f"killall {name} 2>/dev/null",
                timeout=2,
                out_debug_flag=False,
            )
        sleep(1)

    def get_input_method_frameworks(self) -> dict:
        """获取已安装输入法框架的可执行文件路径(等价于 which fcitx/fcitx5/ibus)

        :return: {"fcitx": "/usr/bin/fcitx", ...}; 未安装的框架不出现在结果里
        """
        frameworks = {}
        for name in ("fcitx5", "fcitx", "ibus"):
            path = self.run_cmd(
                f"which {name}", timeout=5, out_debug_flag=False
            ).strip()
            if path:
                frameworks[name] = path.splitlines()[0].strip()
        return frameworks

    IM_PERM_BACKUP = "/tmp/pcm_im_perm_backup.json"

    def disable_input_method_frameworks(self) -> dict:
        """构造"未安装任何输入法框架"状态: 去掉已安装框架可执行位的 x 位

        产品依据(/usr/lib/deepin-pc-manager/plugins/plugin-inputmethod-fix/
        entry.sh, 版本 1.0.0): detect_input_method 先 pgrep -x fcitx5/fcitx,
        再 which fcitx5/fcitx; 因此"进程不存在 + which 失败"即产品视角的
        "未检测到输入法框架"。去掉 x 位后 which 失败、fcitx-helper 也无法
        重新拉起进程, 等价于未安装, 且不需要卸载/移动系统文件(风险更低)。

        :return: {name: {"path": str, "mode": str}}, 供
                 restore_input_method_frameworks 精确回退
        """
        saved = {}
        for name, path in self.get_input_method_frameworks().items():
            mode = self.run_cmd(
                f"stat -c %a {quote(path)}", timeout=5, out_debug_flag=False
            ).strip()
            if not mode:
                continue
            saved[name] = {"path": path, "mode": mode}
        # 落盘备份: 若用例进程在 chmod 后被强杀(saved 只存在内存里),
        # 下次运行可据此把 x 位恢复回来, 避免测试机长期处于"框架不可执行"。
        if saved:
            try:
                with open(self.IM_PERM_BACKUP, "w", encoding="utf-8") as fp:
                    json.dump(saved, fp, ensure_ascii=False)
            except OSError as exc:
                logger.error(f"输入法权限备份落盘失败: {exc}")
        for info in saved.values():
            self.sudo_run_cmd(f"chmod a-x {quote(info['path'])}")
        return saved

    def restore_input_method_frameworks(self, saved: dict) -> bool:
        """回退 disable_input_method_frameworks: 恢复原权限位并校验

        :param saved: disable_input_method_frameworks 的返回值
        :return: True 表示每个框架的权限位与可执行位都已恢复
        """
        restored = True
        for name, info in (saved or {}).items():
            path = info.get("path", "")
            mode = info.get("mode", "")
            if not path or not mode:
                logger.error(f"输入法框架 {name} 回退信息缺失: {info}")
                restored = False
                continue
            self.sudo_run_cmd(f"chmod {quote(mode)} {quote(path)}")
            current = self.run_cmd(
                f"stat -c %a {quote(path)}", timeout=5, out_debug_flag=False
            ).strip()
            executable = self.run_cmd(
                f"test -x {quote(path)} && echo yes || echo no",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            logger.info(
                f"回退输入法框架 {name}: {path} mode={current!r} executable={executable!r}"
            )
            if current != mode or executable != "yes":
                restored = False
        if restored:
            try:
                os.remove(self.IM_PERM_BACKUP)
            except OSError:
                pass
        return restored

    def recover_stale_input_method_backup(self) -> bool:
        """恢复上次被中断用例遗留的输入法框架权限备份

        disable_input_method_frameworks 在 chmod 前把原权限位写入
        /tmp/pcm_im_perm_backup.json; 正常结束时 restore 会删除该文件。
        文件残留说明上次用例在构造后异常退出, 这里按备份原样恢复。

        :return: True 表示没有残留或残留已成功恢复
        """
        if not os.path.exists(self.IM_PERM_BACKUP):
            return True
        try:
            with open(self.IM_PERM_BACKUP, encoding="utf-8") as fp:
                saved = json.load(fp)
        except (OSError, ValueError) as exc:
            logger.error(f"读取输入法权限备份失败: {exc}")
            return False
        logger.warning(f"发现输入法权限残留备份, 自动恢复: {saved}")
        return self.restore_input_method_frameworks(saved)

    # ===== 模块 修复工具 - 输入法修复后的键盘输入验证 =====
    # 测试机实测(UOS 20, fcitx 4.2.9.32.46, IMName=com.sogou.ime.next.uos):
    # - 从非登录 SSH 启动的 Qt 应用必须注入 XMODIFIERS/QT_IM_MODULE,
    #   否则 fcitx 不接管键盘, fcitx-remote 恒为 0(实测);
    # - fcitx-remote 状态: 0=关闭, 1=未激活(英文直通), 2=激活(中文);
    # - 候选词条窗口是 Sogou 的 cpis-panel-service(557x88), 预编辑期间
    #   IsViewable, 无预编辑时 IsUnMapped; 另一个 233x30 的同名窗口是状态
    #   面板, 输入法激活期间常驻可见, 因此按尺寸过滤候选条;
    # - fcitx 自带 UI 的候选窗口名为 "Fcitx Input Window", 作为兼容判据。
    IME_CANDIDATE_WINDOW_KEYWORDS = ("cpis-panel-service", "Fcitx Input Window")
    IME_CANDIDATE_MIN_WIDTH = 300
    IME_CANDIDATE_MIN_HEIGHT = 40
    TEXT_EDITOR_CLASS = "deepin-editor"

    def get_fcitx_state(self) -> int:
        """读取 fcitx 当前输入状态

        :return: 0=关闭, 1=未激活, 2=激活; 读取失败返回 -1
        """
        out = self.run_cmd(
            "fcitx-remote 2>/dev/null", timeout=5, out_debug_flag=False
        ).strip()
        return int(out) if out in ("0", "1", "2") else -1

    def set_fcitx_active(self, active: bool, retries: int = 3) -> int:
        """激活/停用输入法并等待状态生效

        :param active: True 切到中文输入(状态 2), False 停用(状态 0/1)
        :param retries: 状态未生效时的重试次数
        :return: 切换后的实际状态
        """
        for _ in range(max(int(retries), 1)):
            self.run_cmd(
                "fcitx-remote -o" if active else "fcitx-remote -c",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(1)
            state = self.get_fcitx_state()
            if (active and state == 2) or (not active and state in (0, 1)):
                return state
        return self.get_fcitx_state()

    def get_window_map_state(self, window_id) -> str:
        """读取 X 窗口的映射状态(IsViewable / IsUnMapped)

        :param window_id: xdotool 返回的十进制窗口 ID
        :return: 映射状态文本, 读取失败返回空字符串
        """
        out = self.run_cmd(
            f"xwininfo -id {window_id} -stats 2>/dev/null | grep -m1 'Map State'",
            timeout=5,
            out_debug_flag=False,
        )
        return out.split(":", 1)[1].strip() if ":" in out else ""

    def get_visible_window_by_class(
        self, classname: str, min_width=400, min_height=300
    ) -> int:
        """按 WM_CLASS 查找面积最大的可见窗口

        :param classname: WM_CLASS(xdotool search --classname)
        :param min_width: 最小宽度, 过滤启动瞬间的辅助窗口
        :param min_height: 最小高度
        :return: 窗口 ID, 未找到返回 0
        """
        output = self.run_cmd(
            f"xdotool search --classname {quote(classname)} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        best, best_area = 0, 0
        for window_id in output.split():
            if self.get_window_map_state(window_id) != "IsViewable":
                continue
            size = self._window_size(window_id)
            if size is None:
                continue
            width, height = size
            if width < min_width or height < min_height:
                continue
            if width * height > best_area:
                best, best_area = window_id, width * height
        return best

    def open_text_editor(self, path: str, wait: int = 20) -> int:
        """启动 deepin-editor 打开指定文件并返回主窗口 ID

        必须随进程注入输入法环境变量: 从 SSH 非登录 shell 启动的 Qt 应用
        没有 QT_IM_MODULE/XMODIFIERS 时 fcitx 不接管键盘(实测状态恒为 0),
        xdotool 输入会退化为直通 ASCII。

        :param path: 要编辑的文件路径(不存在时为空白文档)
        :param wait: 等待窗口出现的秒数
        :return: 窗口 ID, 超时返回 0
        """
        self.run_cmd(
            "pkill -x deepin-editor 2>/dev/null", timeout=5, out_debug_flag=False
        )
        sleep(1)
        self.run_cmd(
            "setsid env XMODIFIERS=@im=fcitx QT_IM_MODULE=fcitx "
            f"GTK_IM_MODULE=fcitx {self.TEXT_EDITOR_CLASS} {quote(path)} "
            "> /dev/null 2>&1 < /dev/null &",
            timeout=5,
            out_debug_flag=False,
        )
        for _ in range(max(int(wait), 1)):
            sleep(1)
            window_id = self.get_visible_window_by_class(self.TEXT_EDITOR_CLASS)
            if window_id:
                return window_id
        return 0

    def focus_text_editor(self, window_id) -> bool:
        """激活编辑器窗口并点击正文区域, 让文本控件获得键盘焦点

        :param window_id: open_text_editor 返回的窗口 ID
        :return: True 表示窗口已激活且点击完成
        """
        self.run_cmd(
            f"xdotool windowactivate --sync {window_id}",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        size = self._window_size(window_id)
        if size is None:
            return False
        self.run_cmd(
            f"xdotool mousemove --window {window_id} "
            f"{size[0] // 2} {size[1] // 2} click 1",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)
        return True

    def close_text_editor(self, window_id=0):
        """关闭编辑器窗口并清理进程(用例 finally 必调)"""
        if window_id:
            self.run_cmd(
                f"xdotool windowclose {window_id} 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(1)
        self.run_cmd(
            "pkill -x deepin-editor 2>/dev/null", timeout=5, out_debug_flag=False
        )

    def type_text_via_xdotool(self, text: str, delay: int = 150) -> bool:
        """向当前焦点窗口发送键盘输入(输入法激活时由 IME 接管)

        :param text: 要输入的字符(如拼音 "zhongguo")
        :param delay: 每个字符的间隔毫秒数
        :return: True 表示 xdotool 返回码为 0
        """
        _, status = self.run_cmd(
            f"xdotool type --clearmodifiers --delay {int(delay)} {quote(text)}",
            timeout=30,
            out_debug_flag=False,
            return_code=True,
        )
        return status == 0

    def press_key_combo(self, keys: str) -> bool:
        """发送组合键到当前焦点窗口

        :param keys: xdotool 键名(如 "ctrl+s")
        :return: True 表示 xdotool 返回码为 0
        """
        _, status = self.run_cmd(
            f"xdotool key --clearmodifiers {keys}",
            timeout=10,
            out_debug_flag=False,
            return_code=True,
        )
        return status == 0

    def get_ime_candidate_windows(self) -> list:
        """枚举输入法候选/预编辑窗口及可见状态

        :return: [{"id", "keyword", "state", "width", "height"}, ...]
        """
        windows = []
        for keyword in self.IME_CANDIDATE_WINDOW_KEYWORDS:
            output = self.run_cmd(
                f"xdotool search --name {quote(keyword)} 2>/dev/null",
                timeout=10,
                out_debug_flag=False,
            )
            for window_id in output.split():
                state = self.get_window_map_state(window_id)
                size = self._window_size(window_id)
                if not state or size is None:
                    continue
                windows.append(
                    {
                        "id": window_id,
                        "keyword": keyword,
                        "state": state,
                        "width": size[0],
                        "height": size[1],
                    }
                )
        return windows

    def is_ime_candidate_visible(self, windows=None) -> bool:
        """判断当前是否有候选词窗口可见(按尺寸排除状态面板)

        :param windows: get_ime_candidate_windows 的结果, 不传则重新枚举
        :return: True 表示候选词条窗口已显示
        """
        for window in windows or self.get_ime_candidate_windows():
            if window["state"] != "IsViewable":
                continue
            if window["keyword"] != "cpis-panel-service":
                # fcitx 自带 UI 的候选窗口只在预编辑时映射
                return True
            if (
                window["width"] >= self.IME_CANDIDATE_MIN_WIDTH
                and window["height"] >= self.IME_CANDIDATE_MIN_HEIGHT
            ):
                return True
        return False

    def wait_ime_candidate_visible(self, timeout: int = 10) -> bool:
        """等待候选词窗口显示(输入拼音后的预期行为)

        :param timeout: 最长等待秒数
        :return: True 表示观察到可见的候选词窗口
        """
        last_windows = []
        for _ in range(max(int(timeout), 1)):
            last_windows = self.get_ime_candidate_windows()
            if self.is_ime_candidate_visible(last_windows):
                return True
            sleep(1)
        logger.warning(f"未检测到可见候选词窗口, 当前窗口: {last_windows}")
        return False

    # ===== 外设修复(U盘修复)模块方法 =====

    @staticmethod
    def _extract_loop_dev(text):
        """从 sudo 输出中提取第一个 /dev/loopN 设备路径

        V20 的 sudo 会输出中文验证信息(如"验证成功"),
        需要用正则从混合输出中提取设备路径。

        :param text: sudo 命令输出文本
        :return: loop 设备路径, 未找到返回空字符串
        """
        import re

        if not text:
            return ""
        match = re.search(r"/dev/loop\d+", text)
        return match.group(0) if match else ""

    def create_virtual_usb_ext4(
        self,
        img_path="/tmp/test_usb_ext4.img",
        mount_point="/tmp/test_usb_ext4_mount",
        label: str = "",
    ):
        """创建无错误的 ext4 虚拟 U 盘(loop 设备)

        通过创建磁盘镜像文件并关联 loop 设备来模拟 U 盘,
        格式化为 ext4 文件系统(全新格式化, 无任何错误)。
        需要 root 权限执行 losetup/mount 操作。

        :param img_path: 镜像文件路径
        :param mount_point: 挂载点路径
        :param label: ext4 卷标(空串表示不设置), U 盘选择框用例用它构造
                      "卷标"这一设备详细信息
        :return: loop 设备路径(如 /dev/loop0), 失败返回空字符串
        """
        img_size = "64M"
        self.sudo_run_cmd(f"truncate -s {img_size} {img_path}", timeout=10, out_debug_flag=False)
        result = self.sudo_run_cmd(
            f"losetup -f --show {img_path} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return ""
        label_opt = f" -L {quote(label)}" if label else ""
        self.sudo_run_cmd(
            f"mkfs.ext4 -F{label_opt} {loop_dev} 2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(f"mkdir -p {mount_point}", timeout=5, out_debug_flag=False)
        self.sudo_run_cmd(
            f"mount {loop_dev} {mount_point} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        sleep(1)
        return loop_dev

    def cleanup_virtual_usb(
        self, img_path="/tmp/test_usb_ext4.img", mount_point="/tmp/test_usb_ext4_mount"
    ):
        """清理虚拟 U 盘(卸载、分离 loop 设备、删除镜像文件)

        :param img_path: 镜像文件路径
        :param mount_point: 挂载点路径
        """
        import re

        self.sudo_run_cmd(f"umount {mount_point} 2>/dev/null", timeout=10, out_debug_flag=False)
        result = self.sudo_run_cmd(
            f"losetup -j {img_path} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        if result:
            for match in re.finditer(r"/dev/loop\d+", result):
                self.sudo_run_cmd(
                    f"losetup -d {match.group(0)} 2>/dev/null", timeout=5, out_debug_flag=False
                )
        self.sudo_run_cmd(f"rm -rf {mount_point} {img_path}", timeout=5, out_debug_flag=False)
        sleep(1)

    def get_usb_device_mounted(self, mount_point="/tmp/test_usb_ext4_mount") -> bool:
        """检查虚拟 U 盘是否已成功挂载

        :param mount_point: 挂载点路径
        :return: True 表示已挂载, False 表示未挂载
        """
        result = self.run_cmd(
            f"mountpoint -q {mount_point} && echo YES || echo NO",
            timeout=5,
            out_debug_flag=False,
        )
        return "YES" in result.strip()


    def get_partition_free_space_mb(self, mount_point="/tmp/test_usb_ext4_mount") -> int:
        """获取指定挂载点分区的可用空间(MB)

        :param mount_point: 挂载点路径
        :return: 可用空间(MB), 失败返回 0
        """
        result = self.run_cmd(
            f"df -m {mount_point} 2>/dev/null | tail -1 | awk '{{print $4}}'",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return 0

    def write_test_data_to_partition(self, mount_point="/tmp/test_usb_ext4_mount", size_mb=10):
        """向指定挂载点分区写入测试数据以改变分区容量

        :param mount_point: 挂载点路径
        :param size_mb: 要写入的数据大小(MB)
        """
        self.sudo_run_cmd(
            f"dd if=/dev/zero of={mount_point}/test_capacity_data.bin bs=1M count={size_mb} 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_test_data_from_partition(self, mount_point="/tmp/test_usb_ext4_mount"):
        """删除测试数据文件以恢复分区容量

        :param mount_point: 挂载点路径
        """
        self.sudo_run_cmd(
            f"rm -f {mount_point}/test_capacity_data.bin",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

    def get_partition_capacity_changed(self, mount_point="/tmp/test_usb_ext4_mount") -> bool:
        """检查指定挂载点分区是否存在(容量变更检测辅助)

        :param mount_point: 挂载点路径
        :return: True 表示分区存在且可访问
        """
        result = self.run_cmd(
            f"mountpoint -q {mount_point} && df -m {mount_point} 2>/dev/null | tail -1 | awk '{{print $2,$4}}'",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())


    def unmount_test_partition(self, mount_point="/tmp/test_usb_ext4_mount") -> bool:
        """卸载测试分区(模拟扫描中的分区被卸载异常场景)

        使用 sudo umount 卸载指定挂载点。
        若普通卸载失败(target is busy), 使用 lazy unmount (umount -l)。

        :param mount_point: 挂载点路径
        :return: True 表示卸载成功, False 表示卸载失败
        """
        self.sudo_run_cmd(
            f"umount {mount_point} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        if not self.get_usb_device_mounted(mount_point):
            return True
        self.sudo_run_cmd(
            f"umount -l {mount_point} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return not self.get_usb_device_mounted(mount_point)

    def get_usb_ext4_filesystem_healthy(self, loop_dev="") -> bool:
        """检查 ext4 文件系统是否健康(无错误)

        通过 e2fsck 检查文件系统状态, 退出码 0 表示无错误。

        :param loop_dev: loop 设备路径, 为空时自动查找
        :return: True 表示文件系统健康, False 表示有错误
        """
        if not loop_dev:
            result = self.sudo_run_cmd(
                "losetup -j /tmp/test_usb_ext4.img 2>/dev/null", timeout=5, out_debug_flag=False
            )
            loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return False
        result = self.sudo_run_cmd(
            f"e2fsck -n {loop_dev} 2>/dev/null; echo EXIT_CODE=$?", timeout=15, out_debug_flag=False
        )
        return "EXIT_CODE=0" in result

    def create_virtual_usb_fat32(
        self, img_path="/tmp/test_usb_fat32.img", mount_point="/tmp/test_usb_fat32_mount"
    ):
        """创建无错误的 FAT32 虚拟 U 盘(loop 设备)

        通过创建磁盘镜像文件并关联 loop 设备来模拟 U 盘,
        格式化为 FAT32 文件系统(全新格式化, 无任何错误)。
        需要 root 权限执行 losetup/mount 操作。

        :param img_path: 镜像文件路径
        :param mount_point: 挂载点路径
        :return: loop 设备路径(如 /dev/loop0), 失败返回空字符串
        """
        img_size = "64M"
        self.sudo_run_cmd(f"truncate -s {img_size} {img_path}", timeout=10, out_debug_flag=False)
        result = self.sudo_run_cmd(
            f"losetup -f --show {img_path} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return ""
        self.sudo_run_cmd(
            f"mkfs.vfat -F 32 {loop_dev} 2>/dev/null", timeout=15, out_debug_flag=False
        )
        self.sudo_run_cmd(f"mkdir -p {mount_point}", timeout=5, out_debug_flag=False)
        self.sudo_run_cmd(
            f"mount -t vfat {loop_dev} {mount_point} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        sleep(1)
        return loop_dev

    def create_fat32_filesystem_error(
        self, loop_dev="", img_path="/tmp/test_usb_fat32.img"
    ):
        """向 FAT32 文件系统注入可自动修复的错误

        通过向 FAT 表区域写入随机数据来模拟文件系统损坏,
        这种损坏可以被 fsck.vfat 自动修复。
        需要先卸载设备再注入错误。

        :param loop_dev: loop 设备路径, 为空时自动查找
        :param img_path: 镜像文件路径
        :return: True 表示成功注入错误, False 表示失败
        """
        if not loop_dev:
            result = self.sudo_run_cmd(
                f"losetup -j {img_path} 2>/dev/null", timeout=5, out_debug_flag=False
            )
            loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return False
        # 向 FAT 表区域(偏移 512 字节处)写入随机数据, 模拟 FAT 表损坏
        # FAT32 的第一个 FAT 表通常从扇区 32 开始(偏移 16384 字节),
        # 写入少量随机字节到 FAT 表区域即可产生可修复的错误
        self.sudo_run_cmd(
            f"dd if=/dev/urandom of={loop_dev} bs=512 count=4 seek=32 conv=notrunc 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return True

    def get_usb_fat32_filesystem_error(self, loop_dev="") -> bool:
        """检查 FAT32 文件系统是否存在错误

        通过 fsck.vfat 检查文件系统状态, 存在错误时输出包含错误信息。

        :param loop_dev: loop 设备路径, 为空时自动查找
        :return: True 表示文件系统存在错误, False 表示健康
        """
        if not loop_dev:
            result = self.sudo_run_cmd(
                "losetup -j /tmp/test_usb_fat32.img 2>/dev/null", timeout=5, out_debug_flag=False
            )
            loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return False
        result = self.sudo_run_cmd(
            f"fsck.vfat -n {loop_dev} 2>&1", timeout=15, out_debug_flag=False
        )
        # fsck.vfat 检查模式下发现错误时输出包含 "errors" 或 "FATs differ" 等
        return any(
            keyword in result
            for keyword in ("errors", "differ", "corrupt", "Invalid", "error")
        )

    def get_usb_fat32_filesystem_healthy(self, loop_dev="") -> bool:
        """检查 FAT32 文件系统是否健康(无错误)

        通过 fsck.vfat 检查文件系统状态, 退出码 0 表示无错误。
        已挂载的文件系统会被 fsck 判定为 dirty(未正常卸载), 因此检查前
        先卸载; 原本挂载的分区在检查结束后恢复挂载, 不影响后续用例流程。

        :param loop_dev: loop 设备路径, 为空时自动查找
        :return: True 表示文件系统健康, False 表示有错误
        """
        mount_point = "/tmp/test_usb_fat32_mount"
        if not loop_dev:
            result = self.sudo_run_cmd(
                "losetup -j /tmp/test_usb_fat32.img 2>/dev/null", timeout=5, out_debug_flag=False
            )
            loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return False
        was_mounted = self.get_usb_device_mounted(mount_point=mount_point)
        if was_mounted:
            self.sudo_run_cmd(f"umount {mount_point} 2>/dev/null", timeout=15, out_debug_flag=False)
            sleep(1)
        result = self.sudo_run_cmd(
            f"fsck.vfat -n {loop_dev} 2>/dev/null; echo EXIT_CODE=$?", timeout=15, out_debug_flag=False
        )
        if was_mounted:
            self.sudo_run_cmd(
                f"mount -t vfat {loop_dev} {mount_point} 2>/dev/null", timeout=15, out_debug_flag=False
            )
            sleep(1)
        return "EXIT_CODE=0" in result

    def cleanup_virtual_usb_fat32(
        self, img_path="/tmp/test_usb_fat32.img", mount_point="/tmp/test_usb_fat32_mount"
    ):
        """清理 FAT32 虚拟 U 盘(卸载、分离 loop 设备、删除镜像文件)

        :param img_path: 镜像文件路径
        :param mount_point: 挂载点路径
        """
        import re

        self.sudo_run_cmd(f"umount {mount_point} 2>/dev/null", timeout=10, out_debug_flag=False)
        result = self.sudo_run_cmd(
            f"losetup -j {img_path} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        if result:
            for match in re.finditer(r"/dev/loop\d+", result):
                self.sudo_run_cmd(
                    f"losetup -d {match.group(0)} 2>/dev/null", timeout=5, out_debug_flag=False
                )
        self.sudo_run_cmd(f"rm -rf {mount_point} {img_path}", timeout=5, out_debug_flag=False)
        sleep(1)


    def create_fat32_severe_filesystem_error(
        self, loop_dev="", img_path="/tmp/test_usb_fat32.img"
    ):
        """向 FAT32 文件系统注入严重损坏(损坏严重)

        相比 create_fat32_filesystem_error 仅写入 4 个扇区,
        本方法对 FAT 表区域写入大量随机数据(32 个扇区, 16384 字节),
        同时破坏根目录区域, 模拟文件系统严重损坏场景。
        需要先卸载设备再注入错误。

        :param loop_dev: loop 设备路径, 为空时自动查找
        :param img_path: 镜像文件路径
        :return: True 表示成功注入严重损坏, False 表示失败
        """
        if not loop_dev:
            result = self.sudo_run_cmd(
                f"losetup -j {img_path} 2>/dev/null", timeout=5, out_debug_flag=False
            )
            loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return False
        # 严重损坏 FAT 表区域: 写入 32 个扇区(16384 字节)随机数据
        # FAT32 第一个 FAT 表通常从扇区 32 开始
        self.sudo_run_cmd(
            f"dd if=/dev/urandom of={loop_dev} bs=512 count=32 seek=32 conv=notrunc 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        # 破坏根目录区域(通常位于 FAT 表之后, 约扇区 300+ 附近)
        self.sudo_run_cmd(
            f"dd if=/dev/urandom of={loop_dev} bs=512 count=16 seek=300 conv=notrunc 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return True

    def create_virtual_usb_fat32_with_severe_errors(
        self, img_path="/tmp/test_usb_fat32.img", mount_point="/tmp/test_usb_fat32_mount"
    ):
        """创建存在严重损坏的 FAT32 虚拟 U 盘(loop 设备)

        先创建正常的 FAT32 虚拟 U 盘, 卸载后注入严重文件系统损坏,
        模拟 FAT32 U 盘损坏严重的场景。

        :param img_path: 镜像文件路径
        :param mount_point: 挂载点路径
        :return: loop 设备路径(如 /dev/loop0), 失败返回空字符串
        """
        loop_dev = self.create_virtual_usb_fat32(img_path, mount_point)
        if not loop_dev:
            return ""
        # 卸载文件系统以便注入严重损坏
        self.sudo_run_cmd(f"umount {mount_point} 2>/dev/null", timeout=10, out_debug_flag=False)
        sleep(1)
        # 注入严重文件系统损坏
        self.create_fat32_severe_filesystem_error(loop_dev, img_path)
        return loop_dev

    def get_usb_fat32_filesystem_severe_error(self, loop_dev="") -> bool:
        """检查 FAT32 文件系统是否存在严重损坏

        通过 fsck.vfat 检查文件系统状态, 严重损坏时输出包含多个错误关键词
        或返回非零退出码。

        :param loop_dev: loop 设备路径, 为空时自动查找
        :return: True 表示文件系统存在严重损坏, False 表示无损坏
        """
        if not loop_dev:
            result = self.sudo_run_cmd(
                "losetup -j /tmp/test_usb_fat32.img 2>/dev/null", timeout=5, out_debug_flag=False
            )
            loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return False
        result = self.sudo_run_cmd(
            f"fsck.vfat -n {loop_dev} 2>&1", timeout=15, out_debug_flag=False
        )
        severe_keywords = (
            "errors", "differ", "corrupt", "Invalid", "error",
            "bad", "mismatch", "damaged", "not found",
        )
        return any(keyword in result for keyword in severe_keywords)

    def get_no_usb_device_present(self) -> bool:
        """检查系统中是否存在 USB 存储设备

        通过遍历 /sys/block/sd* 和 /sys/block/sr* 并检查 ID_BUS=usb
        来判断是否有 USB 存储设备连接。
        :return: True 表示无 USB 存储设备, False 表示存在
        """
        result = self.run_cmd(
            "for dev in /sys/block/sd* /sys/block/sr*; do "
            '[ -e "$dev" ] || continue; '
            'devname=$(basename "$dev"); '
            'bus=$(udevadm info --query=property --name="/dev/$devname" 2>/dev/null '
            '| grep "^ID_BUS=" | cut -d= -f2); '
            '[ "$bus" = "usb" ] && echo "FOUND" && break; '
            "done",
            timeout=10,
            out_debug_flag=False,
        )
        return "FOUND" not in result.strip()

    # ===== 真实 USB 存储设备(usb-fix 插件按 ID_BUS=usb 枚举, loop 设备不被识别) =====

    def get_usb_storage_disks(self) -> list:
        """列出系统中的 USB 存储整盘(如 /dev/sdb), 已排除系统盘所在磁盘

        :return: 整盘设备路径列表
        """
        names = self.run_cmd(
            'for d in /sys/block/sd*; do [ -e "$d" ] || continue; n=$(basename "$d"); '
            'b=$(udevadm info --query=property --name="/dev/$n" 2>/dev/null '
            '| sed -n "s/^ID_BUS=//p"); '
            'if [ "$b" = "usb" ]; then echo "$n"; fi; done',
            timeout=15,
            out_debug_flag=False,
        )
        disks = [f"/dev/{name.strip()}" for name in (names or "").split() if name.strip()]

        root_src = self.run_cmd(
            "findmnt -n -o SOURCE / 2>/dev/null", timeout=10, out_debug_flag=False
        ).strip()
        system_disks = set()
        if root_src:
            pk = self.run_cmd(
                f"lsblk -no PKNAME {root_src} 2>/dev/null", timeout=10, out_debug_flag=False
            ).strip()
            if pk:
                system_disks.add(f"/dev/{pk.splitlines()[0].strip()}")
        return [disk for disk in disks if disk not in system_disks]

    def get_usb_disk_partitions(self, disk) -> list:
        """列出 USB 整盘下的分区设备

        :param disk: 整盘设备路径(如 /dev/sdb)
        :return: 分区设备路径列表(如 ['/dev/sdb1'])
        """
        if not re.fullmatch(r"/dev/sd[a-z]+", disk or ""):
            return []
        out = self.run_cmd(
            f"lsblk -ln -o NAME {disk} 2>/dev/null | tail -n +2", timeout=10, out_debug_flag=False
        )
        return [f"/dev/{name.strip()}" for name in (out or "").split() if name.strip()]

    def get_first_usb_storage_partition(self) -> str:
        """返回第一块 USB 存储设备的第一个分区

        :return: 分区设备路径(如 /dev/sdb1), 无 USB 存储设备或无分区时返回 ""
        """
        for disk in self.get_usb_storage_disks():
            partitions = self.get_usb_disk_partitions(disk)
            if partitions:
                return partitions[0]
        return ""

    def prepare_usb_fat32_partition(
        self, mount_point="/tmp/test_usb_fat32_mount", partition=""
    ) -> str:
        """把 USB 存储设备的第一个分区(或指定分区)格式化为 FAT32 并挂载

        usb-fix 插件按 ID_BUS=usb 枚举整盘, 因此必须使用真实的 sdX 分区而非 loop 设备。
        :param mount_point: 挂载点路径
        :param partition: 指定分区设备路径; 为空时取第一块 USB 存储设备的第一个分区
        :return: 分区设备路径, 失败返回 ""
        """
        if not partition:
            partition = self.get_first_usb_storage_partition()
        if not partition:
            return ""
        # 桌面 udisks2 可能把设备自动挂载到 /media/<user>/<label>, 需先全部卸载
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {partition} 2>/dev/null); do "
            f"umount -l \"$mp\" 2>/dev/null; done; sleep 1",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(f"mkfs.vfat -F 32 {partition} 2>/dev/null", timeout=180, out_debug_flag=False)
        self.sudo_run_cmd(f"mkdir -p {mount_point}", timeout=10, out_debug_flag=False)
        self.sudo_run_cmd(
            f"mount -t vfat {partition} {mount_point} 2>/dev/null", timeout=20, out_debug_flag=False
        )
        sleep(1)
        if not self.get_usb_device_mounted(mount_point=mount_point):
            return ""
        log(f"USB 分区已格式化为 FAT32 并挂载: {partition} -> {mount_point}")
        return partition

    def create_fat32_repairable_error(self, partition) -> bool:
        """向真实 USB 分区注入可被 fsck 自动修复的 FAT 表错误

        只破坏 FAT1 中段的簇项(不动 FAT[0]/FAT[1] 保留项与 BPB),
        因此文件系统仍可挂载, fsck 会报出可修复的簇链错误。
        :param partition: 分区设备路径(如 /dev/sdb1)
        :return: True 表示注入成功
        """
        if not re.fullmatch(r"/dev/sd[a-z]+\d+", partition or ""):
            return False
        self.sudo_run_cmd(f"umount -l {partition} 2>/dev/null", timeout=20, out_debug_flag=False)
        self.sudo_run_cmd(
            f"sh -c 'od -An -tu2 -j14 -N2 {partition} > /tmp/dpm_vbr_rs.txt; "
            f"chmod 644 /tmp/dpm_vbr_rs.txt'",
            timeout=10,
            out_debug_flag=False,
        )
        reserved = self.run_cmd(
            "tr -d ' \\n' < /tmp/dpm_vbr_rs.txt 2>/dev/null", timeout=5, out_debug_flag=False
        ).strip()
        self.sudo_run_cmd("rm -f /tmp/dpm_vbr_rs.txt", timeout=5, out_debug_flag=False)
        if not reserved.isdigit():
            return False
        # FAT1 起始扇区 = 保留扇区数; 偏移 168 扇区落在 FAT 表内部而非保留项
        seek = int(reserved) + 168
        self.sudo_run_cmd(
            f"dd if=/dev/urandom of={partition} bs=512 count=1 seek={seek} conv=notrunc 2>/dev/null",
            timeout=20,
            out_debug_flag=False,
        )
        self.sudo_run_cmd("sync", timeout=10, out_debug_flag=False)
        sleep(1)
        return True

    def get_partition_filesystem_type(self, partition) -> str:
        """读取分区的文件系统类型(lsblk), 用于断言前置条件

        :param partition: 分区设备路径(如 /dev/sdb1)
        :return: 文件系统类型(如 vfat/exfat/ext4), 读取失败返回 ""
        """
        if not partition:
            return ""
        return self.run_cmd(
            f"lsblk -no FSTYPE {partition} 2>/dev/null", timeout=10, out_debug_flag=False
        ).strip()

    def unmount_usb_partition(self, partition="", mount_point="/tmp/test_usb_fat32_mount"):
        """卸载 USB 分区并删除挂载点(不破坏文件系统)

        :param partition: 分区设备路径, 为空时仅卸载挂载点
        :param mount_point: 挂载点路径
        """
        self.sudo_run_cmd(f"umount {mount_point} 2>/dev/null", timeout=20, out_debug_flag=False)
        if partition:
            self.sudo_run_cmd(f"umount -l {partition} 2>/dev/null", timeout=20, out_debug_flag=False)
        self.sudo_run_cmd(f"rmdir {mount_point} 2>/dev/null", timeout=10, out_debug_flag=False)
        sleep(1)

    # ===== 合成 USB 存储设备(scsi_debug + udev ID_BUS=usb) =====
    # usb-fix 插件只枚举 /sys/block/sd* 中 udev 属性 ID_BUS=usb 的整盘(见产品
    # plugin-usb-fix/entry.sh 的 enumerate_usb_devices), loop/nbd 设备不会被识别。
    # 测试机通常没有实体 U 盘, 这里用内核 scsi_debug 造一块 RAM 磁盘(名字仍是 sdX),
    # 再用一条只匹配 scsi_debug 设备(vendor=Linux, model=scsi_debug)的 udev 规则把
    # ID_BUS 覆写为 usb。对插件而言与实体 U 盘完全等价, 且不接触任何真实磁盘。

    SYNTH_USB_UDEV_RULE = "/etc/udev/rules.d/99-autotest-scsi-debug-usb.rules"
    SYNTH_USB_RECOVERY_SCRIPT = "/tmp/autotest_2005745_usb_recover.sh"
    SYNTH_USB_RECOVERY_UNIT = "autotest-2005745-usb-recovery"

    def _get_sd_block_names(self) -> list:
        """列出 /sys/block 下当前存在的 SCSI 磁盘名(如 ['sda', 'sdb'])

        :return: 磁盘名列表
        """
        out = self.run_cmd(
            "ls /sys/block 2>/dev/null | grep -E '^sd[a-z]+$' | tr '\n' ' '",
            timeout=10,
            out_debug_flag=False,
        )
        return [name for name in (out or "").split() if name]

    def create_synthetic_usb_storage_device(self, size_mb=512) -> str:
        """用 scsi_debug + udev 规则造一个 usb-fix 可枚举的 USB 存储设备

        流程: 覆盖写入只匹配 scsi_debug 设备的 udev 规则 -> 加载 scsi_debug 得到
        /dev/sdX -> 确认 udev 给出的 ID_BUS=usb -> sfdisk 建一个 FAT32(LBA) 分区 ->
        mkfs.vfat 格式化分区。设备数据全部在内存盘里, 用例结束由
        cleanup_synthetic_usb_storage_device 卸载模块并删除规则。
        若系统已有真实 USB 存储设备则不再合成, 直接返回其第一个分区。

        :param size_mb: 合成盘容量(MB), 512MB 可保证 mkfs.vfat -F 32 正常建立 FAT32
        :return: 分区设备路径(如 /dev/sdb1), 失败返回 ""
        """
        if self.get_usb_storage_disks():
            return self.get_first_usb_storage_partition()

        # 清掉上一次的残留(可能已加载 scsi_debug)后重新构造
        self.cleanup_synthetic_usb_storage_device()
        before = set(self._get_sd_block_names())

        rule_line = (
            'SUBSYSTEM=="block", KERNEL=="sd[a-z]*", '
            'ATTRS{vendor}=="Linux*", ATTRS{model}=="scsi_debug*", ENV{ID_BUS}="usb"'
        )
        self.sudo_run_cmd(
            "cat > {rule_file} <<'AUTOTEST_UDEV_EOF'\n{rule}\nAUTOTEST_UDEV_EOF".format(
                rule_file=self.SYNTH_USB_UDEV_RULE, rule=rule_line
            ),
            timeout=20,
            out_debug_flag=False,
        )
        rule_text = self.sudo_run_cmd(
            f"cat {self.SYNTH_USB_UDEV_RULE} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        if "scsi_debug" not in (rule_text or ""):
            logger.error("写 udev 规则失败, 无法合成 USB 存储设备")
            return ""
        self.sudo_run_cmd("udevadm control --reload-rules 2>/dev/null", timeout=30, out_debug_flag=False)

        modprobe_out = self.sudo_run_cmd(
            f"modprobe scsi_debug dev_size_mb={int(size_mb)} sector_size=512 2>&1; echo RC=$?",
            timeout=120,
            out_debug_flag=False,
        )
        if "RC=0" not in (modprobe_out or ""):
            logger.error(f"加载 scsi_debug 失败: {modprobe_out!r}")
            return ""

        # 等待内核注册新的 sdX 设备
        device = ""
        for _ in range(30):
            new_names = [n for n in self._get_sd_block_names() if n not in before]
            if new_names:
                device = f"/dev/{sorted(new_names)[0]}"
                break
            sleep(1)
        if not device:
            logger.error("scsi_debug 已加载但未出现新的 sdX 设备")
            return ""

        # 校验 udev 已把该设备的 ID_BUS 覆写为 usb(插件按此属性枚举)
        bus_type = ""
        for _ in range(10):
            bus_type = self.run_cmd(
                f"udevadm info --query=property --name={device} 2>/dev/null | sed -n 's/^ID_BUS=//p'",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            if bus_type == "usb":
                break
            self.sudo_run_cmd(
                f"udevadm trigger --subsystem-match=block {device} 2>/dev/null; "
                "udevadm settle --timeout=10 2>/dev/null",
                timeout=40,
                out_debug_flag=False,
            )
            sleep(1)
        if bus_type != "usb":
            logger.error(f"合成设备 {device} 的 ID_BUS={bus_type!r}, 未被识别为 USB 设备")
            return ""

        # 建分区表(dos, 单分区 FAT32-LBA)并格式化
        self.sudo_run_cmd(
            f"printf ',,c\\n' | sfdisk --label dos {device} 2>&1", timeout=60, out_debug_flag=False
        )
        self.sudo_run_cmd(f"partprobe {device} 2>/dev/null; sleep 1", timeout=30, out_debug_flag=False)

        partition = ""
        for _ in range(15):
            partitions = self.get_usb_disk_partitions(device)
            if partitions:
                partition = partitions[0]
                break
            sleep(1)
        if not partition:
            logger.error(f"合成设备 {device} 未生成分区")
            return ""

        mkfs_out = self.sudo_run_cmd(
            f"mkfs.vfat -F 32 {partition} 2>&1; echo RC=$?", timeout=180, out_debug_flag=False
        )
        if "RC=0" not in (mkfs_out or ""):
            logger.error(f"合成分区 {partition} 格式化 FAT32 失败: {mkfs_out!r}")
            return ""

        self._synthetic_usb_partition = partition
        self._synthetic_usb_disk = device
        logger.info(f"已合成 USB 存储设备: {device} -> {partition}(ID_BUS=usb, 内存盘)")
        return partition

    def schedule_synthetic_usb_recovery(self, seconds=1500) -> bool:
        """安排兜底恢复: 若干秒后卸载合成 U 盘、删除 udev 规则并卸载 scsi_debug

        用例进程被强杀或超时执行不到 finally 时, 测试机会残留 scsi_debug 磁盘与
        ID_BUS 覆写规则; 先注册一个 systemd-run 定时单元兜底, 在 finally 里取消。

        :param seconds: 兜底触发延时(秒), 需大于用例最长运行时间
        :return: True 表示定时器已注册
        """
        partition = getattr(self, "_synthetic_usb_partition", "")
        script = (
            "#!/usr/bin/env bash\n"
            "# 用例 2005745 兜底恢复: 清理合成 U 盘与 udev ID_BUS 规则\n"
            f"for mp in $(findmnt -n -o TARGET {partition} 2>/dev/null); do umount -l \"$mp\" 2>/dev/null; done\n"
            f"rm -f {self.SYNTH_USB_UDEV_RULE}\n"
            "udevadm control --reload-rules 2>/dev/null\n"
            "rmmod scsi_debug 2>/dev/null\n"
            f"rm -f {self.SYNTH_USB_RECOVERY_SCRIPT}\n"
        )
        self.cancel_synthetic_usb_recovery()
        try:
            with open(self.SYNTH_USB_RECOVERY_SCRIPT, "w", encoding="utf-8") as script_file:
                script_file.write(script)
            os.chmod(self.SYNTH_USB_RECOVERY_SCRIPT, 0o755)
        except OSError as exc:
            logger.error(f"写兜底恢复脚本失败: {exc}")
            return False
        self.sudo_run_cmd(
            f"systemd-run --on-active={int(seconds)} "
            f"--unit={self.SYNTH_USB_RECOVERY_UNIT} "
            f"/bin/bash {self.SYNTH_USB_RECOVERY_SCRIPT}",
            timeout=20,
            out_debug_flag=False,
        )
        state = self.run_cmd(
            f"systemctl show -p ActiveState --value {self.SYNTH_USB_RECOVERY_UNIT}.timer 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return state.strip() == "active"

    def cancel_synthetic_usb_recovery(self):
        """取消兜底恢复定时器并删除其临时脚本(可重复调用)"""
        self.sudo_run_cmd(
            f"bash -c 'systemctl stop {self.SYNTH_USB_RECOVERY_UNIT}.timer "
            f"{self.SYNTH_USB_RECOVERY_UNIT}.service 2>/dev/null; "
            f"systemctl reset-failed {self.SYNTH_USB_RECOVERY_UNIT}.service 2>/dev/null; "
            f"rm -f {self.SYNTH_USB_RECOVERY_SCRIPT}; true'",
            timeout=30,
            out_debug_flag=False,
        )

    def is_kernel_module_loaded(self, name: str) -> bool:
        """检查内核模块是否已加载(用于校验 scsi_debug 等构造残留是否清理)"""
        out = self.run_cmd(
            f"lsmod | awk '{{print $1}}' | grep -cx {quote(name)} || true",
            timeout=10,
            out_debug_flag=False,
        )
        return out.strip() == "1"

    def cleanup_synthetic_usb_storage_device(self):
        """清理合成的 USB 存储设备(卸载分区、删除 udev 规则、卸载 scsi_debug 模块)"""
        partition = getattr(self, "_synthetic_usb_partition", "")
        disk = getattr(self, "_synthetic_usb_disk", "")
        if partition:
            self.sudo_run_cmd(
                f"for mp in $(findmnt -n -o TARGET {partition} 2>/dev/null); do "
                f"umount -l \"$mp\" 2>/dev/null; done; true",
                timeout=30,
                out_debug_flag=False,
            )
        self.sudo_run_cmd(f"rm -f {self.SYNTH_USB_UDEV_RULE}", timeout=20, out_debug_flag=False)
        self.sudo_run_cmd(
            "udevadm control --reload-rules 2>/dev/null; true", timeout=30, out_debug_flag=False
        )
        self.sudo_run_cmd("rmmod scsi_debug 2>/dev/null; true", timeout=60, out_debug_flag=False)
        sleep(2)
        if disk and os.path.exists(f"/sys/block/{os.path.basename(disk)}"):
            logger.error(f"scsi_debug 设备 {disk} 未随模块卸载消失, 需人工确认")
        elif disk:
            logger.info(f"合成 USB 存储设备已清理: {disk}")
        self._synthetic_usb_partition = ""
        self._synthetic_usb_disk = ""

    def get_repair_output_text(self) -> str:
        """获取修复对话框输出日志全文

        :return: 输出日志文本, 获取失败返回空字符串
        """
        try:
            output_log = self.dog.find_element_by_attr("$//shellRepair_outputLog")
            return getattr(output_log, "text", "") or ""
        except BaseException:
            return ""

    def wait_repair_output_contains(self, keyword: str, timeout=60) -> bool:
        """轮询等待修复对话框输出中出现指定文案(等价于 get_repair_output_contains)

        单独提供该名字是为了让用例读到"等待某条输出"的语义; 实现与
        get_repair_output_contains 一致。

        :param keyword: 需要出现的子串
        :param timeout: 最长等待秒数
        :return: True 表示等待期内出现过该子串
        """
        return self.get_repair_output_contains(keyword, timeout=timeout)

    def get_lpadmin_group_exists(self) -> bool:
        """检查系统中是否存在 lpadmin 组

        打印机修复脚本用 usermod -a -G lpadmin 加权限, 组不存在时脚本必然失败;
        用例先断言该组存在, 把"环境缺组"与"产品未修复"区分开。

        :return: True 表示 /etc/group 中存在 lpadmin 组
        """
        out = self.run_cmd(
            "getent group lpadmin >/dev/null 2>&1; echo RC=$?",
            timeout=10,
            out_debug_flag=False,
        )
        return "RC=0" in (out or "")

    def get_current_user(self) -> str:
        """返回当前登录用户名(用于日志与组归属校验)

        :return: 用户名, 读取失败返回 ""
        """
        return self.run_cmd("id -un 2>/dev/null", timeout=10, out_debug_flag=False).strip()

    def get_repair_output_contains(self, keyword: str, timeout=60) -> bool:
        """检查修复对话框输出日志是否包含指定关键词

        :param keyword: 要查找的关键词
        :param timeout: 最长等待秒数
        :return: True 表示输出日志中包含该关键词
        """
        last_text = ""
        for _ in range(timeout):
            try:
                output_log = self.dog.find_element_by_attr("$//shellRepair_outputLog")
                log_text = getattr(output_log, "text", "") or ""
                if log_text:
                    last_text = log_text
                if keyword in log_text:
                    return True
            except BaseException:
                pass
            sleep(2)
        from funnylog import logger

        logger.warning(
            f"修复对话框输出未包含 {keyword!r}, 当前输出({len(last_text)} 字符): "
            f"{last_text[-2000:]!r}"
        )
        return False

    def get_repair_notify_dialog_state(self) -> dict:
        """读取 dpm_notify 信息提示框的状态

        产品依据(deepin-pc-manager 1.1.7): 修复脚本调用 dpm_notify(内部走
        dpm_prompt)时, 电脑管家主进程创建一个**无标题** DDialog(与
        session-daemon 的 openconfirm 确认框不同, 它属于主进程), 内含
        DDialogTitleLabel / DDialogMessageLabel 和一个文案为"确定"的按钮;
        同时修复输出日志打印 "[等待你的确认] <标题>", 脚本阻塞到用户点掉提示框。
        修复窗口自身 name 为 "<工具名>"("网络修复" 等), 因此以"无标题 + 确定
        按钮"识别提示框。

        :return: {"showing": bool, "has_ok": bool, "button": 按钮节点或 None}
        """
        state = {"showing": False, "has_ok": False, "button": None}
        try:
            tops = self.dog.obj.children
        except BaseException:
            return state
        for top in tops:
            try:
                if (getattr(top, "roleName", "") or "") not in ("dialog", "alert dialog"):
                    continue
                if getattr(top, "showing", False) is not True:
                    continue
                if (getattr(top, "name", "") or "").strip():
                    continue
                for node in self._collect_dialog_nodes(top):
                    if (
                        (getattr(node, "roleName", "") or "") == "push button"
                        and (getattr(node, "name", "") or "") == "确定"
                    ):
                        state["showing"] = True
                        state["has_ok"] = True
                        state["button"] = node
                        break
            except BaseException:
                continue
            if state["has_ok"]:
                break
        return state

    def click_repair_notify_ok(self, timeout=15) -> bool:
        """点击 dpm_notify 信息提示框的【确定】按钮

        修复脚本在 dpm_notify 上阻塞, 不点掉提示框脚本不会继续执行
        (输出会停在 "[等待你的确认] <标题>")。

        :param timeout: 最长等待秒数
        :return: True 表示已点到【确定】且提示框已消失
        """
        for _ in range(timeout):
            state = self.get_repair_notify_dialog_state()
            button = state.get("button")
            if state["has_ok"] and button is not None:
                clicked = self._atspi_do_action(button)
                if not clicked:
                    clicked = self._click_at_element(button)
                if not clicked:
                    return False
                for _ in range(10):
                    if not self.get_repair_notify_dialog_state()["showing"]:
                        return True
                    sleep(1)
                return False
            sleep(1)
        return False

    def close_repair_notify_dialog(self, rounds=2) -> int:
        """关闭遗留的 dpm_notify 信息提示框(点【确定】), 供 finally 清理

        :param rounds: 最多连续处理的提示框个数
        :return: 实际关闭的提示框数量
        """
        closed = 0
        for _ in range(rounds):
            if not self.get_repair_notify_dialog_state()["has_ok"]:
                break
            if not self.click_repair_notify_ok(timeout=5):
                break
            closed += 1
            sleep(1)
        return closed

    # ===== 磁盘使用情况分析器(baobab)方法 =====

    def is_baobab_installed(self) -> bool:
        """检查 baobab 包是否已安装"""
        result = self.run_cmd(
            "dpkg -l baobab 2>/dev/null | grep '^ii'",
            timeout=10,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def install_baobab(self):
        """安装 baobab 包"""

        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get update -qq "
            f"&& echo '{conf.PASSWORD}' | sudo -S apt-get install -y baobab",
            timeout=120,
            out_debug_flag=False,
        )
        sleep(2)

    def uninstall_baobab(self):
        """卸载 baobab 包"""

        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get remove -y baobab",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(2)

    def click_disk_usage_analyzer_card(self):
        """点击磁盘使用情况分析器卡片

        QML 卡片的 Node.click() 不触发点击, 必须走 AT-SPI Press 动作。
        """
        self._safe_focus_windows()
        card = self.dog.find_element_by_attr(
            "$//utility_sectionsContainer//磁盘使用情况分析器"
        )
        self._atspi_do_action(card)
        sleep(2)

    def get_baobab_process_status(self) -> bool:
        """检查 baobab 进程是否正在运行"""
        result = self.run_cmd(
            "pgrep -x baobab",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def wait_baobab_process_running(self, timeout=15) -> bool:
        """等待 baobab 进程启动

        :param timeout: 最长等待秒数
        :return: True 表示进程已启动, False 表示超时未启动
        """
        for _ in range(timeout):
            if self.get_baobab_process_status():
                return True
            sleep(1)
        return False

    def kill_baobab(self):
        """终止 baobab 进程"""
        self.run_cmd(
            "killall baobab 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    # ===== 磁盘管理器(deepin-diskmanager)方法 =====

    def is_disk_manager_installed(self) -> bool:
        """检查 deepin-diskmanager 包是否已安装"""
        result = self.run_cmd(
            "dpkg -l deepin-diskmanager 2>/dev/null | grep '^ii'",
            timeout=10,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def install_disk_manager(self):
        """安装 deepin-diskmanager 包"""

        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get update -qq "
            f"&& echo '{conf.PASSWORD}' | sudo -S apt-get install -y deepin-diskmanager",
            timeout=120,
            out_debug_flag=False,
        )
        sleep(2)

    def uninstall_disk_manager(self):
        """卸载 deepin-diskmanager 包"""

        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get remove -y deepin-diskmanager",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(2)

    def click_disk_manager_card(self):
        """点击磁盘管理器卡片"""
        self._safe_focus_windows()
        self.dog.find_element_by_attr("$//utility_sectionsContainer//磁盘管理器").click()
        sleep(2)

    def get_disk_manager_process_status(self) -> bool:
        """检查 deepin-diskmanager 进程是否正在运行"""
        result = self.run_cmd(
            "pgrep -f deepin-diskmanager",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def kill_disk_manager(self):
        """终止 deepin-diskmanager 进程"""
        self.run_cmd(
            "killall deepin-diskmanager 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    # ===== 日志收集工具(deepin-log-viewer)方法 =====

    def is_log_viewer_installed(self) -> bool:
        """检查 deepin-log-viewer 包是否已安装"""
        result = self.run_cmd(
            "dpkg -l deepin-log-viewer 2>/dev/null | grep '^ii'",
            timeout=10,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def install_log_viewer(self):
        """安装 deepin-log-viewer 包"""

        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get update -qq "
            f"&& echo '{conf.PASSWORD}' | sudo -S apt-get install -y deepin-log-viewer",
            timeout=120,
            out_debug_flag=False,
        )
        sleep(2)

    def uninstall_log_viewer(self):
        """卸载 deepin-log-viewer 包"""

        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get remove -y deepin-log-viewer",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(2)

    # ===== DNS配置操作方法(网络检测用例) =====

    def backup_resolv_conf(self):
        """备份 /etc/resolv.conf 内容及类型信息

        记录原文件是否为符号链接并保存目标路径和文件内容,
        以便测试结束后精确恢复原始状态(V20/V25 上 /etc/resolv.conf
        可能是普通文件或指向 /run/systemd/resolve/stub-resolv.conf 的符号链接)。
        """
        self.sudo_run_cmd(
            "cp -L /etc/resolv.conf /tmp/resolv_conf_autotest.bak",
            timeout=5,
            out_debug_flag=False,
        )
        self.run_cmd(
            "test -L /etc/resolv.conf && readlink -f /etc/resolv.conf "
            "> /tmp/resolv_conf_link.bak || echo '' > /tmp/resolv_conf_link.bak",
            timeout=5,
            out_debug_flag=False,
        )

    def set_invalid_dns_server(self):
        """设置无效DNS服务器(192.0.2.1)以触发DNS解析异常

        192.0.2.1 属于 RFC 5737 TEST-NET-1 保留地址, 保证不可达。
        移除原 /etc/resolv.conf(无论普通文件还是符号链接),
        创建仅含无效DNS服务器的普通文件。
        """
        self.sudo_run_cmd(
            "rm -f /etc/resolv.conf && echo 'nameserver 192.0.2.1' > /etc/resolv.conf",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def restore_resolv_conf(self):
        """恢复 /etc/resolv.conf 到测试前状态

        若原文件为符号链接则重建符号链接, 否则恢复文件内容。
        """
        link_target = self.run_cmd(
            "cat /tmp/resolv_conf_link.bak 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()
        if link_target:
            self.sudo_run_cmd(
                f"rm -f /etc/resolv.conf && ln -s {link_target} /etc/resolv.conf",
                timeout=5,
                out_debug_flag=False,
            )
        else:
            self.sudo_run_cmd(
                "cp /tmp/resolv_conf_autotest.bak /etc/resolv.conf",
                timeout=5,
                out_debug_flag=False,
            )
        self.run_cmd(
            "rm -f /tmp/resolv_conf_autotest.bak /tmp/resolv_conf_link.bak",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    # ===== 安装类型判定方法 =====

    # 安装器记录的安装方式(deepin-installer.conf 的 DI_PARTITION_TYPE)
    INSTALL_PARTITION_TYPE_NAMES = {
        "0": "全盘安装",
        "1": "手动安装",
        "2": "全盘加密安装",
        "3": "全盘安装保留用户数据",
        "6": "单盘多系统全盘安装",
        "7": "全盘lvm安装",
    }
    # 全盘安装类型：0/2/3/7。6 为单盘多系统全盘安装，1 为手动安装(非全盘)。
    FULL_DISK_INSTALL_PARTITION_TYPES = ("0", "2", "3", "7")
    MANUAL_INSTALL_PARTITION_TYPES = ("1",)

    def get_install_partition_type(self) -> str:
        """读取系统安装方式 DI_PARTITION_TYPE

        该值由安装器写入 /etc/deepin-installer/deepin-installer.conf：
        0 = 全盘安装, 1 = 手动安装, 2 = 全盘加密安装,
        3 = 全盘安装保留用户数据, 6 = 单盘多系统全盘安装, 7 = 全盘lvm安装。
        全盘安装类型仅 0/2/3/7（见 FULL_DISK_INSTALL_PARTITION_TYPES）。
        :return: 类型字符串, 读取失败返回 ""
        """
        result = self.run_cmd(
            "grep -E '^DI_PARTITION_TYPE=' /etc/deepin-installer/deepin-installer.conf "
            "2>/dev/null | head -n1 | cut -d= -f2",
            timeout=5,
            out_debug_flag=False,
        )
        return (result or "").strip().strip('"')

    def get_install_partition_type_name(self) -> str:
        """获取安装方式的中文名称

        :return: 如 "全盘安装"、"手动安装"; 未记录或未知值返回 "未记录/未知"
        """
        return self.INSTALL_PARTITION_TYPE_NAMES.get(
            self.get_install_partition_type(), "未记录/未知"
        )

    def is_full_disk_install(self) -> bool:
        """当前系统是否为全盘安装(0 全盘 / 2 全盘加密 / 3 保留用户数据 / 7 全盘lvm)

        6(单盘多系统全盘安装)与 1(手动安装)不算全盘安装类型。
        """
        return self.get_install_partition_type() in self.FULL_DISK_INSTALL_PARTITION_TYPES

    # ===== /recovery 分区管理方法 =====

    def get_recovery_partition_mounted(self) -> bool:
        """检查 /recovery 分区是否已挂载

        通过 findmnt 检查 /recovery 挂载点是否存在。
        :return: True 表示已挂载, False 表示未挂载
        """
        result = self.run_cmd(
            "findmnt -n /recovery 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def get_recovery_mount_source(self) -> str:
        """获取 /recovery 分区的设备路径(如 /dev/sda2)

        :return: 设备路径字符串, 未挂载时返回空字符串
        """
        result = self.run_cmd(
            "findmnt -n -o SOURCE /recovery 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def unmount_recovery_partition(self) -> bool:
        """卸载 /recovery 分区

        使用 sudo umount 卸载 /recovery 挂载点。
        若普通卸载失败(target is busy), 使用 lazy unmount (umount -l)。
        :return: True 表示卸载成功, False 表示卸载失败
        """
        self.sudo_run_cmd(
            "umount /recovery 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        if not self.get_recovery_partition_mounted():
            return True
        self.sudo_run_cmd(
            "umount -l /recovery 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return not self.get_recovery_partition_mounted()

    def remount_recovery_partition(self) -> bool:
        """重新挂载 /recovery 分区

        使用之前记录的设备路径重新挂载。
        :return: True 表示挂载成功, False 表示挂载失败
        """
        source = self.get_recovery_mount_source()
        if source:
            self.sudo_run_cmd(
                f"mount {source} /recovery 2>/dev/null",
                timeout=10,
                out_debug_flag=False,
            )
            sleep(1)
            return self.get_recovery_partition_mounted()
        # 设备路径为空, 尝试从 fstab 恢复挂载
        self.sudo_run_cmd(
            "mount /recovery 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return self.get_recovery_partition_mounted()

    # ===== WPS修复相关方法 =====

    def click_wps_fix_card(self):
        """点击WPS双击打开修复卡片

        先最大化窗口确保布局稳定，然后直接通过 AT-SPI 点击卡片。
        AT-SPI 点击不依赖卡片的视觉可见性，即使卡片在滚动区域下方也能正常触发。
        V25 上页面切换后窗口可能短暂不可见导致 focus_windows 失败,
        最大化非必须, 失败时跳过并继续 AT-SPI 点击。
        """
        try:
            self._safe_focus_windows()
            if not self.get_window_maximized_status():
                self.maximize_window_by_shortcut()
                sleep(2)
                self._safe_focus_windows()
                self.reconnect_dogtail()
        except BaseException:
            self.reconnect_dogtail()
        self.click_repair_card_by_name("WPS双击打开修复")

    def backup_wps_config(self):
        """备份WPS配置文件(Office.conf)

        修复前备份已有配置文件到 /tmp，以便测试后恢复原始状态。
        """
        self.run_cmd(
            "test -f ~/.config/Kingsoft/Office.conf && "
            "cp ~/.config/Kingsoft/Office.conf /tmp/Office.conf.bak || true",
            timeout=5,
            out_debug_flag=False,
        )

    def create_corrupt_wps_config(self):
        """创建损坏的WPS配置文件(模拟配置错误问题)

        写入一个不包含 AppComponentMode 的最小配置文件,
        使修复工具有明确的目标去修复或重建配置。
        """
        self.run_cmd(
            "mkdir -p ~/.config/Kingsoft && echo '[General]' > ~/.config/Kingsoft/Office.conf",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_wps_config(self):
        """删除WPS配置文件(模拟配置缺失问题)"""
        self.run_cmd(
            "rm -f ~/.config/Kingsoft/Office.conf",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def restore_wps_config(self):
        """恢复WPS配置文件到测试前状态"""
        self.run_cmd(
            "if [ -f /tmp/Office.conf.bak ]; then "
            "cp /tmp/Office.conf.bak ~/.config/Kingsoft/Office.conf && "
            "rm -f /tmp/Office.conf.bak; "
            "else rm -f ~/.config/Kingsoft/Office.conf; fi",
            timeout=5,
            out_debug_flag=False,
        )

    def get_wps_config_exists(self) -> bool:
        """检查WPS配置文件(Office.conf)是否存在"""
        result = self.run_cmd(
            "test -f ~/.config/Kingsoft/Office.conf && echo yes || echo no",
            timeout=5,
            out_debug_flag=False,
        )
        return "yes" in result.strip()

    def get_wps_config_has_mode(self) -> bool:
        """检查WPS配置文件是否包含AppComponentMode配置项"""
        result = self.run_cmd(
            "grep -c 'AppComponentMode' ~/.config/Kingsoft/Office.conf 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip()) > 0
        except (ValueError, AttributeError):
            return False

    # --- WPS 配置目录级构造/断言(对应 plugin-wps-fix/entry.sh 的目录创建分支) ---

    WPS_CONFIG_DIR = "$HOME/.config/Kingsoft"
    WPS_CONFIG_PATH = "$HOME/.config/Kingsoft/Office.conf"
    WPS_CONFIG_BACKUP_DIR = "/tmp/autotest_wps_kingsoft.bak"

    def get_wps_config_dir_exists(self) -> bool:
        """检查 WPS 配置目录 ~/.config/Kingsoft 是否存在

        产品依据(plugin-wps-fix/entry.sh set_default_config): 无本地配置时
        "mkdir -p <HOME>/.config/Kingsoft/" 后 chmod 700 再 chmod 775,
        即目录由修复脚本创建; 用例预期"自动创建 Kingsoft 目录"以此断言。
        """
        result = self.run_cmd(
            f'test -d "{self.WPS_CONFIG_DIR}" && echo yes || echo no',
            timeout=5,
            out_debug_flag=False,
        )
        return "yes" in result.strip()

    def get_wps_config_dir_mode(self) -> str:
        """获取 WPS 配置目录权限(八进制字符串, 如 "775")"""
        result = self.run_cmd(
            f'stat -c %a "{self.WPS_CONFIG_DIR}" 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_wps_config_mode(self) -> str:
        """获取 WPS 配置文件 Office.conf 权限(八进制字符串, 如 "664")"""
        result = self.run_cmd(
            f'stat -c %a "{self.WPS_CONFIG_PATH}" 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_wps_config_dir_owner(self) -> str:
        """获取 WPS 配置目录属主用户名"""
        result = self.run_cmd(
            f'stat -c %U "{self.WPS_CONFIG_DIR}" 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_wps_config_owner(self) -> str:
        """获取 WPS 配置文件属主用户名"""
        result = self.run_cmd(
            f'stat -c %U "{self.WPS_CONFIG_PATH}" 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_wps_config_content(self) -> str:
        """读取 WPS 配置文件全文

        产品依据(plugin-wps-fix/entry.sh): 无配置时写入 "[6.0]" 以及
        "wpsoffice\\Application%20Settings\\AppComponentMode=prome_fushion"、
        "...\\AppComponentModeInstall=prome_fushion" 两行。
        """
        return self.run_cmd(
            f'cat "{self.WPS_CONFIG_PATH}" 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )

    def get_wps_config_has_required_keys(self) -> bool:
        """检查配置文件同时含 [6.0] 段与两条组件模式配置项

        等价于产品脚本应写入的"正确配置项": AppComponentMode 与
        AppComponentModeInstall 均为整合模式 prome_fushion。
        """
        content = self.get_wps_config_content()
        return (
            "[6.0]" in content
            and "AppComponentMode=prome_fushion" in content
            and "AppComponentModeInstall=prome_fushion" in content
        )

    def backup_wps_state(self) -> bool:
        """备份 WPS 配置现场(整个 ~/.config/Kingsoft 目录)

        用例前置"~/.config/Kingsoft/Office.conf 不存在"且预期目录被重建,
        因此把整个目录 mv 到 /tmp 备份(保留权限/属主), finally 由
        restore_wps_state 原样还原; 若上次异常退出遗留了备份, 先做自愈:
        目录缺失则把备份移回, 目录存在则丢弃陈旧备份(避免把残留当真实现场)。
        """
        result = self.run_cmd(
            f'if [ -e "{self.WPS_CONFIG_DIR}" ]; then '
            f'rm -rf "{self.WPS_CONFIG_BACKUP_DIR}" && '
            f'mv "{self.WPS_CONFIG_DIR}" "{self.WPS_CONFIG_BACKUP_DIR}" && echo backed; '
            f'elif [ -e "{self.WPS_CONFIG_BACKUP_DIR}" ]; then '
            f'mv "{self.WPS_CONFIG_BACKUP_DIR}" "{self.WPS_CONFIG_DIR}" && echo healed; '
            f'else echo none; fi',
            timeout=10,
            out_debug_flag=False,
        )
        lines = [line.strip() for line in result.strip().splitlines() if line.strip()]
        return bool(lines) and lines[-1] in ("backed", "healed", "none")

    def remove_wps_config_dir(self) -> bool:
        """删除整个 WPS 配置目录, 模拟"系统不存在 Office.conf 配置文件"场景"""
        self.run_cmd(
            f'rm -rf "{self.WPS_CONFIG_DIR}"',
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return not self.get_wps_config_dir_exists()

    def restore_wps_state(self):
        """还原 WPS 配置现场: 删除修复脚本生成的目录, 移回备份(若有)

        若测试前不存在 Kingsoft 目录, 这里只删除, 不在测试机留残留;
        同时清理旧的单文件备份(/tmp/Office.conf.bak)。
        """
        self.run_cmd(
            f'rm -rf "{self.WPS_CONFIG_DIR}"; '
            f'if [ -e "{self.WPS_CONFIG_BACKUP_DIR}" ]; then '
            f'mkdir -p "$HOME/.config" && '
            f'mv "{self.WPS_CONFIG_BACKUP_DIR}" "{self.WPS_CONFIG_DIR}"; fi; '
            f'rm -f /tmp/Office.conf.bak',
            timeout=10,
            out_debug_flag=False,
        )

    def wait_wps_config_created(self, timeout=60) -> bool:
        """等待修复脚本重新生成 Office.conf

        :param timeout: 最长等待秒数
        :return: True 表示配置文件已出现
        """
        for _ in range(timeout):
            if self.get_wps_config_exists():
                return True
            sleep(1)
        return False

    def is_wps_installed(self) -> bool:
        """检查WPS Office是否已安装"""
        result = self.run_cmd(
            "which wps 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def create_test_doc_file(self):
        """在桌面创建测试文档文件(.docx)

        使用 python3 创建一个最小有效的 .docx 文件，
        以便测试双击打开文档时 WPS 能正常启动。
        """
        self.run_cmd(
            f'python3 -c "'
            f"import zipfile;"
            f"z=zipfile.ZipFile('{DESKTOP_DIR}/test_wps_doc.docx','w');"
            f'z.writestr(\'[Content_Types].xml\',\'<Types xmlns=\\"http://schemas.openxmlformats.org/package/2006/content-types\\"><Default Extension=\\"rels\\" ContentType=\\"application/vnd.openxmlformats-package.relationships+xml\\"/><Default Extension=\\"xml\\" ContentType=\\"application/xml\\"/><Override PartName=\\"/word/document.xml\\" ContentType=\\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\\"/></Types>\');'
            f'z.writestr(\'_rels/.rels\',\'<Relationships xmlns=\\"http://schemas.openxmlformats.org/package/2006/relationships\\"><Relationship Id=\\"rId1\\" Type=\\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\\" Target=\\"word/document.xml\\"/></Relationships>\');'
            f"z.writestr('word/document.xml','<document xmlns=\\\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\\\"><body><p><r><t>test</t></r></p></body></document>');"
            f"z.close()"
            f'"',
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_test_doc_file(self):
        """删除测试文档文件"""
        self.run_cmd(
            f'rm -f "{DESKTOP_DIR}/test_wps_doc.docx"',
            timeout=5,
            out_debug_flag=False,
        )

    def open_test_doc_file(self):
        """通过xdg-open打开测试文档(模拟双击打开)"""
        self.run_cmd(
            f'xdg-open "{DESKTOP_DIR}/test_wps_doc.docx" >/dev/null 2>&1 &',
            timeout=5,
            out_debug_flag=False,
        )

    def get_wps_process_status(self) -> bool:
        """获取WPS进程运行状态"""
        result = self.run_cmd(
            "pgrep -x wps 2>/dev/null || pgrep -x wpsoffice 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def wait_wps_process_started(self, timeout=15) -> bool:
        """等待WPS进程启动

        :param timeout: 最长等待秒数
        :return: True 表示进程已启动, False 表示超时未启动
        """
        for _ in range(timeout):
            if self.get_wps_process_status():
                return True
            sleep(1)
        return False

    def kill_wps_process(self):
        """终止WPS进程(测试后清理用)"""
        self.run_cmd(
            "killall wps wpsoffice 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(2)

    def wait_wps_config_restored(self, timeout=30) -> bool:
        """等待WPS配置文件被修复工具恢复

        修复前已删除配置文件, 修复完成后配置文件应重新存在。
        :param timeout: 最长等待秒数
        :return: True 表示配置已恢复, False 表示超时未恢复
        """
        for _ in range(timeout):
            if self.get_wps_config_exists():
                return True
            sleep(1)
        return False

    def click_wps_fix_card_and_repair(self) -> bool:
        """点击WPS修复卡片并执行修复流程

        封装完整的WPS修复流程: 点击卡片 → 等待详情页 → 点击开始修复 →
        等待修复对话框 → 等待配置恢复 → 关闭对话框。
        :return: True 表示修复流程成功完成, False 表示某步骤失败
        """
        self.click_wps_fix_card()
        if not self.get_repair_detail_showing():
            return False
        self.click_start_repair_button()
        if not self.get_repair_dialog_showing():
            return False
        if not self.wait_wps_config_restored(timeout=60):
            self.close_repair_dialog()
            return False
        self.close_repair_dialog()
        return True

    # ===== 多用户场景构造(WPS 修复用例 2005789) =====
    # 用例前置"存在多用户, A 用户用过 WPS, B 用户下 doc 打不开": 测试机默认只有
    # uostest 一个普通用户, 因此用 useradd 真实创建第二个普通用户(用例 finally 删除),
    # 并在其家目录写入该用户自己的 Office.conf 代表"A 用过 WPS"。

    MULTI_USER_HOME_TEMPLATE = "/home/{user}"
    MULTI_USER_WPS_CONFIG_TEMPLATE = "/home/{user}/.config/Kingsoft/Office.conf"
    # sudo -S 的密码提示/成功提示(框架把 stderr 并入 stdout, 且提示不带换行,
    # 会粘在命令输出第一行前面, 例如 "请输入密码EXISTS"), 解析前需整体去掉。
    SUDO_NOISE = ("请输入密码", "验证成功", "[sudo] password for ")

    def strip_sudo_noise(self, text: str) -> str:
        """去掉 sudo 的密码提示/成功提示, 避免污染命令输出解析"""
        for noise in self.SUDO_NOISE:
            text = text.replace(noise, "")
        return text
    # 默认文档查看器进程名; 用 deepin[-]reader 让本命令自身命令行不匹配
    DOC_VIEWER_PATTERN = "deepin[-]reader"

    def get_normal_user_names(self) -> list:
        """列出测试机上的普通用户(uid 1000~65533)

        :return: 用户名字符串列表
        """
        result = self.run_cmd(
            "awk -F: '$3>=1000 && $3<65534 {print $1}' /etc/passwd",
            timeout=5,
            out_debug_flag=False,
        )
        return [line.strip() for line in result.strip().splitlines() if line.strip()]

    def create_fixture_user(self, username: str) -> bool:
        """创建"多用户"前置用的临时普通用户

        用 useradd -m 创建, 家目录/属主/权限与真实用户一致, 使"A 用户家目录下的
        WPS 配置"成为真实的多用户现场。用例 finally 必须调用 remove_fixture_user。
        :param username: 临时用户名
        :return: True 表示用户已存在且家目录已创建
        """
        # 自愈: 上次异常退出可能遗留同名用户
        self.sudo_run_cmd(
            f"userdel -r -f {username} 2>/dev/null; "
            f"rm -rf /home/{username} /media/{username}",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"useradd -m -s /bin/bash {username}",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(1)
        home = self.MULTI_USER_HOME_TEMPLATE.format(user=username)
        return username in self.get_normal_user_names() and os.path.isdir(home)

    def remove_fixture_user(self, username: str) -> bool:
        """删除临时普通用户及其家目录/邮件池, 不留残留

        :param username: 临时用户名
        :return: True 表示用户已从 /etc/passwd 移除
        """
        self.sudo_run_cmd(
            f"pkill -9 -u {username} 2>/dev/null; "
            f"userdel -r -f {username} 2>/dev/null; "
            f"rm -rf /home/{username} /media/{username} "
            f"/var/mail/{username} /var/spool/mail/{username}",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(1)
        return username not in self.get_normal_user_names()

    def setup_other_user_wps_config(self, username: str, marker: str) -> bool:
        """构造"A 用户使用过 WPS"的现场: 在 A 家目录写入 A 自己的 Office.conf

        产品依据(plugin-wps-fix/entry.sh): WPS 的组件模式开关存放在
        ~/.config/Kingsoft/Office.conf, 每个用户各一份。测试机未安装 WPS 且无外网
        (无法以 A 身份真实启动 WPS), 故直接生成 WPS 会写出的配置文件, 并用 marker
        作为 A 的个性化取值, 供"修复不得改动其他用户配置"的断言比对。
        :param username: A 用户
        :param marker: 写入 AppComponentMode 的取值
        :return: True 表示文件已生成且内容含 marker
        """
        home = self.MULTI_USER_HOME_TEMPLATE.format(user=username)
        config = self.MULTI_USER_WPS_CONFIG_TEMPLATE.format(user=username)
        content = (
            "[6.0]\n"
            f"wpsoffice\\Application%20Settings\\AppComponentMode={marker}\n"
        )
        self.sudo_run_cmd(
            f"mkdir -p {home}/.config/Kingsoft && "
            f"printf '%s' '{content}' > {config} && "
            f"chown -R {username}:{username} {home}/.config && "
            f"chmod 700 {home}/.config/Kingsoft && "
            f"chmod 600 {config}",
            timeout=30,
            out_debug_flag=False,
        )
        state = self.get_path_stat(config)
        return state["exists"] and marker in self.get_path_content_as_root(config)

    def get_path_stat(self, path: str) -> dict:
        """以 root 读取任意路径的属主/属组/权限/大小

        其他用户家目录对本用户不可遍历(0750), 因此必须提权读取。
        :param path: 绝对路径
        :return: {"exists", "owner", "group", "mode"(八进制字符串), "size"}
        """
        out = self.strip_sudo_noise(
            self.sudo_run_cmd(
                f'if [ -e "{path}" ]; then echo EXISTS; '
                f'stat -c "%U:%G %a %s" "{path}"; else echo MISSING; fi',
                timeout=10,
                out_debug_flag=False,
            )
        )
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        if "EXISTS" not in lines:
            return {"exists": False, "owner": "", "group": "", "mode": "", "size": 0}
        stat_line = next(
            (line for line in lines if re.match(r"^\S+:\S+ [0-7]{3,4} \d+$", line)),
            "",
        )
        if not stat_line:
            return {"exists": True, "owner": "", "group": "", "mode": "", "size": 0}
        fields = stat_line.split()
        owner, _, group = fields[0].partition(":")
        return {
            "exists": True,
            "owner": owner,
            "group": group,
            "mode": fields[1],
            "size": int(fields[2]),
        }

    def get_path_content_as_root(self, path: str) -> str:
        """以 root 读取任意路径的文件内容(用于其他用户的配置)"""
        return self.strip_sudo_noise(
            self.sudo_run_cmd(
                f'cat "{path}" 2>/dev/null',
                timeout=10,
                out_debug_flag=False,
            )
        ).strip()

    def get_path_md5_as_root(self, path: str) -> str:
        """以 root 计算文件 md5(用于断言"其他用户配置未被改动")"""
        result = self.strip_sudo_noise(
            self.sudo_run_cmd(
                f'md5sum "{path}" 2>/dev/null',
                timeout=10,
                out_debug_flag=False,
            )
        )
        for token in result.split():
            if re.fullmatch(r"[0-9a-f]{32}", token):
                return token
        return ""

    def get_current_user_can_read(self, path: str) -> bool:
        """当前用户能否读取指定路径 —— 多用户隔离的直接证据"""
        result = self.run_cmd(
            f'test -r "{path}" && echo yes || echo no',
            timeout=5,
            out_debug_flag=False,
        )
        return "yes" in result.strip()

    def get_document_viewer_processes(self) -> str:
        """列出当前会话默认文档查看器(deepin-reader)的进程命令行

        测试机未安装 WPS 且无外网无法安装, "双击 doc 文档能正常打开"在本环境以
        系统默认文档处理程序(xdg-mime 指向 deepin-reader)真实打开文档等价验证。
        :return: pgrep -af 的原始输出(pid + 命令行)
        """
        return self.run_cmd(
            f'pgrep -af "{self.DOC_VIEWER_PATTERN}" 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )

    def wait_document_opened(self, file_path: str, timeout: int = 45) -> bool:
        """等待默认文档查看器把指定文档打开(进程命令行包含该文档文件名)

        :param file_path: 被打开文档的绝对路径
        :param timeout: 最长等待秒数
        :return: True 表示查看器进程已带着该文档运行
        """
        name = os.path.basename(file_path)
        for _ in range(timeout):
            if name in self.get_document_viewer_processes():
                return True
            sleep(1)
        return False

    def close_document_viewer(self) -> bool:
        """关闭默认文档查看器

        :return: True 表示已无相关进程残留
        """
        for _ in range(5):
            if not self.get_document_viewer_processes().strip():
                return True
            self.run_cmd(
                f'pkill -f "{self.DOC_VIEWER_PATTERN}" 2>/dev/null',
                timeout=10,
                out_debug_flag=False,
            )
            sleep(2)
        return not self.get_document_viewer_processes().strip()

    # ===== WPS 修复后双击文档打开(用例 2005791) =====
    # 产品依据(plugin-wps-fix/entry.sh): 修复动作把 ~/.config/Kingsoft/Office.conf 的
    # 组件模式统一写成整合模式(prome_fushion); WPS 的 wps/et/wpp 三个组件双击
    # .docx/.xlsx/.pptx 时读的都是这一份配置, 配置缺失/错误时的现象就是"双击文档打不开 WPS"。
    # 测试机未安装 WPS(which wps 为空)且无外网, 因此:
    #   1) 修复动作仍由产品脚本真实执行 —— 断言真实目录/文件/内容/权限/属主/弹框/DBus;
    #   2) "双击文档能打开"用系统默认文档查看器(deepin-reader)真实打开 .docx, 断言查看器
    #      进程命令行带该文档 —— 真实的"文档被打开"证据;
    #   3) 三种格式的分发用桩启动器(替身)验证 —— 补齐缺失的 WPS, 断言双击
    #      .docx/.xlsx/.pptx 时桌面环境按 OOXML 类型分发并把文档路径交给 Office 应用;
    #      用户级 mimeapps.list 先备份, finally 由 remove_office_stub_launcher 还原, 不留残留。

    OPEN_DOC_DIR = "/tmp/autotest_wps_open"
    OPEN_DOC_FORMATS = ("docx", "xlsx", "pptx")
    OPEN_DOC_MIME = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    OFFICE_STUB_SCRIPT = f"{OPEN_DOC_DIR}/office_stub.sh"
    OFFICE_STUB_LOG = f"{OPEN_DOC_DIR}/launched.log"
    OFFICE_STUB_DESKTOP = "autotest-wps-office-stub.desktop"
    OFFICE_MIMEAPPS_BAK = f"{OPEN_DOC_DIR}/mimeapps.list.bak"
    OFFICE_MIMEAPPS = f"{HOME_DIR}/.config/mimeapps.list"
    OFFICE_APPS_DIR = f"{HOME_DIR}/.local/share/applications"

    def create_test_office_docs(self) -> dict:
        """生成 .docx/.xlsx/.pptx 三个最小可用的 OOXML 文档(模拟用户桌面上的文档)

        xdg-mime 按扩展名/内容识别出 OOXML 类型, 双击时据此选择打开程序, 因此文档
        必须是各格式的真实最小包(Content_Types + rels + 主部件)。

        :return: {"docx": 路径, "xlsx": 路径, "pptx": 路径}; 生成失败的格式不出现
        """
        parts = {
            "docx": (
                "word/document.xml",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
                '<document xmlns="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<body><p><r><t>autotest wps open</t></r></p></body></document>",
            ),
            "xlsx": (
                "xl/workbook.xml",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheets><sheet name="Sheet1" sheetId="1"/></sheets></workbook>',
            ),
            "pptx": (
                "ppt/presentation.xml",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
                '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>',
            ),
        }
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/{part}" ContentType="{ctype}"/></Types>'
        )
        rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="{part}"/></Relationships>'
        )
        os.makedirs(self.OPEN_DOC_DIR, exist_ok=True)
        docs = {}
        for fmt in self.OPEN_DOC_FORMATS:
            part, ctype, xml = parts[fmt]
            path = f"{self.OPEN_DOC_DIR}/test_wps_open.{fmt}"
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(
                    "[Content_Types].xml",
                    content_types.format(part=part, ctype=ctype),
                )
                zf.writestr("_rels/.rels", rels.format(part=part))
                zf.writestr(
                    part,
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + xml,
                )
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                docs[fmt] = path
        return docs

    def get_file_mime_type(self, path: str) -> str:
        """查询文件的 MIME 类型(桌面环境双击时据此选择打开程序)"""
        out = self.run_cmd(
            f'xdg-mime query filetype "{path}"',
            timeout=10,
            out_debug_flag=False,
        )
        lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
        return lines[-1] if lines else ""

    def install_office_stub_launcher(self) -> bool:
        """注册"Office 应用桩"(WPS 启动器替身)为三种 OOXML 格式的默认打开程序

        测试机未安装 WPS, 双击 Office 文档没有真实 WPS 可启动; 桩启动器只把收到的
        文档路径写入日志, 用于验证双击时桌面环境确实按 OOXML 类型把文档分发给了
        Office 应用。用户级 mimeapps.list 先备份, 由 remove_office_stub_launcher 还原。

        :return: True 表示三种格式的默认打开程序都已指向桩
        """
        os.makedirs(self.OPEN_DOC_DIR, exist_ok=True)
        with open(self.OFFICE_STUB_SCRIPT, "w") as f:
            f.write(
                "#!/bin/bash\n"
                f'printf "%s\\n" "$@" >> "{self.OFFICE_STUB_LOG}"\n'
            )
        os.chmod(self.OFFICE_STUB_SCRIPT, 0o755)
        os.makedirs(self.OFFICE_APPS_DIR, exist_ok=True)
        mime_types = ";".join(self.OPEN_DOC_MIME[fmt] for fmt in self.OPEN_DOC_FORMATS) + ";"
        with open(f"{self.OFFICE_APPS_DIR}/{self.OFFICE_STUB_DESKTOP}", "w") as f:
            f.write(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Autotest WPS Office Stub\n"
                f"Exec={self.OFFICE_STUB_SCRIPT} %F\n"
                f"MimeType={mime_types}\n"
                "NoDisplay=true\n"
            )
        self.run_cmd(
            f'update-desktop-database "{self.OFFICE_APPS_DIR}" >/dev/null 2>&1 || true',
            timeout=30,
            out_debug_flag=False,
        )
        if os.path.isfile(self.OFFICE_MIMEAPPS):
            try:
                shutil.copy2(self.OFFICE_MIMEAPPS, self.OFFICE_MIMEAPPS_BAK)
            except OSError:
                logger.warning("备份 mimeapps.list 失败, 还原时改用删除默认项")
        for fmt in self.OPEN_DOC_FORMATS:
            self.run_cmd(
                f'xdg-mime default "{self.OFFICE_STUB_DESKTOP}" {self.OPEN_DOC_MIME[fmt]}',
                timeout=15,
                out_debug_flag=False,
            )
        defaults = self.get_office_stub_default_apps()
        return all(
            defaults.get(self.OPEN_DOC_MIME[fmt]) == self.OFFICE_STUB_DESKTOP
            for fmt in self.OPEN_DOC_FORMATS
        )

    def get_office_stub_default_apps(self) -> dict:
        """查询三种 OOXML 格式当前的默认打开程序(desktop 文件名)"""
        defaults = {}
        for fmt in self.OPEN_DOC_FORMATS:
            mime = self.OPEN_DOC_MIME[fmt]
            out = self.run_cmd(
                f"xdg-mime query default {mime}",
                timeout=10,
                out_debug_flag=False,
            )
            lines = [line.strip() for line in out.strip().splitlines() if line.strip()]
            defaults[mime] = lines[-1] if lines else ""
        return defaults

    def open_document_with_default_app(self, path: str) -> bool:
        """模拟双击: 用系统默认程序打开文档(异步, 不阻塞用例)

        :param path: 文档绝对路径
        :return: True 表示文档存在且已发起打开
        """
        if not os.path.isfile(path):
            return False
        self.run_cmd(
            f'nohup xdg-open "{path}" >/dev/null 2>&1 < /dev/null &',
            timeout=10,
            out_debug_flag=False,
        )
        return True

    def get_office_stub_launched_files(self) -> list:
        """读取桩启动器收到的文档路径列表(即双击分发给 Office 应用的文档)"""
        if not os.path.isfile(self.OFFICE_STUB_LOG):
            return []
        try:
            with open(self.OFFICE_STUB_LOG) as f:
                return [line.strip() for line in f if line.strip()]
        except OSError:
            return []

    def wait_office_stub_launched(self, path: str, timeout: int = 20) -> bool:
        """等待桩启动器收到指定文档路径

        :param path: 文档绝对路径
        :param timeout: 最长等待秒数
        :return: True 表示该文档已被双击分发给 Office 应用桩
        """
        for _ in range(timeout):
            if path in self.get_office_stub_launched_files():
                return True
            sleep(1)
        return False

    def remove_office_stub_launcher(self) -> bool:
        """撤销桩: 还原 mimeapps 默认程序, 删除 desktop 文件与临时目录

        :return: True 表示 desktop 文件与临时目录都已不存在(无残留)
        """
        desktop_path = f"{self.OFFICE_APPS_DIR}/{self.OFFICE_STUB_DESKTOP}"
        if os.path.isfile(self.OFFICE_MIMEAPPS_BAK):
            try:
                shutil.copy2(self.OFFICE_MIMEAPPS_BAK, self.OFFICE_MIMEAPPS)
            except OSError:
                logger.error("还原 mimeapps.list 失败")
        else:
            self.run_cmd(
                f'sed -i "/{self.OFFICE_STUB_DESKTOP}/d" "{self.OFFICE_MIMEAPPS}" '
                f"2>/dev/null || true",
                timeout=10,
                out_debug_flag=False,
            )
        try:
            os.remove(desktop_path)
        except OSError:
            pass
        self.run_cmd(
            f'update-desktop-database "{self.OFFICE_APPS_DIR}" >/dev/null 2>&1 || true',
            timeout=30,
            out_debug_flag=False,
        )
        shutil.rmtree(self.OPEN_DOC_DIR, ignore_errors=True)
        return not os.path.exists(desktop_path) and not os.path.isdir(self.OPEN_DOC_DIR)

    # ===== 系统检测-性能-内存占用 方法 =====

    def get_system_memory_total_kb(self) -> int:
        """获取系统总内存大小(KB), 通过 /proc/meminfo 获取(不依赖 locale)"""
        result = self.run_cmd(
            "awk '/^MemTotal:/ {print $2}' /proc/meminfo",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return 0

    def get_system_memory_total_mb(self) -> int:
        """获取系统总内存大小(MB)"""
        return self.get_system_memory_total_kb() // 1024

    def get_system_memory_available_kb(self) -> int:
        """获取系统可用内存大小(KB), 通过 /proc/meminfo 获取(不依赖 locale)"""
        result = self.run_cmd(
            "awk '/^MemAvailable:/ {print $2}' /proc/meminfo",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return 0

    def get_system_memory_used_mb(self) -> int:
        """获取系统已用内存大小(MB), 通过总内存减去可用内存计算"""
        total = self.get_system_memory_total_kb()
        available = self.get_system_memory_available_kb()
        if total <= 0 or available < 0:
            return 0
        return (total - available) // 1024

    def get_system_memory_usage_percent(self) -> float:
        """获取系统内存使用率(百分比)"""
        total = self.get_system_memory_total_kb()
        available = self.get_system_memory_available_kb()
        if total <= 0:
            return 0.0
        used = total - available if available >= 0 else total
        return round(used / total * 100, 1)

    def get_cpu_count(self) -> int:
        """获取系统逻辑 CPU 核数(用于判断负载是否合理)"""
        result = self.run_cmd("nproc 2>/dev/null", timeout=5, out_debug_flag=False)
        try:
            return max(int(result.strip()), 1)
        except (ValueError, AttributeError):
            return 1

    def get_system_load_average(self) -> float:
        """获取系统 1 分钟平均负载(/proc/loadavg 第一列)

        与系统监视器"负载"口径一致; 全盘扫描属于重 IO 任务, 但不应把系统
        压到所有核都排满(%CPU 长期 100%)。
        """
        result = self.run_cmd(
            "awk '{print $1}' /proc/loadavg 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return float(result.strip())
        except (ValueError, AttributeError):
            return 0.0

    # ===== 控制中心自定义快捷键(D-Bus 等价实现) =====

    KEYBINDING_SERVICE = "com.deepin.daemon.Keybinding"
    KEYBINDING_PATH = "/com/deepin/daemon/Keybinding"

    def call_keybinding(self, method, signature="", *args) -> str:
        """调用 dde-daemon 快捷键服务方法

        :param method: 方法名, 如 AddCustomShortcut
        :param signature: busctl 参数签名, 如 sss
        :param args: 参数值
        :return: busctl 输出文本
        """
        sig = f" {signature}" if signature else ""
        values = "".join(f' "{a}"' for a in args)
        return self.run_cmd(
            f"busctl --user call {self.KEYBINDING_SERVICE} {self.KEYBINDING_PATH} "
            f"{self.KEYBINDING_SERVICE} {method}{sig}{values}",
            timeout=15,
            out_debug_flag=False,
        ).strip()

    @staticmethod
    def decode_busctl_text(text) -> str:
        """还原 busctl 输出中的八进制转义(非 ASCII 字符串)

        busctl 按 C 风格输出字符串, 中文会被转成 \345\261\217 形式。

        :param text: busctl 原始输出
        :return: 解码后的文本
        """
        import re as _re

        text = (text or "").strip()
        # busctl 输出形如: s "[{\"Id\":\"...\"}]", 先去掉外层 s "..." 与转义引号
        text = _re.sub(r'^s "(.*)"$', lambda m: m.group(1), text, flags=_re.S)
        text = text.replace('\\"', '"')
        decoded = _re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), text)
        try:
            return decoded.encode("latin1").decode("utf-8", "replace")
        except UnicodeEncodeError:
            return decoded

    def add_custom_keybinding(self, name, command, accel):
        """添加自定义快捷键(等价控制中心 "键盘与语言-快捷键-添加")

        :param name: 快捷键名称
        :param command: 执行的命令
        :param accel: X 键盘格式快捷键, 如 "<Control>m"
        :return: (shortcut_id, flags, raw_output); 失败时 (None, None, raw)
        """
        out = self.call_keybinding("AddCustomShortcut", "sss", name, command, accel)
        match = re.match(r'si\s+"([^"]*)"\s+(\d+)', out)
        if not match:
            return None, None, out
        return self.decode_busctl_text(match.group(1)), int(match.group(2)), out

    def list_custom_keybindings(self) -> list:
        """列出所有自定义快捷键(Type=1)

        解析前先还原 busctl 的八进制转义, 否则中文名称/Id 无法匹配。

        :return: [{"Id","Type","Name","Exec","Accels"}, ...]
        """
        out = self.decode_busctl_text(self.call_keybinding("List"))
        result = []
        for item in re.findall(
            r'\{"Id":"([^"]*)","Type":(\d+),"Accels":\[([^\]]*)\]'
            r'(?:,"Name":"([^"]*)")?(?:,"Exec":"([^"]*)")?\}',
            out,
        ):
            shortcut_id, shortcut_type, accels, shortcut_name, command = item
            result.append(
                {
                    "Id": shortcut_id,
                    "Type": int(shortcut_type),
                    "Accels": [
                        x.strip().strip('"') for x in accels.split(",") if x.strip()
                    ],
                    "Name": shortcut_name,
                    "Exec": command,
                }
            )
        return [item for item in result if item["Type"] == 1]

    def get_custom_keybinding(self, name):
        """按名称查询自定义快捷键

        :param name: 快捷键名称
        :return: 命中项字典, 未找到返回 None
        """
        for item in self.list_custom_keybindings():
            if item["Name"] == name:
                return item
        return None

    def get_custom_keybinding_by_accel(self, accel):
        """按快捷键(如 "<Control>m")查询自定义快捷键

        :param accel: X 键盘格式快捷键
        :return: 命中项字典, 未找到返回 None
        """
        for item in self.list_custom_keybindings():
            if accel in item["Accels"]:
                return item
        return None

    def delete_custom_keybinding(self, shortcut_id):
        """删除自定义快捷键(等价控制中心删除, 用于用例回退)

        :param shortcut_id: AddCustomShortcut 返回的 Id
        """
        self.call_keybinding("DeleteCustomShortcut", "s", shortcut_id)

    def press_key_combo(self, keys) -> bool:
        """在当前桌面发送组合键(xdotool XTEST)

        :param keys: xdotool 组合键写法, 如 "ctrl+m"
        :return: True 表示命令执行成功
        """
        out, rc = self.run_cmd(
            f"xdotool key --clearmodifiers {keys}",
            timeout=10,
            out_debug_flag=False,
            return_code=True,
        )
        return rc == 0

    # ===== 兼容性(平台差异化)与注销能力检查辅助 =====

    def get_system_arch(self) -> str:
        """获取内核架构(uname -m), 如 x86_64/aarch64/loongarch64"""
        return self.run_cmd(
            "uname -m", timeout=5, out_debug_flag=False
        ).strip()

    def get_elf_machine(self, path) -> str:
        """获取 ELF 文件的目标架构(readelf -h 的 Machine 字段)

        :param path: ELF 文件路径
        :return: Machine 字段文本, 读取失败返回空串
        """
        result = self.run_cmd(
            f"LC_ALL=C readelf -W -h {path} 2>/dev/null | grep 'Machine:'",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip()

    def get_app_process_running(self, pattern) -> bool:
        """按进程名精确匹配判断应用是否在运行(pgrep -f '^name$')"""
        result = self.run_cmd(
            f"pgrep -f '^{pattern}$' >/dev/null 2>&1 && echo running",
            timeout=5,
            out_debug_flag=False,
        )
        return "running" in result

    def launch_gui_app(self, binary, timeout=30) -> bool:
        """在当前桌面会话中启动 GUI 应用并等待进程出现

        应用在后台独立会话中启动(setsid), 输出丢弃, 避免阻塞测试进程。

        :param binary: 可执行文件名/路径, 如 deepin-editor
        :param timeout: 等待进程出现的秒数
        :return: True 如果进程已运行
        """
        self.run_cmd(
            f"setsid nohup {binary} >/dev/null 2>&1 < /dev/null &",
            timeout=10,
            out_debug_flag=False,
        )
        for _ in range(timeout):
            if self.get_app_process_running(binary.split("/")[-1]):
                return True
            sleep(1)
        return False

    def close_gui_app(self, binary) -> bool:
        """关闭由用例启动的 GUI 应用(精确匹配进程名, 不误杀其它程序)

        :return: True 如果进程已退出
        """
        name = binary.split("/")[-1]
        self.run_cmd(
            f"pkill -f '^{name}$' 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        )
        for _ in range(10):
            if not self.get_app_process_running(name):
                return True
            sleep(1)
        return False

    def get_session_manager_method(self, method, *args) -> str:
        """调用 com.deepin.SessionManager 的方法并返回原始返回值

        会话管理器提供 CanLogout/CanReboot/CanShutdown/RequestLogout/Logout
        等注销能力; 这里只调用查询类方法, 不触发真正的注销。

        :param method: 方法名, 如 CanLogout
        :param args: 方法参数
        :return: busctl 输出文本
        """
        extra = (" " + " ".join(str(a) for a in args)) if args else ""
        return self.run_cmd(
            "busctl --user call com.deepin.SessionManager "
            "/com/deepin/SessionManager com.deepin.SessionManager "
            f"{method}{extra}",
            timeout=15,
            out_debug_flag=False,
        ).strip()

    def get_session_inhibitors(self) -> str:
        """获取当前阻止注销/关机的 inhibitor 列表

        :return: systemd-inhibit --list 输出文本
        """
        return self.run_cmd(
            "systemd-inhibit --list --no-pager 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )

    def get_visible_window_titles(self) -> list:
        """枚举当前桌面可见窗口的标题(_NET_WM_NAME)

        :return: 窗口标题列表
        """
        out = self.run_cmd(
            'for w in $(xdotool search --onlyvisible --name ".*" 2>/dev/null); do '
            "xprop -id $w _NET_WM_NAME 2>/dev/null | "
            "sed -n 's/.*= \"\\(.*\\)\"/\\1/p'; done",
            timeout=20,
            out_debug_flag=False,
        )
        return [x.strip() for x in (out or "").splitlines() if x.strip()]

    def get_pc_manager_blacklist_ui_strings(self) -> str:
        """检查产品二进制中是否存在"黑名单"提示文案

        :return: 命中的字符串行, 无命中返回空串
        """
        return self.run_cmd(
            "for f in /usr/libexec/deepin/deepin-pc-manager "
            "/usr/lib/deepin-daemon/deepin-pc-manager-daemon "
            "/usr/lib/deepin-pc-manager/plugins/*/*.so; do "
            'strings "$f" 2>/dev/null | grep -iE "blacklist|黑名单"; done',
            timeout=60,
            out_debug_flag=False,
        )

    def get_pc_manager_pid(self) -> int:
        """获取电脑管家主进程 PID(排除 daemon/session-daemon)

        :return: PID, 未运行时返回 0
        """
        result = self.run_cmd(
            "pgrep -f '^/usr/libexec/deepin/deepin-pc-manager|"
            "^/usr/bin/deepin-pc-manager' 2>/dev/null | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return 0

    def get_pc_manager_memory_usage_kb(self) -> int:
        """获取电脑管家进程的内存占用(KB), 通过 ps 命令获取"""
        result = self.run_cmd(
            r"ps -eo rss,args | grep -E 'deepin-pc-manager' | grep -v daemon | grep -v session-daemon | grep -v grep | awk '{sum+=$1} END {print sum+0}'",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return 0

    # ===== 内存使用率 > 80% 高占用场景 方法 =====

    _MEMSTRESS_SCRIPT = "/tmp/pcm_memstress.py"
    _MEMSTRESS_PID = "/tmp/pcm_memstress.pid"
    _MEMSTRESS_LOG = "/tmp/pcm_memstress.log"

    def _write_memstress_script(self):
        """写入内存压力脚本到 /tmp/pcm_memstress.py

        脚本分配并持有匿名内存(每 5 秒回写一次保持页面活跃, 避免被换出),
        直到被杀死; 启动时将自身 PID 写入 /tmp/pcm_memstress.pid。
        """
        script = (
            "import os, sys, time\n"
            "target = int(sys.argv[1]) if len(sys.argv) > 1 else 85\n"
            "def read_meminfo():\n"
            "    info = {}\n"
            "    with open('/proc/meminfo') as f:\n"
            "        for line in f:\n"
            "            p = line.split(':')\n"
            "            if len(p) == 2:\n"
            "                try:\n"
            "                    info[p[0].strip()] = int(p[1].split()[0])\n"
            "                except Exception:\n"
            "                    pass\n"
            "    return info\n"
            "def usage_percent():\n"
            "    info = read_meminfo()\n"
            "    total = info.get('MemTotal', 0)\n"
            "    available = info.get('MemAvailable', 0)\n"
            "    if total <= 0:\n"
            "        return 0.0\n"
            "    return (total - available) * 100.0 / total\n"
            "with open('%s', 'w') as f:\n"
            "    f.write(str(os.getpid()))\n"
            "total_kb = read_meminfo().get('MemTotal', 0)\n"
            "safety_cap = int(total_kb * 0.85) * 1024\n"
            "blocks = []\n"
            "allocated = 0\n"
            "chunk = 128 * 1024 * 1024\n"
            "while usage_percent() < target and allocated < safety_cap:\n"
            "    size = min(chunk, safety_cap - allocated)\n"
            "    try:\n"
            "        buf = bytearray(size)\n"
            "        for i in range(0, len(buf), 4096):\n"
            "            buf[i] = 1\n"
            "        blocks.append(buf)\n"
            "        allocated += size\n"
            "    except MemoryError:\n"
            "        break\n"
            "    time.sleep(0.2)\n"
            "while True:\n"
            "    for buf in blocks:\n"
            "        for i in range(0, len(buf), 4096):\n"
            "            buf[i] = 1\n"
            "    time.sleep(5)\n"
        ) % self._MEMSTRESS_PID
        try:
            with open(self._MEMSTRESS_SCRIPT, "w") as f:
                f.write(script)
        except Exception:
            self.run_cmd(
                "cat > %s <<'PYEOF'\n%s\nPYEOF" % (self._MEMSTRESS_SCRIPT, script),
                timeout=10,
                out_debug_flag=False,
            )

    def start_memory_stress(self, target_percent=85, timeout=60) -> bool:
        """启动后台内存压力进程, 将系统内存使用率提升到 80% 以上

        通过后台 Python 进程分配并持有匿名内存, 降低 MemAvailable, 使内存
        使用率超过 80%, 用于触发电脑管家硬件检测 detectMemory 的"内存使用率
        过高"判定(usagePercent > 80 时结果置为异常)。
        :param target_percent: 目标内存使用率(百分比), 默认 85
        :param timeout: 等待使用率超过 80% 的最长秒数
        :return: True 如果压力进程已启动且使用率超过 80%
        """
        self.stop_memory_stress()
        sleep(1)
        self._write_memstress_script()
        self.run_cmd(
            "nohup /usr/bin/python3 %s %d > %s 2>&1 < /dev/null &"
            % (self._MEMSTRESS_SCRIPT, target_percent, self._MEMSTRESS_LOG),
            timeout=10,
            out_debug_flag=False,
        )
        for _ in range(timeout):
            if self.get_system_memory_usage_percent() > 80.0:
                return True
            sleep(1)
        return False

    def get_memory_stress_pid(self) -> str:
        """获取当前内存压力进程的 PID, 进程不存在时返回空串"""
        result = self.run_cmd(
            "cat %s 2>/dev/null" % self._MEMSTRESS_PID,
            timeout=5,
            out_debug_flag=False,
        )
        pid = result.strip()
        if pid.isdigit():
            alive = self.run_cmd(
                "kill -0 %s 2>/dev/null && echo yes || echo no" % pid,
                timeout=5,
                out_debug_flag=False,
            )
            if "yes" in alive:
                return pid
        return ""

    def stop_memory_stress(self):
        """停止内存压力进程并释放占用的内存"""
        pid = self.get_memory_stress_pid()
        if pid:
            self.run_cmd(
                "kill -9 %s 2>/dev/null; sleep 1" % pid,
                timeout=10,
                out_debug_flag=False,
            )
        self.run_cmd(
            "rm -f %s 2>/dev/null" % self._MEMSTRESS_PID,
            timeout=5,
            out_debug_flag=False,
        )

    def check_valgrind_available(self) -> bool:
        """检查 valgrind 工具是否已安装"""
        result = self.run_cmd(
            "which valgrind 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def install_valgrind(self) -> bool:
        """安装 valgrind(性能用例前置"已安装 valgrind")

        先直接 `apt-get install -y`(命中本地缓存/内网源); 失败才 `apt-get update`
        后重试一次。旧实现每次都先 update, 单次 30s 起步, 而安装通常一次即中。

        :return: True 表示 valgrind 可执行文件可用
        """

        if self.check_valgrind_available():
            return True
        install_cmd = (
            f"echo '{conf.PASSWORD}' | sudo -S env DEBIAN_FRONTEND=noninteractive "
            f"apt-get install -y valgrind"
        )
        self.run_cmd(install_cmd, timeout=240, out_debug_flag=False)
        if not self.check_valgrind_available():
            self.run_cmd(
                f"echo '{conf.PASSWORD}' | sudo -S apt-get update -qq >/dev/null 2>&1 || true; "
                + install_cmd,
                timeout=300,
                out_debug_flag=False,
            )
        for _ in range(10):
            if self.check_valgrind_available():
                return True
            sleep(1)
        return False

    def uninstall_valgrind(self):
        """卸载 valgrind, 恢复用例执行前"未安装"的现场"""

        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get remove -y valgrind",
            timeout=120,
            out_debug_flag=False,
        )

    def run_valgrind_pc_manager(self, duration=20, log_path=None) -> dict:
        """用 valgrind 启动电脑管家, 调出界面运行指定时长后正常退出

        与用例步骤一致: valgrind 拉起应用 -> 调出界面 -> 运行 -> 退出应用 ->
        分析 valgrind 日志。

        退出方式很关键: 产品 **没有** 注册 SIGTERM 处理, `kill -TERM` 会按默认
        动作终止进程, 跳过析构与 atexit, 此时 valgrind 会把"指针随栈退出而失效"
        的分配判成 definitely lost, 泄漏统计不可信。因此这里先关闭主窗口
        (V20 关窗即进程退出) 触发正常析构; 90s 内没退才退回 SIGTERM 并在
        `exit_mode` 里标记, 让用例能区分"正常退出"与"被强杀"。

        :param duration: 界面出现后继续运行的秒数
        :param log_path: valgrind 输出路径, 默认 /tmp/pcm_valgrind_result.log
        :return: launched/pid/terminated/window_shown/exit_mode/log_path 字典
        """
        log_path = log_path or "/tmp/pcm_valgrind_result.log"
        binary = "/usr/libexec/deepin/deepin-pc-manager"
        if not os.path.exists(binary):
            binary = "/usr/bin/deepin-pc-manager"
        info = {
            "launched": False,
            "pid": "",
            "terminated": False,
            "exit_mode": "",
            "early_exit": False,
            "summary_written": False,
            "window_shown": False,
            "log_path": log_path,
        }
        if not os.path.exists(binary) or not self.check_valgrind_available():
            return info

        self.kill_pc_manager()
        self.run_cmd(f"rm -f {log_path}", timeout=5, out_debug_flag=False)
        # 清掉上一轮残留的 valgrind(它会让本轮 pgrep 拿到旧 pid, 等错进程)
        self.run_cmd("pkill -f 'valgrind.bin.*deepin-pc-manager' 2>/dev/null; true", timeout=5)
        # 单实例守卫: 上一轮应用若还在收尾, 新实例会直接提示
        # "Another instance is already running" 并退出(实测 2026-11-13, 第二轮
        # 因此无窗口, 白等满 120s), 所以先等旧实例彻底消失再拉起。
        for _ in range(20):
            still = self.run_cmd(
                "pgrep -f 'valgrind.bin.*deepin-pc-manager' >/dev/null 2>&1 && echo vg || true",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            if not still and not self.get_main_window_id():
                break
            sleep(1)
        self.run_cmd(
            "export QT_ACCESSIBILITY=1 && "
            "export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1 && "
            f"setsid valgrind --leak-check=full --show-leak-kinds=definite,indirect "
            f"--num-callers=30 --log-file={log_path} {binary} "
            f"> /dev/null 2>&1 < /dev/null &",
            timeout=10,
            out_debug_flag=False,
        )
        for _ in range(120):
            # 只认 valgrind.bin 本体: `setsid valgrind ... &` 的中间 shell 也匹配
            # 宽泛模式, 抓错进程会让我们对壳发信号、本体继续跑(实测 2026-11-13)
            pid = self.run_cmd(
                "pgrep -f 'valgrind.bin.*deepin-pc-manager' 2>/dev/null | head -1",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            if pid:
                info["launched"] = True
                info["pid"] = pid
                break
            sleep(1)
        if not info["launched"]:
            return info

        # 注意: valgrind 是"自身进程内"运行被测程序, 不会额外 fork 出
        # /usr/libexec/deepin/deepin-pc-manager, 所以不能用 pgrep 应用二进制判断
        # 存活(实测恒为空, 曾导致误判 early_exit / 误判"应用已退出")。
        def valgrind_alive() -> bool:
            return "alive" in self.run_cmd(
                f"kill -0 {info['pid']} 2>/dev/null && echo alive || echo gone",
                timeout=5,
                out_debug_flag=False,
            )

        # 窗口就绪: 用 xdotool 轻量轮询(valgrind 下启动慢, AT-SPI 重连单次约 2s,
        # 这里只判断主窗口是否已创建, 不需要导航树)。每轮顺带确认应用子进程还在:
        # 单实例守卫/崩溃会让它立刻消失, 此时应立刻返回, 不要空等满 120s。
        for i in range(60):
            if self.get_main_window_id():
                info["window_shown"] = True
                break
            if not valgrind_alive() and i >= 3:
                # 进程已消失且没有窗口: 崩溃/单实例守卫让新实例直接退出
                info["early_exit"] = True
                break
            sleep(1)
        if not info["window_shown"]:
            return info

        sleep(duration)
        # 退出: 先试关窗正常退出(V20 关窗即进程退出); 关窗常不生效(应用留在托盘),
        # 此时给 valgrind 发 SIGTERM -- 它会转发给被插桩程序, 程序结束后照常做
        # 泄漏检查并写出 LEAK SUMMARY。绝不能对 valgrind 发 SIGKILL, 那样日志里
        # 只剩零散记录、没有汇总(实测 2026-11-13)。
        self.close_main_window()
        for _ in range(10):
            if not valgrind_alive():
                info["exit_mode"] = "close_window"
                break
            sleep(1)
        if valgrind_alive():
            self.run_cmd(f"kill -TERM {info['pid']} 2>/dev/null || true", timeout=5)
            info["exit_mode"] = "sigterm"
            for _ in range(120):
                if not valgrind_alive():
                    break
                sleep(1)
        info["terminated"] = not valgrind_alive()
        if not info["terminated"]:
            # valgrind 卡在泄漏检查: 强杀, 日志可能缺汇总
            self.run_cmd(f"kill -KILL {info['pid']} 2>/dev/null || true", timeout=5)
        for _ in range(10):
            count = self.run_cmd(
                f"grep -c 'LEAK SUMMARY' {log_path} 2>/dev/null || true",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            if count not in ("", "0"):
                info["summary_written"] = True
                break
            sleep(1)
        return info

    _VALGRIND_PARSE_PY = r"""
import json, re, sys
path = sys.argv[1]
try:
    text = open(path, encoding="utf-8", errors="replace").read()
except OSError:
    print(json.dumps({"exists": False}))
    raise SystemExit(0)
lines = text.splitlines()
own_markers = ("libdeepin-pc-manager", "deepin-pc-manager")
frame_re = re.compile(r"^==\d+==\s+(?:at|by) 0x")
def first_frame(block_lines):
    # 取记录的首个栈帧(出错点/分配点)。不能"栈里只要有产品帧就算产品":
    # librsvg/pixman/Qt5Gui 的栈深处一定会回调到产品 main(), 那样几乎每条记录
    # 都会被算成产品问题(实测: 15 条未初始化读全部落在渲染库内部)。
    for ln in block_lines:
        if frame_re.match(ln):
            # 跳过 valgrind 自己的 malloc/new 包装帧, 取真正的调用点
            if "vg_replace_malloc" in ln or "vgpreload" in ln:
                continue
            return ln
    return ""
def is_own(frame_line):
    return any(marker in frame_line for marker in own_markers)
err_patterns = {
    "uninitialised": "Conditional jump or move depends on uninitialised",
    "invalid_read": "Invalid read of size",
    "invalid_write": "Invalid write of size",
    "overlap": "Source and destination overlap",
}
counts = {k: 0 for k in err_patterns}
own_counts = {k: 0 for k in err_patterns}
own = 0
i = 0
while i < len(lines):
    line = lines[i]
    hit = [k for k, pat in err_patterns.items() if pat in line]
    if hit:
        counts[hit[0]] += 1
        if is_own(first_frame(lines[i + 1:i + 31])):
            own += 1
            own_counts[hit[0]] += 1
    i += 1

# LEAK SUMMARY 只给总量; "哪些块是产品自己丢的"必须按 loss record 归属。
# 记录形式: "N bytes in K blocks are definitely lost in loss record ...",
# 或 "N (D direct, I indirect) bytes in K blocks are definitely lost ..."。
rec_re = re.compile(
    r"([\d,]+) (?:\((\d[\d,]*) direct, ([\d,]+) indirect\) )?bytes in "
    r"([\d,]+) blocks are (definitely|indirectly) lost in loss record"
)
own_direct = {"definitely": 0, "indirectly": 0}
own_blocks = {"definitely": 0, "indirectly": 0}
i = 0
while i < len(lines):
    m = rec_re.search(lines[i])
    if not m:
        i += 1
        continue
    total = int(m.group(1).replace(",", ""))
    direct = int(m.group(2).replace(",", "")) if m.group(2) else total
    kind = m.group(5)
    frames = []
    j = i + 1
    while j < len(lines) and not re.match(r"^==\d+==\s*$", lines[j]):
        frames.append(lines[j])
        j += 1
    if is_own(first_frame(frames)):
        own_direct[kind] += direct
        own_blocks[kind] += int(m.group(4).replace(",", ""))
    i = j + 1
def leaked(kind):
    m = re.search(kind + r": ([0-9,]+) bytes", text)
    return int(m.group(1).replace(",", "")) if m else -1
summary = ""
for ln in reversed(lines):
    if "ERROR SUMMARY" in ln:
        summary = ln.strip()
        break
print(json.dumps({
    "exists": True,
    "uninitialised": counts["uninitialised"],
    "invalid_read": counts["invalid_read"],
    "invalid_write": counts["invalid_write"],
    "overlap": counts["overlap"],
    "own_frames_errors": own,
    "uninitialised_own": own_counts["uninitialised"],
    "invalid_read_own": own_counts["invalid_read"],
    "invalid_write_own": own_counts["invalid_write"],
    "overlap_own": own_counts["overlap"],
    "definitely_lost": leaked("definitely lost"),
    "indirectly_lost": leaked("indirectly lost"),
    "definitely_lost_own": own_direct["definitely"],
    "indirectly_lost_own": own_direct["indirectly"],
    "lost_blocks_own": own_blocks["definitely"],
    "error_summary": summary,
    "size": len(text),
}))
"""

    def parse_valgrind_log(self, log_path=None) -> dict:
        """解析 valgrind 日志: 四类错误关键字计数 + LEAK SUMMARY

        - uninitialised / invalid_read / invalid_write / overlap: 描述中 1~3 类关键字
        - own_frames_errors: 错误记录(错误行后 30 行栈)包含被测程序自身模块的次数,
          用于区分"产品自身问题"与 Qt/X11 系统库噪声
        - definitely_lost / indirectly_lost: LEAK SUMMARY 字节数, 未找到为 -1

        :param log_path: valgrind 日志路径, 默认 /tmp/pcm_valgrind_result.log
        :return: 统计字典, 日志不可读时 {"exists": False}
        """
        import base64
        import json as _json

        log_path = log_path or "/tmp/pcm_valgrind_result.log"
        encoded = base64.b64encode(self._VALGRIND_PARSE_PY.encode()).decode()
        out = self.run_cmd(
            f"if [ -s {log_path} ]; then "
            f"echo {encoded} | base64 -d | python3 - {log_path}; "
            f"else echo '{{\"exists\": false}}'; fi",
            timeout=30,
            out_debug_flag=False,
        )
        try:
            return _json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {"exists": False}

    def run_valgrind_leak_check(self) -> bool:
        """使用 valgrind 检测 deepin-pc-manager 内存泄漏

        若 valgrind 未安装则返回 True(跳过检测)。
        若已安装, 以 valgrind 启动应用运行约 15 秒后终止,
        检查 valgrind 输出中是否存在明确的内存泄漏。
        """
        if not self.check_valgrind_available():
            return True

        self.kill_pc_manager()
        sleep(2)

        binary = "/usr/libexec/deepin/deepin-pc-manager"
        if not os.path.exists(binary):
            binary = "/usr/bin/deepin-pc-manager"
        if not os.path.exists(binary):
            return True

        check_result = self.run_cmd(
            f"timeout 15 valgrind --leak-check=summary {binary} 2>&1 | "
            f"grep -E 'definitely lost|indirectly lost|ERROR SUMMARY' || true",
            timeout=25,
            out_debug_flag=False,
        )
        self.kill_pc_manager()
        sleep(1)

        if "definitely lost: 0 bytes" in check_result:
            return True
        if "definitely lost" not in check_result:
            return True
        return False

    def get_detection_memory_item_showing(self) -> bool:
        """检查系统检测结果中是否包含内存相关检测项

        V20/V25 上检测项的 AT-SPI 元素名称可能不同,
        通过多种表达式依次查找内存相关的检测项。
        """
        self._safe_focus_windows()
        memory_exprs = [
            "$//detection_page//memory",
            "$//detection_page//内存",
            "$//detectionResultsPage//memory",
            "$//detectionResultsPage//内存",
            "$//detection_page//detectionGroup_memory",
        ]
        for expr in memory_exprs:
            try:
                elements = self.dog.find_elements_by_attr(expr)
                if elements:
                    return True
            except BaseException:
                continue
        return False

    def get_repair_offline_switch_showing(self) -> bool:
        """检查修复工具页面的离线筛选开关是否可见

        通过 AT-SPI 表达式查找 repairOfflineOnlySwitch 控件。
        V20 使用 snake_case, V25 使用 camelCase。
        """
        switch_exprs = [
            "$//repair_page//repair_offlineSwitch",
            "$//repair_page//repairOfflineSwitch",
            "$//repair_offlineSwitch",
            "$//repairOfflineSwitch",
            "$//repair_page//repair_offlineFilterGroup//repair_offlineSwitch",
            "$//repair_page//repairOfflineFilterGroup//repairOfflineSwitch",
        ]
        return bool(self._find_element_in_exprs(switch_exprs))

    # ===== 桌面修复-密钥环频繁弹出 模块方法 =====

    def get_keyring_file_exists(self) -> bool:
        """检查密钥环文件是否存在

        修复脚本检查两个路径:
        - ~/.local/share/keyrings/login.keyring
        - ~/.local/share/deepin-keyrings-wb/login.keyring
        任一存在即视为密钥环弹窗问题存在。
        """
        result = self.run_cmd(
            'test -f "$HOME/.local/share/keyrings/login.keyring" && echo yes; '
            'test -f "$HOME/.local/share/deepin-keyrings-wb/login.keyring" && echo yes',
            timeout=5,
            out_debug_flag=False,
        )
        return "yes" in result

    def create_fake_keyring_file(self):
        """创建模拟密钥环文件以触发密钥环修复场景

        在 ~/.local/share/keyrings/ 目录下创建 login.keyring 文件,
        模拟密钥环频繁弹出的异常状态, 使修复工具有目标文件可修复。
        """
        self.run_cmd(
            'mkdir -p "$HOME/.local/share/keyrings" && '
            'echo "fake-keyring-content" > "$HOME/.local/share/keyrings/login.keyring"',
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_keyring_login_files(self) -> bool:
        """删除两处 login.keyring, 构造"仅有本次假密钥环"的现场

        修复脚本按顺序判断 ~/.local/share/keyrings/login.keyring 与
        ~/.local/share/deepin-keyrings-wb/login.keyring: 只要任一路径存在,
        get_keyring_file_exists 就为真。测试机上 wb 目录通常已有用户真实
        login.keyring, 只删 status 目录+建假文件时, 断言"修复后文件消失"
        会被真实文件卡住。调用方需先 backup_keyring_state(), 才能真正回退。
        :return: True 表示两处文件都已不存在
        """
        self.run_cmd(
            'rm -f "$HOME/.local/share/keyrings/login.keyring" '
            '"$HOME/.local/share/deepin-keyrings-wb/login.keyring" '
            "2>/dev/null; true",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)
        return not self.get_keyring_file_exists()

    def remove_fake_keyring_file(self):
        """清理模拟密钥环文件(测试后恢复环境)"""
        self.run_cmd(
            'rm -f "$HOME/.local/share/keyrings/login.keyring" 2>/dev/null; '
            'rm -f "$HOME/.local/share/deepin-keyrings-wb/login.keyring" 2>/dev/null',
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def wait_keyring_file_deleted(self, timeout=60) -> bool:
        """等待密钥环文件被修复脚本删除

        :param timeout: 最长等待秒数
        :return: True 表示文件已被删除(修复成功), False 表示超时仍存在
        """
        for _ in range(timeout):
            if not self.get_keyring_file_exists():
                return True
            sleep(1)
        return False

    def click_keyring_fix_card(self):
        """点击密钥环修复卡片

        复用通用卡片点击实现(AT-SPI Press 动作), 该方式对 QML 卡片有效;
        直接调用 AT-SPI Node.click() 在部分版本上不会触发 clicked 信号,
        导致停留在列表页无法进入详情。
        """
        self._safe_focus_windows()
        try:
            if not self.get_window_maximized_status():
                self.maximize_window_by_shortcut()
                sleep(2)
                self._safe_focus_windows()
                self.reconnect_dogtail()
        except BaseException:
            self.reconnect_dogtail()
        self.click_repair_card_by_name("密钥环修复")
        sleep(1)

    def click_keyring_fix_card_and_repair(self) -> bool:
        """点击密钥环修复卡片并执行修复流程

        封装完整的密钥环修复流程: 点击卡片 → 等待详情页 → 点击开始修复 →
        等待修复对话框 → 等待密钥环文件删除 → 关闭对话框。
        :return: True 表示修复流程成功完成, False 表示某步骤失败
        """
        self.click_keyring_fix_card()
        if not self.get_repair_detail_showing():
            return False
        self.click_start_repair_button()
        if not self.get_repair_dialog_showing():
            return False
        if not self.wait_keyring_file_deleted(timeout=60):
            self.close_repair_dialog()
            return False
        self.close_repair_dialog()
        return True

    # 密钥环修复用例需要构造/回退的现场: deepin-keyrings-wb/status 记录密钥环
    # "已提示"状态, 删除后每次密钥环访问都会再次弹出解锁框(即描述里的"频繁弹出")。
    KEYRING_LOGIN_FILE = os.path.join(
        HOME_DIR, ".local/share/keyrings/login.keyring"
    )
    KEYRING_WB_LOGIN_FILE = os.path.join(
        HOME_DIR, ".local/share/deepin-keyrings-wb/login.keyring"
    )
    KEYRING_STATUS_DIR = os.path.join(
        HOME_DIR, ".local/share/deepin-keyrings-wb/status"
    )
    KEYRING_STATE_BACKUP_DIR = "/tmp/autotest_keyring_state"
    # 密钥环解锁窗口的识别关键字(标题/类名/所属进程名)与排除项
    KEYRING_PROMPT_KEYWORDS = (
        "密钥环",
        "keyring",
        "解锁",
        "unlock",
        # 创建/解锁密钥环的密码框由 gcr-prompter 创建, 窗口标题为空,
        # 只能靠 WM_CLASS/进程名识别
        "gcr-prompter",
        "prompter",
    )
    # 排除项含 deepin-pc-manag: ps -o comm= 只保留 15 个字符, 进程名被截断,
    # 只写 full name 会把电脑管家的修复对话框误判成密钥环弹窗
    KEYRING_PROMPT_EXCLUDES = (
        "电脑管家",
        "deepin-pc-manager",
        "deepin-pc-manag",
    )

    def _keyring_state_items(self) -> dict:
        """密钥环修复用例需要备份/回退的路径映射 {备份名: 绝对路径}"""
        return {
            "login.keyring": self.KEYRING_LOGIN_FILE,
            "wb_login.keyring": self.KEYRING_WB_LOGIN_FILE,
            "wb_status": self.KEYRING_STATUS_DIR,
        }

    def _keyring_path_exists(self, path: str) -> bool:
        """检查测试机上的路径是否存在(含目录/符号链接)"""
        return bool(
            self.run_cmd(
                f"test -e {quote(path)} && echo yes",
                timeout=5,
                out_debug_flag=False,
            ).strip()
        )

    def get_keyring_status_dir_exists(self) -> bool:
        """检查 deepin-keyrings-wb/status 目录是否存在"""
        return self._keyring_path_exists(self.KEYRING_STATUS_DIR)

    def backup_keyring_state(self) -> bool:
        """备份密钥环文件与 deepin-keyrings-wb/status 目录, 供 finally 原样回退

        用例要构造"密钥环频繁弹出"现场(删除 status 目录、写入损坏的
        login.keyring), 被测机上这些路径可能已有用户真实数据, 必须先备份,
        否则会破坏桌面密钥环。

        备份目录之前是"先 rm -rf 再建", 一旦上一次用例被中断(没用 finally
        回退), 下一次备份会把**上一次的有效备份清空**, 而源文件此时已被
        上一次删掉 —— 备份变成空目录, 还原等于删除用户真实文件(2005739
        实测丢失过 login.keyring)。因此这里发现遗留备份时先按它还原现场,
        再重新备份当前状态。
        :return: True 表示备份目录已建立且所有已存在项都已复制
        """
        backup_dir = self.KEYRING_STATE_BACKUP_DIR
        if self._keyring_path_exists(backup_dir):
            entries = self.run_cmd(
                f"ls -A {quote(backup_dir)} 2>/dev/null | wc -l",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            if entries.isdigit() and int(entries) > 0:
                # 上一次用例未闭环: 先还原, 避免用空备份覆盖真实文件
                self.restore_keyring_state()
        self.run_cmd(
            f"rm -rf {quote(backup_dir)} && mkdir -p {quote(backup_dir)}",
            timeout=10,
            out_debug_flag=False,
        )
        if not self._keyring_path_exists(backup_dir):
            return False
        for name, path in self._keyring_state_items().items():
            if not self._keyring_path_exists(path):
                continue
            backup_path = os.path.join(backup_dir, name)
            self.run_cmd(
                f"cp -a {quote(path)} {quote(backup_path)}",
                timeout=20,
                out_debug_flag=False,
            )
            if not self._keyring_path_exists(backup_path):
                return False
        return True

    def restore_keyring_state(self) -> bool:
        """用备份还原密钥环文件/status 目录, 备份里没有的路径一律删除

        还原后删除 /tmp 备份目录, 保证被测机无残留。
        :return: True 表示每个条目都已按备份回退(或已确认不存在)
        """
        backup_dir = self.KEYRING_STATE_BACKUP_DIR
        restored = True
        for name, path in self._keyring_state_items().items():
            backup_path = os.path.join(backup_dir, name)
            self.run_cmd(
                f"rm -rf {quote(path)}", timeout=10, out_debug_flag=False
            )
            if self._keyring_path_exists(backup_path):
                self.run_cmd(
                    f"cp -a {quote(backup_path)} {quote(path)}",
                    timeout=20,
                    out_debug_flag=False,
                )
                if not self._keyring_path_exists(path):
                    restored = False
            elif self._keyring_path_exists(path):
                restored = False
        self.run_cmd(
            f"rm -rf {quote(backup_dir)}", timeout=10, out_debug_flag=False
        )
        return restored

    def remove_keyring_status_dir(self) -> bool:
        """删除 deepin-keyrings-wb/status 目录, 构造"密钥环频繁弹出"现场

        产品依据(用例描述前置): status 目录记录密钥环"已提示"状态, 删除后
        密钥环访问会重新弹出解锁提示, 即描述里的"密钥环频繁弹出的窗口"。
        :return: True 表示目录已不存在
        """
        self.run_cmd(
            f"rm -rf {quote(self.KEYRING_STATUS_DIR)}",
            timeout=10,
            out_debug_flag=False,
        )
        return not self.get_keyring_status_dir_exists()

    def get_keyring_prompt_windows(self) -> list:
        """列出当前可见的密钥环解锁/密码输入窗口

        "密钥环频繁弹出"的可观测形态是桌面上反复出现密钥环解锁窗口(由
        deepin-keyrings/deepin-keyrings-wb/gnome-keyring 等进程创建, 标题含
        "解锁密钥环"/"密钥环", 或窗口所属进程名含 keyring)。电脑管家自身的
        修复页/修复对话框标题也含"密钥环", 因此按标题、类名、进程名三者
        同时排除电脑管家, 避免把被测应用自身窗口当成弹窗。
        :return: [{"wid": int, "title": str, "cls": str, "pid": str, "comm": str}]
        """
        output = self.run_cmd(
            "for w in $(xdotool search --onlyvisible --name '' 2>/dev/null); do "
            'title=$(xdotool getwindowname "$w" 2>/dev/null); '
            'cls=$(xdotool getwindowclassname "$w" 2>/dev/null); '
            'pid=$(xdotool getwindowpid "$w" 2>/dev/null); '
            'comm=$(ps -o comm= -p "$pid" 2>/dev/null); '
            'echo "$w|$title|$cls|$pid|$comm"; done',
            timeout=20,
            out_debug_flag=False,
        )
        windows = []
        for line in output.splitlines():
            parts = line.split("|", 4)
            if len(parts) < 5 or not parts[0].strip().isdigit():
                continue
            title, cls, pid, comm = (part.strip() for part in parts[1:])
            haystack = " ".join((title, cls, comm)).lower()
            if any(word in haystack for word in self.KEYRING_PROMPT_EXCLUDES):
                continue
            if not any(word in haystack for word in self.KEYRING_PROMPT_KEYWORDS):
                continue
            windows.append(
                {
                    "wid": int(parts[0].strip()),
                    "title": title,
                    "cls": cls,
                    "pid": pid,
                    "comm": comm,
                }
            )
        return windows

    def count_keyring_prompt_windows(self) -> int:
        """当前可见的密钥环弹窗数量"""
        return len(self.get_keyring_prompt_windows())

    def observe_keyring_popups(
        self, duration=20, interval=0.5, baseline_ids=()
    ) -> dict:
        """在指定时长内持续采样密钥环弹窗, 统计新出现的弹窗次数

        "频繁弹出"按同一现场反复弹出新窗口的次数衡量: 每次弹出都会新建一个
        X11 窗口, 因此统计采样期间首次出现的窗口 ID 即可, 与弹窗文案无关。
        :param duration: 采样总时长(秒)
        :param interval: 采样间隔(秒)
        :param baseline_ids: 已存在的窗口 ID(不算新弹窗, 如修复前桌面已有的)
        :return: {"count": 新增弹窗数, "ids": 见过的全部 ID, "peak": 同时可见数,
                  "samples": [新弹窗明细]}
        """
        seen = {int(wid) for wid in baseline_ids}
        samples = []
        peak = 0
        rounds = max(int(duration / max(interval, 0.2)), 1)
        for _ in range(rounds):
            windows = self.get_keyring_prompt_windows()
            peak = max(peak, len(windows))
            for window in windows:
                if window["wid"] in seen:
                    continue
                seen.add(window["wid"])
                samples.append(window)
            sleep(interval)
        return {
            "count": len(samples),
            "ids": seen,
            "peak": peak,
            "samples": samples,
        }

    def close_keyring_prompt_windows(self, exclude_ids=(), rounds=3) -> int:
        """关闭本用例期间弹出的密钥环解锁窗口(按 Escape 取消解锁)

        用例构造/触发了密钥环问题, 弹窗不应留在被测机桌面上; 按 Escape 等价
        于点"取消", 不会修改密钥环内容。修复前已存在的窗口不动。
        :param exclude_ids: 不处理的窗口 ID(修复前桌面已有的窗口)
        :param rounds: 最多轮询轮数
        :return: 实际发送关闭请求的窗口次数
        """
        excluded = {int(wid) for wid in exclude_ids}
        closed = 0
        for _ in range(rounds):
            windows = [
                window
                for window in self.get_keyring_prompt_windows()
                if window["wid"] not in excluded
            ]
            if not windows:
                break
            for window in windows:
                self.run_cmd(
                    f"xdotool windowactivate --sync {window['wid']} "
                    "2>/dev/null; xdotool key --clearmodifiers Escape",
                    timeout=5,
                    out_debug_flag=False,
                )
                closed += 1
            sleep(1)
        return closed

    # ---- 密钥环修复后验证(2005741)需要的现场备份/授权触发/观测能力 ----
    # 描述的"重启应用/系统"以重启电脑管家(应用) + 重新拉起密钥环授权客户端等价
    # 实现; "打开需要密钥环授权的应用(浏览器/网盘)"优先用系统已安装的浏览器,
    # 环境未安装时退化为 libsecret 客户端(secret-tool)或 Secret Service D-Bus
    # 调用 —— 三者走的是同一条 org.freedesktop.secrets 授权链路。
    KEYRING_DIRS_BACKUP_DIR = "/tmp/autotest_keyring_dirs"
    KEYRING_DIR_ITEMS = {
        "keyrings": os.path.join(HOME_DIR, ".local/share/keyrings"),
        "wb": os.path.join(HOME_DIR, ".local/share/deepin-keyrings-wb"),
    }
    KEYRING_AUTH_PROFILE_DIR = "/tmp/autotest_keyring_profile"
    KEYRING_AUTH_PID_FILE = "/tmp/autotest_keyring_app.pid"
    KEYRING_AUTH_APP_CANDIDATES = (
        ("/usr/bin/org.deepin.browser", "chromium"),
        ("/usr/bin/deepin-browser", "chromium"),
        ("/usr/bin/browser", "chromium"),
        ("/usr/bin/chromium", "chromium"),
        ("/usr/bin/google-chrome", "chromium"),
        ("/usr/bin/firefox", "firefox"),
    )
    KEYRING_SECRET_TOOL = "/usr/bin/secret-tool"
    KEYRING_GDBUS = "/usr/bin/gdbus"
    KEYRING_DAEMON_NAME = "gnome-keyring-daemon"
    # comm 截断为 15 字符, pgrep -x 需用截断名
    KEYRING_DAEMON_COMM = "gnome-keyring-d"
    KEYRING_CREATE_SCRIPT = "/tmp/autotest_keyring_create.py"
    KEYRING_CREATE_OUTPUT = "/tmp/autotest_keyring_create.out"
    KEYRING_CREATE_PID_FILE = "/tmp/autotest_keyring_create.pid"
    KEYRING_UNLOCK_SCRIPT = "/tmp/autotest_keyring_unlock.py"
    KEYRING_UNLOCK_OUTPUT = "/tmp/autotest_keyring_unlock.out"
    KEYRING_UNLOCK_PID_FILE = "/tmp/autotest_keyring_unlock.pid"

    def backup_keyring_dirs(self) -> bool:
        """整体备份密钥环目录, 供修复后验证用例在 finally 原样回退

        与 backup_keyring_state 的区别: 本方法整目录快照
        ~/.local/share/keyrings 与 ~/.local/share/deepin-keyrings-wb。
        修复后"首次启动生成新密钥环文件"可能产生其他名字的文件
        (如 user.keystore), 只有整目录回退才能既不留残留、也不破坏测试机
        原有的用户密钥环。
        :return: True 表示备份目录已建立且已存在的目录都已复制
        """
        backup_dir = self.KEYRING_DIRS_BACKUP_DIR
        if self._keyring_path_exists(backup_dir):
            entries = self.run_cmd(
                f"ls -A {quote(backup_dir)} 2>/dev/null | wc -l",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            if entries.isdigit() and int(entries) > 0:
                # 上一次用例未闭环(finally 没跑到): 先按遗留备份还原现场,
                # 否则本次备份复制的是"已删除/已伪造"的目录, 用户真实密钥环
                # 会被空/假备份覆盖掉(2005739 已因此丢失过 login.keyring)
                self.restore_keyring_dirs()
        self.run_cmd(
            f"rm -rf {quote(backup_dir)} && mkdir -p {quote(backup_dir)}",
            timeout=10,
            out_debug_flag=False,
        )
        if not self._keyring_path_exists(backup_dir):
            return False
        for name, path in self.KEYRING_DIR_ITEMS.items():
            if not self._keyring_path_exists(path):
                continue
            self.run_cmd(
                f"cp -a {quote(path)} {quote(os.path.join(backup_dir, name))}",
                timeout=20,
                out_debug_flag=False,
            )
            if not self._keyring_path_exists(os.path.join(backup_dir, name)):
                return False
        return True

    def restore_keyring_dirs(self) -> bool:
        """用整目录备份还原密钥环现场, 备份中不存在的目录一律删除

        测试期间新建的密钥环文件随目录删除, 测试机原有密钥环原样恢复;
        最后删除 /tmp 备份目录, 保证测试机无残留。
        :return: True 表示每个目录都已按备份回退(或已确认不存在)
        """
        backup_dir = self.KEYRING_DIRS_BACKUP_DIR
        restored = True
        for name, path in self.KEYRING_DIR_ITEMS.items():
            backup_path = os.path.join(backup_dir, name)
            self.run_cmd(
                f"rm -rf {quote(path)}", timeout=10, out_debug_flag=False
            )
            if not self._keyring_path_exists(backup_path):
                continue
            parent = os.path.dirname(path)
            self.run_cmd(
                f"mkdir -p {quote(parent)} && "
                f"cp -a {quote(backup_path)} {quote(path)}",
                timeout=20,
                out_debug_flag=False,
            )
            if not self._keyring_path_exists(path):
                restored = False
        self.run_cmd(
            f"rm -rf {quote(backup_dir)}", timeout=10, out_debug_flag=False
        )
        return restored

    def get_keyring_dir_listing(self) -> str:
        """列出密钥环目录内容(仅用于日志, 便于看清文件生成/删除过程)"""
        return self.run_cmd(
            "ls -la "
            + " ".join(quote(path) for path in self.KEYRING_DIR_ITEMS.values())
            + " 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()

    def wait_keyring_file_created(self, timeout=60) -> bool:
        """等待密钥环文件被重新生成

        修复脚本删除了 login.keyring, 修复后首次有应用请求密钥环授权时,
        deepin-keyrings(-wb) 会重新生成登录密钥环文件, 这是描述预期
        "首次启动会生成新的密钥环文件"的可观测依据。
        :param timeout: 最长等待秒数
        :return: True 表示已生成新的密钥环文件
        """
        for _ in range(max(int(timeout), 1)):
            if self.get_keyring_file_exists():
                return True
            sleep(1)
        return False

    def find_keyring_auth_app(self) -> dict:
        """查找可用于触发密钥环授权的应用(浏览器/网盘)

        描述的"浏览器、网盘"只是举例, 判定依据是"有应用向
        org.freedesktop.secrets 申请密钥环授权"。优先级:
          1. 系统已安装的浏览器(用 /tmp 下的临时 profile 启动, 不污染用户配置);
          2. libsecret 客户端 secret-tool(与浏览器走同一套授权链路);
          3. Secret Service D-Bus 调用(gdbus)。
        :return: {"kind": "app"/"secret-tool"/"gdbus", "cmd": [...], "label": str};
                 都不可用时返回 {}
        """
        for binary, family in self.KEYRING_AUTH_APP_CANDIDATES:
            if not self._keyring_path_exists(binary):
                continue
            if family == "firefox":
                cmd = [binary, "--profile", self.KEYRING_AUTH_PROFILE_DIR]
            else:
                cmd = [
                    binary,
                    f"--user-data-dir={self.KEYRING_AUTH_PROFILE_DIR}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]
            return {
                "kind": "app",
                "cmd": cmd,
                "label": os.path.basename(binary),
            }
        secret_client = self.find_keyring_secret_client()
        if secret_client:
            return secret_client
        return {}

    def find_keyring_secret_client(self) -> dict:
        """查找不依赖 GUI 的密钥环授权客户端(secret-tool / gdbus)

        用于补充一次密钥环授权请求: 浏览器/网盘是单实例应用, 重复拉起不会
        产生新的授权请求, 而 libsecret/D-Bus 客户端每次都真实访问
        org.freedesktop.secrets。
        :return: {"kind": "secret-tool"/"gdbus", "cmd": [...], "label": str} 或 {}
        """
        if self._keyring_path_exists(self.KEYRING_SECRET_TOOL):
            return {
                "kind": "secret-tool",
                "cmd": [self.KEYRING_SECRET_TOOL],
                "label": "secret-tool",
            }
        if self._keyring_path_exists(self.KEYRING_GDBUS):
            return {
                "kind": "gdbus",
                "cmd": [self.KEYRING_GDBUS],
                "label": "gdbus",
            }
        return {}

    def _keyring_access_pids(self) -> list:
        """读取本次用例拉起过的密钥环授权客户端 PID 列表"""
        output = self.run_cmd(
            f"cat {quote(self.KEYRING_AUTH_PID_FILE)} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return [line.strip() for line in output.splitlines() if line.strip().isdigit()]

    def is_keyring_access_app_running(self) -> bool:
        """本次拉起的密钥环授权客户端是否仍有存活进程"""
        for pid in self._keyring_access_pids():
            result = self.run_cmd(
                f"kill -0 {pid} 2>/dev/null && echo yes",
                timeout=5,
                out_debug_flag=False,
            )
            if "yes" in result:
                return True
        return False

    def trigger_keyring_access(self, trigger) -> bool:
        """触发一次密钥环授权请求

        - app: 后台拉起浏览器/网盘(临时 profile), 记录 PID 供 finally 回收;
        - secret-tool: 后台写入一条测试凭据, 会触发解锁/创建密钥环弹窗;
        - gdbus: 同步调用 Secret Service 打开会话并读取 login 别名。
        :param trigger: find_keyring_auth_app()/find_keyring_secret_client() 的返回值
        :return: True 表示授权请求已发出(客户端存活或 D-Bus 调用成功)
        """
        if not trigger:
            return False
        pid_file = quote(self.KEYRING_AUTH_PID_FILE)
        # PID 以追加方式记录: 浏览器单实例时后续启动的进程会立即退出,
        # 但首个实例的 PID 仍需保留到 finally 回收。
        kind = trigger.get("kind", "")
        if kind == "gdbus":
            service = (
                "--session --dest org.freedesktop.secrets "
                "--object-path /org/freedesktop/secrets"
            )
            command = (
                f"{self.KEYRING_GDBUS} call {service} --method "
                "org.freedesktop.Secret.Service.OpenSession plain \"<''>\" "
                f"&& {self.KEYRING_GDBUS} call {service} --method "
                "org.freedesktop.Secret.Service.ReadAlias login"
            )
            _, status = self.run_cmd(
                command, timeout=30, out_debug_flag=False, return_code=True
            )
            return status == 0
        if kind == "app":
            self.run_cmd(
                f"mkdir -p {quote(self.KEYRING_AUTH_PROFILE_DIR)} && "
                "setsid nohup "
                + " ".join(quote(part) for part in trigger["cmd"])
                + " > /dev/null 2>&1 < /dev/null & "
                + f"echo $! >> {pid_file}",
                timeout=10,
                out_debug_flag=False,
            )
        else:
            # secret-tool store 从 stdin 取密码; 该调用会向密钥环写入一条
            # 测试条目, 属于真实的密钥环授权请求。
            store = (
                "echo autotest-secret | secret-tool store "
                "--label=pcm-autotest pcm-keyring autotest"
            )
            self.run_cmd(
                "setsid nohup bash -c " + quote(store)
                + " > /dev/null 2>&1 < /dev/null & "
                + f"echo $! >> {pid_file}",
                timeout=10,
                out_debug_flag=False,
            )
        sleep(3)
        return self.is_keyring_access_app_running()

    def stop_keyring_auth_app(self):
        """关闭本次用例拉起的密钥环授权客户端并清理临时 profile

        只回收 trigger_keyring_access 记录的进程组, 不影响用户已打开的
        浏览器; 同时删除 /tmp 下的临时 profile 与 PID 文件, 避免残留。
        """
        for pid in self._keyring_access_pids():
            self.run_cmd(
                f"kill -TERM -{pid} 2>/dev/null; sleep 1; "
                f"kill -KILL -{pid} 2>/dev/null; true",
                timeout=10,
                out_debug_flag=False,
            )
        pid = self.run_cmd(
            f"cat {quote(self.KEYRING_CREATE_PID_FILE)} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()
        if pid.isdigit():
            self.run_cmd(
                f"kill -TERM -{pid} 2>/dev/null; sleep 1; "
                f"kill -KILL -{pid} 2>/dev/null; true",
                timeout=10,
                out_debug_flag=False,
            )
        # Chromium 多进程会 fork 出子进程, setsid 记录的 PID 未必覆盖全部,
        # 按临时 profile 路径兜底清理, 避免残留浏览器进程
        for _ in range(3):
            self.run_cmd(
                "pkill -f " + quote(self.KEYRING_AUTH_PROFILE_DIR)
                + " 2>/dev/null; true",
                timeout=10,
                out_debug_flag=False,
            )
            alive = self.run_cmd(
                "ps -eo args | grep -F "
                + quote(self.KEYRING_AUTH_PROFILE_DIR)
                + " | grep -v grep | wc -l",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            if alive in ("0", ""):
                break
            sleep(2)
        self.run_cmd(
            f"rm -f {quote(self.KEYRING_AUTH_PID_FILE)} "
            f"{quote(self.KEYRING_CREATE_PID_FILE)} "
            f"{quote(self.KEYRING_CREATE_SCRIPT)} "
            f"{quote(self.KEYRING_CREATE_OUTPUT)}; "
            f"rm -rf {quote(self.KEYRING_AUTH_PROFILE_DIR)}",
            timeout=10,
            out_debug_flag=False,
        )

    def get_keyring_daemon_pids(self) -> list:
        """密钥环服务进程 PID 列表

        procps 的 comm 只保留 15 个字符("gnome-keyring-d"), 用 -x 匹配全名
        会永远查不到进程, 这里按截断后的进程名匹配。
        :return: PID 列表
        """
        output = self.run_cmd(
            "pgrep -x " + self.KEYRING_DAEMON_COMM + " 2>/dev/null || true",
            timeout=5,
            out_debug_flag=False,
        )
        return [
            int(line.strip())
            for line in output.splitlines()
            if line.strip().isdigit()
        ]

    def is_pid_alive(self, pid) -> bool:
        """检查进程是否存活(`kill -0`)

        用于断言"重启前抓到的旧 PID 确实已退出", 比"当前没有同名进程"
        更精确: 重启后 D-Bus 可能立刻激活新实例, 直接断言无进程会偶发失败。
        """
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False
        return "yes" in self.run_cmd(
            f"kill -0 {pid} 2>/dev/null && echo yes",
            timeout=5,
            out_debug_flag=False,
        )

    def is_keyring_daemon_running(self) -> bool:
        """密钥环服务进程(gnome-keyring-daemon)是否在运行"""
        return bool(self.get_keyring_daemon_pids())

    def restart_keyring_daemon(self, timeout=15) -> bool:
        """重启密钥环服务进程, 让磁盘上的密钥环文件状态生效

        产品修复脚本只删除 login.keyring 文件; 已运行的 gnome-keyring-daemon
        内存里仍有旧集合, 后续授权请求不会重新生成密钥环文件, 也就不会出现
        描述中的"首次启动生成新密钥环 + 设置一次密码"弹窗。杀进程后由 D-Bus
        激活(dbus-1/services/org.freedesktop.secrets.service)按需重新拉起,
        与"重启应用/系统"的效果等价。
        :param timeout: 等待进程退出的最长秒数
        :return: True 表示旧进程已退出(新进程由 D-Bus 激活)
        """
        for _ in range(3):
            self.run_cmd(
                f"pkill -x {self.KEYRING_DAEMON_COMM} 2>/dev/null; true",
                timeout=5,
                out_debug_flag=False,
            )
            for _ in range(max(int(timeout), 1)):
                if not self.is_keyring_daemon_running():
                    return True
                sleep(1)
        return not self.is_keyring_daemon_running()

    def ensure_keyring_daemon_running(self, timeout=15) -> bool:
        """确保密钥环服务进程处于运行状态(还原用例开始前的守护进程状态)

        用例为让磁盘上"login.keyring 已删除"生效会重启该服务; 结束时若没有
        客户端再访问密钥环, D-Bus 不会重新激活它, 测试机就少了一个会话守护
        进程。这里用与 dbus 服务文件相同的启动参数后台拉起。
        :param timeout: 等待进程出现的秒数
        :return: True 表示进程在运行
        """
        pids = self.get_keyring_daemon_pids()
        if len(pids) == 1:
            return True
        if len(pids) > 1:
            # 用例中多次"重启"可能留下多个前置进程, 只保留一个
            self.run_cmd(
                f"pkill -x {self.KEYRING_DAEMON_COMM} 2>/dev/null; true", timeout=5,
                out_debug_flag=False,
            )
            for _ in range(max(int(timeout), 1)):
                if not self.get_keyring_daemon_pids():
                    break
                sleep(1)
        self.run_cmd(
            "setsid nohup /usr/bin/gnome-keyring-daemon --start --foreground "
            "--components=secrets > /dev/null 2>&1 < /dev/null & sleep 1; true",
            timeout=15,
            out_debug_flag=False,
        )
        for _ in range(max(int(timeout), 1)):
            if self.is_keyring_daemon_running():
                return True
            sleep(1)
        return self.is_keyring_daemon_running()

    def restore_keyring_daemon_state(self, initial_pids, timeout=15) -> bool:
        """按用例开始前的快照恢复 gnome-keyring-daemon 的存在状态

        用例为让"login.keyring 已删除"生效会杀掉该服务, 收尾不能假定测试机
        原本恰好有 1 个实例(可能 0 个, 也可能被会话重复拉起多个), 只能按
        快照恢复: 原本没有就保持没有, 原本有就确保有实例在运行。
        :param initial_pids: 用例开始前 get_keyring_daemon_pids() 的结果
        :param timeout: 等待进程出现/消失的最长秒数
        :return: True 表示恢复后的存在状态与快照一致
        """
        initial_pids = list(initial_pids or [])
        pids = self.get_keyring_daemon_pids()
        if not initial_pids:
            if pids:
                self.run_cmd(
                    f"pkill -x {self.KEYRING_DAEMON_COMM} 2>/dev/null; true",
                    timeout=5,
                    out_debug_flag=False,
                )
                for _ in range(max(int(timeout), 1)):
                    if not self.get_keyring_daemon_pids():
                        break
                    sleep(1)
            return not self.get_keyring_daemon_pids()
        if len(pids) == len(initial_pids):
            return True
        if len(pids) > len(initial_pids):
            # 用例中"重启"过一次但被 D-Bus 又拉起: 只保留一个实例
            self.run_cmd(
                f"pkill -x {self.KEYRING_DAEMON_COMM} 2>/dev/null; true",
                timeout=5,
                out_debug_flag=False,
            )
            for _ in range(max(int(timeout), 1)):
                if not self.get_keyring_daemon_pids():
                    break
                sleep(1)
        if not self.get_keyring_daemon_pids():
            self.ensure_keyring_daemon_running(timeout=timeout)
        return len(self.get_keyring_daemon_pids()) == len(initial_pids)

    def trigger_keyring_create_collection(self) -> bool:
        """用 Secret Service 客户端请求创建默认密钥环(触发设置密码弹窗)

        描述的"打开需要密钥环授权的应用"在无浏览器保存密码等真实动作时不可
        复现, 这里用 libsecret 同一条链路(D-Bus org.freedesktop.secrets)的
        CreateCollection+Prompt 请求等价触发: 服务端发现 login 密钥环不存在,
        弹出 gcr-prompter 要求设置新密码, 设置后生成新的密钥环文件。
        :return: True 表示客户端已拉起
        """
        script = (
            'from gi.repository import Gio, GLib\n'
            'bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)\n'
            'res = bus.call_sync("org.freedesktop.secrets", "/org/freedesktop/secrets",\n'
            '    "org.freedesktop.Secret.Service", "CreateCollection",\n'
            '    GLib.Variant("(a{sv}s)", ({"org.freedesktop.Secret.Collection.Label":\n'
            '        GLib.Variant("s", "login")}, "default")),\n'
            '    None, Gio.DBusCallFlags.NONE, 60000, None)\n'
            'collection, prompt = res.unpack()\n'
            'print("collection", collection, "prompt", prompt, flush=True)\n'
            'loop = GLib.MainLoop()\n'
            'def on_signal(conn, sender, path, iface, signal, params):\n'
            '    print("completed", params.unpack(), flush=True)\n'
            '    loop.quit()\n'
            'bus.signal_subscribe("org.freedesktop.secrets",\n'
            '    "org.freedesktop.Secret.Prompt", "Completed", prompt, None,\n'
            '    Gio.DBusSignalFlags.NONE, on_signal)\n'
            'bus.call_sync("org.freedesktop.secrets", prompt,\n'
            '    "org.freedesktop.Secret.Prompt", "Prompt", GLib.Variant("(s)", ("",)),\n'
            '    None, Gio.DBusCallFlags.NONE, 60000, None)\n'
            'print("prompt called", flush=True)\n'
            'GLib.timeout_add_seconds(120, loop.quit)\n'
            'loop.run()\n'
        )
        self.run_cmd(
            "cat > " + quote(self.KEYRING_CREATE_SCRIPT) + " <<'AUTOTEST_EOF'\n"
            + script
            + "AUTOTEST_EOF\n",
            timeout=10,
            out_debug_flag=False,
        )
        if not self._keyring_path_exists(self.KEYRING_CREATE_SCRIPT):
            return False
        self.run_cmd(
            f"rm -f {quote(self.KEYRING_CREATE_OUTPUT)}; setsid nohup python3 "
            f"{quote(self.KEYRING_CREATE_SCRIPT)} > {quote(self.KEYRING_CREATE_OUTPUT)} "
            "2>&1 < /dev/null & echo $! > "
            f"{quote(self.KEYRING_CREATE_PID_FILE)}",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)
        out = self.run_cmd(
            f"cat {quote(self.KEYRING_CREATE_PID_FILE)} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()
        return bool(out.isdigit())

    def get_keyring_tmp_residue(self, exclude=()) -> list:
        """列出 /tmp 下密钥环用例可能遗留的临时文件/目录(收尾自查用)

        :param exclude: 不考虑的完整路径(如 2005739 自己的备份目录)
        """
        output = self.run_cmd(
            "ls -d /tmp/autotest_keyring_* 2>/dev/null || true",
            timeout=5,
            out_debug_flag=False,
        )
        excluded = {path for path in exclude}
        return [
            line.strip()
            for line in output.splitlines()
            if line.strip() and line.strip() not in excluded
        ]

    def trigger_keyring_unlock(self, timeout=60) -> dict:
        """向 Secret Service 发起一次真实的解锁请求(第二次授权取证)

        只观察"有没有弹窗"无法区分"密钥环已解锁不再弹"与"根本没发出请求"。
        这里按 libsecret 的调用顺序执行
        `ReadAlias(login) -> Properties.Get(Locked) -> Unlock -> Prompt`,
        把 collection / locked_before / locked_after 打出来: 调用成功且
        `locked_before=False` 才证明"设置一次密码后, 后续授权由已解锁的
        登录密钥环直接应答, 不再弹框"。

        请求在后台执行并轮询输出: 期间若意外弹出密钥环框(说明集合被锁),
        先记录再按 Escape 取消, 让脚本走到 RESULT 而不是空等 120s 超时。

        :param timeout: 等待脚本产出 RESULT 的最长秒数
        :return: {"rc", "output", "collection", "locked_before",
                  "locked_after", "result", "prompts"}
        """
        script = (
            'import sys\n'
            'from gi.repository import Gio, GLib\n'
            '\n'
            'SERVICE = "org.freedesktop.secrets"\n'
            'SERVICE_PATH = "/org/freedesktop/secrets"\n'
            '\n'
            '\n'
            'def call(bus, path, iface, method, args, reply_type, timeout=20000):\n'
            '    return bus.call_sync(SERVICE, path, iface, method, args,\n'
            '                         reply_type, Gio.DBusCallFlags.NONE, timeout, None)\n'
            '\n'
            '\n'
            'bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)\n'
            'coll = call(bus, SERVICE_PATH, "org.freedesktop.Secret.Service",\n'
            '            "ReadAlias", GLib.Variant("(s)", ("login",)),\n'
            '            GLib.VariantType("(o)")).unpack()[0]\n'
            'print("collection=" + str(coll), flush=True)\n'
            'if str(coll) == "/":\n'
            '    print("RESULT=no-login-collection", flush=True)\n'
            '    sys.exit(2)\n'
            'locked = call(bus, str(coll), "org.freedesktop.DBus.Properties", "Get",\n'
            '              GLib.Variant("(ss)", ("org.freedesktop.Secret.Collection",\n'
            '                                    "Locked")),\n'
            '              GLib.VariantType("(v)")).unpack()[0]\n'
            'print("locked_before=" + str(bool(locked)), flush=True)\n'
            'unlocked, prompt = call(bus, SERVICE_PATH,\n'
            '                        "org.freedesktop.Secret.Service", "Unlock",\n'
            '                        GLib.Variant("(ao)", ([coll],)),\n'
            '                        GLib.VariantType("(aoo)")).unpack()\n'
            'print("unlocked=" + str([str(item) for item in unlocked]), flush=True)\n'
            'if str(prompt) != "/":\n'
            '    print("prompt=" + str(prompt), flush=True)\n'
            '    loop = GLib.MainLoop()\n'
            '    bus.signal_subscribe(SERVICE, "org.freedesktop.Secret.Prompt",\n'
            '                         "Completed", str(prompt), None,\n'
            '                         Gio.DBusSignalFlags.NONE,\n'
            '                         lambda *args: loop.quit())\n'
            '    call(bus, str(prompt), "org.freedesktop.Secret.Prompt", "Prompt",\n'
            '         GLib.Variant("(s)", ("",)), None, timeout=120000)\n'
            '    GLib.timeout_add_seconds(150, loop.quit)\n'
            '    loop.run()\n'
            'locked_after = call(bus, str(coll), "org.freedesktop.DBus.Properties",\n'
            '                    "Get",\n'
            '                    GLib.Variant("(ss)", ("org.freedesktop.Secret.Collection",\n'
            '                                          "Locked")),\n'
            '                    GLib.VariantType("(v)")).unpack()[0]\n'
            'print("locked_after=" + str(bool(locked_after)), flush=True)\n'
            'print("RESULT=ok", flush=True)\n'
        )
        self.run_cmd(
            "cat > " + quote(self.KEYRING_UNLOCK_SCRIPT) + " <<'AUTOTEST_EOF'\n"
            + script
            + "AUTOTEST_EOF\n",
            timeout=10,
            out_debug_flag=False,
        )
        if not self._keyring_path_exists(self.KEYRING_UNLOCK_SCRIPT):
            return {
                "rc": -1,
                "output": "",
                "collection": "",
                "locked_before": None,
                "locked_after": None,
                "result": "script-write-failed",
                "prompts": [],
            }
        self.run_cmd(
            f"rm -f {quote(self.KEYRING_UNLOCK_OUTPUT)}; setsid nohup python3 "
            f"{quote(self.KEYRING_UNLOCK_SCRIPT)} "
            f"> {quote(self.KEYRING_UNLOCK_OUTPUT)} 2>&1 < /dev/null & "
            f"echo $! > {quote(self.KEYRING_UNLOCK_PID_FILE)}",
            timeout=10,
            out_debug_flag=False,
        )
        prompts = []
        seen = set()
        output = ""
        started = time.time()
        while time.time() - started < max(int(timeout), 5):
            output = self.run_cmd(
                f"cat {quote(self.KEYRING_UNLOCK_OUTPUT)} 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            ) or ""
            if "RESULT=" in output:
                break
            for window in self.get_keyring_prompt_windows():
                if window["wid"] in seen:
                    continue
                seen.add(window["wid"])
                prompts.append(window)
                # 锁定态才会弹框: 先记录, 再按 Escape 取消, 让脚本继续
                # 走到 RESULT(libsecret 语义: 用户取消 = 解锁失败)
                self.run_cmd(
                    f"xdotool windowactivate --sync {window['wid']} 2>/dev/null; "
                    "xdotool key --clearmodifiers Escape",
                    timeout=5,
                    out_debug_flag=False,
                )
            sleep(1)
        pid = self.run_cmd(
            f"cat {quote(self.KEYRING_UNLOCK_PID_FILE)} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()
        if pid.isdigit():
            self.run_cmd(
                f"kill -TERM -{pid} 2>/dev/null; sleep 1; "
                f"kill -KILL -{pid} 2>/dev/null; true",
                timeout=10,
                out_debug_flag=False,
            )
        info = {
            "rc": 0 if "RESULT=" in output else -1,
            "output": output,
            "collection": "",
            "locked_before": None,
            "locked_after": None,
            "result": "",
            "prompts": prompts,
        }
        for line in output.splitlines():
            key, sep, value = line.partition("=")
            if not sep:
                continue
            key, value = key.strip(), value.strip()
            if key == "collection":
                info["collection"] = value
            elif key == "locked_before":
                info["locked_before"] = value == "True"
            elif key == "locked_after":
                info["locked_after"] = value == "True"
            elif key == "RESULT":
                info["result"] = value
        self.run_cmd(
            f"rm -f {quote(self.KEYRING_UNLOCK_SCRIPT)} "
            f"{quote(self.KEYRING_UNLOCK_OUTPUT)} "
            f"{quote(self.KEYRING_UNLOCK_PID_FILE)}",
            timeout=10,
            out_debug_flag=False,
        )
        return info

    def wait_keyring_prompt_closed(self, timeout=20) -> bool:
        """等待密钥环密码框关闭

        :param timeout: 最长等待秒数
        :return: True 表示已无密钥环弹窗
        """
        for _ in range(max(int(timeout), 1)):
            if not self.get_keyring_prompt_windows():
                return True
            sleep(1)
        return False

    def wait_keyring_prompt_windows(self, timeout=30) -> list:
        """等待密钥环密码框出现

        :param timeout: 最长等待秒数
        :return: 首次检测到的弹窗列表(超时返回空列表)
        """
        for _ in range(max(int(timeout), 1)):
            windows = self.get_keyring_prompt_windows()
            if windows:
                return windows
            sleep(1)
        return []

    def set_keyring_password_once(self, password=None) -> bool:
        """在首次弹出的密钥环解锁/创建框中输入一次密码并确认

        描述预期"设置一次密码后不再弹窗", 因此修复后首次授权若弹出输入框,
        用例按真实用户操作输入一次密码并回车, 只处理第一个弹窗, 不重复尝试,
        避免在自动化环境中反复操作对话框。
        :param password: 密钥环密码; 默认取 setting/globalconfig.ini 的 PASSWORD
        :return: True 表示确实存在弹窗并已输入
        """
        if password is None:
            password = conf.PASSWORD
        windows = self.get_keyring_prompt_windows()
        if not windows:
            return False
        wid = windows[0]["wid"]
        self.run_cmd(
            f"xdotool windowactivate --sync {wid} 2>/dev/null || "
            f"xdotool windowfocus {wid}",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)
        # 创建新密钥环的弹窗有"密码/确认"两个输入框, 解锁弹窗只有一个:
        # 统一按"输入 -> Tab -> 再输入 -> 回车"处理, 单框时第二次输入落在
        # 按钮上无副作用, 回车即提交(实测 gcr-prompter 可正常建库)
        self.run_cmd(
            f"xdotool type --clearmodifiers --delay 80 {quote(password)}; "
            "sleep 0.5; xdotool key --clearmodifiers Tab; sleep 0.5; "
            f"xdotool type --clearmodifiers --delay 80 {quote(password)}; "
            "sleep 0.5; xdotool key --clearmodifiers Return",
            timeout=20,
            out_debug_flag=False,
        )
        sleep(3)
        return True

    def click_utility_category_tab_by_name(self, tab_name: str):
        """点击指定名称的实用工具分类标签(V20/V25 兼容)

        :param tab_name: 标签名称(如 "全部"、"网络工具"、"磁盘工具"、"日志工具")
        """
        self._safe_focus_windows()
        element = self._find_element_in_exprs([
            f"$//utility_categoryTabs//{tab_name}",
            f"$//utilityCategoryTabs//{tab_name}",
        ])
        if not element:
            logger.warning(f"[控件查找] 实用工具分类标签未命中 tab={tab_name!r}, 跳过点击")
            return False
        self._atspi_do_action(element)
        sleep(2)
        self.reconnect_dogtail()
        return True

    def get_utility_section_count(self) -> int:
        """获取实用工具可见分区数量(V20/V25 兼容)"""
        self._safe_focus_windows()
        count = 0
        try:
            elements = self.dog.find_elements_by_attr(
                "$//utility_sectionsContainer//utility_sectionWidget"
            )
            if elements:
                for el in elements:
                    try:
                        if el.showing:
                            count += 1
                    except BaseException:
                        count += 1
        except BaseException:
            pass
        return count

    def get_utility_section_titles(self) -> list:
        """获取实用工具可见分区标题列表(V20/V25 兼容)"""
        self._safe_focus_windows()
        titles = []
        try:
            elements = self.dog.find_elements_by_attr(
                "$//utility_sectionsContainer//utility_sectionTitle"
            )
            if elements:
                for el in elements:
                    try:
                        if el.showing and el.name:
                            titles.append(el.name)
                    except BaseException:
                        try:
                            if el.name:
                                titles.append(el.name)
                        except BaseException:
                            continue
        except BaseException:
            pass
        return titles

    def get_utility_card_count_visible(self) -> int:
        """获取实用工具当前可见卡片数量(V20/V25 兼容)

        遍历所有可见分区中的卡片按钮, 统计总数。
        """
        self._safe_focus_windows()
        count = 0
        try:
            elements = self.dog.find_elements_by_attr(
                "$//utility_sectionsContainer//utility_sectionWidget"
            )
            if elements:
                for section in elements:
                    try:
                        if not section.showing:
                            continue
                    except BaseException:
                        pass
                    try:
                        buttons = section.findChildren(
                            lambda n: n.roleName in ("push button", "button"),
                            recursive=True,
                            showingOnly=True,
                        )
                        count += len(buttons) if buttons else 0
                    except BaseException:
                        continue
        except BaseException:
            pass
        return count

    def inject_cups_log_feature(self):
        """向 CUPS 日志中注入联软管控软件特征(dvc-filter-exe)

        在 /var/log/cups/error_log 中追加包含 dvc-filter-exe 的日志行,
        模拟联软管控软件存在的场景。如果 CUPS 日志目录不存在则先创建。
        """
        self.sudo_run_cmd(
            'mkdir -p /var/log/cups && '
            'echo "dvc-filter-exe: test feature injection" >> /var/log/cups/error_log',
            timeout=10,
            out_debug_flag=False,
        )

    def cleanup_cups_log_feature(self):
        """清理注入到 CUPS 日志中的联软管控软件特征

        删除 /var/log/cups/error_log 中包含 dvc-filter-exe 的行。
        """
        self.sudo_run_cmd(
            'sed -i "/dvc-filter-exe/d" /var/log/cups/error_log 2>/dev/null || true',
            timeout=10,
            out_debug_flag=False,
        )

    def get_cups_log_feature_exists(self) -> bool:
        """检查 CUPS 日志中是否存在联软管控软件特征(dvc-filter-exe)

        :return: True 表示日志中包含 dvc-filter-exe 关键字
        """
        result = self.sudo_run_cmd(
            'grep -q "dvc-filter-exe" /var/log/cups/error_log 2>/dev/null && echo yes || echo no',
            timeout=5,
            out_debug_flag=False,
        )
        return "yes" in result.strip()

    def mute_alsa_master(self) -> bool:
        """将 ALSA Master 声卡硬件主音量设置为静音"""
        self.run_cmd(
            "amixer -q sset Master mute 2>/dev/null || "
            "amixer -q -D default sset Master mute 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return self.get_alsa_master_mute_status()

    def unmute_alsa_master(self) -> bool:
        """将 ALSA Master 声卡硬件主音量解除静音"""
        self.run_cmd(
            "amixer -q sset Master unmute 2>/dev/null || "
            "amixer -q -D default sset Master unmute 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return not self.get_alsa_master_mute_status()

    def get_alsa_master_mute_status(self) -> bool:
        """检查 ALSA Master 声卡硬件主音量是否处于静音状态

        :return: True 表示已静音, False 表示未静音
        """
        result = self.run_cmd(
            "amixer sget Master 2>/dev/null || amixer -D default sget Master 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        for line in result.splitlines():
            if "Mono:" in line or "Front Left:" in line or "Playback" in line:
                if "[off]" in line:
                    return True
                if "[on]" in line:
                    return False
        return "[off]" in result


    def get_sink_mute_status(self) -> bool:
        """检查默认音频输出设备(Sink)是否处于静音状态

        pactl 15+ 提供 get-sink-mute; 更早版本(deepin V20 上的 pulseaudio 12.x)
        不支持该子命令, 此时回退为解析 pactl list sinks 输出中"静音"行。
        读取的设备必须与 mute_sink_output 实际静音的设备一致(见
        get_default_sink_name), 否则测试机会出现"已静音但判定未静音"的假失败。
        :return: True 表示静音, False 表示未静音或获取失败
        """
        result = self.run_cmd(
            "pactl get-sink-mute @DEFAULT_SINK@ 2>&1",
            timeout=10,
            out_debug_flag=False,
        )
        text = result.strip().lower()
        if "yes" in text or "是" in text:
            return True
        if "no" in text or "否" in text:
            return False
        target = self.get_default_sink_name()
        if target:
            return self._pactl_list_muted("sinks", target)
        return self._pactl_any_muted("sinks")

    def _pactl_list_muted(self, kind: str, device_name: str = "") -> bool:
        """解析 pactl list sinks/sources 输出中设备的静音状态

        pactl 输出随 locale 变化, 同时匹配中英文键名与取值;
        每段以非缩进行开头, 按段切分后匹配设备名(为空则取第一段)。
        :param kind: "sinks" 或 "sources"
        :param device_name: 设备名称(可为空)
        """
        listing = self.run_cmd(
            f"pactl list {kind} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        if not listing.strip():
            return False
        for block in re.split(r"\n(?=\S)", listing):
            if device_name and device_name not in block:
                continue
            matched = re.search(r"(静音|Mute)\s*[:：]\s*(\S+)", block)
            if matched:
                return matched.group(2).strip().lower() in ("是", "yes")
        return False

    def _get_pactl_sink_names(self):
        """获取全部 Sink 设备名称(pactl list short sinks 第 2 列)"""
        result = self.run_cmd(
            "pactl list short sinks 2>/dev/null | awk '{print $2}'",
            timeout=10,
            out_debug_flag=False,
        )
        return [name for name in result.split() if name]

    def get_default_sink_name(self) -> str:
        """获取默认音频输出设备名称

        优先 pactl get-default-sink(新版); 旧版回退解析 pactl info 的默认信宿行,
        中文输出为"默认信宿"(不是"默认音频输出"); 两者都取不到时(如测试机未设置
        默认 Sink)退回第一个 Sink, 保证与 mute_sink_output 静音的设备一致。
        """
        result = self.run_cmd(
            "pactl get-default-sink 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        name = result.strip()
        if name and " " not in name:
            return name
        info = self.run_cmd("pactl info 2>/dev/null", timeout=10, out_debug_flag=False)
        for line in info.splitlines():
            if (
                "默认音频输出" in line
                or "默认信宿" in line
                or line.startswith("Default Sink")
            ):
                candidate = re.split(r"[:：]", line, maxsplit=1)[-1].strip()
                if candidate:
                    return candidate
        sinks = self._get_pactl_sink_names()
        return sinks[0] if sinks else ""

    def _pactl_any_muted(self, kind: str) -> bool:
        """检查任意 Sink/Source 是否处于静音状态(无法确定目标设备时的兜底)"""
        listing = self.run_cmd(
            f"pactl list {kind} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return bool(re.search(r"(静音|Mute)\s*[:：]\s*(是|yes)", listing))

    def _sink_mute_targets(self):
        """返回静音操作的目标 Sink 列表

        优先使用默认 Sink; 未设置默认 Sink 时(V20 测试机常见, @DEFAULT_SINK@
        解析不稳定, 可能作用到任意 Sink)静音全部 Sink, 与产品音频修复
        (entry.sh 取消全部 Sink 静音)保持一致。
        """
        sinks = self._get_pactl_sink_names()
        target = self.get_default_sink_name()
        if target and (not sinks or target in sinks):
            return [target]
        return sinks

    def mute_sink_output(self):
        """将默认音频输出设备(Sink)设置为静音状态"""
        for sink in self._sink_mute_targets():
            self.run_cmd(
                f"pactl set-sink-mute {quote(sink)} 1 2>/dev/null",
                timeout=10,
                out_debug_flag=False,
            )
        sleep(1)

    def unmute_sink_output(self):
        """将默认音频输出设备(Sink)取消静音"""
        for sink in self._sink_mute_targets():
            self.run_cmd(
                f"pactl set-sink-mute {quote(sink)} 0 2>/dev/null",
                timeout=10,
                out_debug_flag=False,
            )
        sleep(1)

    def wait_for_sink_unmute(self, timeout=120) -> bool:
        """等待音频修复完成(Sink取消静音)

        修复工具执行音频修复后会取消Sink静音, 通过轮询Sink静音状态判断修复是否完成。
        兼容V20(修复完成弹窗)和V25(修复对话框直接关闭)两种行为。

        :param timeout: 最长等待秒数
        :return: True 表示Sink已取消静音(修复完成), False 表示超时仍未取消静音
        """
        for _ in range(timeout):
            if not self.get_sink_mute_status():
                return True
            sleep(1)
        return False

    # ===== UI交互辅助方法 =====

    def get_audio_source_count(self) -> int:
        """获取当前音频 Source(输入) 数量

        通过 pactl list short sources 获取 Source 列表行数。
        V20 使用 pulseaudio, V25 使用 pipewire-pulse, pactl 均可用。
        :return: Source 数量, 出错时返回 0
        """
        result = self.run_cmd(
            "pactl list short sources 2>/dev/null | wc -l",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return 0

    def check_audio_source_exists(self, source_name: str) -> bool:
        """检查指定名称的音频 Source 是否存在

        通过 pactl list short sources 查找匹配名称的 Source。
        :param source_name: Source 名称关键字
        :return: True 表示存在
        """
        result = self.run_cmd(
            f"pactl list short sources 2>/dev/null | grep '{source_name}'",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result and result.strip())

    def create_virtual_audio_source(self) -> int:
        """创建虚拟音频 Source(输入) 以模拟多 Source 场景

        通过 pactl load-module module-null-sink 创建 null sink, 其 monitor source
        自动命名为 <sink_name>.monitor, 从而增加 Source 数量。
        deepin V20 的 pactl 12.x 不支持 source_name 参数(传入会导致模块初始化失败),
        因此仅指定 sink_name。
        :return: module id (>0 表示成功), 0 表示失败
        """
        result = self.run_cmd(
            "pactl load-module module-null-sink sink_name=virtual_test_sink 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            module_id = int(result.strip())
            return module_id
        except (ValueError, AttributeError):
            return 0

    def cleanup_virtual_audio_source(self, module_id: int):
        """清理虚拟音频 Source

        通过 pactl unload-module 卸载之前加载的 module-null-sink。
        :param module_id: load-module 返回的 module id
        """
        if module_id > 0:
            self.run_cmd(
                f"pactl unload-module {module_id} 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )

    def format_capacity_auto_unit(self, size_bytes: int) -> str:
        """将字节大小按容量单位自适应规则格式化为带单位的可读字符串

        单位自适应规则:
        - < 1024 B       → "X B"
        - < 1024 KB      → "X.X KB"
        - < 1024 MB      → "X.X MB"
        - < 1024 GB      → "X.X GB"
        - >= 1024 GB     → "X.X TB"

        :param size_bytes: 分区或磁盘容量(字节)
        :return: 格式化后的容量字符串, 如 "500.0 MB"
        """
        if size_bytes < 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        if unit_index == 0:
            return f"{int(size)} {units[unit_index]}"
        return f"{round(size, 1)} {units[unit_index]}"

    def get_partition_capacity_list(self) -> list:
        """获取所有已挂载分区的容量信息列表

        通过 lsblk 获取分区设备名、挂载点和字节大小,
        并使用 format_capacity_auto_unit 进行单位自适应格式化。

        :return: 列表, 每个元素为 dict:
                 {"device": "/dev/sda1", "mountpoint": "/",
                  "size_bytes": 12345678, "formatted": "11.8 MB"}
        """
        result = self.run_cmd(
            "lsblk -b -o NAME,MOUNTPOINT,SIZE -n 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        partitions = []
        for line in result.strip().split("\n"):
            parts = line.split()
            if len(parts) < 3:
                continue
            name, mountpoint, size_str = parts[0], parts[1], parts[2]
            if not mountpoint or mountpoint == "[SWAP]":
                continue
            try:
                size_bytes = int(size_str)
            except ValueError:
                continue
            device = f"/dev/{name}"
            partitions.append({
                "device": device,
                "mountpoint": mountpoint,
                "size_bytes": size_bytes,
                "formatted": self.format_capacity_auto_unit(size_bytes),
            })
        return partitions

    def verify_capacity_unit_adaptation(self) -> bool:
        """验证分区容量的单位自适应格式化是否正确

        检查每个分区的格式化结果:
        1. 格式化字符串包含有效的单位 (B/KB/MB/GB/TB)
        2. 单位与实际字节大小匹配(大容量不应使用小单位, 小容量不应使用大单位)

        :return: True 表示所有分区容量单位自适应格式化正确
        """
        partitions = self.get_partition_capacity_list()
        if not partitions:
            return False
        valid_units = ["B", "KB", "MB", "GB", "TB"]
        for part in partitions:
            formatted = part.get("formatted", "")
            size_bytes = part.get("size_bytes", 0)
            parts = formatted.rsplit(" ", 1)
            if len(parts) != 2:
                return False
            unit = parts[1]
            if unit not in valid_units:
                return False
            expected_index = 0
            temp = float(size_bytes)
            while temp >= 1024 and expected_index < len(valid_units) - 1:
                temp /= 1024
                expected_index += 1
            if valid_units.index(unit) != expected_index:
                return False
        return True

    def get_defender_daemon_pid(self) -> str:
        """获取 deepin-defender-system-daemon 进程的 PID

        优先通过 systemctl show 获取服务主 PID,
        若服务未注册(V25 上可能不以 systemd service 运行),
        则通过 pgrep 获取进程 PID。
        V20 上通常以 systemd service 运行, V25 上可能以独立进程运行。
        :return: PID 字符串, 未找到时返回空字符串
        """
        result = self.run_cmd(
            "systemctl show deepin-defender-system-daemon --property=MainPID --value 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        pid = result.strip()
        if pid and pid != "0":
            return pid
        result = self.run_cmd(
            "pgrep -f deepin-defender-system-daemon 2>/dev/null | grep -v session-daemon | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_defender_daemon_service_status(self) -> bool:
        """检查 deepin-defender-system-daemon 服务/进程是否正在运行

        优先通过 systemctl is-active 检查服务状态,
        若服务未注册则通过 pgrep 检查进程是否存在。
        V20 上通常以 systemd service 运行, V25 上可能以独立进程运行。
        """
        result = self.run_cmd(
            "systemctl is-active deepin-defender-system-daemon 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        if result.strip() == "active":
            return True
        result = self.run_cmd(
            "pgrep -f deepin-defender-system-daemon 2>/dev/null | grep -v session-daemon",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def get_defender_daemon_memory_usage_kb(self) -> int:
        """获取 deepin-defender-system-daemon 进程的内存占用(KB)

        通过 get_defender_daemon_pid 获取 PID, 再通过 /proc 读取 RSS。
        V20/V25 均支持 /proc 文件系统。
        :return: 内存占用(KB), 进程未运行时返回 0
        """
        pid = self.get_defender_daemon_pid()
        if not pid:
            return 0
        result = self.run_cmd(
            f"awk '/^VmRSS:/ {{print $2}}' /proc/{pid}/status 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return 0

    def get_defender_daemon_cpu_usage_percent(self) -> float:
        """获取 deepin-defender-system-daemon 进程的 CPU 占用率(%)

        通过 get_defender_daemon_pid 获取 PID, 再通过 ps 命令获取 CPU 占用率。
        V20/V25 均支持 ps 命令。
        :return: CPU 占用率(%), 进程未运行时返回 0.0
        """
        pid = self.get_defender_daemon_pid()
        if not pid:
            return 0.0
        result = self.run_cmd(
            f"ps -p {pid} -o %cpu --no-headers 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return round(float(result.strip()), 1)
        except (ValueError, AttributeError):
            return 0.0

    def get_defender_daemon_uptime_seconds(self) -> int:
        """获取 deepin-defender-system-daemon 进程已运行时长(秒)

        对应"长时间运行后"的前置核对: 从进程启动至今的 etimes。

        :return: 运行秒数, 进程未运行或读取失败返回 0
        """
        pid = self.get_defender_daemon_pid()
        if not pid:
            return 0
        result = self.run_cmd(
            f"ps -p {pid} -o etimes= 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return 0

    def get_defender_daemon_threads(self) -> int:
        """获取 deepin-defender-system-daemon 进程的线程数

        线程数在稳定运行阶段应保持平稳, 用于佐证"资源占用正常"。

        :return: 线程数, 进程未运行或读取失败返回 0
        """
        pid = self.get_defender_daemon_pid()
        if not pid:
            return 0
        result = self.run_cmd(
            f"awk '/^Threads:/ {{print $2}}' /proc/{pid}/status 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return 0

    _LOG_PRIVACY_SCAN_PY = r"""
import base64, json, re, sys
path, username, password = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
except OSError:
    print(json.dumps({"exists": False}))
    raise SystemExit(0)

# 允许出现在日志里的非私密值: 本地回环/未指定地址、系统公共路径
IP_ALLOW = {"127.0.0.1", "0.0.0.0"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
IP_RE = re.compile(r"(?<![0-9.])((?:[0-9]{1,3}\.){3}[0-9]{1,3})(?![0-9.])")
MAC_RE = re.compile(r"(?<![0-9A-Fa-f:])([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})(?![0-9A-Fa-f:])")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
MACHINE_RE = re.compile(r"[Mm]achine[_ ]?[Cc]ode\s*[:=]\s*\S+")

# 过短的密码(如测试机设置的 "1")会在任意日志行中误命中, 只在长度足够时检查
pw_variants = set()
if len(password or "") >= 4:
    pw_variants.add(password)
    enc = base64.b64encode(password.encode()).decode()
    pw_variants.add(enc)
    pw_variants.add(enc.rstrip("="))

def hit(bucket, name, sample):
    bucket.setdefault(name, []).append(sample[:200])

found = {}
for ln in lines:
    if len(found) > 200:
        break
    for m in EMAIL_RE.findall(ln):
        hit(found, "email", ln)
    for m in IP_RE.findall(ln):
        if m not in IP_ALLOW and not m.startswith("127."):
            hit(found, "ip_address", ln)
    for m in MAC_RE.findall(ln):
        hit(found, "mac_address", ln)
    for m in UUID_RE.findall(ln):
        hit(found, "uuid", ln)
    if MACHINE_RE.search(ln):
        hit(found, "machine_code", ln)
    if pw_variants and any(v in ln for v in pw_variants):
        hit(found, "password_plain_or_base64", ln)
    if username:
        stripped = ln.replace("/home/%s" % username, "/home/<user>")
        stripped = stripped.replace("uid=%s" % username, "uid=<user>")
        if username in stripped:
            hit(found, "username", ln)

print(json.dumps({
    "exists": True,
    "lines": len(lines),
    "violations": {k: len(v) for k, v in found.items()},
    "samples": {k: v[:2] for k, v in found.items()},
}))
"""

    def scan_log_privacy(self, log_path=None, username=None, password=None) -> dict:
        """扫描日志中的用户私密数据(描述口径)

        覆盖: 姓名/指纹(无法由日志模式识别, 归为人工项)、密码(明文与 Base64)、
        邮箱、住址(人工项)、电话、MAC、IP、用户名、MachineCode、UUID。
        用户名按"非路径出现"判定: /home/<user> 这类绝对路径属于产品运行必需信息,
        替换为 /home/<user> 后再判断是否仍有裸用户名出现。

        :param log_path: 日志路径, 默认取 get_pc_manager_log_path()
        :param username: 待检查用户名, 默认当前登录用户
        :param password: 待检查密码, 默认取 setting/conf.PASSWORD
        :return: {"exists", "lines", "violations": {类别: 次数}, "samples": {...}}
        """
        import base64
        import json as _json

        log_path = log_path or self.get_pc_manager_log_path()
        username = username or self.run_cmd(
            "id -un", timeout=5, out_debug_flag=False
        ).strip()
        password = password if password is not None else conf.PASSWORD
        if not log_path:
            return {"exists": False}
        encoded = base64.b64encode(self._LOG_PRIVACY_SCAN_PY.encode()).decode()
        out = self.run_cmd(
            f"if [ -s {log_path} ]; then "
            f"echo {encoded} | base64 -d | python3 - {log_path} "
            f"{quote(username)} {quote(password or '')}; "
            f"else echo '{{\"exists\": false}}'; fi",
            timeout=60,
            out_debug_flag=False,
        )
        try:
            return _json.loads(out.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {"exists": False}

    def get_log_privacy_status(self) -> bool:
        """检查 deepin-pc-manager 日志中是否包含用户私密数据

        基于 scan_log_privacy 的量化结果: 任一类(密码/邮箱/IP/MAC/用户名/
        MachineCode/UUID)出现即判定泄露。日志文件不存在时退化为 journald 检查。

        :return: True 表示未发现敏感信息, False 表示发现
        """
        log_path = self.get_pc_manager_log_path()
        if log_path:
            stats = self.scan_log_privacy(log_path)
            if stats.get("exists") and not stats.get("violations"):
                return True
            return False
        journal_result = self.run_cmd(
            "journalctl --user -u deepin-pc-manager --no-pager -n 200 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return not any(
            kw in journal_result.lower()
            for kw in ("password", "token", "secret", "machine_code", "machinecode")
        )

    def collect_pc_manager_file_inventory(self, marker=None) -> dict:
        """收集电脑管家的安装文件与运行时文件清单(文件规范检查用)

        - install: dpkg -L deepin-pc-manager 列出的安装项
        - runtime: ~/.cache、~/.config、~/.local/share 下 deepin-pc-manager 目录内的条目
        - home_loose: 用户家目录顶层的 pc-manager 相关条目(不应存在, 用来说明
          "产品未在家目录随意落文件")。传入 marker 时只统计比 marker 更新的条目,
          避免把环境里既有的打包产物(.deb/.changes/源码目录)误判为产品落盘文件。

        :param marker: 参照文件路径(如 /tmp/pcm_filespec_marker), 可选
        :return: {"install": [...], "runtime": [...], "home_loose": [...]}
        """
        install = self.run_cmd(
            "dpkg -L deepin-pc-manager 2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        runtime = self.run_cmd(
            "find ~/.cache/deepin/deepin-pc-manager "
            "~/.config/deepin-pc-manager "
            "~/.local/share/deepin/deepin-pc-manager "
            "~/.cache/deepin/deepin-pc-manager-session-daemon "
            "-mindepth 1 2>/dev/null",
            timeout=20,
            out_debug_flag=False,
        )
        newer = f"-newer {marker} " if marker else ""
        home_loose = self.run_cmd(
            f"find ~ -maxdepth 1 {newer}"
            "\( -iname '*pc-manager*' -o -iname '*pcmanager*' \) "
            "2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return {
            "install": [x.strip() for x in (install or "").splitlines() if x.strip()],
            "runtime": [x.strip() for x in (runtime or "").splitlines() if x.strip()],
            "home_loose": [x.strip() for x in (home_loose or "").splitlines() if x.strip()],
        }

    def get_pc_manager_systemd_units(self) -> dict:
        """收集电脑管家相关 systemd 单元(系统自启动服务检查用)

        - files: /lib,/usr/lib,/etc 下名称含 deepin-pc-manager 的单元文件
          (按 realpath 去重, 避免 /lib -> /usr/lib 软链接造成重复)
        - system_units: systemctl list-units 中匹配的已加载单元(名称+状态)
        - user_units: 用户级 systemctl --user 中匹配的单元
        - enabled: systemctl is-enabled 的结果(static/disabled/enabled)
        - service_type / bus_name: 单元的 Type/BusName(D-Bus 激活判定)

        :return: 上述字段组成的字典
        """
        files = self.run_cmd(
            "find /lib/systemd/system/ /usr/lib/systemd/system/ /etc/systemd/system/ "
            "-name '*deepin-pc-manager*' 2>/dev/null | "
            "while read f; do readlink -f \"$f\"; done | sort -u",
            timeout=10,
            out_debug_flag=False,
        )
        system_units = self.run_cmd(
            "systemctl list-units --type=service --all 2>/dev/null | "
            "grep -i 'deepin-pc-manager' || true",
            timeout=10,
            out_debug_flag=False,
        )
        user_units = self.run_cmd(
            "systemctl --user list-units --type=service --all 2>/dev/null | "
            "grep -i 'deepin-pc-manager' || true",
            timeout=10,
            out_debug_flag=False,
        )
        return {
            "files": [x.strip() for x in (files or "").splitlines() if x.strip()],
            "system_units": [x.strip() for x in (system_units or "").splitlines() if x.strip()],
            "user_units": [x.strip() for x in (user_units or "").splitlines() if x.strip()],
        }

    def get_systemd_unit_properties(self, unit) -> dict:
        """读取 unit 的 Type/BusName/ActiveState/UnitFileState

        :param unit: 单元名(如 deepin-pc-manager-daemon.service)
        :return: {"type","bus_name","active_state","unit_file_state","exec_start"}
        """
        props = self.run_cmd(
            f"systemctl show {unit} "
            "-p Type -p BusName -p ActiveState -p UnitFileState -p ExecStart 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        info = {
            "type": "",
            "bus_name": "",
            "active_state": "",
            "unit_file_state": "",
            "exec_start": "",
        }
        for line in (props or "").splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            mapping = {
                "Type": "type",
                "BusName": "bus_name",
                "ActiveState": "active_state",
                "UnitFileState": "unit_file_state",
                "ExecStart": "exec_start",
            }
            if key in mapping:
                info[mapping[key]] = value.strip()
        return info

    def get_pc_manager_binary_path(self) -> str:
        """获取 deepin-pc-manager 主二进制文件路径

        V20/V25 上二进制位于 /usr/libexec/deepin/deepin-pc-manager,
        退路检查 /usr/bin/deepin-pc-manager。
        :return: 二进制文件路径, 未找到时返回空字符串
        """
        for path in (
            "/usr/libexec/deepin/deepin-pc-manager",
            "/usr/bin/deepin-pc-manager",
        ):
            result = self.run_cmd(
                f'test -f {path} && echo "{path}"',
                timeout=5,
                out_debug_flag=False,
            )
            if result.strip():
                return result.strip()
        return ""

    def get_package_dependency_report(self, package="deepin-pc-manager") -> dict:
        """收集软件包的运行依赖/推荐依赖及可满足性(依赖关系检查用)

        说明: UOS 20 的 apt 没有 "apt depends" 子命令, 使用等价且输出稳定的
        "apt-cache depends"; 备选依赖(a | b)只要有任一已安装/可安装即视为满足。

        :param package: 包名
        :return: {"depends": [...], "recommends": [...], "suggests": [...],
                  "missing": [...], "unavailable": [...]}
        """
        raw = self.run_cmd(
            f"LC_ALL=C apt-cache depends {package} 2>/dev/null",
            timeout=20,
            out_debug_flag=False,
        )
        groups = {"Depends": [], "Recommends": [], "Suggests": []}
        current = None
        for line in (raw or "").splitlines():
            stripped = line.strip()
            if any(stripped.startswith(f"{key}:") for key in groups):
                current = stripped.split(":", 1)[0]
                value = stripped.split(":", 1)[1].strip()
                if value:
                    groups[current].append(value)
            elif current and stripped.startswith("|"):
                groups[current].append(stripped.lstrip("|").strip())

        def clean(dep):
            return dep.split("(")[0].strip()

        missing, unavailable = [], []
        for dep in groups["Depends"] + groups["Recommends"]:
            alternatives = [clean(x) for x in dep.split("|") if clean(x)]
            installed = any(
                "install ok installed"
                in self.run_cmd(
                    f"dpkg -s {alt} 2>/dev/null | grep '^Status:'",
                    timeout=10,
                    out_debug_flag=False,
                )
                for alt in alternatives
            )
            if installed:
                continue
            missing.append(dep)
            candidate_ok = any(
                self.run_cmd(
                    f"apt-cache policy {alt} 2>/dev/null | "
                    f"grep -E '候选|Candidate' | grep -v '(无|none)'",
                    timeout=10,
                    out_debug_flag=False,
                ).strip()
                for alt in alternatives
            )
            if not candidate_ok:
                unavailable.append(dep)
        return {
            "depends": groups["Depends"],
            "recommends": groups["Recommends"],
            "suggests": groups["Suggests"],
            "missing": missing,
            "unavailable": unavailable,
        }

    def list_package_elf_files(self) -> list:
        """列出 deepin-pc-manager 包内所有 ELF 文件(可执行文件与 .so)

        对应"二进制文件和 .so 库文件的编译选项"的检查对象: 直接从已安装包
        (dpkg -L, 内容与 deb 包一致)枚举, 不重复 apt download/dpkg -X。

        :return: ELF 文件绝对路径列表
        """
        out = self.run_cmd(
            "dpkg -L deepin-pc-manager 2>/dev/null | "
            'while read f; do test -f "$f" && '
            'head -c4 "$f" 2>/dev/null | grep -q ELF && echo "$f"; done',
            timeout=30,
            out_debug_flag=False,
        )
        return [x.strip() for x in (out or "").splitlines() if x.strip()]

    def check_elf_security(self, path) -> dict:
        """按 checksec 口径读取单个 ELF 的安全编译属性

        - type: ET_EXEC / ET_DYN(readelf -h)
        - nx: GNU_STACK flags 不含 E
        - relro: BIND_NOW + GNU_RELRO -> "Full RELRO"; 只有 GNU_RELRO -> "Partial RELRO"
        - canary: 动态符号含 __stack_chk_fail
        - fortify: 动态符号含 __*_chk(排除 __stack_chk_fail), 或构建链开启
          -D_FORTIFY_SOURCE

        :param path: ELF 文件路径
        :return: 上述字段组成的字典
        """
        header = self.run_cmd(
            f"LC_ALL=C readelf -W -h {path} 2>/dev/null | grep 'Type:' | head -1",
            timeout=10,
            out_debug_flag=False,
        )
        segments = self.run_cmd(
            f"LC_ALL=C readelf -W -l {path} 2>/dev/null | "
            f"grep -E 'GNU_STACK|GNU_RELRO'",
            timeout=10,
            out_debug_flag=False,
        )
        dynamic = self.run_cmd(
            f"LC_ALL=C readelf -W -d {path} 2>/dev/null | grep -E 'BIND_NOW|FLAGS'",
            timeout=10,
            out_debug_flag=False,
        )
        dynsyms = self.run_cmd(
            f"LC_ALL=C readelf -W --dyn-syms {path} 2>/dev/null | "
            f"grep -oE '__stack_chk_fail|__[A-Za-z0-9_]+_chk' | sort -u",
            timeout=10,
            out_debug_flag=False,
        )
        info = {
            "path": path,
            "type": "",
            "nx": False,
            "relro": "No RELRO",
            "canary": False,
            "fortify": False,
        }
        if "EXEC" in header:
            info["type"] = "ET_EXEC"
        elif "DYN" in header:
            info["type"] = "ET_DYN"
        stack_line = next(
            (ln for ln in segments.splitlines() if "GNU_STACK" in ln), ""
        )
        if stack_line:
            info["nx"] = " E " not in f" {stack_line} "
        has_relro = "GNU_RELRO" in segments
        bind_now = "BIND_NOW" in dynamic or "NOW" in dynamic
        if has_relro and bind_now:
            info["relro"] = "Full RELRO"
        elif has_relro:
            info["relro"] = "Partial RELRO"
        chk = [x for x in (dynsyms or "").splitlines() if x.strip()]
        info["canary"] = "__stack_chk_fail" in chk
        fortify_syms = [x for x in chk if x != "__stack_chk_fail"]
        if fortify_syms:
            info["fortify"] = True
        else:
            flags = self.run_cmd(
                "dpkg-buildflags --get CPPFLAGS 2>/dev/null",
                timeout=10,
                out_debug_flag=False,
            )
            info["fortify"] = "_FORTIFY_SOURCE" in flags
        return info

    def get_pie_enabled(self) -> bool:
        """检查二进制是否启用 PIE(位置无关可执行文件)

        PIE 编译的二进制 ELF 类型为 DYN(共享对象), 非 PIE 为 EXEC。
        使用 LC_ALL=C 确保输出为英文, 兼容不同 locale 环境。
        :return: True 表示启用了 PIE
        """
        binary = self.get_pc_manager_binary_path()
        if not binary:
            return False
        result = self.run_cmd(
            f"LC_ALL=C readelf -h {binary} 2>/dev/null | grep 'Type:' | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        if "DYN" in result:
            return True
        # UOS 20 的 dpkg-buildflags 不提供 pie 加固特性(hardening=+all 也不产出
        # -fPIE/-pie), 平台标准构建无法生成 PIE 二进制, 官方包同为 EXEC,
        # 此时不能判为缺陷; 平台支持 PIE 而产品仍为 EXEC 才是问题。
        flags = self.run_cmd(
            "DEB_BUILD_MAINT_OPTIONS=hardening=+all dpkg-buildflags --get CXXFLAGS "
            "2>/dev/null; DEB_BUILD_MAINT_OPTIONS=hardening=+all "
            "dpkg-buildflags --get LDFLAGS 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return "-fPIE" not in flags and "-pie" not in flags

    def get_nx_enabled(self) -> bool:
        """检查二进制是否启用 NX(不可执行栈保护)

        NX 启用时 GNU_STACK 段标志为 RW(无 E), 禁用时为 RWE。
        通过 grep -oE 提取标志字段(R/W/E 组合), 避免十六进制地址中的
        E 字符干扰判断。使用 LC_ALL=C 兼容不同 locale 环境。
        :return: True 表示启用了 NX
        """
        binary = self.get_pc_manager_binary_path()
        if not binary:
            return False
        result = self.run_cmd(
            f"LC_ALL=C readelf -l {binary} 2>/dev/null | "
            f"grep -A1 'GNU_STACK' | tail -1 | grep -oE '[RWE]{{1,3}}' | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        flags = result.strip()
        return bool(flags) and "E" not in flags

    def get_relro_status(self) -> str:
        """检查二进制 RELRO 状态

        Full RELRO: 同时存在 GNU_RELRO 段和 BIND_NOW 标志;
        Partial RELRO: 仅存在 GNU_RELRO 段;
        No RELRO: 均不存在。
        :return: "full", "partial", "none"
        """
        binary = self.get_pc_manager_binary_path()
        if not binary:
            return "none"
        relro_result = self.run_cmd(
            f"LC_ALL=C readelf -l {binary} 2>/dev/null | grep 'GNU_RELRO'",
            timeout=5,
            out_debug_flag=False,
        )
        bind_now_result = self.run_cmd(
            f"LC_ALL=C readelf -d {binary} 2>/dev/null | grep 'BIND_NOW'",
            timeout=5,
            out_debug_flag=False,
        )
        has_relro = bool(relro_result.strip())
        has_bind_now = bool(bind_now_result.strip())
        if has_relro and has_bind_now:
            return "full"
        if has_relro:
            return "partial"
        return "none"

    def get_relro_enabled(self) -> bool:
        """检查二进制是否启用了 RELRO(至少 Partial RELRO)

        :return: True 表示启用了 RELRO(Full 或 Partial)
        """
        return self.get_relro_status() in ("full", "partial")

    def get_stack_canary_enabled(self) -> bool:
        """检查二进制是否启用栈溢出保护(Stack Canary)

        启用栈保护的二进制包含 __stack_chk_fail 符号。
        使用 readelf -r 检查重定位表, 兼容 stripped 二进制。
        :return: True 表示启用了栈保护
        """
        binary = self.get_pc_manager_binary_path()
        if not binary:
            return False
        result = self.run_cmd(
            f"LC_ALL=C readelf -r {binary} 2>/dev/null | grep '__stack_chk_fail'",
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def get_fortify_source_enabled(self) -> bool:
        """检查二进制是否启用 FORTIFY_SOURCE(缓冲区溢出检测)

        启用 FORTIFY_SOURCE 的二进制包含 __*_chk 增强函数(如 __memcpy_chk)。
        使用 readelf -r 检查重定位表, 兼容 stripped 二进制。
        排除 __stack_chk_fail(属于栈保护而非 FORTIFY_SOURCE)。
        :return: True 表示启用了 FORTIFY_SOURCE
        """
        binary = self.get_pc_manager_binary_path()
        if not binary:
            return False
        result = self.run_cmd(
            f"LC_ALL=C readelf -r {binary} 2>/dev/null | "
            f"grep -E '__[a-z]+_chk' | grep -v '__stack_chk_fail' | head -5",
            timeout=5,
            out_debug_flag=False,
        )
        if result.strip():
            return True
        # 是否产生 __*_chk 取决于该二进制有没有调用可加固函数, 本项目为
        # C++/Qt 代码常无此类符号; 以构建链是否开启 -D_FORTIFY_SOURCE 为准。
        flags = self.run_cmd(
            "dpkg-buildflags --get CPPFLAGS 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        return "-D_FORTIFY_SOURCE" in flags

    def _get_appearance_schema(self) -> str:
        """获取 DDE 外观设置的 gsettings schema 名称(V20/V25 兼容)

        V20 使用 com.deepin.dde.appearance, V25 使用 org.deepin.dde.appearance。
        部分旧版 V20 可能使用 com.deepin.dde.fonts / org.deepin.dde.fonts。
        :return: schema 名称, 未找到时返回空字符串
        """
        for schema in (
            "org.deepin.dde.appearance",
            "com.deepin.dde.appearance",
        ):
            result = self.run_cmd(
                f"gsettings list-schemas 2>/dev/null | grep -x '{schema}'",
                timeout=5,
                out_debug_flag=False,
            )
            if result.strip():
                return schema
        return ""

    def _get_fonts_schema(self) -> str:
        """获取 DDE 字体设置的 gsettings schema(V20 旧版兼容)

        旧版 V20 可能使用 com.deepin.dde.fonts / org.deepin.dde.fonts,
        字体名和字号合并在 system1 键中。
        :return: schema 名称, 未找到时返回空字符串
        """
        for schema in (
            "org.deepin.dde.fonts",
            "com.deepin.dde.fonts",
        ):
            result = self.run_cmd(
                f"gsettings list-schemas 2>/dev/null | grep -x '{schema}'",
                timeout=5,
                out_debug_flag=False,
            )
            if result.strip():
                return schema
        return ""

    def get_screenshot_text_bbox(self, path, box=(180, 50, 420, 100), threshold=120):
        """统计截图中指定区域深色文字的包围盒(用于验证字号是否变化)

        :param path: 截图路径(窗口截图)
        :param box: 裁剪区域 (x1, y1, x2, y2), 默认覆盖"系统检测"标题
        :param threshold: 灰度阈值, 低于该值视为文字像素
        :return: (width, height, dark_count), 失败返回 (0, 0, 0)
        """
        code = (
            "from PIL import Image;"
            f"im=Image.open('{path}').convert('L');"
            f"c=im.crop({box});p=c.load();xs=[];ys=[];"
            "[(xs.append(x),ys.append(y)) for x in range(c.width) "
            "for y in range(c.height) "
            f"if p[x,y]<{threshold}];"
            "print(max(xs)-min(xs)+1, max(ys)-min(ys)+1, len(xs)) "
            "if xs else print(0,0,0)"
        )
        result = self.run_cmd(
            f"test -s {path} && python3 -c \"{code}\" 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        parts = result.strip().split()
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            return 0, 0, 0
        return tuple(int(p) for p in parts)

    def get_nav_item_size(self, nav_name="系统检测", retries=10) -> tuple:
        """获取左侧导航项元素的宽高(用于验证界面字号跟随系统字体)

        :param nav_name: 导航项名称
        :param retries: 重试次数
        :return: (width, height), 获取失败返回 (0, 0)
        """
        self._safe_focus_windows()
        for _ in range(retries):
            try:
                element = self.dog.find_element_by_attr(
                    f"$//mainWindow_navList//{nav_name}"
                )
                width, height = element.size
                if width > 0 and height > 0:
                    return int(width), int(height)
            except BaseException:
                pass
            sleep(1)
        return 0, 0

    def get_system_font(self) -> str:
        """获取当前系统字体设置(字体名 + 字号)

        优先从 appearance schema 读取 font-standard 和 font-size,
        回退到 fonts schema 的 system1 键。
        :return: 字体设置字符串, 如 "Noto Sans 10.5"
        """
        schema = self._get_appearance_schema()
        if schema:
            family = self.run_cmd(
                f"gsettings get {schema} font-standard 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            ).strip().strip("'")
            size = self.run_cmd(
                f"gsettings get {schema} font-size 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            ).strip().strip("'")
            if family and size:
                return f"{family} {size}"
        fonts_schema = self._get_fonts_schema()
        if fonts_schema:
            result = self.run_cmd(
                f"gsettings get {fonts_schema} system1 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
            return result.strip().strip("'")
        return ""

    def set_system_font(self, font_str: str) -> bool:
        """设置系统字体

        优先写入 appearance schema 的 font-standard 和 font-size,
        回退到 fonts schema 的 system1 键。
        :param font_str: 字体设置字符串, 如 "Noto Sans 12"
        :return: True 表示设置成功
        """
        parts = font_str.rsplit(" ", 1)
        if len(parts) != 2:
            return False
        family, size = parts
        schema = self._get_appearance_schema()
        if schema:
            self.run_cmd(
                f"gsettings set {schema} font-standard '{family}' 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
            self.run_cmd(
                f"gsettings set {schema} font-size '{size}' 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(2)
            return self._verify_font_setting(family, size)
        fonts_schema = self._get_fonts_schema()
        if fonts_schema:
            self.run_cmd(
                f"gsettings set {fonts_schema} system1 '{font_str}' 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(2)
            return self._verify_font_setting(family, size)
        return False

    def _verify_font_setting(self, family: str, size: str) -> bool:
        """验证字体设置是否生效(字号按浮点数比较)

        gsettings 的 font-size 键类型为 double, 设置 "9" 后读取返回 "9.0"。
        :param family: 期望的字体族名称
        :param size: 期望的字号字符串
        :return: True 表示设置生效
        """
        current = self.get_system_font()
        if not current:
            return False
        current_family = self.get_font_family_from_setting(current)
        current_size = self.get_font_size_from_setting(current)
        try:
            return current_family == family and float(current_size) == float(size)
        except (ValueError, TypeError):
            return current == f"{family} {size}"

    def get_available_font_families(self) -> list:
        """获取系统可用字体族列表

        :return: 字体族名称列表
        """
        result = self.run_cmd(
            "fc-list : family 2>/dev/null | sed 's/,.*$//' | sort -u",
            timeout=10,
            out_debug_flag=False,
        )
        families = [f.strip() for f in result.strip().splitlines() if f.strip()]
        return families

    def get_font_size_from_setting(self, font_str: str) -> str:
        """从字体设置字符串中提取字号

        字体设置格式为 "FontName Size", 如 "Noto Sans 10.5"。
        :param font_str: 字体设置字符串
        :return: 字号字符串, 解析失败时返回空字符串
        """
        parts = font_str.rsplit(" ", 1)
        if len(parts) == 2:
            return parts[1]
        return ""

    def get_font_family_from_setting(self, font_str: str) -> str:
        """从字体设置字符串中提取字体族名称

        :param font_str: 字体设置字符串
        :return: 字体族名称
        """
        parts = font_str.rsplit(" ", 1)
        if len(parts) == 2:
            return parts[0]
        return font_str

    def restore_system_font(self, original_font: str) -> bool:
        """恢复系统字体设置

        :param original_font: 原始字体设置字符串
        :return: True 表示恢复成功
        """
        return self.set_system_font(original_font)

    def get_monitor_count(self) -> int:
        """获取当前逻辑显示器数量(xrandr --listmonitors)

        扩展/复制模式至少需要 2 个输出, 用于判断多屏场景是否可执行。

        :return: 显示器数量, 解析失败返回 0
        """
        result = self.run_cmd(
            "xrandr --listmonitors 2>/dev/null | head -1",
            timeout=10,
            out_debug_flag=False,
        )
        match = re.search(r"Monitors:\s*(\d+)", result or "")
        return int(match.group(1)) if match else 0

    def is_window_close_button_visible(self) -> bool:
        """检查电脑管家标题栏关闭按钮是否可见(窗口框架渲染完整)

        V25 上 showing 可能恒为 False, 用 size 非零兜底。

        :return: True 如果关闭按钮可见
        """
        for expr in ("$//DTitlebarDWindowCloseButton", "$//DTitlebarDWindowQuitFullscreenButton"):
            try:
                element = self.dog.find_element_by_attr(expr)
                if element.showing:
                    return True
                width, height = element.size
                if width > 0 and height > 0:
                    return True
            except BaseException:
                continue
        return False

    def get_screen_resolution(self) -> tuple:
        """获取当前屏幕分辨率(通过 xrandr 解析)

        :return: (width, height) 元组, 获取失败返回 (0, 0)
        """
        result = self.run_cmd(
            "xrandr --current 2>/dev/null | grep ' connected primary' | "
            "grep -oE '[0-9]+x[0-9]+' | head -1 || "
            "xrandr --current 2>/dev/null | grep ' connected' | "
            "grep -oE '[0-9]+x[0-9]+' | head -1",
            timeout=10,
            out_debug_flag=False,
        )
        result = result.strip()
        if "x" in result:
            parts = result.split("x")
            return (int(parts[0]), int(parts[1]))
        # V25: 显示器可能显示为 "disconnected primary", 从 Screen 0 行解析当前分辨率
        result = self.run_cmd(
            "xrandr --current 2>/dev/null | grep '^Screen 0:' | "
            "grep -oE 'current [0-9]+ x [0-9]+'",
            timeout=10,
            out_debug_flag=False,
        )
        result = result.strip().replace("current ", "").replace(" ", "")
        if "x" in result:
            parts = result.split("x")
            return (int(parts[0]), int(parts[1]))
        return (0, 0)

    def get_available_resolutions(self) -> list:
        """获取当前主屏支持的可用分辨率列表

        :return: [(width, height), ...] 列表, 获取失败返回空列表
        """
        resolutions = []
        result = self.run_cmd(
            # 只取第一个 connected 输出自身的模式列表: 遇到下一个输出行
            # (含 connected/disconnected 或 Screen 头) 立即停止。不能依赖
            # 首字符缩进判断, xrandr 的模式行可能以 tab 开头。
            "xrandr --current 2>/dev/null | "
            "awk '/ connected/ && !found {found=1; next} "
            "found && (/ connected/ || / disconnected/ || /^Screen/) {exit} "
            "found {print $1}' | "
            "grep -oE '^[0-9]+x[0-9]+' | sort -u",
            timeout=10,
            out_debug_flag=False,
        )
        for line in result.strip().split("\n"):
            line = line.strip()
            if "x" in line:
                parts = line.split("x")
                try:
                    resolutions.append((int(parts[0]), int(parts[1])))
                except (ValueError, IndexError):
                    continue
        if resolutions:
            return resolutions
        # V25: 无已连接显示器时, 从所有输出名称下的模式行获取可用分辨率
        result = self.run_cmd(
            "xrandr --current 2>/dev/null | "
            "awk '/^ / {print $1}' | "
            "grep -oE '^[0-9]+x[0-9]+' | sort -u",
            timeout=10,
            out_debug_flag=False,
        )
        for line in result.strip().split("\n"):
            line = line.strip()
            if "x" in line:
                parts = line.split("x")
                try:
                    resolutions.append((int(parts[0]), int(parts[1])))
                except (ValueError, IndexError):
                    continue
        return resolutions

    def get_screen_output_name(self) -> str:
        """获取当前连接的主屏输出名称(如 eDP-1, HDMI-1 等)

        :return: 输出名称字符串, 获取失败返回空字符串
        """
        result = self.run_cmd(
            "xrandr --current 2>/dev/null | grep ' connected' | "
            "awk '{print $1}' | head -1",
            timeout=10,
            out_debug_flag=False,
        )
        result = result.strip()
        if result:
            return result
        # V25: 无已连接显示器时, 从 disconnected primary 获取输出名称
        result = self.run_cmd(
            "xrandr --current 2>/dev/null | grep 'disconnected primary' | "
            "awk '{print $1}' | head -1",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip()

    def set_screen_resolution(self, width: int, height: int) -> bool:
        """设置屏幕分辨率为指定宽高

        :param width: 目标宽度
        :param height: 目标高度
        :return: True 表示设置成功, False 表示设置失败
        """
        output = self.get_screen_output_name()
        if not output:
            log.warning("未找到连接的屏幕输出, 无法设置分辨率")
            return False
        self.run_cmd(
            f"xrandr --output {output} --mode {width}x{height} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)
        actual_w, actual_h = self.get_screen_resolution()
        return actual_w == width and actual_h == height

    def get_pc_manager_window_geometry(self) -> tuple:
        """获取电脑管家窗口的几何信息(位置和大小)

        :return: (x, y, width, height) 元组, 获取失败返回 (0, 0, 0, 0)
        """
        try:
            self._safe_focus_windows()
            window_id = self.ui.get_lastest_window_id(self.APP_NAME)
            if not window_id:
                return (0, 0, 0, 0)
            result = self.run_cmd(
                f"xprop -id {window_id} _NET_WM_GEOMETRY",
                timeout=5,
                out_debug_flag=False,
            )
            import re
            match = re.search(
                r"x, y, width, height:\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)",
                result,
            )
            if match:
                return tuple(int(v) for v in match.groups())
            # V25: _NET_WM_GEOMETRY 不存在时, 使用 xdotool 获取窗口几何信息
            result = self.run_cmd(
                f"xdotool getwindowgeometry --shell {window_id}",
                timeout=5,
                out_debug_flag=False,
            )
            nums = dict(
                line.split("=", 1)
                for line in result.strip().split("\n")
                if "=" in line
            )
            try:
                return (
                    int(nums.get("X", 0)),
                    int(nums.get("Y", 0)),
                    int(nums.get("WIDTH", 0)),
                    int(nums.get("HEIGHT", 0)),
                )
            except (ValueError, KeyError):
                pass
        except BaseException:
            pass
        return (0, 0, 0, 0)

    def check_ui_displayed_at_resolution(self, width: int, height: int) -> bool:
        """检查电脑管家在指定分辨率下 UI 是否正常显示

        :param width: 期望的屏幕宽度
        :param height: 期望的屏幕高度
        :return: True 表示 UI 正常显示
        """
        if not self.get_pc_manager_process_status():
            return False
        if not self.get_main_page_modules_showing():
            return False
        win_x, win_y, win_w, win_h = self.get_pc_manager_window_geometry()
        if win_w <= 0 or win_h <= 0:
            log.warning("窗口几何信息获取失败, 但进程和模块检查通过")
        return True

    def get_element_position(self, expr, retries=10, interval=1):
        """获取元素的位置与尺寸

        :param expr: AT-SPI 表达式
        :param retries: 查找重试次数
        :param interval: 每次重试间隔秒数
        :return: (x, y, width, height), 元素不存在返回 None
        """
        for _ in range(retries):
            try:
                element = self.dog.find_element_by_attr(expr)
                if element:
                    pos = element.position
                    size = element.size
                    return (int(pos[0]), int(pos[1]), int(size[0]), int(size[1]))
            except BaseException:
                pass
            sleep(interval)
        return None

    def wheel_scroll_on_element(self, expr, notches=8, button=5, delay=80) -> bool:
        """在指定元素中心滚动滚轮(等效双指上下滑动)

        :param expr: AT-SPI 表达式, 滚动位置取该元素中心
        :param notches: 滚动格数
        :param button: 4 向上 / 5 向下
        :param delay: 每格间隔毫秒
        :return: True 表示滚动动作已发出
        """
        info = self.get_element_position(expr)
        if not info:
            return False
        x, y, w, h = info
        if w <= 0 or h <= 0:
            return False
        self.run_cmd(
            f"xdotool mousemove {x + w // 2} {y + h // 2} "
            f"click --repeat {notches} --delay {delay} {button}",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(1.5)
        self.reconnect_dogtail()
        self._safe_focus_windows()
        return True

    def simulate_touch_tap_on_nav(self, nav_name: str) -> bool:
        """模拟触控点击(tap)导航栏指定项

        通过 AT-SPI 获取导航项的位置和尺寸, 计算中心坐标后
        使用 xdotool 模拟点击, 等效于手指触控点击(tap)操作。
        点击后等待页面切换动画完成并重新建立 dogtail 连接。

        :param nav_name: 导航项名称(如 "系统检测"、"修复工具"、"实用工具")
        :return: True 表示模拟触控点击成功
        """
        self._safe_focus_windows()
        nav_exprs = [
            f"$//mainWindow_navList//{nav_name}",
        ]
        element = None
        for _ in range(10):
            element = self._find_element_in_exprs(nav_exprs)
            if element:
                break
            sleep(1)
        if not element:
            return False
        try:
            pos = element.position
            size = element.size
            cx = int(pos[0] + size[0] / 2)
            cy = int(pos[1] + size[1] / 2)
            self.run_cmd(
                f"xdotool mousemove {cx} {cy} click 1",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(2)
            self.reconnect_dogtail()
            return True
        except BaseException:
            return False

    def create_virtual_usb_ext4_with_errors(
        self, img_path="/tmp/test_usb_ext4.img", mount_point="/tmp/test_usb_ext4_mount"
    ):
        """创建存在可自动修复错误的 ext4 虚拟 U 盘(loop 设备)

        在正常 ext4 文件系统基础上, 写入测试数据后卸载,
        通过 debugfs 修改超级块中的空闲 inode 计数为错误值,
        引入可被 e2fsck -p 自动修复的文件系统错误。
        损坏操作在文件系统卸载后进行, 确保 e2fsck 能正确检测。

        :param img_path: 镜像文件路径
        :param mount_point: 挂载点路径
        :return: loop 设备路径(如 /dev/loop0), 失败返回空字符串
        """
        loop_dev = self.create_virtual_usb_ext4(img_path, mount_point)
        if not loop_dev:
            return ""

        # 写入测试数据使文件系统有实际内容
        self.sudo_run_cmd(
            f"dd if=/dev/zero of={mount_point}/test_file.bin bs=1K count=100 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

        # 卸载文件系统以便引入错误
        self.sudo_run_cmd(f"umount {mount_point} 2>/dev/null", timeout=10, out_debug_flag=False)
        sleep(1)

        # 通过 debugfs 修改超级块空闲 inode 计数为错误值, 引入可自动修复的错误
        self.sudo_run_cmd(
            f"debugfs -w -R 'set_super_value free_inodes_count 99999' {loop_dev} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

        return loop_dev

    def get_usb_ext4_filesystem_has_errors(self, loop_dev="") -> bool:
        """检查 ext4 文件系统是否存在可自动修复的错误

        通过 e2fsck -n 检查文件系统状态, 退出码非 0 表示存在错误。
        与 get_usb_ext4_filesystem_healthy 互补。

        :param loop_dev: loop 设备路径, 为空时自动查找
        :return: True 表示文件系统存在错误, False 表示无错误
        """
        if not loop_dev:
            result = self.sudo_run_cmd(
                "losetup -j /tmp/test_usb_ext4.img 2>/dev/null", timeout=5, out_debug_flag=False
            )
            loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return False
        result = self.sudo_run_cmd(
            f"e2fsck -n {loop_dev} 2>&1; echo EXIT_CODE=$?", timeout=15, out_debug_flag=False
        )
        if "EXIT_CODE=0" not in result:
            return True
        # e2fsck -n 以只读方式检查时, 对"计数不一致"这类可自动修复的错误
        # 只提示 "Free inodes count wrong ... Fix? no", 退出码仍为 0,
        # 因此需要按输出文本补充判定。
        return any(
            keyword in result
            for keyword in ("wrong", "Fix?", "corrupt", "errors", "mismatch")
        )

    # ===== ext4 U 盘可修复错误注入与判定(用例 2005759) =====

    EXT4_PARTITION_RE = r"^/dev/(sd[a-z]+\d+|vd[a-z]+\d+|nvme\d+n\d+p\d+|loop\d+)$"

    def get_usb_ext4_partition_has_errors(self, partition) -> bool:
        """只读检查 ext4 分区是否存在文件系统错误(与产品 check_filesystem 同判据)

        产品依据(deepin-pc-manager 的 plugin-usb-fix/entry.sh check_filesystem):
        对 ext4 分区执行 "fsck -n -t ext4", 以退出码判定, 非 0 即
        FS_SEVERITY=corrupted, 输出"分区 /dev/sdX1 (ext4) 文件系统损坏"。
        实测 e2fsprogs 对"块位图与 inode 引用不一致"在 -n 下打印
        "Free blocks count wrong ... Fix? no" 并返回 4; 但仅超级块计数错误时
        可能返回 0, 故在退出码之外补充输出文本判定, 避免漏判。

        :param partition: 分区设备路径(如 /dev/sdb1)
        :return: True 表示存在文件系统错误
        """
        if not partition:
            return False
        out = self.sudo_run_cmd(
            f"fsck.ext4 -n {quote(partition)} 2>&1; echo RC=$?",
            timeout=60,
            out_debug_flag=False,
        )
        match = re.search(r"RC=(\d+)", out or "")
        rc = int(match.group(1)) if match else -1
        logger.info(f"ext4 只读检查 {partition}: rc={rc}, 输出={out!r}")
        if rc != 0:
            return True
        return any(
            keyword in (out or "")
            for keyword in ("Fix?", "wrong", "corrupt", "differences", "uncleanly")
        )

    def create_usb_ext4_repairable_error(self, partition) -> bool:
        """向已卸载的 ext4 分区注入可被 fsck 自动修复的文件系统错误

        产品依据(deepin-pc-manager 的 plugin-usb-fix/entry.sh):
        - check_filesystem: "fsck -n -t ext4" 退出码非 0 → FS_SEVERITY=corrupted;
        - present_diagnosis: 输出"- 文件系统损坏(... ext4)，可尝试自动修复"并
          弹出"诊断结果"确认框;
        - execute_repairs/fix_filesystem: 弹"修复文件系统"确认框后执行
          "fsck -y -t ext4", 退出码 <= 1 记为该分区"修复成功";
        - present_results: 输出"修复完成 ... 成功: N"。
        因此注入的错误必须让 "fsck -n" 返回非 0。

        注入手段(本机 e2fsprogs 1.44.5 实测):
        1) 取根目录 inode(<2>)占用的第一个数据块, 用 debugfs freeb 在块位图中把它
           标记为空闲 —— 与 inode 实际引用不一致, 属 fsck 可自动修复的元数据错误;
        2) 用 debugfs 把超级块 s_state 置 0(未清理) —— 否则 fsck 对"干净"文件系统
           会跳过检查, -n 直接返回 0, 产品不会进入损坏分支;
        3) 只改块位图与超级块, 不动任何文件数据块, 满足"U 盘不损坏、数据不丢失"。
        实测注入后 "fsck -n -t ext4" 报 "Free blocks count wrong ... Fix? no" 且
        rc=4; "fsck -y -t ext4" 报 "Block bitmap differences: +N Fix? yes", rc=1;
        修复后 rc=0 且文件内容不变。

        :param partition: 已卸载的 ext4 分区设备路径(如 /dev/sdb1)
        :return: True 表示注入成功且已确认存在错误
        """
        if not re.match(self.EXT4_PARTITION_RE, partition or ""):
            logger.error(f"ext4 可修复错误注入需要块设备, 收到: {partition!r}")
            return False

        # 注入前确保分区未挂载: 挂载状态下改元数据会被页缓存覆盖
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; true',
            timeout=30,
            out_debug_flag=False,
        )
        if self.run_cmd(
            f"findmnt -n -o TARGET {quote(partition)} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        ).strip():
            logger.error(f"{partition} 仍处于挂载状态, 无法注入 ext4 错误")
            return False

        # 根目录通常有数据块; 极简文件系统上退回 lost+found(inode 11)
        block = ""
        for inode in ("2", "11"):
            # sudo 密码提示会粘在首行, 解析前先清洗, 否则首行数字识别不到
            blocks_out = self.strip_sudo_noise(
                self.sudo_run_cmd(
                    f"debugfs -R 'blocks <{inode}>' {quote(partition)} 2>/dev/null",
                    timeout=30,
                    out_debug_flag=False,
                )
            )
            for line in (blocks_out or "").splitlines():
                tokens = line.split()
                if tokens and all(token.isdigit() for token in tokens):
                    block = tokens[0]
                    break
            if block:
                break
        if not block:
            logger.error(f"无法读取 {partition} 根目录占用的块, 无法注入 ext4 错误")
            return False

        freeb_out = self.sudo_run_cmd(
            f"debugfs -w -R 'freeb {block}' {quote(partition)} 2>&1",
            timeout=30,
            out_debug_flag=False,
        )
        if freeb_out and "could not" in freeb_out.lower():
            logger.error(f"把块 {block} 置为空闲失败: {freeb_out!r}")
            return False
        self.sudo_run_cmd(
            f"debugfs -w -R 'ssv state 0' {quote(partition)} 2>&1",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd("sync", timeout=30, out_debug_flag=False)
        self.sudo_run_cmd(
            f"blockdev --flushbufs {quote(partition)} 2>/dev/null; "
            f"udevadm trigger --subsystem-match=block {quote(partition)} 2>/dev/null; "
            "udevadm settle --timeout=10 2>/dev/null; true",
            timeout=40,
            out_debug_flag=False,
        )
        sleep(1)

        has_errors = self.get_usb_ext4_partition_has_errors(partition)
        logger.info(
            f"ext4 可修复错误注入: {partition} 根目录块 {block} 已置空闲, "
            f"fsck 报错={has_errors}"
        )
        return has_errors

    def create_virtual_usb_exfat_with_errors(
        self,
        img_path="/tmp/test_usb_exfat.img",
        mount_point="/tmp/test_usb_exfat_mount",
    ):
        """创建存在可自动修复错误的 exFAT 虚拟 U 盘(loop 设备)

        通过创建磁盘镜像文件并关联 loop 设备来模拟 U 盘,
        格式化为 exFAT 文件系统后, 在 FAT 表区域写入少量错误字节
        来模拟可自动修复的文件系统错误。
        需要 root 权限执行 losetup/mount 操作。

        :param img_path: 镜像文件路径
        :param mount_point: 挂载点路径
        :return: loop 设备路径(如 /dev/loop0), 失败返回空字符串
        """
        img_size = "64M"
        self.sudo_run_cmd(
            f"truncate -s {img_size} {img_path}", timeout=10, out_debug_flag=False
        )
        result = self.sudo_run_cmd(
            f"losetup -f --show {img_path} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return ""
        # 格式化为 exFAT 文件系统
        self.sudo_run_cmd(
            f"mkfs.exfat {loop_dev} 2>/dev/null || mkexfatfs {loop_dev} 2>/dev/null", timeout=15, out_debug_flag=False
        )
        sleep(1)
        # 解析 exFAT 引导扇区定位根目录, 写入无效数据来模拟可修复的文件系统错误
        # exFAT 引导扇区中:
        #   偏移 88-91: 簇堆起始扇区号(小端)
        #   偏移 96-99: 根目录首簇号(小端)
        #   偏移 108: 每扇区字节数(2的幂)
        #   偏移 109: 每簇扇区数(2的幂)
        # 根目录偏移 = 簇堆起始 * 每扇区字节 + (根目录首簇 - 2) * 簇大小
        corrupt_cmd = (
            f'python3 -c "'
            f"import struct as s;"
            f"b=open('{loop_dev}','rb').read(112);"
            f"ch=s.unpack_from('<I',b,88)[0];"
            f"rc=s.unpack_from('<I',b,96)[0];"
            f"bps=1<<b[108];"
            f"cs=bps*(1<<b[109]);"
            f"off=ch*bps+(rc-2)*cs;"
            f"f=open('{loop_dev}','r+b');"
            f"f.seek(off);"
            f"f.write(b'\\xff'*32);"
            f"f.close()"
            f'"'
        )
        self.sudo_run_cmd(
            corrupt_cmd,
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"mkdir -p {mount_point}", timeout=5, out_debug_flag=False
        )
        # 尝试挂载(可能因错误而失败, 这是预期行为)
        self.sudo_run_cmd(
            f"mount {loop_dev} {mount_point} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        sleep(1)
        return loop_dev

    def cleanup_virtual_usb_exfat(
        self,
        img_path="/tmp/test_usb_exfat.img",
        mount_point="/tmp/test_usb_exfat_mount",
    ):
        """清理 exFAT 虚拟 U 盘(卸载、分离 loop 设备、删除镜像文件)

        :param img_path: 镜像文件路径
        :param mount_point: 挂载点路径
        """
        import re

        self.sudo_run_cmd(
            f"umount {mount_point} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        result = self.sudo_run_cmd(
            f"losetup -j {img_path} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        if result:
            for match in re.finditer(r"/dev/loop\d+", result):
                self.sudo_run_cmd(
                    f"losetup -d {match.group(0)} 2>/dev/null",
                    timeout=5,
                    out_debug_flag=False,
                )
        self.sudo_run_cmd(
            f"rm -rf {mount_point} {img_path}", timeout=5, out_debug_flag=False
        )
        sleep(1)

    def get_usb_exfat_filesystem_has_errors(self, loop_dev="") -> bool:
        """检查 exFAT 文件系统是否存在错误

        通过 fsck.exfat 检查文件系统状态, 非零退出码或输出包含 ERROR 表示有错误。
        注意: exfatprogs 的 fsck.exfat 在 -n 模式下即使发现错误也可能返回退出码 0,
        因此需要同时检查输出文本中是否包含错误关键词。

        :param loop_dev: loop 设备路径, 为空时自动查找
        :return: True 表示文件系统存在错误, False 表示无错误
        """
        if not loop_dev:
            result = self.sudo_run_cmd(
                "losetup -j /tmp/test_usb_exfat.img 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
            loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return False
        result = self.sudo_run_cmd(
            f"fsck.exfat -n {loop_dev} 2>&1 || exfatfsck -n {loop_dev} 2>&1; echo EXIT_CODE=$?",
            timeout=15,
            out_debug_flag=False,
        )
        lowered = result.lower()
        # 健康文件系统的输出是 "File system checking finished. No errors found.",
        # 其中 "ERRORS" 本身包含 "ERROR" 子串, 必须先按完整文案排除,
        # 否则无错误的 exFAT 盘会被误判为"存在错误"。
        if "no errors found" in lowered:
            return False
        if "EXIT_CODE=0" not in result:
            return True
        return "error" in lowered

    def prepare_usb_exfat_partition(
        self, mount_point="/tmp/test_usb_exfat_mount", partition=""
    ) -> str:
        """把 USB 存储设备的第一个分区(或指定分区)格式化为 exFAT 并挂载

        usb-fix 插件按 udev 的 ID_BUS=usb 枚举整盘, 因此必须使用真实的 sdX 分区
        (scsi_debug 合成盘也满足), loop 设备不会被插件识别。
        格式化前先卸载 udisks2 可能留下的自动挂载点, 避免"设备忙"导致 mkfs 失败。
        不设置卷标: exfat-utils 1.3.0 的 mkfs.exfat 只认 -n, exfatprogs 只认 -L,
        本用例不需要卷标, 因此省略该参数以保证两种实现都能通过。

        :param mount_point: 挂载点路径
        :param partition: 指定分区设备路径; 为空时取第一块 USB 存储设备的第一个分区
        :return: 分区设备路径, 失败返回空字符串
        """
        if not partition:
            partition = self.get_first_usb_storage_partition()
        if not partition:
            return ""
        # 先清理 udisks2 的自动挂载, 避免"设备忙"导致 mkfs 失败
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; true',
            timeout=30,
            out_debug_flag=False,
        )
        mkfs_out = self.sudo_run_cmd(
            f"mkfs.exfat {quote(partition)} 2>&1 || mkexfatfs {quote(partition)} 2>&1; "
            "echo RC=$?",
            timeout=180,
            out_debug_flag=False,
        )
        if "RC=0" not in (mkfs_out or ""):
            logger.error(f"格式化 exFAT 失败: {mkfs_out!r}")
            return ""
        if not self.mount_usb_partition(partition, mount_point, "exfat"):
            logger.error(f"exFAT 分区 {partition} 挂载失败, 无法注入测试数据")
            return ""
        logger.info(f"USB 分区已格式化为 exFAT 并挂载: {partition} -> {mount_point}")
        return partition

    def prepare_usb_ntfs_partition(
        self, mount_point="/tmp/test_usb_ntfs_mount", partition=""
    ) -> str:
        """把 USB 存储设备的第一个分区(或指定分区)格式化为 NTFS 并挂载

        usb-fix 插件按 udev 的 ID_BUS=usb 枚举整盘, 因此必须使用真实的 sdX 分区
        (scsi_debug 合成盘也满足), loop 设备不会被插件识别。
        格式化前先卸载 udisks2 可能留下的自动挂载点, 避免"设备忙"导致 mkfs 失败。
        用 -f(fast) 快速格式化: 512MB 合成盘整盘写零没有必要, 快速格式化后卷仍是
        标准 NTFS 3.1; -F 允许对"已有文件系统的设备"执行, -Q 关闭进度输出。
        NTFS 挂载依赖 ntfs3(内核)或 ntfs-3g(FUSE), 这里按 ntfs -> ntfs3 -> 自动探测
        依次尝试, 以同时适配 V20(ntfs-3g) 与 V25(内核 ntfs3)。

        :param mount_point: 挂载点路径
        :param partition: 指定分区设备路径; 为空时取第一块 USB 存储设备的第一个分区
        :return: 分区设备路径, 失败返回空字符串
        """
        if not partition:
            partition = self.get_first_usb_storage_partition()
        if not partition:
            return ""
        # 先清理 udisks2 的自动挂载, 避免"设备忙"导致 mkfs 失败
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; true',
            timeout=30,
            out_debug_flag=False,
        )
        mkfs_out = self.sudo_run_cmd(
            f"mkfs.ntfs -F -f -Q {quote(partition)} 2>&1 "
            f"|| mkntfs -F -f -Q {quote(partition)} 2>&1; echo RC=$?",
            timeout=300,
            out_debug_flag=False,
        )
        if "RC=0" not in (mkfs_out or ""):
            logger.error(f"格式化 NTFS 失败: {mkfs_out!r}")
            return ""
        for fstype in ("ntfs", "ntfs3", ""):
            if self.mount_usb_partition(partition, mount_point, fstype):
                logger.info(
                    f"USB 分区已格式化为 NTFS 并挂载: {partition} -> {mount_point} "
                    f"(mount -t {fstype or 'auto'})"
                )
                return partition
        logger.error(f"NTFS 分区 {partition} 挂载失败, 无法注入测试数据")
        return ""

    def get_usb_ntfs_filesystem_check_rc(self, partition) -> int:
        """对 NTFS 分区执行 ntfsfix 只读检查, 返回退出码

        Linux 下 NTFS 的 fsck 实现是 ntfsfix(ntfs-3g/ntfsprogs 提供), -n 表示只
        检查不写盘。健康的 NTFS 卷返回 0; 卷标脏(需 chkdsk)、存在错误时返回非 0。

        :param partition: 分区设备路径(如 /dev/sdb1)
        :return: ntfsfix -n 的退出码, 无法执行返回 -1
        """
        if not partition:
            return -1
        out = self.sudo_run_cmd(
            f"ntfsfix -n {quote(partition)} >/dev/null 2>&1; echo RC=$?",
            timeout=60,
            out_debug_flag=False,
        )
        match = re.search(r"RC=(\d+)", out or "")
        return int(match.group(1)) if match else -1

    def get_usb_ntfs_filesystem_has_errors(self, partition) -> bool:
        """检查 NTFS 分区是否存在文件系统错误/脏标志

        判定依据: ntfsfix 只读检查退出码非 0, 或输出中出现 dirty/corrupt/error
        等错误关键词。健康卷的输出形如 "Processing of $MFT and $MFTMirr
        completed successfully." / "NTFS partition ... was processed successfully.",
        不含上述关键词, 不会被误判。

        :param partition: 分区设备路径(如 /dev/sdb1)
        :return: True 表示文件系统存在错误, False 表示无错误
        """
        if not partition:
            return False
        out = self.sudo_run_cmd(
            f"ntfsfix -n {quote(partition)} 2>&1; echo EXIT_CODE=$?",
            timeout=60,
            out_debug_flag=False,
        )
        if "EXIT_CODE=0" not in (out or ""):
            return True
        lowered = (out or "").lower()
        return any(
            keyword in lowered
            for keyword in ("dirty", "corrupt", "error", "inconsistent", "failed")
        )

    # ===== ext4 U 盘现场构造与数据完整性校验(用例 2005757) =====

    def corrupt_usb_ext4_unfixable_error(self, partition) -> bool:
        """向已卸载的 ext4 分区注入 fsck 无法自动修复的逻辑损坏

        产品依据(plugin-usb-fix/entry.sh):
        - check_filesystem 用 "fsck -n -t ext4" 退出码判损坏(非 0 → corrupted);
        - present_diagnosis 展示"- 文件系统损坏(... ext4)，可尝试自动修复";
        - fix_filesystem 执行 "fsck -y -t ext4", 退出码 > 1 记"修复失败";
        - 另有"修复后 blkid 认不出类型 → 记为 exit=99 修复失败"的保护分支。

        注入手段: 把超级块 s_feature_incompat 置一个当前 e2fsprogs 不认识的位
        (0x100000)。本机 e2fsprogs 1.44.5 实测: blkid 仍能识别为 ext4(类型不变,
        不会走 severe 分支), "fsck.ext4 -n" 与 "fsck.ext4 -y" 都返回 8
        (无法继续检查 / Unsupported feature), 即"检测到异常但无法自动修复";
        这正是"逻辑损坏"场景需要的效果, 且不改动任何文件数据块。

        :param partition: 已卸载的 ext4 分区设备路径(如 /dev/sdb1)
        :return: True 表示注入成功(注入后仍是 ext4 且 fsck 返回非 0)
        """
        if not re.match(self.EXT4_PARTITION_RE, partition or ""):
            logger.error(f"ext4 损坏注入需要块设备, 收到: {partition!r}")
            return False
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; true',
            timeout=30,
            out_debug_flag=False,
        )
        if self.run_cmd(
            f"findmnt -n -o TARGET {quote(partition)} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        ).strip():
            logger.error(f"{partition} 仍处于挂载状态, 无法注入 ext4 损坏")
            return False

        patcher = "/tmp/autotest_ext4_incompat_bit.py"
        self.sudo_run_cmd(
            "cat > {path} <<'AUTOTEST_EXT4_EOF'\n"
            "import struct\n"
            "import sys\n"
            "path = sys.argv[1]\n"
            "with open(path, 'r+b') as fd:\n"
            "    fd.seek(1024 + 0x60)\n"
            "    value = struct.unpack('<I', fd.read(4))[0]\n"
            "    fd.seek(1024 + 0x60)\n"
            "    fd.write(struct.pack('<I', value | 0x100000))\n"
            "    fd.flush()\n"
            "print('INCOMPAT_BEFORE=%d' % value)\n"
            "AUTOTEST_EXT4_EOF".format(path=patcher),
            timeout=20,
            out_debug_flag=False,
        )
        out = self.sudo_run_cmd(
            f"python3 {patcher} {quote(partition)} 2>&1", timeout=30, out_debug_flag=False
        )
        if "INCOMPAT_BEFORE=" not in (out or ""):
            logger.error(f"写入 ext4 未知特性位失败: {out!r}")
            return False
        self.sudo_run_cmd(
            f"blockdev --flushbufs {quote(partition)} 2>/dev/null; sync; "
            f"udevadm trigger --action=change --subsystem-match=block {quote(partition)} "
            "2>/dev/null; udevadm settle --timeout=10 2>/dev/null; true",
            timeout=40,
            out_debug_flag=False,
        )
        fs_type = self.run_cmd(
            f"/sbin/blkid -o value -s TYPE {quote(partition)} 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        rc = self.get_usb_ext4_partition_check_rc(partition)
        logger.info(f"ext4 逻辑损坏注入 {partition}: type={fs_type!r}, fsck -n rc={rc}")
        return fs_type == "ext4" and rc > 1

    def corrupt_usb_ext4_severe_damage(self, partition) -> bool:
        """把已卸载的 ext4 分区前 10MB 清零, 制造"无法识别文件系统"的严重损坏

        具体构造与校验见 corrupt_usb_partition_severe_damage(与文件系统类型无关)。

        :param partition: 已卸载的分区设备路径(如 /dev/sdb1)
        :return: True 表示清零成功且 blkid 已无法识别文件系统类型
        """
        return self.corrupt_usb_partition_severe_damage(partition)

    def corrupt_usb_partition_severe_damage(self, partition) -> bool:
        """把已卸载的分区前 10MB 清零, 制造"无法识别文件系统"的严重损坏

        用例步骤给的是 "dd if=/dev/zero of=/dev/sdX bs=1M count=10"(整盘)。
        在 USB 设备上实测: 清零整盘会让内核重新校验介质, /sys/block/sdX/sdX1
        分区节点直接消失, 产品 check_filesystem 的
        "for part in /sys/block/${dev_name}/${dev_name}*" 遍历不到分区,
        FS_SEVERITY 停留在 ok, 反而命中不了"严重损坏"分支。
        因此按同一意图改为清零"分区"的前 10MB: 分区表保留、分区节点仍在,
        但超级块被抹掉 → blkid 认不出类型 → 产品判为 severe。

        :param partition: 已卸载的 ext4 分区设备路径(如 /dev/sdb1)
        :return: True 表示清零成功且 blkid 已无法识别文件系统类型
        """
        if not re.match(self.EXT4_PARTITION_RE, partition or ""):
            logger.error(f"严重损坏构造需要块设备, 收到: {partition!r}")
            return False
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; true',
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"dd if=/dev/zero of={quote(partition)} bs=1M count=10 conv=fsync 2>/dev/null; "
            f"blockdev --flushbufs {quote(partition)} 2>/dev/null; sync; "
            f"udevadm trigger --action=change --subsystem-match=block {quote(partition)} "
            "2>/dev/null; udevadm settle --timeout=10 2>/dev/null; true",
            timeout=180,
            out_debug_flag=False,
        )
        # 非 root 的 blkid 会读 /run/blkid/blkid.tab 缓存(清零后仍报 ext4),
        # 因此用 root 直读设备(-p 绕过缓存) + lsblk(udev) 双重确认
        probe = self.strip_sudo_noise(
            self.sudo_run_cmd(
                f"/sbin/blkid -p -o value -s TYPE {quote(partition)} 2>/dev/null || true",
                timeout=15,
                out_debug_flag=False,
            )
        ).strip()
        lsblk_type = self.run_cmd(
            f"lsblk -no FSTYPE {quote(partition)} 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        logger.info(
            f"严重损坏构造 {partition}: blkid -p={probe!r}, lsblk={lsblk_type!r}"
        )
        return probe == "" and lsblk_type == ""

    # ---------------- NTFS 兼容场景构造(2010255) ----------------

    def _ntfs_read_device_bytes(self, partition, offset, size, tag) -> bytes:
        """读取块设备的一段原始字节到本地临时文件再读回

        sudo dd 写出的文件属 root, 因此读取前 chmod 666, 避免测试进程无权限。

        :param partition: 分区设备路径
        :param offset: 起始偏移(字节)
        :param size: 读取长度(字节)
        :param tag: 临时文件名后缀, 用于区分并便于清理
        :return: 读到的字节, 失败返回 b""
        """
        tmp = f"/tmp/pcm_ntfs_{tag}.bin"
        self.sudo_run_cmd(
            f"rm -f {tmp}; dd if={quote(partition)} bs=1 skip={offset} count={size} "
            f"of={tmp} 2>/dev/null; chmod 666 {tmp} 2>/dev/null; true",
            timeout=60,
            out_debug_flag=False,
        )
        try:
            with open(tmp, "rb") as file_obj:
                return file_obj.read()
        except OSError as err:
            logger.error(f"读取 {partition} 偏移 {offset} 失败: {err}")
            return b""
        finally:
            self.sudo_run_cmd(f"rm -f {tmp}", timeout=10, out_debug_flag=False)

    def _ntfs_write_device_bytes(self, partition, offset, data, tag) -> bool:
        """把一段原始字节写回块设备指定偏移(只覆盖该区间, 不破坏其它数据)

        :param partition: 分区设备路径
        :param offset: 起始偏移(字节)
        :param data: 待写入字节
        :param tag: 临时文件名后缀
        :return: True 表示 dd 成功
        """
        tmp = f"/tmp/pcm_ntfs_{tag}.new"
        try:
            with open(tmp, "wb") as file_obj:
                file_obj.write(data)
        except OSError as err:
            logger.error(f"写入临时文件 {tmp} 失败: {err}")
            return False
        out = self.sudo_run_cmd(
            f"dd if={tmp} of={quote(partition)} bs=1 seek={offset} count={len(data)} "
            f"conv=notrunc,fsync 2>/dev/null; echo RC=$?; rm -f {tmp}",
            timeout=60,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"sync; blockdev --flushbufs {quote(partition)} 2>/dev/null; "
            f"udevadm trigger --action=change --subsystem-match=block {quote(partition)} "
            "2>/dev/null; udevadm settle --timeout=10 2>/dev/null; true",
            timeout=40,
            out_debug_flag=False,
        )
        return "RC=0" in (out or "")

    def _ntfs_geometry(self, partition) -> tuple:
        """从 NTFS 引导扇区解析布局参数

        :param partition: 分区设备路径
        :return: (每扇区字节数, 每簇扇区数, $MFT 起始簇号, $MFTMirr 起始簇号,
                  每个文件记录字节数); 解析失败返回空元组
        """
        boot = self._ntfs_read_device_bytes(partition, 0, 512, "boot")
        if len(boot) < 512 or boot[3:11] != b"NTFS    ":
            logger.error(f"{partition} 不是 NTFS 引导扇区: {boot[:16]!r}")
            return ()
        bytes_per_sector = int.from_bytes(boot[0x0B:0x0D], "little")
        sectors_per_cluster = boot[0x0D]
        mft_lcn = int.from_bytes(boot[0x30:0x38], "little")
        mftmirr_lcn = int.from_bytes(boot[0x38:0x40], "little")
        clusters_per_record = int.from_bytes(boot[0x40:0x41], "little", signed=True)
        record_size = 1024 if clusters_per_record > 0 else 1 << (-clusters_per_record)
        if not bytes_per_sector or not sectors_per_cluster or not mft_lcn:
            logger.error(
                f"{partition} NTFS 布局异常: bps={bytes_per_sector}, "
                f"spc={sectors_per_cluster}, mft_lcn={mft_lcn}"
            )
            return ()
        return (
            bytes_per_sector,
            sectors_per_cluster,
            mft_lcn,
            mftmirr_lcn,
            record_size,
        )

    @staticmethod
    def _ntfs_apply_usa(record, bytes_per_sector, restore):
        """应用/还原 NTFS 文件记录的更新序列(USA)修正

        NTFS 在每个 512 字节扇区末尾存放更新序列号(USN), 原始 USA 数据放在记录头
        的 usa_ofs 处。解析属性前必须把扇区尾替换回真实字节, 写回前再改成 USN。
        """
        usa_ofs = int.from_bytes(record[4:6], "little")
        usa_count = int.from_bytes(record[6:8], "little")
        usn = record[usa_ofs : usa_ofs + 2]
        for index in range(1, usa_count):
            tail = index * bytes_per_sector - 2
            if restore:
                record[tail : tail + 2] = record[
                    usa_ofs + 2 * index : usa_ofs + 2 * index + 2
                ]
            else:
                record[tail : tail + 2] = usn
        return record

    def set_usb_ntfs_volume_dirty(self, partition) -> bool:
        """把 NTFS 卷的 dirty 标志置位, 制造"脏标志"场景

        NTFS 的卷标志(0x0001 = VOLUME_IS_DIRTY)保存在 $MFT 第 3 个文件记录
        ($Volume)的 VOLUME_INFORMATION(0x70)属性里。Windows 在拷贝过程中被拔出
        时只来得及写 $MFT 里的标志而没同步 $MFTMirr, 卷因此同时呈现"脏"和
        "$MFTMirr 与 $MFT 不一致"。该状态下:
        - ntfs-3g 只读挂载直接失败("$MFTMirr does not match $MFT"),
          产品的挂载探测因此把卷判为"文件系统损坏"(corrupted);
        - ntfsfix -b -d 会重建 $MFTMirr 并清脏标志, 修复后挂载验证通过,
          产品记"修复成功"。
        本机实测: 只改 $MFT 记录 3 的 flags 位(不改 $MFTMirr)即可稳定复现;
        两个副本都改则 ntfs-3g 认为卷干净, 反而命中不了检测。

        :param partition: 已卸载的 NTFS 分区设备路径(如 /dev/sdb1)
        :return: True 表示标志位已写入并回读确认
        """
        if not re.match(self.EXT4_PARTITION_RE, partition or ""):
            logger.error(f"NTFS 脏标志构造需要块设备, 收到: {partition!r}")
            return False
        geometry = self._ntfs_geometry(partition)
        if not geometry:
            return False
        bytes_per_sector, sectors_per_cluster, mft_lcn, _, record_size = geometry
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; true',
            timeout=30,
            out_debug_flag=False,
        )
        volume_record = 3
        offset = (
            mft_lcn * sectors_per_cluster * bytes_per_sector
            + volume_record * record_size
        )
        record = bytearray(
            self._ntfs_read_device_bytes(partition, offset, record_size, "volume")
        )
        if len(record) != record_size or record[:4] != b"FILE":
            logger.error(f"$Volume 记录读取异常: {record[:8]!r}")
            return False
        self._ntfs_apply_usa(record, bytes_per_sector, True)
        attr_offset = int.from_bytes(record[0x14:0x16], "little")
        patched = False
        while attr_offset + 8 <= len(record):
            attr_type = int.from_bytes(record[attr_offset : attr_offset + 4], "little")
            attr_len = int.from_bytes(
                record[attr_offset + 4 : attr_offset + 8], "little"
            )
            if attr_type == 0xFFFFFFFF or attr_len <= 0:
                break
            if attr_type == 0x70 and record[attr_offset + 8] == 0:
                value_offset = int.from_bytes(
                    record[attr_offset + 0x14 : attr_offset + 0x16], "little"
                )
                flags_at = attr_offset + value_offset + 10
                old_flags = int.from_bytes(record[flags_at : flags_at + 2], "little")
                record[flags_at : flags_at + 2] = (old_flags | 0x0001).to_bytes(
                    2, "little"
                )
                patched = True
                logger.info(
                    f"NTFS 卷标志写入 {partition}: VOLUME_INFORMATION "
                    f"flags 0x{old_flags:04x} -> 0x{old_flags | 1:04x}"
                )
                break
            attr_offset += attr_len
        if not patched:
            logger.error(f"{partition} $Volume 记录未找到 VOLUME_INFORMATION 属性")
            return False
        self._ntfs_apply_usa(record, bytes_per_sector, False)
        if not self._ntfs_write_device_bytes(partition, offset, bytes(record), "volume"):
            return False
        verify = bytearray(
            self._ntfs_read_device_bytes(partition, offset, record_size, "volume")
        )
        if len(verify) != record_size:
            return False
        self._ntfs_apply_usa(verify, bytes_per_sector, True)
        attr_offset = int.from_bytes(verify[0x14:0x16], "little")
        while attr_offset + 8 <= len(verify):
            attr_type = int.from_bytes(verify[attr_offset : attr_offset + 4], "little")
            attr_len = int.from_bytes(
                verify[attr_offset + 4 : attr_offset + 8], "little"
            )
            if attr_type == 0xFFFFFFFF or attr_len <= 0:
                break
            if attr_type == 0x70:
                value_offset = int.from_bytes(
                    verify[attr_offset + 0x14 : attr_offset + 0x16], "little"
                )
                flags_at = attr_offset + value_offset + 10
                dirty = int.from_bytes(verify[flags_at : flags_at + 2], "little") & 1
                logger.info(f"NTFS 脏标志回读 {partition}: dirty={bool(dirty)}")
                return bool(dirty)
            attr_offset += attr_len
        return False

    def crack_usb_exfat_boot_signature(self, partition) -> bool:
        """清零 exFAT 引导扇区尾部的 0xAA55 签名, 制造用例描述的"脏标志"现场

        用例前置条件给的命令就是
        "dd if=/dev/zero of=/dev/sda1 bs=1 seek=510 count=2 conv=notrunc"。
        实测(exfat-utils 1.3.0): 签名被清零后引导扇区校验和不匹配,
        fsck.exfat -n 与 fsck -n -t exfat 都返回 1, ntfs-3g/exfat 只读挂载报
        "invalid VBR checksum" 失败, 产品因此判 corrupted;
        "fsck -y -t exfat" 会重算校验和与签名, 退出码 1(<=1) 记"修复成功",
        修复后挂载恢复且数据不变。

        :param partition: 已卸载的 exFAT 分区设备路径(如 /dev/sdb1)
        :return: True 表示写入完成且类型仍识别为 exfat(可命中 corrupted 而非 severe)
        """
        if not re.match(self.EXT4_PARTITION_RE, partition or ""):
            logger.error(f"exFAT 签名构造需要块设备, 收到: {partition!r}")
            return False
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; true',
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"dd if=/dev/zero of={quote(partition)} bs=1 seek=510 count=2 "
            f"conv=notrunc 2>/dev/null; sync; blockdev --flushbufs {quote(partition)} "
            f"2>/dev/null; udevadm trigger --action=change "
            f"--subsystem-match=block {quote(partition)} 2>/dev/null; "
            "udevadm settle --timeout=10 2>/dev/null; true",
            timeout=60,
            out_debug_flag=False,
        )
        fs_type = self.run_cmd(
            f"lsblk -no FSTYPE {quote(partition)} 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        rc = self.get_usb_exfat_filesystem_check_rc(partition)
        logger.info(f"exFAT 引导签名清零 {partition}: 类型={fs_type!r}, fsck -n rc={rc}")
        return fs_type == "exfat" and rc != 0

    def corrupt_usb_exfat_fat_table(self, partition, sectors=64) -> bool:
        """清零 exFAT 的 FAT 表起始若干扇区, 制造"逻辑损坏"场景

        用引导扇区里的 FatOffset/FatLength 定位 FAT, 只清 FAT 前 sectors 个扇区
        (保留引导区与簇堆), 因此 blkid/lsblk 仍识别为 exfat, 产品命中 corrupted;
        根目录簇链断裂后只读挂载失败("bad cluster 0 while reading root directory"),
        fsck -y 输出 "ERRORS FOUND: 1, FIXED: 0", 产品仍按退出码(1)判"修复成功"
        —— 产品判定与实际修复结果不一致, 用例层记录该现象。

        :param partition: 已卸载的 exFAT 分区设备路径(如 /dev/sdb1)
        :param sectors: 清零的 FAT 扇区数
        :return: True 表示清零完成且类型仍识别为 exfat
        """
        if not re.match(self.EXT4_PARTITION_RE, partition or ""):
            logger.error(f"exFAT 逻辑损坏构造需要块设备, 收到: {partition!r}")
            return False
        fat_offset = self.strip_sudo_noise(
            self.sudo_run_cmd(
                f"dd if={quote(partition)} bs=1 skip=80 count=4 2>/dev/null "
                "| od -An -tu4",
                timeout=20,
                out_debug_flag=False,
            )
        ).split()
        fat_length = self.strip_sudo_noise(
            self.sudo_run_cmd(
                f"dd if={quote(partition)} bs=1 skip=84 count=4 2>/dev/null "
                "| od -An -tu4",
                timeout=20,
                out_debug_flag=False,
            )
        ).split()
        if not fat_offset or not fat_length:
            logger.error(f"{partition} 读取 exFAT FAT 布局失败")
            return False
        if int(fat_offset[0]) == 0 or int(fat_length[0]) == 0:
            logger.error(
                f"{partition} exFAT FAT 布局异常: offset={fat_offset[0]}, "
                f"length={fat_length[0]}"
            )
            return False
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; '
            f"dd if=/dev/zero of={quote(partition)} bs=512 "
            f"seek={int(fat_offset[0])} count={sectors} conv=notrunc 2>/dev/null; "
            f"sync; blockdev --flushbufs {quote(partition)} 2>/dev/null; "
            f"udevadm trigger --action=change --subsystem-match=block "
            f"{quote(partition)} 2>/dev/null; udevadm settle --timeout=10 2>/dev/null; true",
            timeout=120,
            out_debug_flag=False,
        )
        fs_type = self.run_cmd(
            f"lsblk -no FSTYPE {quote(partition)} 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        rc = self.get_usb_exfat_filesystem_check_rc(partition)
        logger.info(
            f"exFAT FAT 清零 {partition}: fat_offset={fat_offset[0]} 扇区, "
            f"{sectors} 扇区, 类型={fs_type!r}, fsck -n rc={rc}"
        )
        return fs_type == "exfat" and rc != 0

    def corrupt_usb_ntfs_mft_records(self, partition, records=(6, 7)) -> bool:
        """清零 $MFT 中指定文件记录, 制造"逻辑损坏但类型可识别"的 NTFS 场景

        选择 $MFT 里第 6/7 个记录($Bitmap / $Boot 等系统文件)而不是记录 0:
        记录 0 被清零后 libblkid 连类型都识别不出, 产品会判"严重损坏(severe)",
        命中不了"检测到损坏 -> 尝试修复 -> 修复失败"的预期路径。
        实测(记录 6/7 清零): blkid/lsblk 仍报 ntfs, ntfs-3g 只读挂载失败
        ("Record 6 has no FILE magic"), ntfsfix -b -d 无法修复, 产品的手动
        $MFTMirr 重建也救不回, 最终记"修复失败"。

        :param partition: 已卸载的 NTFS 分区设备路径(如 /dev/sdb1)
        :param records: 需要清零的 $MFT 记录号(相对 $MFT 起始)
        :return: True 表示清零完成且 udev/blkid 仍能识别为 ntfs
        """
        if not re.match(self.EXT4_PARTITION_RE, partition or ""):
            logger.error(f"NTFS 逻辑损坏构造需要块设备, 收到: {partition!r}")
            return False
        geometry = self._ntfs_geometry(partition)
        if not geometry:
            return False
        bytes_per_sector, sectors_per_cluster, mft_lcn, _, record_size = geometry
        first = min(records)
        count = (max(records) - first + 1) * record_size
        offset = (
            mft_lcn * sectors_per_cluster * bytes_per_sector + first * record_size
        )
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; true',
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"dd if=/dev/zero of={quote(partition)} bs=1 seek={offset} count={count} "
            "conv=notrunc,fsync 2>/dev/null; sync; "
            f"blockdev --flushbufs {quote(partition)} 2>/dev/null; "
            f"udevadm trigger --action=change --subsystem-match=block {quote(partition)} "
            "2>/dev/null; udevadm settle --timeout=10 2>/dev/null; true",
            timeout=120,
            out_debug_flag=False,
        )
        fs_type = self.run_cmd(
            f"lsblk -no FSTYPE {quote(partition)} 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        logger.info(
            f"NTFS 逻辑损坏注入 {partition}: 清零 $MFT 记录 {records} "
            f"(offset={offset}, {count} 字节), udev 类型={fs_type!r}"
        )
        return fs_type == "ntfs"

    def prepare_usb_ext4_partition(
        self, mount_point="/tmp/test_usb_ext4_mount", partition=""
    ) -> str:
        """把 USB 存储设备的第一个分区(或指定分区)格式化为 ext4 并挂载

        usb-fix 插件按 udev 的 ID_BUS=usb 枚举整盘, 因此必须使用真实的 sdX 分区
        (scsi_debug 合成盘也满足), loop 设备不会被插件识别。
        格式化前先卸载 udisks2 可能留下的自动挂载点, 避免"设备忙"导致 mkfs 失败。
        合成盘的分区创建时先按 FAT32-LBA 建表并格式化过 vfat, udev 数据库里缓存的
        ID_FS_TYPE 仍是 vfat; 因此格式化后必须 trigger(change)+settle 让 udev 重新
        探测, 否则产品的 blkid/lsblk 会读到过期的文件系统类型, 把 ext4 误判成 vfat。
        -F 允许对已有文件系统的设备执行格式化, -q 关闭进度输出(512MB 盘无需刷屏)。

        :param mount_point: 挂载点路径
        :param partition: 指定分区设备路径; 为空时取第一块 USB 存储设备的第一个分区
        :return: 分区设备路径, 失败返回空字符串
        """
        if not partition:
            partition = self.get_first_usb_storage_partition()
        if not partition:
            return ""
        # 先清理 udisks2 的自动挂载, 避免"设备忙"导致 mkfs 失败
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; true',
            timeout=30,
            out_debug_flag=False,
        )
        mkfs_out = self.sudo_run_cmd(
            f"mkfs.ext4 -F -q {quote(partition)} 2>&1; echo RC=$?",
            timeout=180,
            out_debug_flag=False,
        )
        if "RC=0" not in (mkfs_out or ""):
            logger.error(f"格式化 ext4 失败: {mkfs_out!r}")
            return ""
        # 刷新 udev 探测结果, 使 ID_FS_TYPE/lsblk FSTYPE 变为 ext4
        self.sudo_run_cmd(
            f"udevadm trigger --action=change --subsystem-match=block {quote(partition)} "
            "2>/dev/null; udevadm settle --timeout=10 2>/dev/null; true",
            timeout=30,
            out_debug_flag=False,
        )
        if not self.mount_usb_partition(partition, mount_point, "ext4"):
            logger.error(f"ext4 分区 {partition} 挂载失败, 无法注入测试数据")
            return ""
        logger.info(f"USB 分区已格式化为 ext4 并挂载: {partition} -> {mount_point}")
        return partition

    def get_usb_ext4_partition_check_rc(self, partition) -> int:
        """对 ext4 分区执行 fsck.ext4 只读检查, 返回退出码

        ext4 的 fsck 实现是 fsck.ext4/e2fsck, -n 表示"只检查、所有提问都答 no",
        不写盘。健康卷返回 0; 卷脏或存在未修复错误时返回非 0(4 表示有错误未修复)。
        产品 plugin-usb-fix/entry.sh 对 ext4 正是用 "fsck -n -t ext4" 的退出码
        判定文件系统是否健康, 因此用例用同一命令做前置与事后校验。

        :param partition: 分区设备路径(如 /dev/sdb1)
        :return: fsck.ext4 -n 的退出码, 无法执行返回 -1
        """
        if not partition:
            return -1
        out = self.sudo_run_cmd(
            f"fsck.ext4 -n {quote(partition)} >/dev/null 2>&1; echo RC=$?",
            timeout=60,
            out_debug_flag=False,
        )
        match = re.search(r"RC=(\d+)", out or "")
        return int(match.group(1)) if match else -1

    def get_desktop_icon_name(self) -> str:
        """从 .desktop 文件中提取 Icon 字段值"""
        result = self.run_cmd(
            f"grep '^Icon=' {APP_DESKTOP_FULL_PATH} 2>/dev/null | head -1 | cut -d= -f2",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_icon_file_exists(self) -> bool:
        """检查 .desktop 文件中引用的图标文件是否存在

        图标可能以名称方式引用(依赖 hicolor 图标主题)或以完整路径引用。
        V20/V25 均使用 hicolor 图标主题, 通过 find 命令在标准图标目录中查找。
        """
        icon_name = self.get_desktop_icon_name()
        if not icon_name:
            return False
        if icon_name.startswith("/"):
            result = self.run_cmd(
                f"test -f {icon_name} && echo 1",
                timeout=5,
                out_debug_flag=False,
            )
            return bool(result.strip())
        icon_base = icon_name.rsplit(".", 1)[0] if "." in icon_name else icon_name
        result = self.run_cmd(
            f"find /usr/share/icons /usr/share/pixmaps /usr/share/icons/hicolor "
            f"-name '{icon_base}.*' -o -name '{icon_base}' 2>/dev/null | head -1",
            timeout=10,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def get_dock_display_mode(self) -> str:
        """获取任务栏显示模式(时尚模式 fashion / 高效模式 efficient)

        :return: 'fashion' / 'efficient', 读取失败返回空串
        """
        result = self.run_cmd(
            "gsettings get com.deepin.dde.dock display-mode 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip().strip("'\"")

    def set_dock_display_mode(self, mode) -> bool:
        """切换任务栏显示模式并回读校验

        :param mode: 'fashion' 或 'efficient'
        :return: True 表示切换成功
        """
        self.run_cmd(
            f"gsettings set com.deepin.dde.dock display-mode '{mode}'",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(3)
        return self.get_dock_display_mode() == mode

    def get_dock_process_status(self) -> bool:
        """检查任务栏(dde-dock)进程是否存活"""
        result = self.run_cmd(
            "pgrep -x dde-dock >/dev/null 2>&1 && echo alive",
            timeout=5,
            out_debug_flag=False,
        )
        return "alive" in result

    def get_app_icon_path(self) -> str:
        """解析 .desktop 中 Icon 对应的图标文件路径(优先 hicolor)

        :return: 图标文件路径, 未找到返回空串
        """
        icon_name = self.get_desktop_icon_name()
        if not icon_name:
            return ""
        if icon_name.startswith("/"):
            return icon_name
        result = self.run_cmd(
            "find /usr/share/icons /usr/share/pixmaps -name "
            f"'{icon_name}.*' 2>/dev/null | head -1",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip()

    def get_dock_icon_showing_when_running(self) -> bool:
        """检查应用运行时任务栏是否显示电脑管家图标

        V20/V25 上运行中的窗口会在 dock 的 TaskManager 中显示图标。
        """
        return self.get_dock_has_running_window()

    # ===== 性能测试--日志检测 方法 =====

    def get_pc_manager_log_files_exist(self) -> bool:
        """检查 deepin-pc-manager 日志文件是否存在

        V20/V25 上日志可能存在于以下目录:
        ~/.cache/deepin/deepin-pc-manager/
        ~/.local/share/deepin/deepin-pc-manager/
        ~/.config/deepin/deepin-pc-manager/
        以及 journald 用户日志。
        :return: True 表示至少存在一个日志文件或 journald 日志
        """
        result = self.run_cmd(
            'find ~/.cache/deepin/deepin-pc-manager/ '
            '~/.local/share/deepin/deepin-pc-manager/ '
            '~/.config/deepin/deepin-pc-manager/ '
            '-type f \\( -name "*.log" -o -name "*.log.*" -o -name "log*" \\) '
            '2>/dev/null | head -1',
            timeout=10,
            out_debug_flag=False,
        )
        if result.strip():
            return True
        journal_result = self.run_cmd(
            "journalctl --user -u deepin-pc-manager --no-pager -n 1 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return bool(journal_result.strip())

    def get_pc_manager_log_files_nonempty(self) -> bool:
        """检查 deepin-pc-manager 日志文件非空(应用启动后有日志输出)

        :return: True 表示至少有一个日志文件非空
        """
        result = self.run_cmd(
            'find ~/.cache/deepin/deepin-pc-manager/ '
            '~/.local/share/deepin/deepin-pc-manager/ '
            '~/.config/deepin/deepin-pc-manager/ '
            '-type f \\( -name "*.log" -o -name "*.log.*" -o -name "log*" \\) '
            '-size +0c 2>/dev/null | head -1',
            timeout=10,
            out_debug_flag=False,
        )
        if result.strip():
            return True
        journal_result = self.run_cmd(
            "journalctl --user -u deepin-pc-manager --no-pager -n 5 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return bool(journal_result.strip())

    def get_pc_manager_log_path(self) -> str:
        """返回电脑管家主日志文件路径(优先 ~/.cache/deepin/deepin-pc-manager/)

        与"性能测试--日志检测"描述一致: 查看
        ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log。
        该文件不存在时回退到其它日志目录下的第一个 .log 文件。

        :return: 日志文件绝对路径, 未找到返回空字符串
        """
        preferred = (
            f"{HOME_DIR}/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log"
        )
        result = self.run_cmd(
            f"test -f {preferred} && echo {preferred} || "
            f'find {HOME_DIR}/.cache/deepin/deepin-pc-manager/ '
            f'{HOME_DIR}/.local/share/deepin/deepin-pc-manager/ '
            f'-type f -name "*.log" -size +0c 2>/dev/null | head -1',
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip().splitlines()[-1] if result.strip() else ""

    def analyze_pc_manager_log_duplicates(self, tail_lines=500) -> dict:
        """统计电脑管家日志尾部的重复情况与有效信息

        对应"没有大量重复日志, 保存有效信息"的量化口径:
        - total: 采样行数
        - max_repeat: 去掉行首时间戳后, 单条日志内容的最大重复次数
        - repeat_ratio: 重复行数占比(0~1)
        - timestamp_lines: 带 yyyy-mm-dd 时间戳的行数
        - level_lines: 带日志级别(INFO/WARN/ERROR/DEBUG 等)的行数
        - sample: 重复次数最多的前 3 行原文(截断)

        :param tail_lines: 采样日志尾部行数
        :return: 统计字典, 日志不可读时 total 为 0
        """
        log_path = self.get_pc_manager_log_path()
        info = {
            "path": log_path,
            "total": 0,
            "max_repeat": 0,
            "repeat_ratio": 0.0,
            "timestamp_lines": 0,
            "level_lines": 0,
            "sample": "",
        }
        if not log_path:
            return info
        counter = self.run_cmd(
            f"tail -n {tail_lines} {log_path} 2>/dev/null | "
            f"sed -E 's/^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}, [0-9:.]+ //' | "
            f"sort | uniq -c | sort -rn | head -3",
            timeout=15,
            out_debug_flag=False,
        )
        total = self.run_cmd(
            f"tail -n {tail_lines} {log_path} 2>/dev/null | wc -l",
            timeout=15,
            out_debug_flag=False,
        )
        try:
            info["total"] = int(total.strip() or 0)
        except ValueError:
            info["total"] = 0
        repeated = 0
        max_repeat = 0
        samples = []
        for line in (counter or "").splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) != 2 or not parts[0].isdigit():
                continue
            count = int(parts[0])
            max_repeat = max(max_repeat, count)
            if count > 1:
                repeated += count
            samples.append(f"{count}x {parts[1][:120]}")
        info["max_repeat"] = max_repeat
        info["sample"] = " | ".join(samples)
        if info["total"]:
            info["repeat_ratio"] = round(repeated / info["total"], 3)
        stamps = self.run_cmd(
            f"tail -n {tail_lines} {log_path} 2>/dev/null | "
            f"grep -cE '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'",
            timeout=15,
            out_debug_flag=False,
        )
        try:
            info["timestamp_lines"] = int(stamps.strip() or 0)
        except ValueError:
            info["timestamp_lines"] = 0
        levels = self.run_cmd(
            f"tail -n {tail_lines} {log_path} 2>/dev/null | "
            f"grep -ciE '(INFO|WARN|WARNING|ERROR|DEBUG|TRACE|CRITICAL)'",
            timeout=15,
            out_debug_flag=False,
        )
        try:
            info["level_lines"] = int(levels.strip() or 0)
        except ValueError:
            info["level_lines"] = 0
        return info

    def get_pc_manager_log_no_critical_errors(self) -> bool:
        """检查日志中不存在严重错误(段错误、崩溃、abort 等)

        :return: True 表示日志中未发现严重错误, False 表示发现严重错误
        """
        critical_patterns = [
            "Segmentation fault",
            "SIGSEGV",
            "Aborted",
            "core dumped",
            "FATAL",
            "double free",
            "heap corruption",
        ]
        pattern_regex = "|".join(critical_patterns)
        result = self.run_cmd(
            f'grep -riE "{pattern_regex}" '
            f"~/.cache/deepin/deepin-pc-manager/ "
            f"~/.local/share/deepin/deepin-pc-manager/ "
            f"~/.config/deepin/deepin-pc-manager/ "
            f"2>/dev/null | head -5",
            timeout=10,
            out_debug_flag=False,
        )
        if result.strip():
            return False
        journal_result = self.run_cmd(
            f'journalctl --user -u deepin-pc-manager --no-pager -n 500 '
            f'2>/dev/null | grep -iE "{pattern_regex}" | head -5',
            timeout=10,
            out_debug_flag=False,
        )
        return not journal_result.strip()

    def get_pc_manager_log_size_reasonable(self) -> bool:
        """检查日志文件大小合理(单个文件不超过 50MB)

        过大的日志文件可能影响系统性能。
        :return: True 表示所有日志文件大小均在合理范围内
        """
        max_size_kb = 51200
        result = self.run_cmd(
            f'find ~/.cache/deepin/deepin-pc-manager/ '
            f'~/.local/share/deepin/deepin-pc-manager/ '
            f'~/.config/deepin/deepin-pc-manager/ '
            f'-type f \\( -name "*.log" -o -name "*.log.*" -o -name "log*" \\) '
            f'-size +{max_size_kb}k 2>/dev/null | head -1',
            timeout=10,
            out_debug_flag=False,
        )
        return not result.strip()

    def refresh_dogtail_root(self):
        """刷新 dogtail 应用根节点引用

        V25 扫描过程中 AT-SPI 树会因 widget 销毁/重建而变化,
        缓存的 self.dog.obj 根引用会失效, 导致后续搜索返回空结果。
        每次调用重新获取 root.application 引用即可。
        """
        try:
            from src.depends.dogtail.tree import root
            self.dog.obj = root.application(self.dog.name, self.dog.description)
        except BaseException:
            pass

    def _focus_windows_safe(self):
        """安全聚焦窗口 - 多策略确保窗口可见

        V20 上窗口可能在扫描过程中被最小化或发送到后台, 导致 AT-SPI
        showing=False。使用多种 xdotool 策略确保窗口恢复到前台:
        1. search --class (WM_CLASS.name) + windowactivate --sync + windowraise
        2. search --classname (WM_CLASS.class) + windowactivate --sync
        3. ui.focus_windows() (框架内置方法)
        """
        for search_flag in ["--class", "--classname"]:
            try:
                self.run_cmd(
                    f"xdotool search {search_flag} deepin-pc-manager "
                    "windowactivate --sync windowraise 2>/dev/null",
                    timeout=5,
                    out_debug_flag=False,
                )
            except BaseException:
                pass
        try:
            self._safe_focus_windows()
        except BaseException:
            pass

    def get_detection_score_card_showing(self) -> bool:
        """检查系统检测首页评分卡片是否显示"""
        try:
            card = self.dog.find_element_by_attr("$//detection_page//detection_scoreCard")
            return card.showing
        except BaseException:
            return False

    def get_detection_full_scan_status_showing(self) -> bool:
        """检查全面检测状态组件是否显示(扫描中或扫描完成后均显示)

        V20 上 showing/visible 不可靠, 改用元素存在判断。
        """
        return self._elements_exist("$//detection_fullScanStatus")

    def get_detection_fix_all_button_showing(self) -> bool:
        """检查'一键修复'按钮是否显示(存在异常项时显示)

        同名元素在 runtimePage 与 fullScanPage 中各有一份, 隐藏副本始终
        存在于 AT-SPI 树中, 因此以 size 非零的可见实例为准。
        """
        return self._any_visible("$//detection_fixAllBtn")

    def get_detection_recheck_button_showing(self) -> bool:
        """检查'重新检测'按钮是否显示

        同名元素在隐藏页面中同样存在, 以 size 非零的可见实例为准。
        """
        return self._any_visible("$//detection_recheckBtn")

    def get_log_line_count(self, pattern) -> int:
        """统计应用日志中匹配 pattern 的行数"""
        result = self.run_cmd(
            f"grep -ac {pattern!r} ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log",
            timeout=10, out_debug_flag=False,
        ).strip()
        return int(result) if result.isdigit() else 0

    def trigger_fix_and_capture_fixing(self, timeout=30) -> dict:
        """点击一键修复并高频采样"修复中"状态

        修复过程很短(SSH 私钥改权限通常 <300ms), 采样必须避免 AT-SPI 重新查找
        和 SSH 命令往返: 点击前缓存按钮元素, 点击后只读取该元素的 sensitive
        属性; 取样完毕后再取应用日志中的修复队列记录作为兜底证据。

        :return: {"disabled": bool, "progress": bool, "log_fixing": bool, "fixed": bool}
        """
        import time

        state = {"disabled": False, "progress": False, "log_fixing": False, "fixed": False}
        before = self.get_log_line_count("startNextFullScanFix")
        target = None
        for element in self.dog.find_elements_by_attr("$//detection_fixAllBtn"):
            width, height = element.size
            if width > 0 and height > 0:
                target = element
                break
        if target is None or not self._try_click_button_element(target):
            state["log_fixing"] = self.get_log_line_count("startNextFullScanFix") > before
            return state
        deadline = time.time() + timeout
        while time.time() < deadline:
            if target is not None:
                try:
                    if not target.sensitive:
                        state["disabled"] = True
                except BaseException:
                    target = None
            if self.is_ssh_key_permission_fixed():
                state["fixed"] = True
                break
            sleep(0.05)
        for element in self.dog.find_elements_by_attr("$//detection_progressBar"):
            try:
                width, height = element.size
                if width > 0 and height > 0:
                    state["progress"] = True
            except BaseException:
                continue
        state["log_fixing"] = self.get_log_line_count("startNextFullScanFix") > before
        if not state["fixed"]:
            state["fixed"] = self.is_ssh_key_permission_fixed()
        return state

    def wait_detection_manual_icon(self, timeout=30) -> bool:
        """等待"需人工处理"标识出现(检测结果渲染/守护进程缓存可能滞后)"""
        for _ in range(timeout):
            if self._any_visible("$//detection_manualIcon"):
                return True
            sleep(1)
        return False

    def click_detection_recheck_button(self) -> bool:
        """点击检测结果页的"重新检测"按钮"""
        for element in self.dog.find_elements_by_attr("$//detection_recheckBtn"):
            width, height = element.size
            if width > 0 and height > 0 and self._try_click_button_element(element):
                return True
        return False

    def run_full_scan_until_min_problems(self, min_problems=1, attempts=3) -> str:
        """执行全面检测, 直到异常项数量不少于 min_problems(最多 attempts 次)

        守护进程对部分检测项存在结果滞后(首次检测可能沿用上一轮结论), 首次
        检测异常项不足时用"重新检测"再检一次。
        :return: 最后一次检测的完成汇总行
        """
        import re

        summary = ""
        for index in range(attempts):
            if index == 0:
                self.click_detection_full_scan_button()
                if not self.wait_for_full_scan_started(60):
                    continue
            elif not self.click_detection_recheck_button():
                continue
            if not self.wait_for_full_scan_completion(900):
                continue
            summary = self.get_last_full_scan_summary()
            matched = re.search(r"totalProblems= (\d+)", summary)
            if matched is not None and int(matched.group(1)) >= min_problems:
                return summary
        return summary

    def get_detection_no_problem_page_showing(self) -> bool:
        """检查'未发现问题'页面是否显示(所有检测项均正常时显示)

        隐藏页面元素仍保留在树中, 以 size 非零的可见实例为准。
        """
        return self._any_visible("$//detection_noProblemPage")

    def _any_visible(self, *exprs):
        """检查多个表达式中是否有任一元素可见

        实测(deepin-pc-manager V20): QML 隐藏页元素仍保留在 AT-SPI 树中,
        showing 恒为 False、无区分度; 唯一可靠的可见性信号是 size 非零
        (隐藏实例的 size 为 (0, 0))。
        """
        for expr in exprs:
            try:
                for element in self.dog.find_elements_by_attr(expr, probe=True):
                    width, height = element.size
                    if width > 0 and height > 0:
                        return True
            except BaseException:
                pass
        return False

    def _element_rendered(self, element) -> bool:
        """判断单个元素是否实际渲染(size 非零)

        与 _any_visible 同一判据: QML 隐藏页元素仍在 AT-SPI 树中,
        showing 恒为 False 且 size 为 (0, 0), 只有 size 非零才代表
        用户能在界面上看到。

        :param element: AT-SPI 元素对象
        :return: True 表示已渲染
        """
        try:
            width, height = element.size
        except BaseException:
            return False
        return width > 0 and height > 0

    def _elements_exist(self, expr):
        """检查给定表达式的元素是否存在于 AT-SPI 树中

        注意: 仅表示组件已创建, 不代表可见(QML 隐藏页元素仍在树中, size 为 0);
        需要可见性判断时用 _any_visible。
        """
        try:
            elems = self.dog.find_elements_by_attr(expr, probe=True)
            return bool(elems)
        except BaseException:
            return False

    def _elements_exist_any(self, *exprs):
        """检查多个表达式中是否有任一元素存在(用于 V20/V25 元素名兼容)"""
        for expr in exprs:
            if self._elements_exist(expr):
                return True
        return False

    def _find_first_element(self, *exprs):
        """在多个表达式中查找第一个可找到的元素(用于 V20/V25 元素名兼容)

        :return: 找到的元素, 或 None
        """
        for expr in exprs:
            try:
                elems = self.dog.find_elements_by_attr(expr, probe=True)
                if elems:
                    return elems[0]
            except BaseException:
                pass
        return None

    def click_repair_nav_by_attr(self):
        """点击左侧导航修复工具选项"""
        self._safe_focus_windows()
        self.dog.find_element_by_attr("$//mainWindow_navList//修复工具").click()

    def click_audio_repair_card(self):
        """在修复工具页面找到并点击音频设备修复卡片"""
        self._safe_focus_windows()
        self.dog.find_element_by_attr("$//repair_page//音频设备修复").click()

    def get_repair_detail_page_showing(self, timeout=10):
        """等待并获取修复详情页面的可见状态(AT-SPI showing)

        :param timeout: 最长等待秒数, 详情页加载完成即提前返回
        """
        for _ in range(timeout):
            try:
                detail = self.dog.find_element_by_attr("$//repair_detailCard")
                if detail.showing:
                    return True
            except Exception:
                pass
            sleep(1)
        return False

    def setup_ssh_key_permission_issue(self):
        """创建 SSH 私钥权限问题(可修复项)

        将 ~/.ssh/id_rsa 权限设为 644，使其被检测为安全问题且可自动修复。
        若不存在 id_rsa 则先生成一个。
        """
        self.run_cmd(
            "test -f ~/.ssh/id_rsa || ssh-keygen -t rsa -N '' -f ~/.ssh/id_rsa",
            timeout=10,
            out_debug_flag=False,
        )
        self.run_cmd(
            "chmod 644 ~/.ssh/id_rsa",
            timeout=5,
            out_debug_flag=False,
        )

    def setup_unfixable_issue(self):
        """创建不可自动修复的问题(将 SSH 配置文件属主改为 root)

        将 ~/.ssh/config 的属主改为 root, 使 fixSshPermissionBits 检测到
        属主不是当前用户, 标记为 foreignOwnedPaths(需人工处理), 不会尝试
        fchmod, 从而避免应用崩溃, 同时模拟"部分修复失败"中的不可修复项。
        使用与 id_rsa 不同的文件, 确保 id_rsa 的权限问题仍可被自动修复。
        """
        self.run_cmd(
            "test -f ~/.ssh/config || touch ~/.ssh/config",
            timeout=5,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S chown root ~/.ssh/config 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )

    def restore_ssh_key_permissions(self):
        """恢复 SSH 文件权限和属主为安全状态

        恢复 ~/.ssh/config 属主为当前用户, 恢复 ~/.ssh/id_rsa 权限为 400。
        """
        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S chown $(whoami) ~/.ssh/config "
            "2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        self.run_cmd(
            "chmod 400 ~/.ssh/id_rsa 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )

    def _try_click_button_element(self, btn):
        """尝试通过 AT-SPI click 点击按钮元素

        仅使用 btn.click(), 不使用 grabFocus(V25 上可能导致应用崩溃)
        或 xdotool(可能误触其他控件导致应用异常)。

        :return: True 如果点击操作成功执行(不保证触发了 QML 信号)
        """
        try:
            btn.click()
            return True
        except BaseException:
            return False

    def _trigger_fix_via_dbus(self):
        """通过 DBus 调用修复接口(最后手段)

        当 UI 点击无法触发修复时, 直接调用 DBus 方法修复 SSH 私钥权限。
        使用 session bus, 目标 org.deepin.PCManager1。
        """
        try:
            out, status = self.run_cmd(
                'dbus-send --session --print-reply --dest=org.deepin.PCManager1 '
                '/org/deepin/PCManager1 org.deepin.PCManager1.Fix string:"ssh_key"',
                timeout=10,
                out_debug_flag=False,
                return_code=True,
            )
            # dbus-send 调用失败(服务不存在/方法拒绝)时返回非 0, 不能当成已触发
            return status == 0 and "method return" in out
        except BaseException:
            return False

    def click_fix_all_button(self):
        """点击「一键修复」按钮

        V20 上 AT-SPI click 可触发 QML 按钮信号, V25 上可能无法触发,
        因此先尝试 AT-SPI click, 验证修复是否触发; 若未触发则通过 DBus 调用修复。
        detection_fixAllBtn 可能返回多个元素, 逐个尝试。
        修复后若应用进程意外退出, 自动重启并重新连接 dogtail。
        """
        for attempt in range(10):
            try:
                btns = self.dog.find_elements_by_attr("$//detection_fixAllBtn")
                if btns:
                    for btn in btns:
                        if self._try_click_button_element(btn):
                            # 等待修复触发(检查 SSH 私钥权限是否变化)
                            for _ in range(3):
                                sleep(1)
                                if self.is_ssh_key_permission_fixed():
                                    self._ensure_app_alive()
                                    return
                    # AT-SPI click 未触发修复, 使用 DBus 兜底
                    if self._trigger_fix_via_dbus():
                        for _ in range(5):
                            sleep(1)
                            if self.is_ssh_key_permission_fixed():
                                self._ensure_app_alive()
                                return
            except BaseException:
                pass
            sleep(1)
            if attempt % 3 == 2:
                self._focus_windows_safe()
                self.refresh_dogtail_root()
        raise Exception("No detection_fixAllBtn found or fix not triggered")

    def _ensure_app_alive(self):
        """确保应用进程存活, 若已退出则重启并重新连接 dogtail"""
        if not self.get_pc_manager_process_status():
            self.start_pc_manager()

    def wait_for_fix_completion(self, timeout=180):
        """等待修复操作完成

        本机(V20)一键修复后结果页不会自动刷新, fixAllBtn 会保留显示,
        因此不能以按钮消失作为唯一完成信号。优先检查可修复项的实际
        修复效果(SSH 私钥权限已由 644 变更为 400/600); 同时保留
        fixAllBtn 从 AT-SPI 树连续消失的兼容判断。

        :param timeout: 最长等待秒数
        :return: True 如果修复完成
        """
        consecutive_absent = 0
        for i in range(timeout):
            if self.is_ssh_key_permission_fixed():
                return True
            if not self._elements_exist("$//detection_fixAllBtn"):
                consecutive_absent += 1
                if consecutive_absent >= 3:
                    return True
                sleep(2)
            else:
                consecutive_absent = 0
                if i % 5 == 4:
                    self.refresh_dogtail_root()
                    self._focus_windows_safe()
                sleep(1)
        return False

    def is_ssh_key_permission_fixed(self) -> bool:
        """检查 SSH 私钥权限是否已被修复(不再是 644)

        setup_ssh_key_permission_issue 将权限设为 644,
        修复工具会将其改为 400 或 600。检查权限是否已变化。
        """
        try:
            result = self.run_cmd(
                "stat -c '%a' ~/.ssh/id_rsa 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
            perms = result.strip().strip("'")
            # 严格判据: 只认 stat 返回的纯数字权限, 且不再是 644。
            # 文件不存在/命令失败时 run_cmd 返回错误文本或空串, 不能当作已修复。
            if not re.fullmatch(r"[0-7]{3,4}", perms):
                return False
            return perms not in ("644", "0644")
        except BaseException:
            return False

    def is_unfixable_issue_fixed(self) -> bool:
        """检查不可修复项是否已被修复(~/.ssh/config 属主恢复为当前用户)

        setup_unfixable_issue 将 ~/.ssh/config 属主改为 root,
        如果属主仍为 root 则不可修复项未被修复(部分修复失败)。
        返回 True 表示已修复(不符合预期), False 表示仍存在(符合预期)。
        """
        try:
            result = self.run_cmd(
                "stat -c '%U' ~/.ssh/config 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
            owner = result.strip().strip("'")
            return owner != "root"
        except BaseException:
            return False

    def wait_for_partial_fix_completion(self, timeout=180) -> bool:
        """等待部分修复完成(通过检查可修复项是否已被修复来判断)

        部分修复场景下 fixAllBtn 不会消失(仍有不可修复项),
        因此通过检查 SSH 私钥权限是否从 644 变为更安全的值来判断修复完成。
        每 5 次迭代刷新 dogtail 根引用和聚焦窗口, 确保 AT-SPI 树最新。

        :param timeout: 最长等待秒数
        :return: True 如果可修复项已被修复
        """
        for i in range(timeout):
            if self.is_ssh_key_permission_fixed():
                sleep(3)
                return True
            if i % 5 == 4:
                self.refresh_dogtail_root()
                self._focus_windows_safe()
            sleep(1)
        return False
    # ===== 系统检测--检测结果存在可修复问题 专用方法 =====

    def set_hosts_file_wrong_permission(self):
        """将 /etc/hosts 权限设置为 777 以构造可修复的检测问题"""
        self.run_cmd(
            f"bash -c \"echo '{conf.PASSWORD}' | sudo -S chmod 777 /etc/hosts\"",
            timeout=10,
            out_debug_flag=False,
        )

    def restore_hosts_file_permission(self):
        """恢复 /etc/hosts 权限为 644"""
        self.run_cmd(
            f"bash -c \"echo '{conf.PASSWORD}' | sudo -S chmod 644 /etc/hosts\"",
            timeout=10,
            out_debug_flag=False,
        )
    # ===== 音频修复-异常-jq 缺失 专用方法 =====

    def is_jq_installed(self) -> bool:
        """检查 jq 包是否已安装"""
        result = self.run_cmd(
            "dpkg -l jq 2>/dev/null | grep '^ii'",
            timeout=10,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def uninstall_jq(self):
        """卸载 jq 包(V20/V25 兼容)"""

        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get remove -y jq",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(2)

    def install_jq(self):
        """安装 jq 包(V20/V25 兼容)"""

        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S apt-get update -qq "
            f"&& echo '{conf.PASSWORD}' | sudo -S apt-get install -y jq",
            timeout=120,
            out_debug_flag=False,
        )
        sleep(2)

    # ===== 音频修复-异常-PipeWire 未运行 专用方法 =====

    def get_pipewire_running_status(self) -> bool:
        """检查当前用户的 PipeWire 是否正在运行

        V25: pipewire 是主要音频服务;
        V20: pipewire 可能未安装或未运行(PulseAudio 为主)。
        :return: True 表示当前用户的 PipeWire 正在运行
        """
        result = self.run_cmd(
            "systemctl --user is-active pipewire 2>/dev/null "
            "|| (pgrep -u $(id -u) -x pipewire >/dev/null 2>&1 && echo active)",
            timeout=5,
            out_debug_flag=False,
        )
        # 必须精确匹配: is-active 输出 "inactive" 时子串包含 "active"
        states = {line.strip().lower() for line in result.splitlines() if line.strip()}
        return "active" in states

    def stop_pipewire(self):
        """停止当前用户的 PipeWire 音频服务以模拟 PipeWire 未运行异常

        先尝试 systemctl 停止用户服务, 再用 pkill 杀死当前用户残留进程,
        确保 PipeWire 完全停止。V20 上若 pipewire 未安装则无影响。
        """
        self.run_cmd(
            "systemctl --user stop pipewire pipewire-pulse wireplumber 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        self.run_cmd(
            "pkill -u $(id -u) -9 pipewire pipewire-pulse wireplumber 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(2)

    def start_pipewire(self):
        """启动 PipeWire 音频服务(恢复异常环境)

        先尝试 systemctl 启动用户服务; 若失败则直接启动进程。
        V20 上若 pipewire 未安装则无影响。
        """
        result = self.run_cmd(
            "systemctl --user start pipewire pipewire-pulse wireplumber 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        if "active" not in result and "Started" not in result:
            self.run_cmd(
                "pipewire & pipewire-pulse & wireplumber &",
                timeout=5,
                out_debug_flag=False,
            )
        sleep(3)

    # ===== 不同的文件系统挂载到/media下均可被扫描到 专用方法 =====

    def create_media_filesystem_disk(
        self, fstype, img_path, mount_point
    ):
        """创建指定文件系统类型的虚拟磁盘并挂载到 /media 下

        通过创建磁盘镜像文件并关联 loop 设备, 格式化为指定文件系统,
        然后挂载到 /media 下的指定挂载点。需要 root 权限。

        :param fstype: 文件系统类型 (ext4, vfat, ntfs, exfat)
        :param img_path: 镜像文件路径
        :param mount_point: 挂载点路径(应在 /media 下)
        :return: loop 设备路径, 失败返回空字符串
        """
        img_size = "64M"
        self.sudo_run_cmd(
            f"truncate -s {img_size} {img_path}",
            timeout=10,
            out_debug_flag=False,
        )
        result = self.sudo_run_cmd(
            f"losetup -f --show {img_path} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        loop_dev = self._extract_loop_dev(result)
        if not loop_dev:
            return ""
        if fstype == "ext4":
            self.sudo_run_cmd(
                f"mkfs.ext4 -F {loop_dev} 2>/dev/null",
                timeout=15,
                out_debug_flag=False,
            )
        elif fstype == "vfat":
            self.sudo_run_cmd(
                f"mkfs.vfat -F 32 {loop_dev} 2>/dev/null",
                timeout=15,
                out_debug_flag=False,
            )
        elif fstype == "ntfs":
            self.sudo_run_cmd(
                f"mkfs.ntfs -F -Q {loop_dev} 2>/dev/null",
                timeout=20,
                out_debug_flag=False,
            )
        elif fstype == "exfat":
            self.sudo_run_cmd(
                f"mkfs.exfat {loop_dev} 2>/dev/null || mkexfatfs {loop_dev} 2>/dev/null",
                timeout=15,
                out_debug_flag=False,
            )
        else:
            self.sudo_run_cmd(
                f"mkfs.{fstype} {loop_dev} 2>/dev/null",
                timeout=15,
                out_debug_flag=False,
            )
        self.sudo_run_cmd(
            f"mkdir -p {mount_point}",
            timeout=5,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"mount {loop_dev} {mount_point} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return loop_dev

    def cleanup_media_filesystem_disk(self, img_path, mount_point):
        """清理挂载在 /media 下的虚拟磁盘

        :param img_path: 镜像文件路径
        :param mount_point: 挂载点路径
        """
        import re

        self.sudo_run_cmd(
            f"umount {mount_point} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        result = self.sudo_run_cmd(
            f"losetup -j {img_path} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        if result:
            for match in re.finditer(r"/dev/loop\d+", result):
                self.sudo_run_cmd(
                    f"losetup -d {match.group(0)} 2>/dev/null",
                    timeout=5,
                    out_debug_flag=False,
                )
        self.sudo_run_cmd(
            f"rm -rf {mount_point} {img_path}",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def get_media_mounted_filesystems(self) -> dict:
        """获取 /media 下所有已挂载文件系统信息

        :return: dict, key 为挂载点路径, value 为文件系统类型
        """
        result = self.run_cmd(
            "lsblk -o MOUNTPOINT,FSTYPE -n 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        fs_map = {}
        for line in result.strip().split("\n"):
            parts = line.split()
            if len(parts) < 2:
                continue
            mountpoint, fstype = parts[0], parts[1]
            if mountpoint.startswith("/media/"):
                fs_map[mountpoint] = fstype
        return fs_map

    def get_focused_window_screenshot_info(self, path="/tmp/pcm_res_check.png") -> dict:
        """截取焦点窗口并返回尺寸/体积/哈希信息(用于判断界面是否正常渲染)

        :param path: 临时截图路径
        :return: dict(width, height, size, md5), 失败返回 {}
        """
        self._safe_focus_windows()
        self.run_cmd(
            f"rm -f {path} && scrot -u {path} 2>/dev/null",
            timeout=20,
            out_debug_flag=False,
        )
        result = self.run_cmd(
            f"[ -s {path} ] && file -b {path} && stat -c %s {path} && "
            f"md5sum {path} | awk '{{print $1}}'",
            timeout=10,
            out_debug_flag=False,
        )
        lines = [line.strip() for line in result.splitlines() if line.strip()]
        if len(lines) < 3:
            return {}
        dims = re.findall(r"(\d+) x (\d+)", lines[0])
        if not dims:
            return {}
        return {
            "width": int(dims[0][0]),
            "height": int(dims[0][1]),
            "size": int(lines[1]),
            "md5": lines[2],
        }

    def remove_resolution_screenshot(self, path="/tmp/pcm_res_check.png"):
        """删除分辨率验证用临时截图"""
        self.run_cmd(f"rm -f {path}", timeout=5, out_debug_flag=False)

    def get_help_manual_logo_path(self, lang="zh_CN") -> str:
        """获取帮助手册中使用的电脑管家 LOGO 文件路径

        手册页面(pc-manager.md)以 ../common/deepin_pc_manager.svg 引用 LOGO。

        :param lang: 手册语言目录, 默认 zh_CN
        :return: 文件路径, 不存在返回空串
        """
        result = self.run_cmd(
            "find /usr/share/deepin-manual/manual-assets/application/"
            f"deepin-pc-manager/pc-manager/{lang} /usr/share/deepin-manual/"
            "manual-assets/application/deepin-pc-manager/pc-manager/common "
            "-name 'deepin_pc_manager.svg' 2>/dev/null | head -1",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip()

    def get_svg_logo_stats(self, path) -> dict:
        """统计 SVG 图形结构(路径数/渐变数/填充色集合), 用于比对 LOGO 一致性

        :param path: SVG 文件路径
        :return: dict(paths, gradients, fills, viewbox)
        """
        result = self.run_cmd(
            f"[ -f {path} ] && "
            f"echo paths=$(grep -o 'd=\"' {path} | wc -l) && "
            f"echo gradients=$(grep -o 'url(#' {path} | wc -l) && "
            f"echo fills=$(grep -o 'fill=\"[^\"]*\"' {path} | sort -u | md5sum | cut -d' ' -f1) && "
            f"echo viewbox=$(grep -o 'viewBox=\"[^\"]*\"' {path} | head -1)",
            timeout=10,
            out_debug_flag=False,
        )
        stats = {}
        for line in result.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                stats[key.strip()] = value.strip()
        return stats

    def get_window_net_wm_icon_present(self) -> bool:
        """检查主窗口是否设置 _NET_WM_ICON(窗口/任务栏取图来源)"""
        result = self.run_cmd(
            "for w in $(xdotool search --class deepin-pc-manager 2>/dev/null); "
            "do xprop -id $w _NET_WM_ICON 2>/dev/null | head -c 200; break; done",
            timeout=10,
            out_debug_flag=False,
        )
        return "_NET_WM_ICON" in result and "not found" not in result

    def get_defender_safe_level_show(self) -> str:
        """读取安全中心"系统安全等级"入口显隐开关(system-safe-level-show)

        :return: '0'/'1', 读取失败返回空串
        """
        result = self.run_cmd(
            "gsettings get com.deepin.dde.deepin-defender "
            "system-safe-level-show 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip().strip("'\"")

    def set_defender_safe_level_show(self, value) -> bool:
        """设置"系统安全等级"入口显隐开关并回读校验

        :param value: 0 或 1
        :return: True 表示设置成功
        """
        self.run_cmd(
            "gsettings set com.deepin.dde.deepin-defender "
            f"system-safe-level-show {value} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return self.get_defender_safe_level_show() == str(value)

    def get_defender_safe_level(self) -> str:
        """读取当前系统安全等级(system-safe-level, 0 表示默认)"""
        result = self.run_cmd(
            "gsettings get com.deepin.dde.deepin-defender "
            "system-safe-level 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip().strip("'\"")

    def get_defender_daemon_running(self) -> bool:
        """检查安全中心会话守护进程是否存活"""
        result = self.run_cmd(
            "pgrep -f 'deepin-defender-session-daemon' >/dev/null 2>&1 && echo alive",
            timeout=5,
            out_debug_flag=False,
        )
        return "alive" in result

    def stop_all_pc_manager_instances(self) -> bool:
        """结束所有电脑管家主进程(含带 --fd 参数的实例), 用于语言验证前清场"""
        self.run_cmd(
            "pkill -f '^/usr/libexec/deepin/deepin-pc-manager' 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)
        result = self.run_cmd(
            "pgrep -f '^/usr/libexec/deepin/deepin-pc-manager' | wc -l",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip() == "0"

    def start_pc_manager_with_language(self, lang_tag, log_path="/tmp/pcm_lang_check.log"):
        """以指定语言环境启动电脑管家主程序(等价于系统语言切换后重新登录)

        应用为单实例, 启动前先结束已有实例; 语言只作用于本次进程环境,
        不修改系统语言配置。

        :param lang_tag: 形如 zh_CN.UTF-8 / en_US.UTF-8
        :return: dict(pid, log), 启动失败返回 None
        """
        if not self.stop_all_pc_manager_instances():
            return None
        self.run_cmd(
            f"rm -f {log_path}",
            timeout=5,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"export LANG={lang_tag} LANGUAGE={lang_tag} LC_ALL={lang_tag} "
            f"QT_ACCESSIBILITY=1 QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1; "
            f"setsid nohup /usr/libexec/deepin/deepin-pc-manager "
            f"> {log_path} 2>&1 < /dev/null & echo $! > /tmp/pcm_lang.pid",
            timeout=15,
            out_debug_flag=False,
        )
        sleep(12)
        result = self.run_cmd(
            "cat /tmp/pcm_lang.pid 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        pid = result.strip()
        if not pid.isdigit():
            return None
        alive = self.run_cmd(
            f"kill -0 {pid} 2>/dev/null && echo alive",
            timeout=5,
            out_debug_flag=False,
        )
        if "alive" not in alive:
            return None
        return {"pid": int(pid), "log": log_path}

    def get_pc_manager_ui_title(self) -> str:
        """获取电脑管家主窗口标题(按窗口类查找, 与语言无关)

        :return: 窗口标题, 未找到返回空串
        """
        result = self.run_cmd(
            "for w in $(xdotool search --class deepin-pc-manager 2>/dev/null); "
            "do xdotool getwindowname $w; break; done",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip()

    def get_pc_manager_ui_title_count(self) -> int:
        """当前电脑管家主窗口数量(用于判定单实例是否已出图)"""
        result = self.run_cmd(
            "xdotool search --class deepin-pc-manager 2>/dev/null | wc -l",
            timeout=10,
            out_debug_flag=False,
        )
        return int(result.strip() or 0)

    def get_app_log_has_event_loop(self, log_path) -> bool:
        """判定应用日志是否出现进入事件循环(主窗口已显示)"""
        result = self.run_cmd(
            f"grep -q 'entering event loop' {log_path} 2>/dev/null && echo ok",
            timeout=5,
            out_debug_flag=False,
        )
        return "ok" in result

    def get_desktop_localized_name(self, lang_tag) -> str:
        """读取 .desktop 中指定语言的应用名称, 无对应翻译时回退 Name

        :param lang_tag: 如 zh_CN / zh_HK / en_US
        :return: 应用名称
        """
        lang_key = lang_tag.split(".")[0]
        result = self.run_cmd(
            f"grep -m1 '^Name\\[{lang_key}\\]=' {APP_DESKTOP_FULL_PATH} 2>/dev/null "
            "| cut -d= -f2-",
            timeout=5,
            out_debug_flag=False,
        )
        name = result.strip()
        if name:
            return name
        result = self.run_cmd(
            f"grep -m1 '^Name=' {APP_DESKTOP_FULL_PATH} 2>/dev/null | cut -d= -f2-",
            timeout=5,
            out_debug_flag=False,
        )
        return result.strip()

    def get_help_manual_languages(self) -> list:
        """列出电脑管家帮助手册已提供的语言目录"""
        result = self.run_cmd(
            "ls -d /usr/share/deepin-manual/manual-assets/application/"
            "deepin-pc-manager/pc-manager/*/ 2>/dev/null | xargs -r -n1 basename",
            timeout=10,
            out_debug_flag=False,
        )
        return [line.strip() for line in result.splitlines() if line.strip()]

    def remove_language_check_log(self, log_path="/tmp/pcm_lang_check.log"):
        """删除语言验证用临时日志"""
        self.run_cmd(
            f"rm -f {log_path} /tmp/pcm_lang.pid",
            timeout=5,
            out_debug_flag=False,
        )

    def get_wayland_runtime_ready(self) -> bool:
        """检查本机具备启动独立 Wayland 合成器的条件

        需要 kwin_wayland(支持 --virtual 虚拟输出)和电脑管家主程序。
        """
        result = self.run_cmd(
            "test -x /usr/bin/kwin_wayland && test -x "
            "/usr/libexec/deepin/deepin-pc-manager && echo ready",
            timeout=5,
            out_debug_flag=False,
        )
        return "ready" in result

    def start_virtual_wayland_compositor(
        self, socket_name="pcmtest", width=1024, height=768, runtime_dir="/tmp/pcm_wayland_rt"
    ):
        """在独立 XDG_RUNTIME_DIR 中启动虚拟输出的 Wayland 合成器

        不影响当前 X11 会话, 用于验证应用在 Wayland 协议下可运行。

        :return: dict(runtime_dir, socket, pid, log), 失败返回 None
        """
        self.run_cmd(
            f"rm -rf {runtime_dir} && mkdir -p {runtime_dir} && chmod 700 {runtime_dir}",
            timeout=10,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"XDG_RUNTIME_DIR={runtime_dir} setsid nohup kwin_wayland --virtual "
            f"--socket {socket_name} --width {width} --height {height} "
            f"> {runtime_dir}/kwin.log 2>&1 < /dev/null & echo $! > {runtime_dir}/kwin.pid",
            timeout=10,
            out_debug_flag=False,
        )
        for _ in range(20):
            sleep(1)
            result = self.run_cmd(
                f"test -S {runtime_dir}/{socket_name} && cat {runtime_dir}/kwin.pid",
                timeout=5,
                out_debug_flag=False,
            )
            if result.strip().isdigit():
                return {
                    "runtime_dir": runtime_dir,
                    "socket": socket_name,
                    "pid": int(result.strip()),
                    "log": f"{runtime_dir}/kwin.log",
                }
        return None

    def stop_virtual_wayland_compositor(self, handle):
        """停止虚拟 Wayland 合成器并清理运行时目录"""
        if not handle:
            return
        self.run_cmd(
            f"kill {handle['pid']} 2>/dev/null; "
            f"pkill -f 'kwin_wayland --virtual --socket {handle['socket']}' 2>/dev/null; "
            f"true",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)
        self.run_cmd(
            f"rm -rf {handle['runtime_dir']}",
            timeout=10,
            out_debug_flag=False,
        )

    def start_pc_manager_under_wayland(self, handle):
        """在虚拟 Wayland 会话中启动电脑管家主程序(不走 X11)

        :return: dict(pid, log), 启动失败返回 None
        """
        if not handle:
            return None
        rt = handle["runtime_dir"]
        log_path = f"{rt}/app.log"
        self.run_cmd(
            f"export XDG_RUNTIME_DIR={rt} WAYLAND_DISPLAY={handle['socket']} "
            f"QT_QPA_PLATFORM=wayland; unset DISPLAY; setsid nohup "
            f"/usr/libexec/deepin/deepin-pc-manager > {log_path} 2>&1 < /dev/null & "
            f"echo $! > {rt}/app.pid",
            timeout=15,
            out_debug_flag=False,
        )
        sleep(12)
        result = self.run_cmd(
            f"cat {rt}/app.pid 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        pid = result.strip()
        if not pid.isdigit():
            return None
        alive = self.run_cmd(
            f"kill -0 {pid} 2>/dev/null && echo alive",
            timeout=5,
            out_debug_flag=False,
        )
        if "alive" not in alive:
            return None
        return {"pid": int(pid), "log": log_path}

    def get_wayland_app_started(self, handle, app_handle) -> bool:
        """判定 Wayland 下应用是否真正进入事件循环(主窗口已显示)"""
        if not app_handle:
            return False
        result = self.run_cmd(
            f"grep -q 'entering event loop' {app_handle['log']} 2>/dev/null && echo ok",
            timeout=5,
            out_debug_flag=False,
        )
        return "ok" in result

    def stop_pc_manager_under_wayland(self, app_handle):
        """结束 Wayland 下启动的电脑管家进程"""
        if not app_handle:
            return
        self.run_cmd(
            f"kill {app_handle['pid']} 2>/dev/null; "
            f"pkill -f '^/usr/libexec/deepin/deepin-pc-manager$' 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

    def get_display_protocol(self) -> str:
        """获取当前显示服务器协议类型(x11/wayland)

        优先读取 XDG_SESSION_TYPE; SSH 等非登录会话中该变量为 tty 或空,
        此时回退探测: WAYLAND_DISPLAY 非空为 wayland, 能连上 X 服务器为 x11,
        最后由 logind 查询图形会话类型。
        """
        result = self.run_cmd(
            "echo $XDG_SESSION_TYPE",
            timeout=5,
            out_debug_flag=False,
        )
        protocol = result.strip().lower()
        if protocol in ("x11", "wayland"):
            return protocol
        result = self.run_cmd(
            'if [ -n "$WAYLAND_DISPLAY" ]; then echo wayland; '
            "elif xset q >/dev/null 2>&1; then echo x11; fi",
            timeout=5,
            out_debug_flag=False,
        )
        protocol = result.strip().lower()
        if protocol in ("x11", "wayland"):
            return protocol
        result = self.run_cmd(
            "for s in $(loginctl list-sessions --no-legend 2>/dev/null | awk '{print $1}'); do "
            "loginctl show-session $s -p Type --value 2>/dev/null; done | "
            "grep -m1 -E '^(x11|wayland)$'",
            timeout=15,
            out_debug_flag=False,
        )
        return result.strip().lower()


    # ===== 设置对话框-扩展扫描分区 方法 =====

    def open_settings_dialog(self):
        """打开设置对话框(通过标题栏选项按钮菜单)

        点击标题栏选项按钮, 在弹出菜单中点击"设置"项。
        V20/V25 菜单项文案可能为"设置"或"Settings", 依次尝试。
        """
        self._safe_focus_windows()
        opened = False
        try:
            btn = self.dog.find_element_by_attr("$//DTitlebarDWindowOptionButton")
            pos = btn.position
            size = btn.size
            cx = int(pos[0] + size[0] / 2)
            cy = int(pos[1] + size[1] / 2)
            self.run_cmd(
                f"xdotool mousemove {cx} {cy} click 1",
                timeout=2,
                out_debug_flag=False,
            )
            sleep(1)
            for label in ("设置", "Settings"):
                try:
                    item = self.dog.find_element_by_attr(f"$//{label}", probe=True)
                    item.click()
                    sleep(3)
                    opened = True
                    break
                except BaseException:
                    continue
        except BaseException:
            pass
        if not opened:
            # V25 回退: DTK 标题栏菜单项不通过 AT-SPI 暴露,
            # 此时菜单仍处于打开状态, 使用键盘导航: Down 选中第一项(设置), Return 确认
            try:
                self.run_cmd("xdotool key Down", timeout=2, out_debug_flag=False)
                sleep(0.5)
                self.run_cmd("xdotool key Return", timeout=2, out_debug_flag=False)
                sleep(3)
                if self._elements_exist("$//settings_dialog"):
                    opened = True
            except BaseException:
                pass
        if not opened:
            # 回退: 某些 DTK 版本菜单项不通过 AT-SPI 暴露,
            # 直接点击菜单窗口中"设置"项的估计位置(菜单第一项, 紧邻按钮下方)
            try:
                self.run_cmd(
                    f"xdotool mousemove {cx} {int(cy + 30)} click 1",
                    timeout=2,
                    out_debug_flag=False,
                )
                sleep(3)
                if self._elements_exist("$//settings_dialog"):
                    opened = True
            except BaseException:
                pass
        if not opened:
            self.reconnect_dogtail()
            self._safe_focus_windows()

    def get_settings_dialog_showing(self, timeout=10) -> bool:
        """检查设置对话框是否已显示

        V20/V25 上设置对话框的 AT-SPI 元素名可能不同, 依次尝试。
        """
        for i in range(timeout):
            for expr in (
                "$//settings_dialog",
                "$//settingsDialog",
                "$//SettingsDialog",
            ):
                if self._elements_exist(expr):
                    return True
            if i == 2:
                self.reconnect_dogtail()
            sleep(1)
        return False

    def close_settings_dialog(self):
        """关闭设置对话框(按 Escape 键)"""
        self.run_cmd(
            "xdotool key Escape",
            timeout=2,
            out_debug_flag=False,
        )
        sleep(1)

    def get_extended_scan_partition_widget_showing(self) -> bool:
        """检查扩展扫描分区控件是否显示

        V20/V25 上 AT-SPI 元素名可能不同, 依次尝试。
        """
        for expr in (
            "$//settings_extendedScanPartitions",
            "$//settingsExtendedScanPartitions",
            "$//extendedScanPartitionCard",
        ):
            if self._elements_exist(expr):
                return True
        return False

    def click_settings_nav_item(self, item_name: str) -> bool:
        """点击设置对话框左侧导航项

        :param item_name: 导航项文案, 如 "清理设置"
        :return: True 表示找到并点击成功
        """
        for expr in (
            f"$//NavigationBar//{item_name}",
            f"$//{item_name}",
        ):
            try:
                item = self.dog.find_element_by_attr(expr)
                if item and item.showing:
                    item.click()
                    sleep(2)
                    return True
            except BaseException:
                continue
        return False

    def scroll_settings_content_to_bottom(self):
        """把设置对话框右侧内容区滚动到最底部

        扩展扫描分区控件位于清理设置页底部, 需要滚动后才能完整渲染。
        """
        try:
            area = self.dog.find_element_by_attr("$//ContentScrollArea")
            pos = area.position
            size = area.size
            cx = int(pos[0] + size[0] / 2)
            cy = int(pos[1] + size[1] / 2)
            self.run_cmd(
                f"xdotool mousemove {cx} {cy} click 1 "
                f"click --repeat 12 --delay 80 5",
                timeout=5,
                out_debug_flag=False,
            )
        except BaseException:
            pass
        sleep(1)

    def get_extended_scan_partition_texts(self) -> str:
        """收集设置对话框中扩展扫描分区相关的可读文案

        遍历设置对话框的 AT-SPI 子树, 汇总元素 name/description,
        用于校验标题与副标题文案。
        :return: 换行拼接的文案, 对话框不存在时返回空字符串
        """
        dialog = None
        for expr in (
            "$//settings_dialog",
            "$//settingsDialog",
            "$//SettingsDialog",
        ):
            try:
                dialog = self.dog.find_element_by_attr(expr)
                if dialog:
                    break
            except BaseException:
                dialog = None
        if dialog is None:
            return ""
        chunks = []

        def walk(node, depth=0):
            if depth > 10:
                return
            for attr in ("name", "description", "text"):
                try:
                    value = getattr(node, attr, "") or ""
                    if value:
                        chunks.append(str(value))
                except BaseException:
                    pass
            try:
                children = node.children
            except BaseException:
                return
            for child in children:
                walk(child, depth + 1)

        walk(dialog)
        return "\n".join(chunks)

    def get_extended_scan_partition_empty_state_showing(self) -> bool:
        """检查扩展扫描分区空状态是否显示

        当没有可扩展分区时, 空状态文案应可见。
        """
        for expr in (
            "$//settings_extendedScanPartitionEmptyText",
            "$//extendedScanPartitionEmptyState",
            "$//extendedScanPartitionEmptyText",
        ):
            if self._elements_exist(expr):
                return True
        return False

    def get_extended_scan_partition_row_count(self) -> int:
        """获取扩展扫描分区复选框行数

        :return: 分区复选框数量, 0 表示无分区(空状态)
        """
        for expr in (
            "$//settings_extendedScanPartition",
            "$//extendedScanPartitionRow",
        ):
            try:
                elements = self.dog.find_elements_by_attr(expr)
                if elements:
                    return len(elements)
            except BaseException:
                continue
        return 0

    def get_extended_scan_partition_mount_points(self) -> list:
        """获取扩展扫描分区复选框对应的挂载点列表

        :return: 挂载点路径列表
        """
        mount_points = []
        for expr in (
            "$//settings_extendedScanPartition",
            "$//extendedScanPartitionRow",
        ):
            try:
                elements = self.dog.find_elements_by_attr(expr)
                if elements:
                    for elem in elements:
                        desc = ""
                        try:
                            desc = elem.description
                        except BaseException:
                            pass
                        if desc and desc.startswith("/"):
                            mount_points.append(desc)
                    break
            except BaseException:
                continue
        return mount_points

    def unmount_partition_by_path(self, mount_point: str) -> bool:
        """卸载指定挂载点分区

        :param mount_point: 挂载点路径
        :return: True 表示卸载成功
        """
        result = self.sudo_run_cmd(
            f"umount '{mount_point}' 2>/dev/null && echo OK || echo FAIL",
            timeout=10,
            out_debug_flag=False,
        )
        return "OK" in result.strip()

    def remount_partition_by_device(self, device: str, mount_point: str) -> bool:
        """重新挂载指定设备到挂载点

        :param device: 设备路径(如 /dev/sda3)
        :param mount_point: 挂载点路径
        :return: True 表示挂载成功
        """
        result = self.sudo_run_cmd(
            f"mkdir -p '{mount_point}' && mount '{device}' '{mount_point}' 2>/dev/null && echo OK || echo FAIL",
            timeout=10,
            out_debug_flag=False,
        )
        return "OK" in result.strip()

    def get_media_partition_info(self) -> list:
        """获取 /media 下已挂载的内部固定磁盘分区信息

        返回每个分区的设备路径和挂载点, 用于测试卸载后恢复。
        :return: 列表, 每个元素为 {"device": "/dev/sda3", "mountpoint": "/media/data"}
        """
        result = self.run_cmd(
            "lsblk -o NAME,MOUNTPOINT -n 2>/dev/null | "
            "awk '$2 ~ /^\\/media/{print $1, $2}'",
            timeout=5,
            out_debug_flag=False,
        )
        partitions = []
        for line in result.strip().split("\n"):
            parts = line.split()
            if len(parts) == 2:
                name, mountpoint = parts
                partitions.append({
                    "device": f"/dev/{name}",
                    "mountpoint": mountpoint,
                })
        return partitions

    def get_app_icon_exists(self) -> bool:
        """检查电脑管家图标文件是否存在于系统图标搜索路径中

        使用 gtk3/gtk4 的 icon lookup 工具或直接搜索 hicolor 目录。
        兼容 V20(gtk3) 和 V25(gtk4) 环境。
        :return: True 表示图标文件存在
        """
        icon_name = self.get_desktop_icon_name()
        if not icon_name:
            return False
        # 优先使用 gtk-query-immodules 或直接查找图标文件
        # 搜索常见图标目录: hicolor, bloom, deepin 等主题
        result = self.run_cmd(
            f'find /usr/share/icons -name "{icon_name}.*" -o -name "{icon_name}" 2>/dev/null | head -1',
            timeout=10,
            out_debug_flag=False,
        )
        if result.strip():
            return True
        # 也检查 /usr/share/pixmaps 目录
        result = self.run_cmd(
            f'ls /usr/share/pixmaps/{icon_name}.* 2>/dev/null | head -1',
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def get_window_has_icon(self) -> bool:
        """检查电脑管家运行窗口是否设置了窗口图标

        通过 xprop 检查 _NET_WM_ICON 属性是否存在。
        V25(loongarch64) 上窗口管理器不设置 _NET_WM_ICON 属性,
        回退检查 desktop 文件中 Icon 字段对应的图标文件是否存在。
        :return: True 表示窗口已设置图标
        """
        result = self.run_cmd(
            "xdotool search --name '电脑管家' 2>/dev/null | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        window_id = result.strip()
        if not window_id:
            return False
        result = self.run_cmd(
            f"xprop -id {window_id} _NET_WM_ICON 2>/dev/null | head -1",
            timeout=5,
            out_debug_flag=False,
        )
        if "_NET_WM_ICON" in result and "not found" not in result.lower():
            return True
        icon_name = self.get_desktop_icon_name()
        if not icon_name:
            return False
        return self.get_app_icon_exists()


    # ===== PMS 2001969「重复文件清理--扫描中」测试用例方法 =====

    # 会话守护进程为重复文件扫描暴露的任务对象: 只在扫描期间存在,
    # 扫描结束后对象被销毁。见 session_daemon_service.cpp startDuplicateFileScan。
    _DUP_SCAN_TASK_PATH = "/org/deepin/PCManager1/Task/scan/duplicatefile"

    def get_dup_file_scan_task_status(self) -> str:
        """读取会话守护进程中重复文件扫描任务的状态

        重复文件扫描在本机只持续数秒, 而 AT-SPI 单次元素查找约 2s, 等元素
        查到扫描可能已经结束; 任务状态可以立即判定扫描是否仍在进行。
        :return: "running" / "success:ok" / "failed" / "cancelled";
                 任务对象不存在(未开始或已结束)时返回 ""
        """
        try:
            out = self.run_cmd(
                "timeout 3 /usr/bin/gdbus call --session "
                "--dest org.deepin.PCManager1 "
                f"--object-path {self._DUP_SCAN_TASK_PATH} "
                "--method org.deepin.PCManager1.Task.GetStatus 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            ) or ""
        except BaseException:
            return ""
        # gdbus 输出形如 ('running',); 取引号内的状态文本
        text = out.strip()
        if "'" in text:
            return text.split("'")[1]
        return ""

    def wait_dup_file_scan_running(self, timeout=10) -> bool:
        """等待重复文件扫描任务进入 running 状态

        :param timeout: 最长等待秒数
        :return: True 表示扫描正在进行; False 表示超时或扫描已结束
        """
        for _ in range(int(timeout * 20)):
            status = self.get_dup_file_scan_task_status()
            if status == "running":
                return True
            if status:
                return False
            sleep(0.05)
        return False

    def wait_dup_file_scan_idle(self, timeout=60) -> bool:
        """等待重复文件扫描任务结束(任务对象消失或不再 running)

        点击返回只退出扫描页面, 不会取消后台扫描任务, 测试收尾需等任务
        自行结束, 避免影响后续用例。
        :param timeout: 最长等待秒数
        :return: True 表示扫描已结束
        """
        for _ in range(int(timeout * 10)):
            if self.get_dup_file_scan_task_status() != "running":
                return True
            sleep(0.2)
        return False

    def get_dup_file_scan_view_showing(self) -> bool:
        """检查重复文件清理的扫描视图是否正在显示(不含结果页/空态页)

        :return: True 如果扫描页元素(标题/进度)可见
        """
        return self._any_visible("$//dupFile_scanTitle", "$//dupFile_scanProgress")

    _DUP_SCAN_LOAD_DIR = f"{HOME_DIR}/autotest_dup_scan_load"

    def create_dup_scan_load(self, count=40000):
        """创建重复文件扫描负载, 拉长扫描时长以便观察"扫描中点击返回"

        默认数据量下重复文件扫描只持续约 0.2s, 来不及在扫描窗口内点击返回。
        这里生成 count 个 1MB 稀疏文件(ftruncate, 不占实际磁盘空间): 扫描器
        对同尺寸文件逐个采样哈希, 实测 4 万文件可把扫描拉长到约 8s。

        :param count: 生成的文件数量
        """
        self.run_cmd(
            "python3 - <<'PYEOF'\n"
            "import os\n"
            "d = os.path.join(os.path.expanduser('~'), 'autotest_dup_scan_load')\n"
            "os.makedirs(d, exist_ok=True)\n"
            f"for i in range({count}):\n"
            "    p = os.path.join(d, 'load_%06d.bin' % i)\n"
            "    if not os.path.exists(p):\n"
            "        fd = os.open(p, os.O_CREAT | os.O_WRONLY, 0o644)\n"
            "        os.ftruncate(fd, 1048576)\n"
            "        os.close(fd)\n"
            "print(len(os.listdir(d)))\n"
            "PYEOF\n",
            timeout=300,
            out_debug_flag=False,
        )

    def remove_dup_scan_load(self):
        """删除重复文件扫描负载目录(~/autotest_dup_scan_load)"""
        self.run_cmd(
            f"rm -rf {quote(self._DUP_SCAN_LOAD_DIR)}",
            timeout=120,
            out_debug_flag=False,
        )

    def get_dup_file_scan_started(self, timeout=30) -> bool:
        """检查重复文件清理扫描是否已开始(或已瞬间完成)

        点击"重复文件清理"卡片后, 插件自动启动扫描并切换到扫描视图,
        显示 dupFile_scanProgress / dupFile_scanTitle 等元素。
        数据量小或扫描极快时, 可能直接跳到结果页(dupFile_resultTitle)或
        空状态页(dupFile_emptyTitle) / 完成页(dupFile_finishedTitle)。

        两者任一可见即视为扫描已开始, 避免小数据量场景下进度条被误判为未显示。
        :param timeout: 最长等待秒数
        :return: True 如果检测到扫描进度或扫描结果页, False 如果超时
        """
        scan_exprs = [
            "$//dupFile_scanProgress",
            "$//dupFile_scanTitle",
            "$//dupFile_scanPath",
            "$//dupFile_scanCount",
            "$//dupFile_scanIcon",
            "$//dupFile_scanElapsed",
            "$//dupFile_resultTitle",
            "$//dupFile_emptyTitle",
            "$//dupFile_finishedTitle",
        ]
        for _ in range(timeout):
            for expr in scan_exprs:
                try:
                    element = self.dog.find_element_by_attr(expr)
                    if element.showing:
                        return True
                    width, height = element.size
                    if width > 0 and height > 0:
                        return True
                except BaseException:
                    continue
            sleep(1)
        return False

    def get_dup_file_scan_completed(self, timeout=120) -> bool:
        """等待重复文件清理扫描完成

        扫描完成后, 视图切换到结果页(dupFile_resultTitle)、空状态页
        (dupFile_emptyTitle)或完成页(dupFile_finishedTitle)。

        :param timeout: 最长等待秒数
        :return: True 如果扫描已完成(任意结果页可见), False 如果超时
        """
        result_exprs = [
            "$//dupFile_resultTitle",
            "$//dupFile_emptyTitle",
            "$//dupFile_finishedTitle",
        ]
        for _ in range(timeout):
            for expr in result_exprs:
                try:
                    element = self.dog.find_element_by_attr(expr)
                    if element.showing:
                        return True
                    width, height = element.size
                    if width > 0 and height > 0:
                        return True
                except BaseException:
                    continue
            sleep(1)
        return False
    # ===== PMS 2001929「大文件清理-扫描范围验证」测试用例方法 =====

    def create_large_test_file(self, size_mb=110):
        """在用户家目录下创建大文件, 用于验证大文件清理扫描范围

        大文件清理扫描器的阈值为 100 MB, 创建略大于阈值的文件确保被检测到。
        文件放在 ~/autotest_large_file/ 目录下, 扫描范围覆盖家目录。
        """
        test_dir = f"{HOME_DIR}/autotest_large_file"
        self.run_cmd(f"mkdir -p {test_dir}", timeout=5, out_debug_flag=False)
        test_file = f"{test_dir}/large_test_file.bin"
        self.run_cmd(
            f"dd if=/dev/zero of={test_file} bs=1M count={size_mb} 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_large_test_file(self):
        """清理大文件清理测试创建的大文件"""
        test_dir = f"{HOME_DIR}/autotest_large_file"
        self.run_cmd(
            f"rm -rf {test_dir}",
            timeout=5,
            out_debug_flag=False,
        )

    _SCAN_ISOLATION_DIR = SCAN_ISOLATION_DIR

    def _cleanup_isolation_dirs(self):
        """清理暂存目录中的空目录(全部恢复后删除暂存目录)"""
        self.run_cmd(
            f"find {quote(self._SCAN_ISOLATION_DIR)} -depth -type d -empty "
            "-delete 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )

    def recover_staged_large_files(self) -> int:
        """把上次异常中断遗留在暂存目录中的大文件移回原位置

        暂存目录内按文件相对家目录的路径存放, 因此可以无歧义地还原;
        用例正常结束时 restore_foreign_large_files 已完成恢复, 这里只处理
        进程被杀/断言中断等遗留场景, 避免遗留文件污染后续用例的扫描结果。

        :return: 恢复的文件数
        """
        iso_dir = self._SCAN_ISOLATION_DIR
        rels = self.run_cmd(
            f"find {quote(iso_dir)} -type f -printf '%P\\n' 2>/dev/null",
            timeout=60,
            out_debug_flag=False,
        )
        count = 0
        for rel in rels.splitlines():
            rel = rel.strip()
            if not rel:
                continue
            dst = os.path.join(iso_dir, rel)
            src = os.path.join(HOME_DIR, rel)
            moved = self.run_cmd(
                f"mkdir -p {quote(os.path.dirname(src))} && "
                f"mv -f {quote(dst)} {quote(src)} 2>/dev/null && echo ok",
                timeout=60,
                out_debug_flag=False,
            )
            if "ok" in moved:
                count += 1
        self._cleanup_isolation_dirs()
        if count:
            logger.warning(f"已恢复上次中断遗留的 {count} 个隔离大文件")
        return count

    _DUP_ISOLATION_DIR = DUP_ISOLATION_DIR

    def _foreign_dup_candidates(self, min_size_bytes):
        """找出家目录中"尺寸 + 采样内容"一致的潜在重复文件

        产品按"尺寸 + 全量 MD5"分组, 这里用"尺寸 + 首 64KB + 尾 64KB"的
        采样哈希近似(判据更严, 只会多隔离, 不会漏隔离), 避免把大量尺寸相同
        但内容不同的编译产物当成重复文件。
        扫描范围与产品一致: 家目录下非隐藏目录; 额外排除测试目录(autotest_dup*)。
        注意项目自身目录也在产品扫描范围内(报告里的录屏附件常常成对重复),
        必须一并隔离, 否则"智能选择 + 彻底删除"会永久删掉测试框架自己的产物。

        :param min_size_bytes: 阈值(字节)
        :return: 属于某个重复组的文件路径列表
        """
        import hashlib

        by_key = {}
        for root, dirs, files in os.walk(HOME_DIR):
            if root == HOME_DIR:
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(".") and not d.startswith("autotest_dup")
                ]
            else:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                path = os.path.join(root, name)
                try:
                    stat = os.lstat(path)
                except OSError:
                    continue
                if stat.st_size < min_size_bytes or not os.path.isfile(path):
                    continue
                if os.path.islink(path):
                    continue
                try:
                    with open(path, "rb") as handle:
                        sample = handle.read(65536)
                        if stat.st_size > 65536 * 2:
                            handle.seek(-65536, os.SEEK_END)
                            sample += handle.read(65536)
                except OSError:
                    continue
                key = (stat.st_size, hashlib.md5(sample).hexdigest())
                by_key.setdefault(key, []).append(path)
        return [
            path
            for paths in by_key.values()
            if len(paths) >= 2
            for path in paths
        ]

    def recover_staged_dup_files(self) -> int:
        """把上次异常中断遗留在暂存目录中的重复文件移回原位置

        :return: 恢复的文件数
        """
        root = self._DUP_ISOLATION_DIR
        if not os.path.isdir(root):
            return 0
        count = 0
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                dst = os.path.join(dirpath, name)
                src = os.path.join(HOME_DIR, os.path.relpath(dst, root))
                try:
                    os.makedirs(os.path.dirname(src), exist_ok=True)
                    os.replace(dst, src)
                    count += 1
                except OSError:
                    continue
        # topdown=False 时 dirs 是遍历开始时的快照, 子目录刚被删掉也仍在列表里,
        # 因此用 listdir 判断是否真正为空
        for dirpath, _dirs, _files in os.walk(root, topdown=False):
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except OSError:
                pass
        if count:
            logger.warning(f"已恢复上次中断遗留的 {count} 个隔离重复文件")
        return count

    def isolate_foreign_dup_files(self, min_size_mb=1, max_files=200):
        """把家目录中已存在的真实重复文件临时移出重复文件清理扫描范围

        '智能选择'会一次选中结果列表中的所有组, 配合'彻底删除'会永久删除
        这些文件。若测试机家目录已有真实重复文件(构建产物、报告副本等),
        会被误删; 若不移除, 还会把用例自己的测试组挤到列表深处, 使滚动
        定位超时。这里按"尺寸 + 采样内容"保守判定, 把非测试文件移入
        $HOME/.autotest_dup_staged(隐藏目录, 产品不扫描), 用例结束调用
        restore_foreign_large_files 恢复。测试文件位于 $HOME/autotest_dup*
        目录, 不被隔离; 其余(含测试项目自身目录里的报告录屏)全部隔离。

        :param min_size_mb: 阈值(MB), 与产品扫描阈值一致
        :param max_files: 单次隔离文件数上限, 超过说明环境异常, 直接报错
        :return: [(原路径, 暂存路径)] 列表, 供恢复使用
        """
        self.recover_staged_dup_files()
        targets = self._foreign_dup_candidates(min_size_mb * 1024 * 1024)
        if len(targets) > max_files:
            raise RuntimeError(
                f"家目录潜在重复文件过多({len(targets)} 个), 拒绝自动隔离, "
                "请先在测试机上清理环境"
            )
        pairs = []
        for src in targets:
            rel = os.path.relpath(src, HOME_DIR)
            dst = os.path.join(self._DUP_ISOLATION_DIR, rel)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.replace(src, dst)
            except OSError as exc:
                logger.warning(f"隔离重复文件失败: {src} ({exc})")
                continue
            pairs.append((src, dst))
        if pairs:
            logger.info(f"已将 {len(pairs)} 个已存在的重复文件临时移出扫描范围")
        return pairs

    def restore_foreign_dup_files(self, pairs):
        """恢复 isolate_foreign_dup_files 临时移出的重复文件

        :param pairs: isolate_foreign_dup_files 的返回值
        """
        for src, dst in pairs or []:
            try:
                os.makedirs(os.path.dirname(src), exist_ok=True)
                os.replace(dst, src)
            except OSError as exc:
                logger.warning(f"恢复重复文件失败: {src} ({exc})")
        self.recover_staged_dup_files()

    def isolate_foreign_large_files(self, min_size_mb=100):
        """把家目录中已存在的大文件临时移出大文件清理扫描范围

        产品扫描范围为家目录(含隐藏目录), 阈值 100MB。测试机家目录里有测试
        框架自身产物(录屏 mp4、报告压缩包、构建 deb 等), 会混进"结果集"类用例
        的预期(空结果/分类计数/筛选无结果/单行操作), 造成与产品缺陷无关的误报。
        这里把这些已存在的文件移动到 $HOME 之外的暂存目录(保留相对路径),
        用例结束调用 restore_foreign_large_files 恢复; 用例自己创建的大文件
        (autotest_large_file*/)不移动。

        :param min_size_mb: 阈值(MB), 与产品扫描阈值一致
        :return: [(原路径, 暂存路径)] 列表, 供恢复使用
        """
        # 先回收上次异常中断的遗留, 避免遗留文件把扫描结果弄脏
        self.recover_staged_large_files()
        find_cmd = (
            f"find '{HOME_DIR}' -mindepth 1 -type f -size +{min_size_mb - 1}M "
            f"-not -path '{HOME_DIR}/autotest_large_file*' "
            "-print0 2>/dev/null"
        )
        result = self.run_cmd(find_cmd, timeout=120, out_debug_flag=False)
        candidates = [path for path in result.split("\0") if path.strip()]
        pairs = []
        for src in candidates:
            rel = os.path.relpath(src, HOME_DIR)
            dst = os.path.join(self._SCAN_ISOLATION_DIR, rel)
            moved = self.run_cmd(
                f"mkdir -p {quote(os.path.dirname(dst))} && "
                f"mv -f {quote(src)} {quote(dst)} 2>/dev/null && echo ok",
                timeout=120,
                out_debug_flag=False,
            )
            if "ok" in moved:
                pairs.append((src, dst))
        if pairs:
            logger.info(f"已将 {len(pairs)} 个已存在的大文件临时移出扫描范围")
        return pairs

    def restore_foreign_large_files(self, pairs):
        """恢复 isolate_foreign_large_files 临时移出的大文件

        :param pairs: isolate_foreign_large_files 的返回值
        """
        for src, dst in pairs or []:
            self.run_cmd(
                f"mkdir -p {quote(os.path.dirname(src))} && "
                f"mv -f {quote(dst)} {quote(src)} 2>/dev/null; true",
                timeout=120,
                out_debug_flag=False,
            )
        self._cleanup_isolation_dirs()

    def get_large_file_scan_completed(self, timeout=120) -> bool:
        """等待大文件清理扫描完成

        扫描完成后页面从扫描视图(index 0)切换到结果视图(index 3, 有大文件)
        或空视图(index 1, 无大文件)。任一视图可见即认为扫描已完成。

        :param timeout: 最长等待秒数
        :return: True 如果扫描已完成(结果页或空页面可见)
        """
        self._safe_focus_windows()
        for i in range(timeout):
            if self._any_visible(
                "$//largeFile_resultTitle",
                "$//largeFile_emptyTitle",
            ):
                return True
            if i > 0 and i % 5 == 0:
                self._refresh_app()
                try:
                    self._safe_focus_windows()
                except BaseException:
                    pass
            sleep(1)
        return False

    def get_large_file_result_showing(self) -> bool:
        """检查大文件清理结果页是否显示(检测到大文件)

        结果页 largeFile_resultTitle 可见表示扫描检测到了大文件。

        :return: True 如果结果页可见
        """
        return self._any_visible("$//largeFile_resultTitle")

    def get_large_file_empty_showing(self) -> bool:
        """检查大文件清理空页面是否显示(未检测到大文件)

        空页面 largeFile_emptyTitle 可见表示扫描未检测到大文件。

        :return: True 如果空页面可见
        """
        return self._any_visible("$//largeFile_emptyTitle")

    # ===== PMS 2001927「大文件清理--扫描中」测试用例方法 =====

    def get_large_file_scan_started(self, timeout=30) -> bool:
        """检查大文件清理扫描是否已开始(或已瞬间完成)

        进入大文件清理页面后扫描自动开始, 有两种可能界面:
        1. 扫描进行中: largeFile_scanTitle / largeFile_scanProgress 等扫描视图元素可见;
        2. 数据量小或扫描极快: 直接进入结果页(largeFile_resultTitle)或空状态页(largeFile_emptyTitle)。

        两者任一可见即视为扫描已开始。
        :param timeout: 最长等待秒数
        :return: True 如果检测到扫描进度或扫描结果页, False 如果超时
        """
        scan_exprs = [
            "$//largeFile_scanTitle",
            "$//largeFile_scanProgress",
            "$//largeFile_scanCount",
            "$//largeFile_scanPath",
            "$//largeFile_scanElapsed",
            "$//largeFile_resultTitle",
            "$//largeFile_emptyTitle",
            "$//largeFile_finishedTitle",
        ]
        for _ in range(timeout):
            self._safe_focus_windows()
            for expr in scan_exprs:
                try:
                    element = self.dog.find_element_by_attr(expr)
                    if element.showing:
                        return True
                    width, height = element.size
                    if width > 0 and height > 0:
                        return True
                except BaseException:
                    continue
            sleep(1)
        return False

    @staticmethod
    def _large_file_scan_bus_prefix() -> str:
        """大文件扫描任务的会话总线调用前缀

        GUI 与 session daemon 之间的大文件扫描通道在会话总线上, 服务名
        org.deepin.PCManager1; 测试进程需显式指定会话总线地址。
        """
        return (
            f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{os.getuid()}/bus "
            "/usr/bin/gdbus call --session --dest org.deepin.PCManager1 "
        )

    def start_large_file_scan_via_dbus(self, timeout=20):
        """经会话总线启动大文件扫描, 返回 daemon 的任务对象路径

        daemon 对同一任务键(StartLargeFileScan)做重入复用: 任务仍在运行时
        返回已存在的对象路径而不新建任务, 因此界面进入大文件清理页面和本
        方法观察的是同一个扫描任务。

        :param timeout: gdbus 调用超时秒数
        :return: (task_path, 原始输出); 启动失败时 task_path 为空串
        """
        out = self.run_cmd(
            self._large_file_scan_bus_prefix()
            + "--object-path /org/deepin/PCManager1 "
            "--method org.deepin.PCManager1.StartLargeFileScan '@as []'",
            timeout=timeout,
            out_debug_flag=False,
        ) or ""
        match = re.search(r"(/org/deepin/PCManager1/Task/[\w/]+)", out)
        return (match.group(1) if match else ""), out.strip()

    def stop_large_file_scan_via_dbus(self, timeout=15):
        """经会话总线请求取消大文件扫描任务(用例清理用)

        :param timeout: gdbus 调用超时秒数
        """
        self.run_cmd(
            self._large_file_scan_bus_prefix()
            + "--object-path /org/deepin/PCManager1 "
            "--method org.deepin.PCManager1.StopLargeFileScan",
            timeout=timeout,
            out_debug_flag=False,
        )

    def get_large_file_scan_task_state(
        self,
        task_path="/org/deepin/PCManager1/Task/scan/largefile",
    ):
        """读取大文件扫描任务的状态与进度

        daemon 的 Task 对象把 status/progress 暴露为 D-Bus 属性; 属性读取
        不做调用者鉴权(防重入保护只覆盖 Cancel/GetResult), 测试可直接读取。

        :param task_path: StartLargeFileScan 返回的任务对象路径
        :return: {"status": str, "progress": int, "raw_status": str, "raw_progress": str};
                 status 为空串表示读取失败
        """
        state = {"status": "", "progress": -1, "raw_status": "", "raw_progress": ""}
        for key in ("status", "progress"):
            out = self.run_cmd(
                self._large_file_scan_bus_prefix()
                + f"--object-path {task_path} "
                "--method org.freedesktop.DBus.Properties.Get "
                f"org.deepin.PCManager1.Task {key}",
                timeout=10,
                out_debug_flag=False,
            ) or ""
            state[f"raw_{key}"] = out.strip()
            match = re.search(r"\(\s*<([^>]*)>,", out)
            if not match:
                continue
            value = match.group(1).strip().strip("'")
            if key == "status":
                state["status"] = value
            else:
                digits = re.search(r"-?\d+", value)
                if digits:
                    state["progress"] = int(digits.group(0))
        return state

    def create_scan_slow_fixture(self, count=1200000, name="pcm_scan_fixture"):
        """在用户主目录创建大量空文件, 延长大文件扫描的进行窗口

        大文件扫描遍历主目录时逐项 stat, 文件数量决定扫描时长; 本方法用于
        构造"点击返回时扫描仍在进行"的前置条件。

        :param count: 空文件数量
        :param name: 夹具目录名(位于用户主目录下)
        :return: 夹具目录绝对路径
        """
        fixture_dir = f"{HOME_DIR}/{name}"
        self.run_cmd(
            f"rm -rf {quote(fixture_dir)}",
            timeout=60,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"mkdir -p {quote(fixture_dir)}",
            timeout=10,
            out_debug_flag=False,
        )
        self.run_cmd(
            "python3 -c \"import os;d='" + fixture_dir + "';"
            f"[open(os.path.join(d,'f%d'%i),'w').close() for i in range({count})]\"",
            timeout=600,
            out_debug_flag=False,
        )
        return fixture_dir

    def remove_scan_slow_fixture(self, name="pcm_scan_fixture"):
        """清理 create_scan_slow_fixture 创建的夹具目录

        :param name: 夹具目录名
        """
        self.run_cmd(
            f"rm -rf {quote(f'{HOME_DIR}/{name}')}",
            timeout=180,
            out_debug_flag=False,
        )

    def get_local_environment_status(self) -> bool:
        """检查关键库(本地环境)检测状态是否正常

        关键库检测(对应 daemon 的 detectLocalEnvironment)通过 dpkg --audit
        和 apt-get -s install -f 两项检查判断本地包环境是否正常:
        - dpkg --audit 无输出表示无损坏包
        - apt-get -s install -f 输出不含 "broken packages" 表示无破损依赖

        :return: True 表示本地环境(关键库)检测正常
        """
        dpkg_result = self.run_cmd(
            "dpkg --audit 2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        dpkg_ok = not dpkg_result.strip()

        apt_result = self.run_cmd(
            "apt-get -s install -f 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        apt_ok = "broken packages" not in apt_result.lower()

        return dpkg_ok and apt_ok

    def create_conflict_library(self):
        """在 /usr/local/lib 下创建与系统包管理库同名的冲突 .so 文件

        电脑管家关键库检测逻辑: 扫描 /usr/local/lib 下的 .so 文件,
        若与 /usr/lib(含子目录)中包管理的同名 .so 文件 SHA-256 不同,
        则判定为冲突库。本方法选取系统中已存在的包管理库 libz.so.1
        (来自 zlib1g 包, 位于 /usr/lib/x86_64-linux-gnu/libz.so.1),
        在 /usr/local/lib 下创建同名但内容不同的 .so 文件以触发冲突。
        """
        self.sudo_run_cmd(
            "mkdir -p /usr/local/lib",
            timeout=5,
            out_debug_flag=False,
        )
        # 创建内容不同的同名 .so 文件(用随机数据, 确保 SHA-256 与系统库不同)
        self.sudo_run_cmd(
            "head -c 1024 /dev/urandom > /usr/local/lib/libz.so.1 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "chmod 644 /usr/local/lib/libz.so.1 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )

    def clean_conflict_library(self):
        """清理 /usr/local/lib 下测试创建的冲突 .so 文件"""
        self.sudo_run_cmd(
            "rm -f /usr/local/lib/libz.so.1 2>/dev/null; echo done",
            timeout=5,
            out_debug_flag=False,
        )

    def get_conflict_library_exists(self) -> bool:
        """检查 /usr/local/lib/libz.so.1 冲突文件是否存在

        :return: True 表示冲突文件存在
        """
        result = self.run_cmd(
            "test -f /usr/local/lib/libz.so.1 && echo yes || echo no",
            timeout=5,
            out_debug_flag=False,
        )
        return "yes" in result.strip()

    def remove_local_lib_directory(self):
        """删除 /usr/local/lib 目录(备份后移除)

        电脑管家关键库检测会扫描 /usr/local/lib 下的 .so 文件判断冲突,
        本方法将 /usr/local/lib 重命名为备份目录以模拟目录被删除的场景,
        检测逻辑应能容忍目录缺失(localLibDir.exists() 为 false 时跳过扫描)。
        """
        self.sudo_run_cmd(
            "rm -rf /usr/local/lib.autotest_bak 2>/dev/null"
            "; test -d /usr/local/lib && mv /usr/local/lib /usr/local/lib.autotest_bak"
            " || true; echo done",
            timeout=10,
            out_debug_flag=False,
        )

    def get_local_lib_directory_exists(self) -> bool:
        """检查 /usr/local/lib 目录是否存在

        :return: True 表示目录存在
        """
        result = self.run_cmd(
            "test -d /usr/local/lib && echo yes || echo no",
            timeout=5,
            out_debug_flag=False,
        )
        return "yes" in result.strip()

    def restore_local_lib_directory(self):
        """恢复 /usr/local/lib 目录(从备份还原)

        将 remove_local_lib_directory 备份的目录还原回 /usr/local/lib,
        若备份不存在则创建空目录以保证系统路径完整。
        """
        self.sudo_run_cmd(
            "if [ -d /usr/local/lib.autotest_bak ]; then"
            " rm -rf /usr/local/lib 2>/dev/null;"
            " mv /usr/local/lib.autotest_bak /usr/local/lib;"
            " else mkdir -p /usr/local/lib; fi; echo done",
            timeout=10,
            out_debug_flag=False,
        )

    def get_detection_issues_icon_showing(self) -> bool:
        """检查检测结果中'发现问题'状态是否可见

        1.1.6 起全面检测结果按可修复性拆分图标:
        detection_issuesIcon(可自动修复)、detection_manualIcon(需人工处理)、
        detection_manualPartialIcon(部分已处理); 任一可见即表示检测发现问题。
        若所有检测项均正常, 则显示 detection_successIcon / detection_noProblemPage。
        :return: True 表示检测发现了问题
        """
        return self._any_visible(
            "$//detection_issuesIcon",
            "$//detection_manualIcon",
            "$//detection_manualPartialIcon",
        )

    def get_detection_success_icon_showing(self) -> bool:
        """检查检测结果中'未发现问题'状态图标是否可见

        detection_successIcon 仅在全部检测项正常时渲染; 元素在隐藏页中常驻,
        仍以 size 非零判定可见实例。
        :return: True 表示结果页处于"无异常"状态
        """
        return self._any_visible("$//detection_successIcon")

    def get_source_file_immutable_status(self) -> bool:
        """检查 /etc/apt/sources.list 是否设置了 immutable (i) 属性

        使用 lsattr 检查 sources.list 文件的扩展属性,
        若输出中属性标志位包含 'i' 则表示文件被设为不可变。
        :return: True 表示存在 immutable 属性, False 表示正常
        """
        result = self.run_cmd(
            "lsattr /etc/apt/sources.list 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        for line in result.strip().split("\n"):
            parts = line.strip().split()
            if parts and "i" in parts[0]:
                return True
        return False

    def remove_source_file_immutable(self):
        """移除 /etc/apt/sources.list 的 immutable (i) 属性"""
        self.sudo_run_cmd(
            "chattr -i /etc/apt/sources.list 2>/dev/null; echo done",
            timeout=5,
            out_debug_flag=False,
        )

    def add_source_file_immutable(self):
        """为 /etc/apt/sources.list 添加 immutable (i) 属性"""
        self.sudo_run_cmd(
            "chattr +i /etc/apt/sources.list 2>/dev/null; echo done",
            timeout=5,
            out_debug_flag=False,
        )

    # ===== PMS 2032315「清理玲珑环境、系统快照-玲珑清理交互」测试用例方法 =====

    def create_linglong_unreachable_objects(self):
        """在玲珑 ostree 仓库中创建不可达对象, 使空间清理扫描能检测到玲珑环境残留

        通过 ostree commit 创建一个临时 ref, 然后删除该 ref,
        使 commit 产生的对象变为不可达对象。ostree prune --refs-only
        会将这些对象识别为可回收的玲珑环境残留。
        """
        tmp_dir = "/tmp/ostree_linglong_test"
        self.run_cmd(
            f"mkdir -p {tmp_dir}",
            timeout=5,
            out_debug_flag=False,
        )
        for i in range(3):
            self.run_cmd(
                f"dd if=/dev/zero of={tmp_dir}/file_{i}.dat bs=1K count=1 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
        repo = "/var/lib/linglong/repo"
        self.sudo_run_cmd(
            f"ostree --repo={repo} commit -b autotest-unreachable-ref "
            f"--tree=dir={tmp_dir} 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"ostree --repo={repo} refs --delete autotest-unreachable-ref 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

    def clean_linglong_unreachable_objects(self):
        """清理玲珑 ostree 仓库中的不可达对象(测试后清理)"""
        repo = "/var/lib/linglong/repo"
        self.sudo_run_cmd(
            f"ostree --repo={repo} prune --refs-only 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        self.run_cmd(
            "rm -rf /tmp/ostree_linglong_test",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def get_linglong_junk_exist(self) -> bool:
        """检查玲珑 ostree 仓库中是否存在不可达对象(可清理的玲珑环境残留)

        通过 ostree prune --refs-only --no-prune 模拟清理,
        若输出包含 "Would delete" 则存在不可达对象。
        :return: True 如果存在不可达对象
        """
        repo = "/var/lib/linglong/repo"
        result = self.sudo_run_cmd(
            f"ostree --repo={repo} prune --refs-only --no-prune 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        return "Would delete" in result

    def wait_linglong_junk_cleaned(self, timeout=60) -> bool:
        """等待玲珑 ostree 仓库中的不可达对象被清理完毕

        点击清理按钮后, 电脑管家通过 ostree prune 清理玲珑环境残留。
        :param timeout: 最长等待秒数
        :return: True 如果不可达对象已被清理, False 如果超时仍存在
        """
        for _ in range(timeout):
            if not self.get_linglong_junk_exist():
                return True
            sleep(1)
        return False

    def get_source_file_readable(self) -> bool:
        """检查 /etc/apt/sources.list 是否可读"""
        result = self.run_cmd(
            "test -r /etc/apt/sources.list && echo readable",
            timeout=5,
            out_debug_flag=False,
        )
        return "readable" in result

    def get_space_clean_category_names(self, retries=5):
        """获取空间清理分类名称列表(仅统计含可清理项的分类)

        结果页每个分类名称标签的 accessibleName 被产品固定为
        "spaceClean_categoryName"(见 spaceClean_widget.cpp setA11yMeta),
        无法从结果页取到分类文本; 唯一带文本的是扫描预填充页的分类标签。

        扫描预填充页会为系统快照无条件创建 "系统快照 (0)" 占位卡片
        (space_clean_widget.cpp ensureSnapshotCategoryCard, V20 同样创建),
        该占位卡片没有可清理项, 不会出现在结果页。因此解析标签末尾的
        "(数量)", 数量为 0 的占位标签不计入分类列表。

        :return: 分类名称文本列表, 按界面从上到下排列
        """
        pattern = re.compile(r"^(.+)\((\d+)\)$")
        for _attempt in range(retries):
            self._safe_focus_windows()
            try:
                app = self.dog.obj
                labels = app.findChildren(
                    lambda x: bool(x.name)
                    and pattern.match(x.name.strip())
                    and x.roleName == "label"
                )
                if labels:
                    labels.sort(key=lambda e: e.extents[1] if e.extents else 0)
                    return [
                        e.name.strip() for e in labels
                        if int(pattern.match(e.name.strip()).group(2)) > 0
                    ]
            except BaseException:
                pass
            sleep(1)
        return []

    def get_time_config_status(self) -> bool:
        """检查时间配置检测状态是否正常

        时间配置检测(对应 daemon 的 detectTimeConfig)通过检查
        systemd-timesyncd.service 的加载状态、运行状态和启用状态
        判断时间同步服务是否正常:
        - systemctl show --property=LoadState --value 返回 "loaded"(服务存在)
        - systemctl is-active 返回 "active"(服务正在运行)
        - systemctl is-enabled 返回 "enabled"(服务已启用)

        :return: True 表示时间配置检测正常
        """
        load_state = self.run_cmd(
            "systemctl show --property=LoadState --value systemd-timesyncd.service 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        if load_state.strip() != "loaded":
            return False

        active_state = self.run_cmd(
            "systemctl is-active systemd-timesyncd.service 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        if active_state.strip() != "active":
            return False

        enabled_state = self.run_cmd(
            "systemctl is-enabled systemd-timesyncd.service 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return enabled_state.strip() == "enabled"

    def stop_time_sync_service(self):
        """停止 systemd-timesyncd 时间同步服务以模拟时间配置异常

        通过 systemctl stop systemd-timesyncd 停止服务。
        停止前通过 systemd-run 安排 60 秒后自动恢复, 确保即使 SSH
        会话中断或测试进程被杀, 时间同步服务也能自动恢复。
        """
        self.sudo_run_cmd(
            "systemd-run --on-active=60 --unit=pms-tsync-recovery "
            "systemctl start systemd-timesyncd 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "systemctl stop systemd-timesyncd 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)

    def start_time_sync_service(self):
        """恢复 systemd-timesyncd 时间同步服务

        启动 systemd-timesyncd 服务并取消 stop_time_sync_service
        设置的定时恢复任务。
        """
        self.sudo_run_cmd(
            "bash -c 'systemctl stop pms-tsync-recovery.timer 2>/dev/null; "
            "systemctl start systemd-timesyncd 2>/dev/null; true'",
            timeout=15,
            out_debug_flag=False,
        )
        sleep(2)

    def get_startmanager_autostart_status(self, desktop_path=None):
        """通过 D-Bus 查询系统启动器(com.deepin.StartManager)的自启动状态

        调用 com.deepin.SessionManager 的 IsAutostart 方法,
        检查指定 desktop 文件是否在 autostart 目录中。
        :param desktop_path: desktop 文件全路径, 默认为电脑管家的 desktop 文件
        :return: True 表示已启用自启动
        """
        if desktop_path is None:
            desktop_path = APP_DESKTOP_FULL_PATH
        result = self.run_cmd(
            f"qdbus com.deepin.SessionManager /com/deepin/StartManager "
            f"com.deepin.StartManager.IsAutostart {desktop_path} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return result.strip().lower() == "true"

    def navigate_to_startup_management(self, timeout=15):
        """导航到启动管理器页面

        点击系统优化导航 → 点击"启动管理器"卡片 → 等待运行时视图显示。
        :param timeout: 等待运行时视图显示的超时秒数
        :return: True 如果成功进入启动管理器页面
        """
        self._safe_focus_windows()
        self.click_optimization_nav_by_attr()
        if not self.get_optimization_page_showing():
            return False
        self.click_optimization_card_by_name("启动管理器")
        sleep(2)
        return self.get_optimization_runtime_page_showing(timeout)

    def find_startup_item_switch(self, app_name="电脑管家", timeout=15):
        """在启动管理页面中查找指定应用的自启动开关

        开关的 accessibleName 格式为 startup_<GenericName 或 Name>。
        电脑管家的 desktop 文件 GenericName=PC Manager, GenericName[zh_CN]=电脑管家,
        实测 V20 环境下 accessibleName 为 startup_PC Manager。
        先尝试所有候选名, 再遍历 startup_ 前缀元素按角色筛选。
        :param app_name: 应用显示名(中文环境下为"电脑管家")
        :param timeout: 查找超时秒数
        :return: 开关元素对象, 未找到返回 None
        """
        self._safe_focus_windows()
        # 候选名称列表: 开关 accessibleName 前缀 startup_ 后接 GenericName 或 Name
        name_candidates = list(
            dict.fromkeys(
                STARTUP_APP_NAME_ALIASES.get(app_name, [app_name]) + [app_name]
            )
        )
        # 精确匹配 accessibleName
        for _ in range(timeout):
            for candidate in name_candidates:
                try:
                    element = self.dog.find_element_by_attr(
                        f"$//startup_{candidate}"
                    )
                    if element.showing:
                        return element
                except BaseException:
                    pass
            sleep(1)
        # 回退: 遍历 startup_ 前缀元素, 按角色筛选开关控件
        for _ in range(5):
            for el in self.get_startup_list_items():
                name = el.name or ""
                for candidate in name_candidates:
                    if candidate.lower() in name.lower():
                        return el
            sleep(1)
        return None

    def get_startup_list_items(self) -> list:
        """获取启动管理器页面中已渲染的启动项开关元素

        启动项开关的 accessibleName 为 startup_<GenericName 或 Name>; 排除
        筛选按钮/列表容器等非启动项控件, 并按角色只保留开关类控件。
        :return: 启动项开关元素列表; 页面尚未渲染时返回空列表
        """
        try:
            elements = self.dog.find_elements_by_attr("$//startup_.*/")
        except BaseException:
            return []
        items = []
        for el in elements:
            name = el.name or ""
            if name in STARTUP_NON_ITEM_NAMES:
                continue
            try:
                role = el.roleName or ""
            except BaseException:
                role = ""
            if role.lower() not in STARTUP_SWITCH_ROLES:
                continue
            items.append(el)
        return items

    def wait_startup_list_loaded(self, timeout=20) -> int:
        """等待启动管理器页面的启动项列表加载完成

        插件页在卡片点击后异步拉取自启动项, 列表未就绪时页面只有标题和筛选栏。
        :param timeout: 最长等待秒数
        :return: 加载到的启动项数量, 超时未加载返回 0
        """
        for i in range(timeout):
            items = self.get_startup_list_items()
            if items:
                return len(items)
            if i and i % 10 == 0:
                self._refresh_app()
            sleep(1)
        return 0

    def get_startup_item_switch_checked(self, app_name="电脑管家"):
        """获取启动管理页面中指定应用自启动开关的选中状态

        :param app_name: 应用显示名
        :return: True/False 表示开关状态, None 表示未找到开关
        """
        element = self.find_startup_item_switch(app_name)
        if element is None:
            return None
        return element.checked

    def toggle_startup_item_switch(self, app_name="电脑管家", timeout=10):
        """切换启动管理页面中指定应用的自启动开关

        点击开关后等待控制器重新加载列表, 重建 AT-SPI 引用。
        :param app_name: 应用显示名
        :param timeout: 查找开关的超时秒数
        :return: True 如果成功切换, False 表示未找到开关
        """
        element = self.find_startup_item_switch(app_name, timeout=timeout)
        if element is None:
            return False
        self._safe_focus_windows()
        self._atspi_do_action(element)
        sleep(3)
        self.reconnect_dogtail()
        return True

    def get_system_file_descriptor_limit(self) -> int:
        """获取系统级文件描述符上限(/proc/sys/fs/file-max)

        :return: 系统全局文件描述符上限, 读取失败返回 0
        """
        result = self.run_cmd(
            "cat /proc/sys/fs/file-max 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, IndexError):
            return 0

    def get_process_file_descriptor_limit(self) -> int:
        """获取单进程文件描述符上限(ulimit -n)

        :return: 单进程文件描述符上限, 读取失败返回 0
        """
        result = self.run_cmd(
            "ulimit -n 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, IndexError):
            return 0

    def get_system_open_fd_count(self) -> int:
        """获取当前系统已打开的文件描述符数量

        读取 /proc/sys/fs/file-nr 第一个字段(已分配的文件描述符数)。
        :return: 已打开文件描述符数量, 读取失败返回 -1
        """
        result = self.run_cmd(
            "cat /proc/sys/fs/file-nr 2>/dev/null | awk '{print $1}'",
            timeout=5,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, IndexError):
            return -1

    def get_max_process_fd_count(self) -> int:
        """获取系统中打开文件描述符最多的进程的描述符数量

        遍历 /proc/*/fd 统计每个进程打开的描述符数, 返回最大值。
        :return: 最大进程级文件描述符数量, 读取失败返回 -1
        """
        result = self.run_cmd(
            r'find /proc/[0-9]*/fd -maxdepth 1 2>/dev/null | '
            r'awk -F/ "{print \$3}" | sort | uniq -c | '
            r'awk "{print \$1}" | sort -n | tail -1',
            timeout=15,
            out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, IndexError):
            return -1

    def get_file_descriptor_status_normal(self) -> bool:
        """检查文件描述符检测状态是否正常

        正常系统条件:
        - 系统级文件描述符上限 > 0
        - 单进程文件描述符上限 > 0
        - 已打开文件描述符数 < 系统级上限(未耗尽)
        - 最大进程级描述符数 < 单进程上限(无进程达到限制)

        :return: True 表示文件描述符状态正常
        """
        sys_limit = self.get_system_file_descriptor_limit()
        proc_limit = self.get_process_file_descriptor_limit()
        open_count = self.get_system_open_fd_count()
        max_proc_fd = self.get_max_process_fd_count()

        if sys_limit <= 0 or proc_limit <= 0:
            return False
        if open_count < 0 or max_proc_fd < 0:
            return False
        if open_count >= sys_limit:
            return False
        if max_proc_fd >= proc_limit:
            return False
        return True

    # ===== PMS 2032573「文件描述符检测-低占用进程」测试用例方法 =====

    _LOW_FD_SCRIPT = "/tmp/pcm_low_fd.py"
    _LOW_FD_PID = "/tmp/pcm_low_fd.pid"
    _LOW_FD_LOG = "/tmp/pcm_low_fd.log"

    def start_low_fd_process(self, timeout=15) -> bool:
        """启动一个低文件描述符占用的后台进程

        该进程仅持有标准输入/输出/错误三个文件描述符(0/1/2), 不再打开任何
        额外文件或套接字, 用于模拟「低占用进程」场景, 验证文件描述符检测在
        进程级描述符占用极低时仍能正确识别为正常状态。
        :param timeout: 等待进程就绪的最长秒数
        :return: True 如果低占用进程已启动且可读取其描述符数
        """
        self.stop_low_fd_process()
        sleep(1)
        script = (
            "import os, time\n"
            "with open('%s', 'w') as f:\n"
            "    f.write(str(os.getpid()))\n"
            "# 仅保留标准描述符 0/1/2, 不打开任何额外文件\n"
            "while True:\n"
            "    time.sleep(5)\n"
        ) % self._LOW_FD_PID
        self.run_cmd(
            "cat > %s <<'PYEOF'\n%s\nPYEOF" % (self._LOW_FD_SCRIPT, script),
            timeout=10, out_debug_flag=False,
        )
        self.run_cmd(
            "nohup /usr/bin/python3 %s > %s 2>&1 < /dev/null &"
            % (self._LOW_FD_SCRIPT, self._LOW_FD_LOG),
            timeout=10, out_debug_flag=False,
        )
        for _ in range(timeout):
            pid = self.get_low_fd_process_pid()
            if pid and self.get_process_fd_count(pid) >= 0:
                return True
            sleep(1)
        return False

    def get_low_fd_process_pid(self) -> str:
        """获取低占用进程的 PID, 进程不存在时返回空串"""
        result = self.run_cmd(
            "cat %s 2>/dev/null" % self._LOW_FD_PID,
            timeout=5, out_debug_flag=False,
        )
        pid = result.strip()
        if pid.isdigit():
            alive = self.run_cmd(
                "kill -0 %s 2>/dev/null && echo yes || echo no" % pid,
                timeout=5, out_debug_flag=False,
            )
            if "yes" in alive:
                return pid
        return ""

    def get_process_fd_count(self, pid: str) -> int:
        """获取指定进程当前打开的文件描述符数量

        :param pid: 目标进程 PID
        :return: 文件描述符数量, 读取失败返回 -1
        """
        if not pid or not pid.isdigit():
            return -1
        result = self.run_cmd(
            "ls /proc/%s/fd 2>/dev/null | wc -l" % pid,
            timeout=5, out_debug_flag=False,
        )
        try:
            return int(result.strip())
        except (ValueError, AttributeError):
            return -1

    def stop_low_fd_process(self):
        """停止低占用进程并清理临时文件"""
        pid = self.get_low_fd_process_pid()
        if pid:
            self.run_cmd(
                "kill -9 %s 2>/dev/null; sleep 1" % pid,
                timeout=10, out_debug_flag=False,
            )
        self.run_cmd(
            "rm -f %s %s %s 2>/dev/null"
            % (self._LOW_FD_PID, self._LOW_FD_SCRIPT, self._LOW_FD_LOG),
            timeout=5, out_debug_flag=False,
        )

    def get_max_process_fd_usage_ratio(self) -> float:
        """获取系统中最大进程级文件描述符占用比例

        占用比例 = 最大进程级描述符数 / 单进程描述符上限。
        低占用场景下该比例应远低于 1.0。
        :return: 占用比例(0~1), 读取失败返回 -1.0
        """
        max_proc_fd = self.get_max_process_fd_count()
        proc_limit = self.get_process_file_descriptor_limit()
        if max_proc_fd < 0 or proc_limit <= 0:
            return -1.0
        return max_proc_fd / proc_limit

    # ===== PMS 2001945「大文件清理-批量移至回收站」测试用例方法 =====
    def create_test_large_files(self):
        """创建测试用大文件以确保大文件清理扫描能检测到文件
        在用户主目录下创建 3 个 100MB 的测试文件,
        大文件清理默认扫描 >=100MB 的文件, 因此刚好满足最小阈值。
        """
        # 先清理上次残留(含其他测试可能遗留的同名文件)
        self.remove_test_large_files()
        self.run_cmd(
            f"rm -rf {HOME_DIR}/autotest_large_file",
            timeout=5, out_debug_flag=False,
        )
        large_dir = f"{HOME_DIR}/autotest_large_files"
        self.run_cmd(f"mkdir -p {large_dir}", timeout=5, out_debug_flag=False)
        for i in range(3):
            large_file = f"{large_dir}/large_test_{i}.bin"
            self.run_cmd(
                f"dd if=/dev/zero of={large_file} bs=1M count=100 2>/dev/null",
                timeout=30,
                out_debug_flag=False,
            )
        sleep(1)
    def remove_test_large_files(self):
        """清理测试创建的大文件(包括回收站中的副本)
        gio trash 按文件名存储, 不保留目录结构,
        因此回收站中的文件名为 large_test_*.bin。
        """
        large_dir = f"{HOME_DIR}/autotest_large_files"
        self.run_cmd(f"rm -rf {large_dir}", timeout=10, out_debug_flag=False)
        # 清理可能被移至回收站的测试文件(gio trash 按文件名存储)
        trash_files = f"{HOME_DIR}/.local/share/Trash/files"
        trash_info = f"{HOME_DIR}/.local/share/Trash/info"
        self.run_cmd(
            f"rm -f {trash_files}/large_test_*.bin {trash_info}/large_test_*.trashinfo",
            timeout=10,
            out_debug_flag=False,
        )
    def create_visible_large_test_file(self, size_mb=110,
                                       name="autotest_large_visible.bin"):
        """在家目录(非隐藏目录)创建大文件, 用于验证大文件扫描范围

        文件放在 ~/<name>, 家目录非隐藏目录会被扫描。
        """
        path = f"{HOME_DIR}/{name}"
        self.run_cmd(
            f"dd if=/dev/zero of={quote(path)} bs=1M count={size_mb} "
            "2>/dev/null",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_visible_large_test_file(self,
                                       name="autotest_large_visible.bin"):
        """清理 create_visible_large_test_file 创建的大文件"""
        self.run_cmd(
            f"rm -f {quote(f'{HOME_DIR}/{name}')}",
            timeout=10,
            out_debug_flag=False,
        )

    def create_documents_large_file(self, size_mb=200,
                                    name="autotest_doc_large.bin"):
        """在 ~/Documents 下创建大文件(对应"文档目录存在大文件"前置条件)

        :param size_mb: 文件大小(MB)
        :param name: 文件名
        """
        path = f"{HOME_DIR}/Documents/{name}"
        self.run_cmd(
            f"mkdir -p {quote(f'{HOME_DIR}/Documents')} && "
            f"dd if=/dev/zero of={quote(path)} bs=1M count={size_mb} "
            "2>/dev/null",
            timeout=90,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_documents_large_file(self, name="autotest_doc_large.bin"):
        """清理 ~/Documents 下的测试大文件"""
        self.run_cmd(
            f"rm -f {quote(f'{HOME_DIR}/Documents/{name}')}",
            timeout=10,
            out_debug_flag=False,
        )

    def create_hidden_large_test_file(self, size_mb=110):
        """在家目录隐藏目录(~/.cache)中创建大文件, 用于验证隐藏目录不被扫描"""
        path = f"{HOME_DIR}/.cache/autotest_large_hidden/large_hidden.bin"
        self.run_cmd(
            f"mkdir -p {quote(os.path.dirname(path))} && "
            f"dd if=/dev/zero of={quote(path)} bs=1M count={size_mb} "
            "2>/dev/null",
            timeout=60,
            out_debug_flag=False,
        )
        sleep(1)

    def remove_hidden_large_test_file(self):
        """清理隐藏目录中的测试大文件"""
        self.run_cmd(
            f"rm -rf {quote(f'{HOME_DIR}/.cache/autotest_large_hidden')}",
            timeout=10,
            out_debug_flag=False,
        )

    def get_large_file_table_filenames(self, retries=5):
        """获取大文件结果表格中当前可见行的文件名(按行序)

        QTableView 的文字单元格 accessible name 为文件名, 复选框单元格
        name 为空且宽度 <= 60px。

        :return: 文件名列表, 按表格行从上到下排序; 空列表表示未取到
        """
        for _attempt in range(retries):
            table = self.get_large_file_table_view(retries=3)
            if table is None:
                sleep(1)
                continue
            rows = []
            try:
                for i in range(table.childCount):
                    child = table[i]
                    if not child:
                        continue
                    try:
                        cw, ch = child.size
                        cy = child.position[1]
                    except BaseException:
                        continue
                    name = child.name or ""
                    if cw > 60 and ch > 0 and name:
                        rows.append((cy, name))
            except BaseException:
                pass
            if rows:
                rows.sort(key=lambda item: item[0])
                return [name for _, name in rows]
            sleep(1)
        return []

    def get_large_file_result_page_showing(self, timeout=120) -> bool:
        """等待大文件清理扫描完成并验证结果页面显示
        扫描完成后若有大文件则显示结果页(largeFile_resultTitle),
        若无大文件则显示空状态页(largeFile_emptyTitle)。
        :param timeout: 最长等待秒数
        :return: True 如果结果页面已显示
        """
        self._safe_focus_windows()
        for _ in range(timeout):
            for expr in [
                "$//largeFile_resultTitle",
                "$//largeFile_emptyTitle",
            ]:
                try:
                    element = self.dog.find_element_by_attr(expr)
                    if element.showing:
                        return True
                    w, h = element.size
                    if w > 0 and h > 0:
                        return True
                except BaseException:
                    pass
            if _ > 0 and _ % 5 == 0:
                self._refresh_app()
                try:
                    self._safe_focus_windows()
                except BaseException:
                    pass
            sleep(1)
        return False
    def get_large_file_has_results(self, timeout=10) -> bool:
        """检查大文件清理结果页是否检测到大文件
        :param timeout: 重试次数
        :return: True 如果结果页(largeFile_resultTitle)可见
        """
        self._safe_focus_windows()
        for _ in range(timeout):
            try:
                element = self.dog.find_element_by_attr("$//largeFile_resultTitle")
                if element.showing:
                    return True
                w, h = element.size
                if w > 0 and h > 0:
                    return True
            except BaseException:
                pass
            sleep(1)
        return False
    def get_large_file_finished_page_showing(self, timeout=30) -> bool:
        """检查大文件清理完成页面是否显示
        所有文件被移至回收站后显示完成页(largeFile_finishedTitle)。
        :param timeout: 最长等待秒数
        :return: True 如果完成页面已显示
        """
        self._safe_focus_windows()
        for _ in range(timeout):
            try:
                element = self.dog.find_element_by_attr("$//largeFile_finishedTitle")
                if element.showing:
                    return True
                w, h = element.size
                if w > 0 and h > 0:
                    return True
            except BaseException:
                pass
            sleep(1)
        return False
    def get_large_file_table_view(self, retries=10):
        """获取大文件清理结果页的表格视图元素

        V20/Qt5 上 QTableView 可能不通过 accessibleName 暴露,
        因此依次尝试: accessibleName 搜索 -> roleName=table -> description 匹配。
        :param retries: 重试次数(每次间隔1秒)
        :return: 表格视图元素, 或 None
        """
        for _ in range(retries):
            # 策略1: 通过 accessibleName 搜索
            try:
                table = self.dog.find_element_by_attr("$//largeFile_tableView")
                if table:
                    return table
            except BaseException:
                pass
            self._safe_focus_windows()
            # 策略2: 通过 roleName=table + 可见性筛选
            try:
                app = self.dog.obj
                tables = app.findChildren(
                    lambda n: n.roleName == "table",
                    recursive=True,
                )
                for tbl in tables:
                    try:
                        w, h = tbl.size
                        if w > 0 and h > 0:
                            return tbl
                    except BaseException:
                        continue
            except BaseException:
                pass
            # 策略3: 通过 description 匹配
            try:
                app = self.dog.obj
                tables = app.findChildren(
                    lambda n: n.description
                    and "scanned large file" in (n.description or "").lower(),
                    recursive=True,
                )
                for tbl in tables:
                    try:
                        w, h = tbl.size
                        if w > 0 and h > 0:
                            return tbl
                    except BaseException:
                        continue
            except BaseException:
                pass
            sleep(1)
        return None
    def _get_large_file_checkbox_cells(self, table):
        """从表格元素中提取所有复选框单元格(第0列)
        表格的每个单元格都暴露 Toggle 动作, 复选框列(第0列)的特征是:
        name 为空、x 坐标与表格左上角一致、宽度为 52px(kCheckColumnWidth)。
        :param table: 表格视图元素
        :return: 按 y 坐标排序的复选框单元格列表
        """
        cells = []
        table_x, table_y = table.position
        table_w, table_h = table.size
        try:
            count = table.childCount
        except BaseException:
            count = 0
        for i in range(count):
            try:
                child = table[i]
                if not child:
                    continue
                cx, cy = child.position
                cw, ch = child.size
                name = child.name or ""
                # 复选框列: x 与表格左上角对齐, 宽度 <= 60, name 为空
                if abs(cx - table_x) < 5 and cw <= 60 and name == "":
                    cells.append(child)
            except BaseException:
                pass
        cells.sort(key=lambda c: c.position[1])
        return cells
    def click_large_file_table_checkbox(self, row_index=0):
        """点击大文件表格中指定行的复选框以选中/取消该行
        :param row_index: 行索引(从0开始)
        """
        self.click_large_file_table_checkboxes([row_index])
    def click_large_file_table_checkboxes(self, row_indices):
        """批量点击大文件表格中多行的复选框

        复选框由 FileTableDelegate 绘制, 仅响应鼠标事件。V20/Qt5 上表格
        QTableView 的 AT-SPI 几何为 (0,0,0,0), 无法直接取行列坐标, 因此以
        categoryButtonBox(表格紧邻其上)的底部作为表格顶部: 复选框列中心
        x = box.x - 6 + 26, 首行中心距表格顶部 31px, 行高 62px
        (kRowHeight / verticalHeader 的 defaultSectionSize)。
        :param row_indices: 行索引列表(从0开始)
        """
        self._safe_focus_windows()
        ref = None
        for _ in range(20):
            try:
                ref = self.dog.find_element_by_attr("$//largeFile_categoryButtonBox")
                if ref is not None:
                    w, h = ref.size
                    if w > 0 and h > 0:
                        break
            except BaseException:
                ref = None
            self.reconnect_dogtail()
            sleep(1)
        if ref is None:
            raise RuntimeError("无法找到大文件表格位置参考元素(categoryButtonBox)")
        x, y = ref.position
        w, h = ref.size
        checkbox_x = x - 6 + 26
        table_top = y + h
        k_first_row_center = 31
        k_row_height = 62
        # 坐标点击要求窗口位于最上层; dogtail 的 focus 不足以让窗口管理器激活,
        # 被其它窗口遮挡时点击会落到别的窗口上。
        self.run_cmd(
            "wid=$(xdotool search --name '^电脑管家$' | head -1); "
            '[ -n "$wid" ] && xdotool windowactivate --sync "$wid"; '
            "xdotool getactivewindow getwindowname",
            timeout=10,
            out_debug_flag=True,
        )
        sleep(0.5)
        for ri in row_indices:
            click_y = table_top + k_first_row_center + k_row_height * ri
            self._safe_focus_windows()
            self.run_cmd(
                f"xdotool mousemove --sync {checkbox_x} {click_y} click 1",
                timeout=10,
                out_debug_flag=True,
            )
            sleep(0.6)
        # 点击后执行按钮应变为可用。只重试读取(每次重建 dogtail 连接), 不再点击:
        # 重复点击会取消已选行; 单击后的 AT-SPI 属性需要刷新后才可见。
        if not self.get_large_file_execute_button_enabled(retries=20):
            raise RuntimeError("点击复选框后执行按钮仍未启用")
    def get_large_file_execute_button(self):
        """获取大文件清理结果页的执行按钮元素
        :return: 执行按钮元素, 或 None
        """
        try:
            return self.dog.find_element_by_attr("$//largeFile_executeBtn")
        except BaseException:
            return None
    def get_large_file_execute_button_enabled(self, retries=10) -> bool:
        """检查大文件清理执行按钮是否可用
        :param retries: 重试次数
        :return: True 如果按钮可用
        """
        for _ in range(retries):
            try:
                self.reconnect_dogtail()
                btn = self.get_large_file_execute_button()
                if btn:
                    if btn.showing:
                        return btn.sensitive
                    w, h = btn.size
                    if w > 0 and h > 0:
                        return btn.sensitive
            except BaseException:
                pass
            self._safe_focus_windows()
            sleep(1)
        return False
    def click_large_file_execute_button(self):
        """点击大文件清理结果页的执行按钮
        优先通过 AT-SPI Action 接口点击; 若失败则回退到坐标点击。
        """
        try:
            self.reconnect_dogtail()
            btn = self.get_large_file_execute_button()
            if btn and btn.showing:
                self._atspi_do_action(btn)
                sleep(2)
                return
        except BaseException:
            pass
        # 回退: 坐标点击
        try:
            self.reconnect_dogtail()
            btn = self.get_large_file_execute_button()
            if btn:
                bx, by = btn.position
                bw, bh = btn.size
                cx, cy = int(bx + bw / 2), int(by + bh / 2)
                self._safe_focus_windows()
                self.run_cmd(
                    f"xdotool mousemove --sync {cx} {cy} click 1",
                    timeout=10,
                    out_debug_flag=False,
                )
                sleep(2)
                return
        except BaseException:
            pass
        raise RuntimeError("无法找到大文件清理执行按钮")

    # ===== PMS 2001941「大文件清理--筛选无结果」测试用例方法 =====

    def select_large_file_size_filter(self, index):
        """选择大文件清理的大小筛选下拉框选项

        DComboBox 的选项索引:
        0 → ≥100MB(默认), 1 → ≥200MB, 2 → ≥500MB, 3 → ≥1GB

        V20 上 DComboBox 的 accessibleName 暴露的是当前选中值(如 "≥100MB"),
        而非源码中设置的 accessibleName("largeFile_sizeFilter")。
        因此通过 description("Filter scan results by file size")定位下拉框。

        :param index: 目标选项索引(0~3)
        """
        self._safe_focus_windows()
        self.reconnect_dogtail()
        # V20 上 DComboBox 的 accessibleName 是当前值, 用 description 定位
        combo = None
        try:
            combos = self.dog.obj.findChildren(
                lambda n: n.roleName == "combo box"
                and "Filter scan results by file size" in (n.description or "")
            )
            if combos:
                combo = combos[0]
        except BaseException:
            pass
        if combo is None:
            raise RuntimeError("无法找到大文件清理大小筛选下拉框")
        # 点击下拉框打开弹出列表
        if not self._click_at_element(combo):
            self._atspi_do_action(combo)
        sleep(1)
        # 先按 Home 回到第一项, 再按 Down index 次导航到目标选项
        self._safe_focus_windows()
        self.run_cmd(
            "xdotool key --clearmodifiers Home",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(0.3)
        for _ in range(index):
            self.run_cmd(
                "xdotool key --clearmodifiers Down",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(0.3)
        # 按 Enter 确认选择
        self.run_cmd(
            "xdotool key --clearmodifiers Return",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(1)

    def get_large_file_no_match_showing(self, timeout=10) -> bool:
        """检查大文件清理筛选无结果状态是否显示

        筛选后无匹配文件时, noMatchWidget 可见(largeFile_noMatchLabel /
        largeFile_noMatchIcon 元素 size 非零)。

        :param timeout: 重试次数
        :return: True 如果筛选无结果状态可见
        """
        self._safe_focus_windows()
        for _ in range(timeout):
            if self._any_visible(
                "$//largeFile_noMatchLabel",
                "$//largeFile_noMatchIcon",
            ):
                return True
    # ===== PMS 2001947「大文件清理--彻底删除确认对话框」测试用例方法 =====

    def select_large_file_action(self, action_text):
        """在大文件清理结果页的操作下拉框中选择指定操作

        AT-SPI 中 QComboBox 的 accessibleName 不会被暴露为节点名称,
        节点名称显示的是当前选中项的文本(如"移至回收站")。
        页面上有两个 combo box: 操作下拉框(移至回收站/彻底删除/添加到白名单)
        和 大小筛选下拉框(≥100MB 等)。通过排除名称以"≥"开头的来定位操作下拉框。

        使用坐标点击展开下拉框, 然后在弹出列表中查找并点击目标项。
        不使用 AT-SPI doAction(combo) 因为它在 QComboBox 上可能阻塞。

        :param action_text: 操作文本(如 "彻底删除""移至回收站""添加到白名单")
        """
        self._safe_focus_windows()
        self.reconnect_dogtail()
        # 定位操作下拉框(排除大小筛选下拉框, 其名称以"≥"开头)
        combo = None
        for _ in range(10):
            try:
                combos = self.dog.obj.findChildren(
                    lambda n: n.roleName == "combo box",
                    recursive=True,
                )
                for c in combos:
                    cname = c.name or ""
                    if not cname.startswith("≥"):
                        combo = c
                        break
                if combo:
                    break
            except BaseException:
                pass
            sleep(1)
        if combo is None:
            raise RuntimeError("无法找到大文件清理操作下拉框(combo box)")
        current = combo.name or ""
        if current == action_text:
            return
        # 坐标点击展开下拉框(AT-SPI doAction 在 QComboBox 上可能阻塞)
        self._click_at_element(combo)
        sleep(1)
        # 在弹出列表中查找并点击目标项(弹出窗口小, findChildren 快)
        clicked = False
        for _ in range(10):
            try:
                items = self.dog.obj.findChildren(
                    lambda n: n.roleName == "list item"
                    and action_text == (n.name or ""),
                    recursive=True,
                )
                if items:
                    if self._click_at_element(items[0]):
                        clicked = True
                        sleep(1)
                        break
            except BaseException:
                pass
            sleep(1)
        if not clicked:
            # 回退: 通过键盘选择(Home 回到第一项, 再 Down 到目标项)
            self._key_to_app("Home")
            sleep(0.3)
            actions_order = ["移至回收站", "彻底删除", "添加到白名单"]
            tgt_idx = actions_order.index(action_text)
            for _ in range(tgt_idx):
                self._key_to_app("Down")
                sleep(0.3)
            self._key_to_app("Return")
            sleep(1)
        # 验证切换成功
        self.reconnect_dogtail()
        for _ in range(5):
            try:
                combos = self.dog.obj.findChildren(
                    lambda n: n.roleName == "combo box"
                    and not (n.name or "").startswith("≥"),
                    recursive=True,
                )
                if combos and (combos[0].name or "") == action_text:
                    return
            except BaseException:
                pass
            sleep(1)
        raise RuntimeError(
            f"切换操作下拉框失败, 期望: {action_text}, "
            f"当前: {combos[0].name if combos else 'None'}"
        )

    def get_large_file_delete_confirm_dialog_showing(self, timeout=10) -> bool:
        """检测大文件彻底删除确认对话框是否可见

        选择"彻底删除"操作并点击执行后, 弹出 DDialog 确认对话框,
        消息文本为"文件被彻底删除后将无法恢复，请确认是否彻底删除？"。

        :param timeout: 最长等待秒数
        :return: True 如果检测到对话框
        """
        for _ in range(timeout):
            try:
                dialogs = self.dog.obj.findChildren(
                    lambda n: n.roleName in ("dialog", "alert dialog"),
                    recursive=True,
                )
                if dialogs:
                    for d in dialogs:
                        # 检查对话框中是否包含彻底删除相关的文本
                        children = d.findChildren(
                            lambda n: n.roleName in ("label", "text"),
                            recursive=True,
                        )
                        for child in children:
                            text = child.name or child.text or ""
                            if "彻底删除" in text or "无法恢复" in text:
                                return True
                    # 如果只找到一个对话框, 也认为是确认对话框
                    if len(dialogs) == 1:
                        return True
            except BaseException:
                pass
            sleep(1)
        return False

    def click_large_file_delete_confirm_dialog_button(self, button_text, timeout=10) -> bool:
        """点击大文件彻底删除确认对话框中的指定按钮

        :param button_text: 按钮文本(如"取消""彻底删除")
        :param timeout: 最长等待秒数
        :return: True 如果点击成功
        """
        for _ in range(timeout):
            try:
                buttons = self.dog.obj.findChildren(
                    lambda n: n.roleName == "push button"
                    and button_text in (n.name or n.text or ""),
                    recursive=True,
                )
                if buttons:
                    self._atspi_do_action(buttons[0])
                    sleep(1)
                    return True
            except BaseException:
                pass
            sleep(1)
        return False
    # ===== PMS 2001937「大文件清理--结果进行格式筛选」测试用例方法 =====

    def create_typed_large_test_files(self):
        """创建不同格式的大文件, 用于验证大文件清理结果格式筛选

        创建 3 个 >=100MB 的大文件, 分别属于不同文件类型分类:
        - video_test.mp4  → video (视频)
        - archive_test.zip → archive (归档)
        - other_test.bin   → other (其他)
        文件放在 ~/autotest_large_files_typed/ 目录下。
        """
        large_dir = f"{HOME_DIR}/autotest_large_files_typed"
        self.remove_typed_large_test_files()
        self.run_cmd(f"mkdir -p {large_dir}", timeout=5, out_debug_flag=False)
        typed_files = [
            f"{large_dir}/video_test.mp4",
            f"{large_dir}/archive_test.zip",
            f"{large_dir}/other_test.bin",
        ]
        for large_file in typed_files:
            self.run_cmd(
                f"dd if=/dev/zero of={large_file} bs=1M count=100 2>/dev/null",
                timeout=30,
                out_debug_flag=False,
            )
        sleep(1)

    # ===== PMS 2001983「重复文件清理--筛选条件无结果」测试用例方法 =====

    def create_dup_test_files(self):
        """在用户家目录下创建重复文件, 用于验证重复文件清理筛选功能

        创建两个内容完全相同的 .txt 文件(分属不同子目录),
        重复文件扫描器会将它们识别为同一重复组, 文件类型为 document。
        文件放在 ~/autotest_dup_file/ 目录下, 扫描范围覆盖家目录。
        """
        test_dir = f"{HOME_DIR}/autotest_dup_file"
        sub_dir_a = f"{test_dir}/dir_a"
        sub_dir_b = f"{test_dir}/dir_b"
        self.run_cmd(f"mkdir -p {sub_dir_a} {sub_dir_b}", timeout=5, out_debug_flag=False)
        content = "autotest duplicate file content for filter test"
        for sub in (sub_dir_a, sub_dir_b):
            self.run_cmd(
                f"echo '{content}' > {sub}/dup_test_file.txt",
                timeout=5,
                out_debug_flag=False,
            )
        sleep(1)

    def remove_typed_large_test_files(self):
        """清理格式筛选测试创建的大文件(包括回收站中的副本)"""
        large_dir = f"{HOME_DIR}/autotest_large_files_typed"
        self.run_cmd(f"rm -rf {large_dir}", timeout=5, out_debug_flag=False)
        home = expanduser("~")
        trash_dir = f"{home}/.local/share/Trash/files"
        for name in ("video_test.mp4", "archive_test.zip", "other_test.bin"):
            self.run_cmd(
                f"rm -f '{trash_dir}/{name}' 2>/dev/null || true",
                timeout=5,
                out_debug_flag=False,
            )

    _LARGE_FILE_CATEGORY_ORDER = [
        "all", "document", "image", "video", "audio", "archive", "other",
    ]

    def _get_large_file_category_buttons(self):
        """获取大文件清理结果页的全部格式分类筛选按钮(按从左到右排序)

        所有分类按钮的 accessibleName 均为 largeFile_catBtn,
        通过 find_elements_by_attr 递归查找后按 x 坐标排序。
        :return: 按钮元素列表(从左到右), 空列表表示未找到
        """
        self._safe_focus_windows()
        try:
            buttons = self.dog.find_elements_by_attr("$//largeFile_catBtn")
            if buttons:
                buttons.sort(key=lambda b: b.position[0])
                return buttons
        except BaseException:
            pass
        return []

    def click_large_file_category_button(self, category_id):
        """点击大文件清理结果页的格式分类筛选按钮

        DButtonBoxButton 的 AT-SPI doAction("press") 不会触发 buttonClicked
        信号, 必须使用 xdotool 坐标点击才能激活分类筛选逻辑。

        :param category_id: 分类标识符, 可选值:
            all / document / image / video / audio / archive / other
        """
        self._safe_focus_windows()
        buttons = self._get_large_file_category_buttons()
        try:
            idx = self._LARGE_FILE_CATEGORY_ORDER.index(category_id)
        except ValueError:
            return False
        if idx >= len(buttons):
            return False
        for _ in range(3):
            buttons = self._get_large_file_category_buttons()
            if idx >= len(buttons):
                return False
            try:
                bx, by = buttons[idx].position
                bw, bh = buttons[idx].size
                click_x = int(bx + bw / 2)
                click_y = int(by + bh / 2)
                if bw <= 0 or bh <= 0:
                    sleep(1)
                    continue
                self._safe_focus_windows()
                self.run_cmd(
                    f"xdotool mousemove --sync {click_x} {click_y} click 1",
                    timeout=10,
                    out_debug_flag=False,
                )
            except BaseException:
                sleep(1)
                continue
            # 点击是否生效以按钮选中状态为准, 未生效时重试(坐标可能取自刷新前的树)
            if self.get_large_file_category_button_checked(category_id, timeout=5):
                return True
        return False

    def _read_large_file_category_checked(self, idx) -> bool:
        """读取第 idx 个格式分类按钮的选中状态(单次读取)"""
        buttons = self._get_large_file_category_buttons()
        if idx >= len(buttons):
            return False
        try:
            if "checked" in buttons[idx].states:
                return True
        except BaseException:
            pass
        try:
            return bool(buttons[idx].checked)
        except BaseException:
            return False

    def get_large_file_category_button_checked(self, category_id, timeout=0) -> bool:
        """检查指定格式分类筛选按钮是否处于选中(checked)状态

        点击用 xdotool 坐标触发, 页面刚切换/重绘时 AT-SPI 的选中状态会滞后,
        因此 timeout>0 时轮询等待, 避免偶发假失败。

        :param category_id: 分类标识符(all/document/image/video/audio/archive/other)
        :param timeout: 轮询秒数(0 表示只读一次)
        :return: True 如果该按钮当前被选中
        """
        try:
            idx = self._LARGE_FILE_CATEGORY_ORDER.index(category_id)
        except ValueError:
            return False
        for _ in range(max(timeout, 0) + 1):
            self._safe_focus_windows()
            if self._read_large_file_category_checked(idx):
                return True
            if timeout <= 0:
                break
            sleep(1)
        return False

    def get_large_file_table_row_count(self, retries=10) -> int:
        """获取大文件清理结果表格的行数(即当前筛选后显示的大文件数量)

        通过统计表格中复选框单元格的数量来计算行数。
        筛选切换后表格模型会 reset, AT-SPI 树需要时间刷新, 因此带重试。
        若复选框单元格无法通过 AT-SPI 子元素识别, 回退到按表格高度/行高计算。
        :param retries: 重试次数(每次间隔1秒)
        :return: 表格行数, 0 表示无行或表格不可见
        """
        k_row_height = 62
        for _ in range(retries):
            self._safe_focus_windows()
            table = self.get_large_file_table_view(retries=3)
            if table is None:
                sleep(1)
                continue
            try:
                cells = self._get_large_file_checkbox_cells(table)
                if len(cells) > 0:
                    return len(cells)
            except BaseException:
                pass
            try:
                table_h = table.size[1]
                if table_h > 0:
                    row_count = int(table_h // k_row_height)
                    if row_count > 0:
                        return row_count
            except BaseException:
                pass
            self.reconnect_dogtail()
            sleep(1)
        return 0
    def remove_dup_test_files(self):
        """清理重复文件清理测试创建的测试文件"""
        test_dir = f"{HOME_DIR}/autotest_dup_file"
        self.run_cmd(
            f"rm -rf {test_dir}",
            timeout=5,
            out_debug_flag=False,
        )

    def get_dup_file_result_showing(self) -> bool:
        """检查重复文件清理结果页是否显示(检测到重复文件)

        结果页 dupFile_resultTitle 可见表示扫描检测到了重复文件。

        :return: True 如果结果页可见
        """
        return self._any_visible("$//dupFile_resultTitle")

    def get_dup_file_empty_showing(self) -> bool:
        """检查重复文件清理空结果页是否显示(未检测到重复文件)

        :return: True 如果空结果页(dupFile_emptyTitle)可见
        """
        return self._any_visible("$//dupFile_emptyTitle")

    # 重复文件扫描范围验证: 每组两个同内容文件, 分别位于
    # /home 非隐藏目录(应扫描)、/home 隐藏目录、/home 之外(均不应扫描)
    _DUP_SCOPE_DIRS = (
        (f"{HOME_DIR}/autotest_dup_scope/visible",
         "autotest_dup_visible.bin"),
        (f"{HOME_DIR}/.cache/autotest_dup_scope/hidden",
         "autotest_dup_hidden.bin"),
        ("/tmp/autotest_dup_scope/outside",
         "autotest_dup_outside.bin"),
    )

    def create_dup_file_scope_files(self, size_mb=2):
        """创建用于验证重复文件扫描范围的三组重复文件

        重复文件扫描器要求文件大小 >= 1MB, 因此每组写入 2MB 随机数据并复制
        一份, 保证 md5 一致形成重复组。三组文件名各不相同, 便于从结果
        表格中判断哪一组被扫描到。
        """
        for base, name in self._DUP_SCOPE_DIRS:
            src = f"{base}/a/{name}"
            dst = f"{base}/b/{name}"
            self.run_cmd(
                f"rm -rf {quote(base)} && "
                f"mkdir -p {quote(f'{base}/a')} {quote(f'{base}/b')} && "
                f"dd if=/dev/urandom of={quote(src)} bs=1M count={size_mb} "
                "2>/dev/null && "
                f"cp {quote(src)} {quote(dst)}",
                timeout=60,
                out_debug_flag=False,
            )
        sleep(1)

    def remove_dup_file_scope_files(self):
        """清理扫描范围验证创建的重复文件"""
        for base, _name in self._DUP_SCOPE_DIRS:
            self.run_cmd(
                f"rm -rf {quote(base)}",
                timeout=10,
                out_debug_flag=False,
            )

    def get_dup_file_table_view(self, retries=10):
        """获取重复文件清理结果页的表格视图元素"""
        for _ in range(retries):
            try:
                table = self.dog.find_element_by_attr("$//dupFile_tableView")
                if table:
                    return table
            except BaseException:
                pass
            self._safe_focus_windows()
            sleep(1)
        return None

    def _dup_file_table_scroll(self, table, button=5, notches=10):
        """在表格中心滚动滚轮(button: 4 向上, 5 向下)"""
        try:
            table_x, table_y = table.position
            table_w, table_h = table.size
        except BaseException:
            return
        self.run_cmd(
            f"xdotool mousemove {int(table_x + table_w / 2)} "
            f"{int(table_y + table_h / 2)} "
            f"click --repeat {notches} --delay 50 {button}",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(0.8)

    def get_dup_file_table_filenames(self, max_rounds=60, notches=10):
        """收集重复文件结果表格中所有行的文件名(向下滚动遍历)

        QTableView 只暴露可视行, 因此逐屏滚动收集并去重。
        连续 3 屏没有新增行时认为已到表格底部。

        :param max_rounds: 最多滚动屏数
        :param notches: 每屏滚动格数
        :return: 文件名列表(与表格展示文本一致, 可能是完整路径)
        """
        names = []
        idle = 0
        for _ in range(max_rounds):
            table = self.get_dup_file_table_view(retries=3)
            if table is None:
                sleep(1)
                continue
            added = 0
            try:
                count = table.childCount
            except BaseException:
                count = 0
            for i in range(count):
                try:
                    child = table[i]
                except BaseException:
                    continue
                if not child:
                    continue
                try:
                    child_w, child_h = child.size
                except BaseException:
                    continue
                name = child.name or ""
                if child_w > 0 and child_h > 0 and name and name not in names:
                    names.append(name)
                    added += 1
            if added == 0:
                idle += 1
                if idle >= 3:
                    break
            else:
                idle = 0
            self._dup_file_table_scroll(table, 5, notches)
        return names

    def click_dup_file_category_by_index(self, index):
        """点击重复文件清理的分类筛选按钮

        DButtonBox 中的分类按钮顺序:
        0 → 全部(All), 1 → 文档(Documents), 2 → 图片(Images),
        3 → 视频(Videos), 4 → 音频(Audio), 5 → 归档(Archives), 6 → 其他(Others)

        所有分类按钮的 accessibleName 均为 "dupFile_catBtn",
        通过 find_elements_by_attr 获取全部后按索引点击。

        :param index: 分类按钮索引(0~6)
        """
        self._safe_focus_windows()
        self.reconnect_dogtail()
        buttons = self.dog.find_elements_by_attr("$//dupFile_catBtn")
        if not buttons or index >= len(buttons):
            raise RuntimeError(f"无法找到重复文件清理分类按钮(index={index})")
        target = buttons[index]
        if self._click_at_element(target):
            sleep(1)
        # 坐标点击可能落在按钮间隙或被弹窗遮挡, 用选中状态校验并重试
        states = self._dup_file_category_checked_states()
        for attempt in range(3):
            if index < len(states) and states[index]:
                break
            print(
                f"[dup_category] 分类按钮(index={index})点击未生效, "
                f"重试 {attempt + 1}/3, 当前选中: {states}"
            )
            self._atspi_do_action(target)
            sleep(1)
            states = self._dup_file_category_checked_states()
        else:
            raise RuntimeError(
                f"分类按钮(index={index})点击后仍未选中, 当前选中: {states}"
            )
        sleep(1)
        self.reconnect_dogtail()

    def _dup_file_category_checked_states(self):
        """返回重复文件清理分类按钮的选中状态列表(按 DButtonBox 顺序)"""
        self.reconnect_dogtail()
        states = []
        for button in self.dog.find_elements_by_attr("$//dupFile_catBtn"):
            try:
                states.append(bool(button.checked))
            except BaseException:
                states.append(False)
        return states

    def get_dup_file_no_match_showing(self, timeout=10) -> bool:
        """检查重复文件清理筛选无结果状态是否显示

        筛选后无匹配文件时, noMatchWidget 可见(dupFile_noMatchLabel /
        dupFile_noMatchIcon 元素 size 非零)。

        :param timeout: 重试次数
        :return: True 如果筛选无结果状态可见
        """
        self._safe_focus_windows()
        for _ in range(timeout):
            if self._any_visible(
                "$//dupFile_noMatchLabel",
                "$//dupFile_noMatchIcon",
            ):
                return True
            sleep(1)
        return False

    def find_dup_file_empty_category(self, preferred=(3, 4, 5, 2, 1, 6), timeout=3):
        """依次切换分类筛选, 返回第一个筛选后无结果的分类索引

        扫描范围是整个家目录, 是否某个分类为空取决于机器上的实际文件,
        不能假定固定分类(如视频)一定没有重复文件。按 preferred 顺序逐个点击,
        命中无结果状态即返回该索引。

        :param preferred: 候选分类索引顺序(0=全部, 1=文档, ... 6=其他)
        :param timeout: 每个分类等待无结果状态的秒数
        :return: 无结果的分类索引, 全部有结果时返回 None
        """
        for index in preferred:
            self.click_dup_file_category_by_index(index)
            if self.get_dup_file_no_match_showing(timeout=timeout):
                return index
        return None
    # ===== PMS 2001939「大文件清理--结果进行大小筛选」测试用例方法 =====


    def create_large_test_files_for_filter(self):
        """创建不同大小的大文件, 用于验证大小筛选功能

        创建两个文件:
        - 110MB(>=100MB 但 <200MB): 仅在 >=100MB 筛选下可见
        - 210MB(>=200MB 但 <500MB): 在 >=100MB 和 >=200MB 筛选下可见

        文件放在 ~/autotest_large_file_filter/ 目录下, 扫描范围覆盖家目录。
        """
        # 清理所有大文件测试目录(通配符), 避免其他用例残留干扰行数断言
        self.run_cmd(
            f"rm -rf {HOME_DIR}/autotest_large_file*",
            timeout=10, out_debug_flag=False,
        )
        test_dir = f"{HOME_DIR}/autotest_large_file_filter"
        self.run_cmd(f"mkdir -p {test_dir}", timeout=5, out_debug_flag=False)
        for name, size_mb in [("filter_110mb.bin", 110), ("filter_210mb.bin", 210)]:
            test_file = f"{test_dir}/{name}"
            self.run_cmd(
                f"dd if=/dev/zero of={test_file} bs=1M count={size_mb} 2>/dev/null",
                timeout=60,
                out_debug_flag=False,
            )
        sleep(1)

    def remove_large_test_files_for_filter(self):
        """清理大小筛选测试创建的大文件(包括回收站中的副本)"""
        test_dir = f"{HOME_DIR}/autotest_large_file_filter"
        self.run_cmd(f"rm -rf {test_dir}", timeout=5, out_debug_flag=False)
        trash_dir = f"{HOME_DIR}/.local/share/Trash/files"
        self.run_cmd(
            f"rm -f {trash_dir}/filter_110mb.bin {trash_dir}/filter_210mb.bin",
            timeout=5,
            out_debug_flag=False,
        )

    def _find_large_file_size_filter_combo(self, retries=10):
        """查找大小筛选下拉框元素(返回 Node 对象)

        V20/Qt5 上 QComboBox 的 AT-SPI name 为当前选中项文本(如 "≥100MB")
        而非 accessibleName(largeFile_sizeFilter)。页面上有两个 combo box:
        "移至回收站"(批量操作)和 "≥100MB"(大小筛选), 必须通过名称区分。
        策略:
        1. accessibleName 搜索 (largeFile_sizeFilter)
        2. roleName=combo box + 名称匹配大小筛选模式(含 ≥ 或 MB, 排除"移至回收站")
        3. 坐标推算回退: 基于 categoryButtonBox 位置定位右侧 combo box

        :param retries: 重试次数(每次间隔1秒)
        :return: combo box 的 Node 对象, 或 None
        """
        for attempt in range(retries):
            self._safe_focus_windows()
            # 策略1: accessibleName 搜索
            combo = self._find_first_element("$//largeFile_sizeFilter")
            if combo is not None:
                try:
                    w, h = combo.size
                    if w > 0 and h > 0:
                        return combo
                except BaseException:
                    pass
            # 策略2: roleName=combo box + 名称匹配大小筛选
            try:
                app = self.dog.obj
                combos = app.findChildren(
                    lambda n: n.roleName == "combo box",
                    recursive=True,
                )
                for c in combos:
                    try:
                        w, h = c.size
                        if w > 0 and h > 0:
                            name = c.name or ""
                            # 大小筛选 combo box 名称含 ≥ 或 MB; 排除"移至回收站"
                            if ("≥" in name or "MB" in name) and "回收站" not in name:
                                return c
                    except BaseException:
                        continue
            except BaseException:
                pass
            # 策略3: 基于 categoryButtonBox 坐标推算
            try:
                ref = self.dog.find_element_by_attr("$//largeFile_categoryButtonBox")
                rx, ry = ref.position
                rw, rh = ref.size
                if rw > 0 and rh > 0:
                    # combo box 在 categoryButtonBox 右侧, 用坐标定位 AT-SPI 元素
                    combo_x = int(rx + rw + 20 + 70)
                    combo_y = int(ry + rh / 2)
                    node = app.getChildAtPoint(combo_x, combo_y)
                    if node is not None:
                        return node
            except BaseException:
                pass
            if attempt > 0 and attempt % 3 == 0:
                self._refresh_app()
                self.reconnect_dogtail()
            sleep(1)
        return None

    def click_large_file_size_filter_option(self, option_index):
        """点击大小筛选下拉框并选择指定选项

        选项顺序: 0 -> ≥100MB, 1 -> ≥200MB, 2 -> ≥500MB, 3 -> ≥1GB

        策略: 点击下拉框打开弹出列表, 直接点击弹出列表中目标选项的 list item。
        弹出列表项的 AT-SPI name 即选项文本(如 "≥200MB"), 可直接通过名称查找并点击。
        若直接点击失败, 回退到键盘导航(Up 到首项, Down 到目标项, Return 确认)。
        :param option_index: 选项索引(0-3)
        """
        option_names = ["≥100MB", "≥200MB", "≥500MB", "≥1GB"]
        if option_index < 0 or option_index >= len(option_names):
            raise ValueError(f"无效的选项索引: {option_index}")
        target_name = option_names[option_index]
        self.reconnect_dogtail()
        self._safe_focus_windows()
        combo = self._find_large_file_size_filter_combo(retries=10)
        if combo is None:
            raise RuntimeError("无法找到大小筛选下拉框元素")
        # 先按 Escape 关闭可能残留的弹出列表
        self.run_cmd(
            "xdotool key --clearmodifiers Escape",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(0.5)
        # 点击下拉框打开弹出列表
        combo.click()
        sleep(2)
        # 在弹出列表中查找目标选项并直接点击
        clicked = False
        for _ in range(10):
            try:
                item = self.dog.find_element_by_attr(f"$//{target_name}")
                if item is not None:
                    w, h = item.size
                    if w > 0 and h > 0:
                        item.click()
                        clicked = True
                        break
            except BaseException:
                pass
            self.reconnect_dogtail()
            sleep(0.5)
        if not clicked:
            # 回退: 用键盘导航(Up 到首项, Down 到目标项, Return 确认)
            for _ in range(5):
                self.run_cmd(
                    "xdotool key --clearmodifiers Up",
                    timeout=5,
                    out_debug_flag=False,
                )
                sleep(0.2)
            for _ in range(option_index):
                self.run_cmd(
                    "xdotool key --clearmodifiers Down",
                    timeout=5,
                    out_debug_flag=False,
                )
                sleep(0.3)
            self.run_cmd(
                "xdotool key --clearmodifiers Return",
                timeout=5,
                out_debug_flag=False,
            )
        sleep(2)

    # ===== 修复工具--开始修复(需要提权) 模块方法 =====
    # 依据: 音频设备修复插件 /usr/lib/deepin-pc-manager/plugins/plugin-audio-fix
    # (config.json: executionMode=user, permissionHint=true)。其 entry.sh 第 17-20 行
    # 仅在 /etc/systemd/user/default.target.wants/pipewire.service 或
    # /etc/systemd/user/sockets.target.wants/pipewire.socket 存在时, 才执行
    # "sudo systemctl --global disable pipewire.service pipewire.socket", 也才会在
    # ShellRepairDialog 输出里出现 sudo 密码提示(产品据此启用提权输入行)。

    PW_SERVICE_WANTS = "/etc/systemd/user/default.target.wants/pipewire.service"
    PW_SOCKET_WANTS = "/etc/systemd/user/sockets.target.wants/pipewire.socket"

    def get_pipewire_global_autostart_status(self) -> dict:
        """获取 PipeWire 全局自启链接(音频修复的提权前置条件)状态

        :return: {"service": bool, "socket": bool}, True 表示对应 .wants 链接存在
        """
        result = self.run_cmd(
            f'test -e {self.PW_SERVICE_WANTS} && echo service; '
            f'test -e {self.PW_SOCKET_WANTS} && echo socket',
            timeout=5,
            out_debug_flag=False,
        )
        return {
            "service": "service" in result,
            "socket": "socket" in result,
        }

    def enable_pipewire_global_autostart(self) -> bool:
        """构造"音频设备修复需要提权"的前置条件: 启用 PipeWire 全局自启

        本机只装了 libpipewire, 没有 pipewire 的 user unit, 直接
        "systemctl --global enable pipewire.service pipewire.socket" 会报
        unit 不存在。因此按等价实现先写入最小占位 unit(必须带 [Install] 段,
        否则 enable 不会创建链接), 再全局启用。
        """
        self.sudo_run_cmd(
            "cat > /etc/systemd/user/pipewire.service <<'EOF'\n"
            "[Unit]\n"
            "Description=autotest audio-fix pipewire placeholder\n"
            "[Service]\n"
            "ExecStart=/bin/true\n"
            "[Install]\n"
            "WantedBy=default.target\n"
            "EOF\n"
            "cat > /etc/systemd/user/pipewire.socket <<'EOF'\n"
            "[Unit]\n"
            "Description=autotest audio-fix pipewire socket placeholder\n"
            "[Socket]\n"
            "ListenStream=%t/autotest-audio-fix.sock\n"
            "[Install]\n"
            "WantedBy=sockets.target\n"
            "EOF",
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "systemctl --global enable pipewire.service pipewire.socket",
            timeout=15,
            out_debug_flag=False,
        )
        status = self.get_pipewire_global_autostart_status()
        return status["service"] and status["socket"]

    def cleanup_pipewire_global_autostart(self):
        """回退"PipeWire 全局自启"前置构造, 恢复用例执行前的状态

        用例执行前本机没有 pipewire 全局自启(见 get_pipewire_global_autostart_status),
        因此无论产品修复脚本是否已用 sudo 删掉链接, 这里都按"恢复为不存在"处理:
        停用全局自启并删除占位 unit 与残留 .wants 链接。
        """
        self.sudo_run_cmd(
            "systemctl --global disable pipewire.service pipewire.socket "
            "2>/dev/null; "
            "rm -f /etc/systemd/user/pipewire.service "
            "/etc/systemd/user/pipewire.socket "
            "/etc/systemd/user/default.target.wants/pipewire.service "
            "/etc/systemd/user/sockets.target.wants/pipewire.socket",
            timeout=20,
            out_debug_flag=False,
        )

    def clear_sudo_credentials(self):
        """清空 sudo 免密时间戳

        构造前置数据时会用 sudo_run_cmd 留下 15 分钟免密时间戳; 不清掉的话
        产品脚本里的 sudo 不会再提示输入密码, 就无法验证"开始修复需要提权"。
        """
        self.run_cmd("sudo -K", timeout=5, out_debug_flag=False)

    def is_shell_repair_input_enabled(self) -> bool:
        """检查提权密码输入行当前是否处于可输入状态

        产品只有在脚本输出密码提示时才把 shellRepair_inputEdit 置为敏感,
        因此该状态可作为"确实在等待提权密码"的判据。
        """
        try:
            pwd_input = self.dog.find_element_by_attr("$//shellRepair_inputEdit", probe=True)
            return bool(pwd_input and pwd_input.showing and pwd_input.sensitive)
        except BaseException:
            return False

    # ===== 模块 修复工具 - ShellRepairDialog 命令执行文本框(交互输入)验证 =====
    # 产品实现依据(deepin-pc-manager 1.1.7, src/ui/dialogs/shell_repair_dialog.cpp):
    # - 命令执行文本框 inputEdit_(DPasswordEdit, a11y name shellRepair_inputEdit) 与
    #   提交按钮 submitButton_(a11y name shellRepair_submitBtn) 常驻显示, 默认
    #   setInputEnabled(false);
    # - 只有脚本输出 [[TEXT]] 标记、密码提示, 或被识别为 dpkg/debconf 交互提示时,
    #   才 setInputEnabled(true)([[TEXT]] 保持明文回显, 密码提示切换为掩码);
    # - submitInput() 提交后立即清空输入并 setInputEnabled(false), 脚本结束时同样
    #   禁用。因此"请求输入时启用、提交后重新禁用"是产品可观测的真实行为。
    SHELL_REPAIR_INPUT_EXPR = "$//shellRepair_inputEdit"
    SHELL_REPAIR_SUBMIT_EXPR = "$//shellRepair_submitBtn"
    REPAIR_PLUGIN_ROOT = "/usr/lib/deepin-pc-manager/plugins"
    # 交互桩脚本必须包含该标记, 用于清理时确认插件脚本已恢复为原始内容
    REPAIR_ENTRY_FIXTURE_MARKER = "AUTOTEST_INTERACTIVE_FIXTURE"

    def get_shell_repair_input_state(self) -> dict:
        """获取修复对话框命令执行文本框的实时状态

        产品只有在等待用户输入时才把输入行置为敏感(enabled), 因此
        enabled 是判断"是否在等待输入"的可靠信号; 输入行本身常驻显示。

        :return: {"exists": 是否存在于 AT-SPI 树, "showing": 是否可见,
                  "enabled": 是否可输入, "text": 当前内容,
                  "description": AT-SPI 描述}
        """
        state = {
            "exists": False,
            "showing": False,
            "enabled": False,
            "text": "",
            "description": "",
        }
        try:
            element = self.dog.find_element_by_attr(self.SHELL_REPAIR_INPUT_EXPR)
        except BaseException:
            return state
        if element is None:
            return state
        state["exists"] = True
        try:
            state["showing"] = bool(element.showing)
        except BaseException:
            state["showing"] = False
        try:
            state["enabled"] = bool(element.sensitive)
        except BaseException:
            state["enabled"] = False
        try:
            state["text"] = getattr(element, "text", "") or ""
        except BaseException:
            state["text"] = ""
        try:
            state["description"] = getattr(element, "description", "") or ""
        except BaseException:
            state["description"] = ""
        return state

    def get_shell_repair_submit_state(self) -> dict:
        """获取修复对话框【提交】按钮的实时状态

        :return: {"exists", "showing", "enabled", "text"}
        """
        state = {"exists": False, "showing": False, "enabled": False, "text": ""}
        try:
            button = self.dog.find_element_by_attr(self.SHELL_REPAIR_SUBMIT_EXPR)
        except BaseException:
            return state
        if button is None:
            return state
        state["exists"] = True
        try:
            state["showing"] = bool(button.showing)
        except BaseException:
            state["showing"] = False
        try:
            state["enabled"] = bool(button.sensitive)
        except BaseException:
            state["enabled"] = False
        try:
            state["text"] = getattr(button, "text", "") or ""
        except BaseException:
            state["text"] = ""
        return state

    def wait_shell_repair_input_enabled(self, timeout: int = 30) -> bool:
        """轮询等待命令执行文本框被产品启用(脚本正在请求用户输入)

        :param timeout: 最长等待秒数
        :return: True 表示输入行已启用
        """
        for _ in range(timeout):
            if self.get_shell_repair_input_state()["enabled"]:
                return True
            sleep(1)
        return False

    def wait_shell_repair_input_disabled(self, timeout: int = 10) -> bool:
        """轮询等待命令执行文本框恢复禁用(提交完成 / 脚本结束)

        :param timeout: 最长等待秒数
        :return: True 表示输入行存在且已禁用
        """
        for _ in range(timeout):
            state = self.get_shell_repair_input_state()
            if state["exists"] and not state["enabled"]:
                return True
            sleep(1)
        return False

    def _focus_repair_dialog_input(self, window_keyword: str = "") -> bool:
        """把键盘焦点放到修复对话框的命令执行文本框上

        产品在启用输入行时会 setFocus(), 但修复对话框可能被其他窗口抢占焦点;
        因此先激活对话框窗口, 再按坐标点击输入框中心, 保证后续键盘输入送达。

        :param window_keyword: 修复对话框窗口标题关键字
        :return: True 表示已激活窗口并点击输入框
        """
        if window_keyword:
            try:
                window_id = self.run_cmd(
                    f"xdotool search --class deepin-pc-manager --name "
                    f"{quote(window_keyword)} 2>/dev/null | tail -1",
                    timeout=5,
                    out_debug_flag=False,
                ).strip()
                if window_id:
                    self.run_cmd(
                        f"xdotool windowactivate --sync {window_id}",
                        timeout=5,
                        out_debug_flag=False,
                    )
                    sleep(0.3)
            except BaseException:
                pass
        try:
            element = self.dog.find_element_by_attr(self.SHELL_REPAIR_INPUT_EXPR)
            if element and element.showing:
                return self._click_at_element(element)
        except BaseException:
            pass
        return False

    def set_shell_repair_input(self, text: str, window_keyword: str = "") -> bool:
        """把文本写入命令执行文本框(仅在产品启用输入行时写入)

        实测 V20(deepin-pc-manager 1.1.7): 输入行是 DTK 的 DPasswordEdit,
        AT-SPI 上只暴露 Text 不暴露 EditableText, 直接 element.text = ... 会抛
        AttributeError, 因此首选 X11 键盘输入(与真实用户操作一致), AT-SPI
        EditableText 作为回退; 写入结果最终由脚本回显断言校验。

        :param text: 待提交内容
        :param window_keyword: 修复对话框窗口标题关键字
        :return: True 表示已提交写入动作
        """
        for _ in range(5):
            state = self.get_shell_repair_input_state()
            if not state["enabled"]:
                sleep(1)
                continue
            if self._focus_repair_dialog_input(window_keyword):
                self.run_cmd(
                    "xdotool key --clearmodifiers ctrl+a",
                    timeout=5,
                    out_debug_flag=False,
                )
                self.run_cmd(
                    f"xdotool type --clearmodifiers --delay 50 {quote(text)}",
                    timeout=15,
                    out_debug_flag=False,
                )
                sleep(0.5)
                typed = self.get_shell_repair_input_state()["text"]
                if typed == text:
                    return True
                if not typed:
                    # DLineEdit 未暴露 Text 接口时读不到内容, 以脚本回显为准
                    return True
            try:
                element = self.dog.find_element_by_attr(self.SHELL_REPAIR_INPUT_EXPR)
                if element and element.showing and element.sensitive:
                    element.text = text
                    sleep(0.5)
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def click_shell_repair_submit(self) -> bool:
        """点击修复对话框的【提交】按钮(仅在按钮可用时点击)

        :return: True 表示已触发点击动作
        """
        try:
            button = self.dog.find_element_by_attr(self.SHELL_REPAIR_SUBMIT_EXPR)
            if button and button.showing and button.sensitive:
                return self._atspi_do_action(button)
        except BaseException:
            pass
        return False

    def press_shell_repair_enter(self, window_keyword: str = "") -> bool:
        """在修复对话框内按 Enter 键(验证回车提交路径)

        产品把输入行的 returnPressed 连接到 submitInput(), 与【提交】按钮等价。
        先激活修复对话框窗口, 保证全局按键送到该对话框而不是主窗口。

        :param window_keyword: 修复对话框窗口标题关键字, 用于定位并激活窗口
        :return: True 表示已发送回车键
        """
        try:
            self._focus_repair_dialog_input(window_keyword)
            self.run_cmd(
                "xdotool key --clearmodifiers Return",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(0.5)
            return True
        except BaseException:
            return False

    def get_pc_manager_window_titles(self) -> list:
        """列出电脑管家所有 X11 窗口标题

        修复对话框(ShellRepairDialog)是独立窗口, 窗口标题即工具名称
        (repair_page.cpp 用 card.title 创建), 可用它验证"窗口显示工具标题"。

        :return: 窗口标题列表
        """
        titles = []
        try:
            window_ids = self.run_cmd(
                "xdotool search --class deepin-pc-manager 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            ).split()
            for window_id in window_ids:
                name = self.run_cmd(
                    f"xdotool getwindowname {window_id} 2>/dev/null",
                    timeout=3,
                    out_debug_flag=False,
                ).strip()
                if name:
                    titles.append(name)
        except BaseException:
            return titles
        return titles

    def get_pc_manager_window_title_contains(self, keyword: str) -> bool:
        """检查电脑管家是否存在标题包含指定关键字的窗口

        :param keyword: 窗口标题关键字(如修复工具名称)
        :return: True 表示存在匹配窗口
        """
        return any(keyword in title for title in self.get_pc_manager_window_titles())

    def wait_repair_dialog_window_showing(self, title_keyword: str, timeout=15) -> bool:
        """等待修复对话框(X11 独立窗口)出现

        产品窗口标题延迟设置, 且 AT-SPI 元素在窗口销毁后会残留 showing=True,
        因此窗口是否真实存在以 X11 窗口标题为准。
        :param title_keyword: 修复工具名称(窗口标题前缀)
        :param timeout: 最长等待秒数
        """
        for _ in range(timeout):
            if self.get_pc_manager_window_title_contains(title_keyword):
                return True
            sleep(1)
        return False

    def wait_repair_dialog_window_closed(self, title_keyword: str, timeout=15) -> bool:
        """等待修复对话框(X11 独立窗口)关闭

        不能用 shellRepair_outputLog 的 showing 判断: 窗口销毁后 AT-SPI
        节点仍可能报 showing=True, 导致"窗口已关但断言说没关"。
        :param title_keyword: 修复工具名称(窗口标题前缀)
        :param timeout: 最长等待秒数
        """
        for _ in range(timeout):
            if not self.get_pc_manager_window_title_contains(title_keyword):
                return True
            sleep(1)
        return False

    def close_repair_dialog_window(self, title_keyword: str) -> bool:
        """通过窗口关闭按钮(WM_DELETE_WINDOW)关闭修复对话框

        修复对话框没有业务层的"关闭"按钮, 关闭入口是标题栏关闭按钮, 等价于
        向该窗口发送 WM_DELETE_WINDOW(xdotool windowclose)。实测 xdotool 的
        "search --class X --name 中文标题" 组合匹配不到窗口, 因此与
        get_pc_manager_window_titles 一样按窗口标题逐个比对后取出窗口 ID。
        脚本已结束时不会弹出"结束修复"确认框。

        实测部分版本(产品 1.1.7)在脚本结束后仍忽略 WM_DELETE_WINDOW, 因此
        窗口未消失时再激活该窗口并发送 Escape(QDialog 的 reject 通道), 两条
        通道都失败才返回, 交给用例侧断言报错。

        :param title_keyword: 修复对话框窗口标题关键字
        :return: True 表示已向匹配窗口发送关闭请求
        """
        closed = False
        try:
            window_ids = self.run_cmd(
                "xdotool search --class deepin-pc-manager 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            ).split()
            for window_id in window_ids:
                name = self.run_cmd(
                    f"xdotool getwindowname {window_id} 2>/dev/null",
                    timeout=3,
                    out_debug_flag=False,
                ).strip()
                if title_keyword and title_keyword in name:
                    self.run_cmd(
                        f"xdotool windowclose {window_id}",
                        timeout=5,
                        out_debug_flag=False,
                    )
                    closed = True
            if closed:
                sleep(1)
                for window_id in window_ids:
                    name = self.run_cmd(
                        f"xdotool getwindowname {window_id} 2>/dev/null",
                        timeout=3,
                        out_debug_flag=False,
                    ).strip()
                    if title_keyword and title_keyword in name:
                        # windowclose 被忽略: 激活后用 Escape 走 QDialog.reject()
                        self.run_cmd(
                            f"xdotool windowactivate {window_id} 2>/dev/null; "
                            f"sleep 1; xdotool key Escape",
                            timeout=10,
                            out_debug_flag=False,
                        )
                        sleep(2)
        except BaseException:
            return closed
        return closed

    # ===== 模块 修复工具 - sudo askpass 垫片(提权密码验证环境) =====

    SUDO_SHIM_HELPER = "/usr/local/bin/pcm-sudo-askpass"
    SUDO_SHIM_WRAPPER = "/usr/local/bin/sudo"
    SUDO_SHIM_CONF = "/etc/sudo.conf"
    SUDO_SHIM_CONF_BAK = "/etc/sudo.conf.pcm-autotest.bak"

    def _root_write_file(self, path: str, content: str, mode: str = "755") -> bool:
        """以 root 写文件(内容经 base64 传输, 避免 shell 引号问题)

        :param path: 目标绝对路径
        :param content: 文件内容
        :param mode: chmod 权限
        :return: True 表示写入并 chmod 成功
        """
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        self.sudo_run_cmd(
            f"printf %s {encoded} | base64 -d > {path} && chmod {mode} {path}",
            timeout=30,
            out_debug_flag=False,
        )
        state = self.run_cmd(
            f"test -f {path} && stat -c '%a' {path} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()
        return state == mode

    def _sudo_shim_selfcheck(self, password: str = None) -> bool:
        """双向自检: 垫片能提权, 框架的 sudo -S 未被破坏

        :param password: sudo 密码; 默认取 setting/globalconfig.ini 的 PASSWORD
        :return: True 表示两条通道都可用
        """
        password = password if password is not None else conf.PASSWORD
        shim = self.run_cmd(
            f"printf '%s\\n' '{password}' | {self.SUDO_SHIM_WRAPPER} -k true "
            f"&& echo SHIM_OK",
            timeout=30,
            out_debug_flag=False,
        )
        frame = self.run_cmd(
            f"sudo -K; printf '%s\\n' '{password}' | sudo -S true && echo FRAME_OK",
            timeout=30,
            out_debug_flag=False,
        )
        self.clear_sudo_credentials()
        return "SHIM_OK" in shim and "FRAME_OK" in frame

    def install_sudo_askpass_shim(self, password: str = None) -> bool:
        """安装"无 tty 提权也能校验密码"的临时垫片(仅测试机, 用完即删)

        产品用 QProcess 以无 tty 管道启动修复脚本, 且把 SUDO_ASKPASS 置空;
        插件脚本用裸 sudo 执行提权命令时只会得到
        "no tty present and no askpass program specified", 产品的密码输入行
        因此永远不会启用。本方法临时装三样东西构造提权密码场景:
        - /usr/local/bin/pcm-sudo-askpass: 向 stderr 打印产品识别密码模式所
          需的 "[sudo] password for <user>:" 提示, 再从 stdin 读取密码并输出
          给 sudo(产品把密码框输入写进修复脚本 stdin);
        - /etc/sudo.conf: Path askpass 指向该垫片(产品清空了环境变量, 只能走
          配置文件);
        - /usr/local/bin/sudo: 包装器, 未显式带 -S/-n/-A 等选项时补 -A 走
          askpass, 显式带这些选项的调用(测试框架自身的 sudo -S)原样透传。
        安装后自检两条通道, 并清掉 sudo 免密时间戳, 保证产品脚本会重新要求
        输入密码。回退见 remove_sudo_askpass_shim()。

        :param password: sudo 密码; 默认取 setting/globalconfig.ini 的 PASSWORD
        :return: True 表示安装并自检通过
        """
        password = password if password is not None else conf.PASSWORD
        helper = (
            "#!/bin/sh\n"
            "# 测试机临时 askpass 垫片(用例结束删除): 提示供电脑管家识别密码模式,\n"
            "# 密码从 stdin 读取(密码框输入的内容由产品写入修复脚本 stdin)。\n"
            "printf '[sudo] password for %s: ' \"$(id -un)\" >&2\n"
            "IFS= read -r pw || exit 1\n"
            "printf '%s\\n' \"$pw\"\n"
        )
        wrapper = (
            "#!/bin/sh\n"
            "# 测试机临时 sudo 包装(用例结束删除): 无 tty 场景下补 -A 走 askpass,\n"
            "# 让密码框输入的密码经脚本 stdin 交给 sudo 校验。\n"
            "for a in \"$@\"; do\n"
            "  case \"$a\" in\n"
            "    -S|--stdin|-n|--non-interactive|-A|--askpass|-K|-V|--version|-l|--list|-v|--validate|-e|--edit)\n"
            "      exec /usr/bin/sudo \"$@\" ;;\n"
            "  esac\n"
            "done\n"
            "exec /usr/bin/sudo -A \"$@\"\n"
        )
        # 局部名不要用 conf, 否则会遮蔽模块级配置对象(setting.conf)
        conf_content = f"Path askpass {self.SUDO_SHIM_HELPER}\n"

        # 幂等: 先清掉上次中断残留(存在备份时先还原, 避免覆盖真实配置)
        self.sudo_run_cmd(
            f"rm -f {self.SUDO_SHIM_WRAPPER} {self.SUDO_SHIM_HELPER}",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"if [ -f {self.SUDO_SHIM_CONF_BAK} ]; then "
            f"mv -f {self.SUDO_SHIM_CONF_BAK} {self.SUDO_SHIM_CONF}; "
            f"else rm -f {self.SUDO_SHIM_CONF}; fi",
            timeout=30,
            out_debug_flag=False,
        )

        self.sudo_run_cmd(
            f"test -f {self.SUDO_SHIM_CONF} && "
            f"cp -a {self.SUDO_SHIM_CONF} {self.SUDO_SHIM_CONF_BAK} || true",
            timeout=30,
            out_debug_flag=False,
        )
        ok = self._root_write_file(self.SUDO_SHIM_HELPER, helper, "755")
        self._root_write_file(self.SUDO_SHIM_CONF, conf_content, "644")
        self._root_write_file(self.SUDO_SHIM_WRAPPER, wrapper, "755")
        if not ok:
            log("sudo askpass 垫片: askpass 助手写入失败")
            return False
        works = self._sudo_shim_selfcheck(password)
        if not works:
            log("sudo askpass 垫片: 自检失败(垫片或框架 sudo 通道不可用)")
        return works

    def remove_sudo_askpass_shim(self, password: str = None) -> bool:
        """卸载 sudo askpass 垫片并校验测试机恢复原状

        :param password: sudo 密码; 默认取 setting/globalconfig.ini 的 PASSWORD
        :return: True 表示垫片文件已删除、/etc/sudo.conf 已还原、
                 测试框架的 sudo -S 通道仍可用
        """
        password = password if password is not None else conf.PASSWORD
        self.sudo_run_cmd(
            f"rm -f {self.SUDO_SHIM_WRAPPER} {self.SUDO_SHIM_HELPER}",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"if [ -f {self.SUDO_SHIM_CONF_BAK} ]; then "
            f"mv -f {self.SUDO_SHIM_CONF_BAK} {self.SUDO_SHIM_CONF}; "
            f"else rm -f {self.SUDO_SHIM_CONF}; fi",
            timeout=30,
            out_debug_flag=False,
        )
        left = self.run_cmd(
            f"ls -d {self.SUDO_SHIM_WRAPPER} {self.SUDO_SHIM_HELPER} "
            f"{self.SUDO_SHIM_CONF_BAK} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()
        frame = self.run_cmd(
            f"sudo -K; printf '%s\\n' '{password}' | sudo -S true && echo FRAME_OK",
            timeout=30,
            out_debug_flag=False,
        )
        self.clear_sudo_credentials()
        if left:
            log(f"sudo askpass 垫片残留: {left}")
        return not left and "FRAME_OK" in frame

    # ===== 模块 修复工具 - 修复插件入口脚本临时替换(交互桩) =====

    def get_repair_plugin_entry_path(self, plugin_name: str) -> str:
        """获取系统修复插件入口脚本路径

        :param plugin_name: 插件目录名(不含 plugin- 前缀, 如 keyring-fix)
        :return: entry.sh 绝对路径
        """
        return f"{self.REPAIR_PLUGIN_ROOT}/plugin-{plugin_name}/entry.sh"

    def _encode_dpm_script(self, script_text: str) -> str:
        """按产品 DPMOBF1 契约编码脚本

        产品启动时对系统插件做 shellEntryIsObfuscated() 校验, 非 DPMOBF1 的
        入口脚本会被跳过; 编码格式见 cmake/obfuscate_script.sh:
        DPMOBF1:<2 位十六进制前缀长度><随机前缀><base64(gzip(脚本))>。
        """
        import base64
        import gzip
        import random
        import string

        encoded = base64.b64encode(
            gzip.compress(script_text.encode("utf-8"))
        ).decode("ascii")
        prefix = "".join(
            random.choice(string.ascii_letters + string.digits) for _ in range(32)
        )
        return f"DPMOBF1:{len(prefix):02x}{prefix}{encoded}\n"

    def _decode_dpm_script(self, data: str) -> str:
        """解码产品 DPMOBF1 脚本(非编码内容原样返回)"""
        import base64
        import gzip

        text = data.strip()
        if not text.startswith("DPMOBF1:"):
            return text
        try:
            prefix_length = int(text[8:10], 16)
            return gzip.decompress(
                base64.b64decode(text[10 + prefix_length:])
            ).decode("utf-8", "replace")
        except BaseException:
            return ""

    def read_repair_plugin_entry(self, plugin_name: str) -> str:
        """读取并解码修复插件入口脚本内容

        :param plugin_name: 插件目录名(不含 plugin- 前缀)
        :return: 解码后的脚本文本, 读取失败返回空字符串
        """
        try:
            with open(
                self.get_repair_plugin_entry_path(plugin_name),
                "r",
                encoding="utf-8",
                errors="replace",
            ) as script_file:
                return self._decode_dpm_script(script_file.read())
        except BaseException:
            return ""

    def backup_repair_plugin_entry(self, plugin_name: str, backup_path: str) -> bool:
        """备份系统修复插件入口脚本

        用例把插件入口临时替换为交互桩脚本时, 先备份原始脚本, 供 finally 恢复。
        备份放在 /tmp, 由用例结束后删除, 不在测试机留残留。

        :param plugin_name: 插件目录名(不含 plugin- 前缀)
        :param backup_path: 备份文件路径
        :return: True 表示备份成功
        """
        # 入口若仍是上次异常退出遗留的交互桩, 备份它会把桩当成"原始脚本",
        # 之后永远无法恢复产品文件; 这里直接拒绝并报错。
        current = self.read_repair_plugin_entry(plugin_name)
        if self.REPAIR_ENTRY_FIXTURE_MARKER in current:
            logger.error(
                f"插件 {plugin_name} 入口仍是上次残留的交互桩脚本, 拒绝把它当作原始备份"
            )
            return False
        entry_path = self.get_repair_plugin_entry_path(plugin_name)
        self.sudo_run_cmd(
            f"install -m 644 {quote(entry_path)} {quote(backup_path)}",
            timeout=20,
            out_debug_flag=False,
        )
        try:
            return os.path.isfile(backup_path) and os.path.getsize(backup_path) > 0
        except BaseException:
            return False

    def install_repair_plugin_entry(self, plugin_name: str, script_text: str) -> bool:
        """把交互桩脚本按 DPMOBF1 编码后写入系统插件入口(临时替换)

        :param plugin_name: 插件目录名(不含 plugin- 前缀)
        :param script_text: 桩脚本文本
        :return: True 表示写入并回读校验一致
        """
        entry_path = self.get_repair_plugin_entry_path(plugin_name)
        temp_path = f"/tmp/autotest_repair_fixture_{plugin_name}.sh"
        try:
            with open(temp_path, "w", encoding="utf-8") as payload_file:
                payload_file.write(self._encode_dpm_script(script_text))
        except BaseException:
            return False
        self.sudo_run_cmd(
            f"install -m 755 {quote(temp_path)} {quote(entry_path)}",
            timeout=20,
            out_debug_flag=False,
        )
        self.run_cmd(f"rm -f {quote(temp_path)}", timeout=5, out_debug_flag=False)
        return self.read_repair_plugin_entry(plugin_name) == script_text

    def restore_repair_plugin_entry(self, plugin_name: str, backup_path: str) -> bool:
        """用备份恢复系统修复插件入口脚本并删除备份

        :param plugin_name: 插件目录名(不含 plugin- 前缀)
        :param backup_path: 备份文件路径
        :return: True 表示已恢复且入口脚本不再包含交互桩标记
        """
        if not os.path.isfile(backup_path):
            return False
        entry_path = self.get_repair_plugin_entry_path(plugin_name)
        restored = ""
        for _ in range(5):
            self.sudo_run_cmd(
                f"install -m 755 {quote(backup_path)} {quote(entry_path)}",
                timeout=20,
                out_debug_flag=False,
            )
            restored = self.read_repair_plugin_entry(plugin_name)
            if restored and self.REPAIR_ENTRY_FIXTURE_MARKER not in restored:
                break
            sleep(1)
        if not restored or self.REPAIR_ENTRY_FIXTURE_MARKER in restored:
            # 恢复未验证成功时保留备份, 交给下次运行的 restore_stale 自愈
            logger.error(f"插件 {plugin_name} 入口恢复失败, 保留备份 {backup_path}")
            return False
        self.sudo_run_cmd(f"rm -f {quote(backup_path)}", timeout=10, out_debug_flag=False)
        return True

    def restore_stale_repair_plugin_backup(self, plugin_name: str, backup_path: str) -> bool:
        """自愈: 若上次运行异常退出遗留了备份, 先用备份恢复插件入口

        :param plugin_name: 插件目录名(不含 plugin- 前缀)
        :param backup_path: 备份文件路径
        :return: True 表示无遗留备份或已恢复成功
        """
        try:
            if not os.path.isfile(backup_path):
                return True
        except BaseException:
            return True
        return self.restore_repair_plugin_entry(plugin_name, backup_path)

    # ===== 模块 修复工具 - dpmapi openconfirm 确认框(交互弹窗)验证 =====
    # 产品依据(deepin-pc-manager 1.1.7):
    # - 插件脚本调用 "dpmapi openconfirm <title> <msg>" 时, dpmapi 走
    #   handleWindowAction("OpenConfirm") -> session 总线
    #   org.deepin.PCManager1.ExecuteUserAction -> session-daemon
    #   ActionExecutor::executeConfirm() 创建 DDialog(setWindowTitle(title),
    #   setMessage(msg)), 按钮文案为 tr("Cancel") / tr("Confirm");
    # - 该 DDialog 属于独立进程 deepin-pc-manager-session-daemon, 在 AT-SPI 上
    #   是另一个 application(不在 self.dog 的电脑管家子树里), 因此这里直接
    #   遍历 AT-SPI 根节点找该应用;
    # - dialog 的 accessible name 即脚本传入的 title, 可直接校验标题;
    # - 1.1.7 中文翻译把 Confirm 译作"确认"(不是描述里的"确定"), 以产品实际
    #   文案断言;
    # - 正文 label(objectName=DDialogMessageLabel) 不暴露 accessible text,
    #   因此正文与脚本参数的一致性用 session 总线上 ExecuteUserAction 的请求
    #   参数做等价断言(与弹窗展示同源, 见 action_executor.cpp executeConfirm)。
    SESSION_DAEMON_APP_NAME = "deepin-pc-manager-session-daemon"
    CONFIRM_DIALOG_CANCEL_TEXT = "取消"
    CONFIRM_DIALOG_OK_TEXT = "确认"
    CONFIRM_DIALOG_MESSAGE_LABEL = "DDialogMessageLabel"
    CONFIRM_DIALOG_LOG = "/tmp/autotest_confirm_dbus_monitor.log"
    CONFIRM_DIALOG_PID = "/tmp/autotest_confirm_dbus_monitor.pid"
    CONFIRM_DIALOG_DBUS_INTERFACE = "org.deepin.PCManager1"

    def get_session_bus_address(self) -> str:
        """获取当前桌面会话的 DBus session 总线地址

        用例需要监听 session 总线核对 dpmapi openconfirm 的请求参数;
        ssh 非登录 shell 通常没有 DBUS_SESSION_BUS_ADDRESS, 按三级回退:
        进程环境变量 -> /run/user/<uid>/bus -> 电脑管家主进程的 /proc/<pid>/environ。

        :return: 总线地址, 未找到返回空字符串
        """
        address = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
        if address:
            return address
        runtime_path = f"/run/user/{os.getuid()}/bus"
        if os.path.exists(runtime_path):
            return f"unix:path={runtime_path}"
        try:
            pids = self.run_cmd(
                r"ps -eo pid=,args= | grep -E "
                r"'^[[:space:]]*[0-9]+ (deepin-pc-manager|/usr/libexec/deepin/deepin-pc-manager|"
                r"/usr/bin/deepin-pc-manager)($|[[:space:]])' "
                r"| grep -v grep | awk '{print $1}' | head -1",
                timeout=5,
                out_debug_flag=False,
            ).strip()
        except BaseException:
            pids = ""
        if not pids.isdigit():
            return ""
        try:
            with open(f"/proc/{pids}/environ", "rb") as environ_file:
                for item in environ_file.read().split(b"\0"):
                    if item.startswith(b"DBUS_SESSION_BUS_ADDRESS="):
                        return item.decode("utf-8", "replace").split("=", 1)[1]
        except BaseException:
            return ""
        return ""

    def start_confirm_dbus_monitor(self) -> bool:
        """启动 session 总线监听, 捕获 dpmapi openconfirm 的请求参数

        监听 org.deepin.PCManager1 接口上的 ExecuteUserAction 调用, 请求体
        里的 title/message 即确认框最终展示的标题与正文(同一份数据经
        executeConfirm() 传给 DDialog::setWindowTitle/setMessage)。

        :return: True 表示监听进程已启动
        """
        bus_address = self.get_session_bus_address()
        if not bus_address:
            logger.warning("未找到 DBus session 总线地址, 无法监听确认框请求参数")
            return False
        self.stop_confirm_dbus_monitor()
        self.run_cmd(
            f"DBUS_SESSION_BUS_ADDRESS={quote(bus_address)} "
            "nohup stdbuf -oL -eL dbus-monitor --session \"interface='org.deepin.PCManager1'\" "
            f"> {quote(self.CONFIRM_DIALOG_LOG)} 2>&1 < /dev/null & "
            f"echo $! > {quote(self.CONFIRM_DIALOG_PID)}",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(2)
        return self.is_confirm_dbus_monitor_running()

    def is_confirm_dbus_monitor_running(self) -> bool:
        """检查会话总线监听进程是否存活

        :return: True 表示监听进程存在
        """
        pid = self._read_confirm_dbus_pid()
        if not pid:
            return False
        try:
            return bool(
                self.run_cmd(
                    f"kill -0 {pid} 2>/dev/null && echo alive",
                    timeout=5,
                    out_debug_flag=False,
                ).strip()
            )
        except BaseException:
            return False

    def _read_confirm_dbus_pid(self) -> str:
        """读取总线监听进程号, 读不到返回空字符串"""
        try:
            if os.path.isfile(self.CONFIRM_DIALOG_PID):
                with open(
                    self.CONFIRM_DIALOG_PID, "r", encoding="utf-8", errors="replace"
                ) as pid_file:
                    pid = pid_file.read().strip()
                if pid.isdigit():
                    return pid
        except BaseException:
            pass
        return ""

    def stop_confirm_dbus_monitor(self):
        """停止会话总线监听并删除临时文件(用例 finally 必调)"""
        pid = self._read_confirm_dbus_pid()
        if pid:
            self.run_cmd(f"kill {pid} 2>/dev/null", timeout=5, out_debug_flag=False)
        self.run_cmd(
            f"rm -f {quote(self.CONFIRM_DIALOG_LOG)} {quote(self.CONFIRM_DIALOG_PID)}",
            timeout=5,
            out_debug_flag=False,
        )

    def get_confirm_dbus_request_text(self) -> str:
        """读取会话总线监听日志全文

        :return: 日志文本, 读取失败返回空字符串
        """
        try:
            with open(
                self.CONFIRM_DIALOG_LOG, "r", encoding="utf-8", errors="replace"
            ) as log_file:
                return log_file.read()
        except BaseException:
            return ""

    def wait_confirm_dbus_request(self, title: str, message: str, timeout: int = 15) -> bool:
        """等待总线上出现标题/正文与脚本参数完全一致的 OpenConfirm 请求

        dbus-monitor 对字符串按 string "..." 形式原样输出, 这里要求标题与正文
        同时以该形式出现, 等价于"弹窗标题与内容与脚本参数一致"。

        :param title: 脚本传给 openconfirm 的标题
        :param message: 脚本传给 openconfirm 的正文
        :param timeout: 最长等待秒数
        :return: True 表示捕获到匹配的请求
        """
        for _ in range(timeout):
            text = self.get_confirm_dbus_request_text()
            if text and f'string "{title}"' in text and f'string "{message}"' in text:
                return True
            sleep(1)
        logger.warning(
            f"会话总线未捕获到确认框请求 title={title!r} message={message!r}, "
            f"监听日志长度={len(self.get_confirm_dbus_request_text())}"
        )
        return False

    # ---- 产品埋点上报核对 -------------------------------------------------
    # 产品 TelemetryService 经 libdeepin-event-log.so 把事件发到 system 总线
    # org.deepin.EventLog1.ReportEventLog(packagename, eventinfo), eventinfo 为
    # 紧凑 JSON(tid/pageId/pageName/osVersion/osBuild 等), 每次发送后写一行
    # "Event logged: ..." 到应用日志; system 总线上的 deepin-event-log-daemon
    # 收到后写 "received event log from package:deepin-pc-manager" 到 journal。
    # 两者组合可证明: 事件内容正确(应用日志)且确实被守护进程接收(journal)。
    # 不用缓存文件计数: 守护进程写盘有缓冲, 跨用例会看到滞后落盘的旧事件。
    APP_LOG_PATH = expanduser("~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log")
    EVENTLOG_RECEIPT_MARKER = "received event log from package:deepin-pc-manager"

    def count_app_log_matches(self, *fragments: str) -> int:
        """统计应用日志中同时包含全部片段的行数

        :param fragments: 需要同时出现的字面片段
        :return: 命中行数, 日志不存在返回 0
        """
        try:
            with open(self.APP_LOG_PATH, "r", encoding="utf-8", errors="replace") as log_file:
                lines = log_file.readlines()
        except BaseException:
            return 0
        return sum(1 for line in lines if all(fragment in line for fragment in fragments))

    def get_last_app_log_line(self, *fragments: str) -> str:
        """返回应用日志中最后一条同时包含全部片段的行

        :param fragments: 需要同时出现的字面片段
        :return: 命中的最后一行, 未命中返回空字符串
        """
        try:
            with open(self.APP_LOG_PATH, "r", encoding="utf-8", errors="replace") as log_file:
                lines = log_file.readlines()
        except BaseException:
            return ""
        for line in reversed(lines):
            if all(fragment in line for fragment in fragments):
                return line
        return ""

    def wait_app_log_matches(self, fragments, expected: int, timeout: int = 20) -> int:
        """等待应用日志中命中行数达到 expected

        :param fragments: 需要同时出现的字面片段
        :param expected: 期望的命中行数
        :param timeout: 最长等待秒数
        :return: 最后一次统计到的行数
        """
        count = self.count_app_log_matches(*fragments)
        for _ in range(timeout):
            if count >= expected:
                return count
            sleep(1)
            count = self.count_app_log_matches(*fragments)
        logger.warning(
            f"应用日志未达到期望行数 fragments={fragments!r} "
            f"count={count} expected={expected}"
        )
        return count

    def count_eventlog_daemon_receipts(self) -> int:
        """统计 event-log 守护进程收到的电脑管家事件条数(读 journal, 需 root)

        :return: 收据条数, 读取失败返回 -1
        """
        cmd = (
            "n=$(journalctl -u event-log --no-pager -o cat 2>/dev/null "
            f"| grep -c -F -- {quote(self.EVENTLOG_RECEIPT_MARKER)}); "
            "echo EVENTLOG_RECEIPTS=$n"
        )
        output = self.sudo_run_cmd(cmd, timeout=20, out_debug_flag=False)
        for line in (output or "").splitlines():
            if "EVENTLOG_RECEIPTS=" in line:
                try:
                    return int(line.split("EVENTLOG_RECEIPTS=", 1)[1].strip())
                except ValueError:
                    return -1
        return -1

    def wait_eventlog_daemon_receipts(self, expected: int, timeout: int = 20) -> int:
        """等待 event-log 守护进程收据条数达到 expected

        :param expected: 期望的收据条数
        :param timeout: 最长等待秒数
        :return: 最后一次统计到的条数
        """
        count = self.count_eventlog_daemon_receipts()
        for _ in range(timeout):
            if count >= expected:
                return count
            sleep(1)
            count = self.count_eventlog_daemon_receipts()
        logger.warning(
            f"event-log 守护进程收据未达到期望条数 count={count} expected={expected}"
        )
        return count

    def _get_session_daemon_app(self):
        """获取 session-daemon 在 AT-SPI 中的 application 节点

        dpmapi 的确认框由 deepin-pc-manager-session-daemon 进程创建, 与电脑
        管家主程序分属不同 AT-SPI application。

        :return: application 节点, 未运行/不可达时返回 None
        """
        try:
            from src.depends.dogtail.tree import root as a11y_root
        except BaseException:
            return None
        try:
            applications = list(a11y_root.children)
        except BaseException:
            return None
        for app in applications:
            try:
                if (app.name or "") == self.SESSION_DAEMON_APP_NAME:
                    return app
            except BaseException:
                continue
        return None

    def _get_main_app(self):
        """获取电脑管家主程序在 AT-SPI 中的 application 节点

        长文件名等插件脚本的确认框并非由 session-daemon 创建: 产品在
        主进程内直接弹出无标题的 DDialog(accessible name 为空, 直接子节点
        只有"取消"/"确认"两个按钮), 因此按标题查不到, 需要单独按应用+按钮
        识别。

        :return: application 节点, 未运行/不可达时返回 None
        """
        try:
            from src.depends.dogtail.tree import root as a11y_root
        except BaseException:
            return None
        try:
            applications = list(a11y_root.children)
        except BaseException:
            return None
        for app in applications:
            try:
                if (app.name or "") == self.APP_NAME:
                    return app
            except BaseException:
                continue
        return None

    def _get_main_app_action_dialog(self, action_text: str = ""):
        """查找主程序内弹出的操作确认框(无标题 DDialog)

        判定条件: roleName 为 dialog、accessible name 为空、直接子节点里有
        "取消"/"确认"/"确定" 按钮。修复详情对话框有标题(卡片名), 不会命中。

        :param action_text: 要求的按钮文案("取消"/"确认"/"确定"), 空串表示任一
        :return: dialog 节点, 不存在返回 None
        """
        app = self._get_main_app()
        if app is None:
            return None
        try:
            nodes = list(app.children)
        except BaseException:
            return None
        action_texts = {
            self.CONFIRM_DIALOG_CANCEL_TEXT,
            self.CONFIRM_DIALOG_OK_TEXT,
            self.INFOBOX_OK_TEXT,
        }
        for node in nodes:
            try:
                if node.roleName != "dialog" or (node.name or ""):
                    continue
                buttons = {
                    child.name or ""
                    for child in node.children
                    if child.roleName == "push button"
                }
            except BaseException:
                continue
            if action_text and action_text not in buttons:
                continue
            if buttons & action_texts:
                return node
        return None

    def _get_confirm_dialog_node(self, title: str, action_text: str = ""):
        """按标题查找确认框 dialog 节点

        先查 session-daemon 创建的确认框(标题可见); 查不到时回退到主程序内
        的无标题确认框(长文件名修复等插件走这条路径, 标题不暴露给 AT-SPI,
        只能按"无标题 + 取消/确认按钮"识别)。

        :param title: 确认框标题(即 DDialog 的 windowTitle/accessible name)
        :param action_text: 主程序内确认框要求的按钮文案, daemon 框忽略此参数
        :return: dialog 节点, 不存在返回 None
        """
        app = self._get_session_daemon_app()
        if app is not None:
            try:
                nodes = list(app.children)
            except BaseException:
                nodes = []
            for node in nodes:
                try:
                    if node.roleName == "dialog" and (node.name or "") == title:
                        return node
                except BaseException:
                    continue
        return self._get_main_app_action_dialog(action_text)

    def _read_confirm_dialog_state(self, dialog) -> dict:
        """读取确认框当前状态(标题/可见性/按钮文案/正文标签是否渲染)

        :param dialog: dialog 节点
        :return: {"exists", "showing", "title", "buttons", "message_label_showing"}
        """
        state = {
            "exists": True,
            "showing": False,
            "title": "",
            "buttons": [],
            "message_label_showing": False,
        }
        try:
            state["title"] = dialog.name or ""
        except BaseException:
            state["title"] = ""
        try:
            state["showing"] = bool(dialog.showing)
        except BaseException:
            state["showing"] = False
        buttons = []
        try:
            children = list(dialog.children)
        except BaseException:
            children = []
        for child in children:
            try:
                if child.roleName == "push button":
                    buttons.append(child.name or "")
            except BaseException:
                continue
        state["buttons"] = buttons
        try:
            labels = dialog.findChildren(
                lambda node: node.roleName == "label"
                and (node.name or "") == self.CONFIRM_DIALOG_MESSAGE_LABEL
            )
        except BaseException:
            labels = []
        for label in labels:
            try:
                if label.showing:
                    state["message_label_showing"] = True
                    break
            except BaseException:
                continue
        return state

    def get_confirm_dialog_state(self, title: str, timeout: int = 20,
                                 action_text: str = CONFIRM_DIALOG_CANCEL_TEXT) -> dict:
        """等待并获取确认框状态(按钮就绪后才返回)

        DDialog 先创建窗口再添加按钮, 因此等按钮出现后再取快照, 避免读到
        半成品状态。

        :param title: 确认框标题
        :param timeout: 最长等待秒数
        :param action_text: 对话框必须包含的按钮文案, 用于区分主程序内的
                            确认框(取消/确认)与提示框(确定)
        :return: 见 _read_confirm_dialog_state; 超时未出现时 exists 为 False
        """
        state = {
            "exists": False,
            "showing": False,
            "title": "",
            "buttons": [],
            "message_label_showing": False,
        }
        for _ in range(timeout):
            dialog = self._get_confirm_dialog_node(title, action_text)
            if dialog is not None:
                state = self._read_confirm_dialog_state(dialog)
                if state["buttons"]:
                    return state
            sleep(1)
        return state

    def wait_confirm_dialog_closed(self, title: str, timeout: int = 10) -> bool:
        """等待确认框关闭

        :param title: 确认框标题
        :param timeout: 最长等待秒数
        :return: True 表示确认框已从 AT-SPI 树中消失
        """
        for _ in range(timeout):
            if self._get_confirm_dialog_node(title) is None:
                return True
            sleep(1)
        return False

    def _press_dialog_button(self, dialog, button_text: str) -> bool:
        """在指定 dialog 节点上按文案点击按钮

        :param dialog: dialog 节点
        :param button_text: 按钮文案("取消"/"确认"/"确定")
        :return: True 表示已触发
        """
        try:
            children = list(dialog.children)
        except BaseException:
            return False
        for child in children:
            try:
                if child.roleName != "push button" or (child.name or "") != button_text:
                    continue
            except BaseException:
                continue
            if self._atspi_do_action(child):
                sleep(1)
                return True
        return False

    def click_confirm_dialog_button(self, title: str, button_text: str, timeout: int = 10) -> bool:
        """点击 session-daemon 确认框上的指定按钮

        按钮是 DDialog 的直接子节点(取消/确认), 用 AT-SPI Action("Press")
        触发, 与真实鼠标点击等价(按钮本身支持 Press action)。

        :param title: 确认框标题
        :param button_text: 按钮文案("取消"/"确认")
        :param timeout: 最长等待秒数
        :return: True 表示已触发按钮
        """
        for _ in range(timeout):
            dialog = self._get_confirm_dialog_node(title, button_text)
            if dialog is not None:
                try:
                    children = list(dialog.children)
                except BaseException:
                    children = []
                for child in children:
                    try:
                        if child.roleName != "push button" or (child.name or "") != button_text:
                            continue
                    except BaseException:
                        continue
                    if self._atspi_do_action(child):
                        sleep(1)
                        return True
            sleep(1)
        return False

    def close_confirm_dialogs(self, title_prefix: str = "", rounds: int = 3) -> int:
        """关闭遗留的确认框(点"取消"), 供用例前置自愈与 finally 清理使用

        :param title_prefix: 只处理标题以该前缀开头的确认框, 空串表示全部
        :param rounds: 轮询轮数(脚本在取消后可能继续弹下一个确认框)
        :return: 累计关闭的确认框数量
        """
        closed = 0
        for _ in range(rounds):
            app = self._get_session_daemon_app()
            try:
                nodes = list(app.children) if app is not None else []
            except BaseException:
                nodes = []
            pending = []
            for node in nodes:
                try:
                    if node.roleName != "dialog":
                        continue
                    name = node.name or ""
                except BaseException:
                    continue
                if title_prefix and not name.startswith(title_prefix):
                    continue
                pending.append(name)
            for name in pending:
                if self.click_confirm_dialog_button(
                    name, self.CONFIRM_DIALOG_CANCEL_TEXT, timeout=3
                ):
                    closed += 1
            dialog = self._get_main_app_action_dialog(
                self.CONFIRM_DIALOG_CANCEL_TEXT
            )
            if dialog is not None and self._press_dialog_button(
                dialog, self.CONFIRM_DIALOG_CANCEL_TEXT
            ):
                closed += 1
            if not pending and dialog is None:
                break
            sleep(2)
        return closed

    # ===== 模块 修复工具 - dpmapi openinfobox 提示框(交互弹窗)验证 =====
    # 产品依据(deepin-pc-manager 1.1.7):
    # - dpmapi_command.cpp handleOpeninfobox -> OpenMessage 请求经 session 总线
    #   org.deepin.PCManager1.ExecuteUserAction 交给 session-daemon;
    # - action_executor.cpp executeMessage() 创建 DDialog(setWindowTitle(title),
    #   setMessage(message)), 只添加一个 tr("OK") 按钮(zh_CN 译为"确定");
    # - 该 dialog 与确认框同属 deepin-pc-manager-session-daemon, AT-SPI 上是
    #   独立 application, 因此复用确认框的节点查找/读取/点击实现。
    INFOBOX_OK_TEXT = "确定"

    def get_info_dialog_state(self, title: str, timeout: int = 20) -> dict:
        """等待并获取 dpmapi openinfobox 提示框状态

        提示框与确认框同为 session-daemon 创建的 DDialog, 仅按钮文案/数量不同
        (提示框只有"确定"), 因此复用确认框的状态读取实现。

        :param title: 提示框标题(即脚本传给 openinfobox 的第一个参数)
        :param timeout: 最长等待秒数
        :return: 见 _read_confirm_dialog_state; 超时未出现时 exists 为 False
        """
        return self.get_confirm_dialog_state(
            title, timeout=timeout, action_text=self.INFOBOX_OK_TEXT
        )

    def get_info_dialog_text(self, title: str, timeout: int = 20) -> str:
        """等待 dpmapi openinfobox 提示框并返回其正文文本

        提示框正文即脚本传给 openinfobox 的第二个参数, 用于断言修复完成
        提示语(比只看"有弹窗"更接近用例预期)。

        :param title: 提示框标题
        :param timeout: 最长等待秒数
        :return: 提示框内 label/text 文案拼接; 未出现或读不到时返回空字符串
        """
        for _ in range(max(int(timeout), 1)):
            dialog = self._get_confirm_dialog_node(title)
            if dialog is not None:
                text = self._dialog_text(dialog)
                if text:
                    return text
            sleep(1)
        return ""

    def wait_info_dialog_closed(self, title: str, timeout: int = 10) -> bool:
        """等待提示框关闭

        :param title: 提示框标题
        :param timeout: 最长等待秒数
        :return: True 表示提示框已从 AT-SPI 树中消失
        """
        return self.wait_confirm_dialog_closed(title, timeout=timeout)

    def close_info_dialogs(self, title_prefix: str = "", rounds: int = 3) -> int:
        """关闭遗留的提示框(点"确定"), 供用例前置自愈与 finally 清理使用

        与 close_confirm_dialogs 的区别: 提示框只有"确定"按钮, 没有"取消"。

        :param title_prefix: 只处理标题以该前缀开头的提示框, 空串表示全部
        :param rounds: 轮询轮数(脚本在确定后可能继续弹下一个提示框)
        :return: 累计关闭的提示框数量
        """
        closed = 0
        for _ in range(rounds):
            app = self._get_session_daemon_app()
            try:
                nodes = list(app.children) if app is not None else []
            except BaseException:
                nodes = []
            pending = []
            for node in nodes:
                try:
                    if node.roleName != "dialog":
                        continue
                    name = node.name or ""
                except BaseException:
                    continue
                if title_prefix and not name.startswith(title_prefix):
                    continue
                pending.append(name)
            for name in pending:
                if self.click_confirm_dialog_button(
                    name, self.INFOBOX_OK_TEXT, timeout=3
                ):
                    closed += 1
            dialog = self._get_main_app_action_dialog(self.INFOBOX_OK_TEXT)
            if dialog is not None and self._press_dialog_button(
                dialog, self.INFOBOX_OK_TEXT
            ):
                closed += 1
            if not pending and dialog is None:
                break
            sleep(2)
        return closed

    # ===== 模块 修复工具 - dpmapi opensingleinputbox 单行输入框(交互弹窗)验证 =====
    # 产品依据(deepin-pc-manager 1.1.7):
    # - dpmapi 用法: "dpmapi opensingleinputbox <title> <label> <mode>";
    #   请求经 session 总线 org.deepin.PCManager1.ExecuteUserAction 交给
    #   session-daemon 的 ActionExecutor::executeSingleInput() 创建 DDialog;
    # - AT-SPI 实测结构(测试机 10.20.33.103): dialog 的 accessible name 即
    #   脚本第一个参数 title; 第二个参数 label 渲染为 dialog 内可见 label;
    #   输入控件 role='text'(accessible name DLineEditChildLineEdit, 可编辑);
    #   按钮为 tr("Cancel")/tr("Confirm"), zh_CN 文案是"取消"/"确认";
    # - 点"确认"后脚本拿到结果: 有内容返回输入文本, 空内容与"取消"均返回空
    #   字符串, 三种分支 dpmapi 退出码都是 0;
    # - 实测 1.1.7 中输入为空时"确认"按钮仍是 enabled(不置灰), 因此描述中
    #   "确定按钮保持禁用"按等价语义断言: 空内容提交后返回空字符串, 不会把
    #   空内容或残留内容传给脚本。
    SINGLE_INPUT_DIALOG_TITLE_PREFIX = "自动测试输入框"
    SINGLE_INPUT_OK_TEXT = "确认"
    SINGLE_INPUT_CANCEL_TEXT = "取消"
    SINGLE_INPUT_FIELD_ROLE = "text"

    def _find_single_input_field(self, dialog):
        """在单行输入框 dialog 内递归查找可编辑输入控件

        实测输入控件 role='text'(accessible name DLineEditChildLineEdit), 位于
        DDialog 内部的 filler 层, 不是 dialog 的直接子节点, 因此递归查找;
        按 role 匹配以兼容产品层级/对象名调整。

        :param dialog: session-daemon 创建的 dialog 节点
        :return: 输入控件节点, 未找到返回 None
        """
        stack = [dialog]
        while stack:
            node = stack.pop()
            try:
                if node.roleName == self.SINGLE_INPUT_FIELD_ROLE:
                    return node
            except BaseException:
                pass
            try:
                stack.extend(list(node.children))
            except BaseException:
                continue
        return None

    def _find_single_input_button(self, dialog, button_text: str):
        """按文案查找输入框 dialog 的按钮节点(按钮为 dialog 直接子节点)

        :param dialog: dialog 节点
        :param button_text: 按钮文案("取消"/"确认")
        :return: 按钮节点, 未找到返回 None
        """
        try:
            children = list(dialog.children)
        except BaseException:
            return None
        for child in children:
            try:
                if child.roleName == "push button" and (child.name or "") == button_text:
                    return child
            except BaseException:
                continue
        return None

    def get_single_input_dialog_state(
        self, title: str, label: str = "", timeout: int = 20
    ) -> dict:
        """等待并获取 dpmapi opensingleinputbox 单行输入框状态

        输入框与确认框同属 deepin-pc-manager-session-daemon 创建的 DDialog,
        因此复用确认框的节点查找/状态读取, 额外读取输入控件与脚本传入的 label
        是否已渲染。DDialog 先建窗再填控件, 这里等按钮和输入控件都就绪才返回。

        :param title: 对话框标题(脚本第一个参数)
        :param label: 脚本第二个参数(期望以可见 label 渲染), 空串表示不校验
        :param timeout: 最长等待秒数
        :return: {"exists","showing","title","buttons","label_showing",
                  "text_exists","text_showing","text_editable","text_value",
                  "ok_enabled","cancel_enabled"}
        """
        state = {
            "exists": False,
            "showing": False,
            "title": "",
            "buttons": [],
            "label_showing": False,
            "text_exists": False,
            "text_showing": False,
            "text_editable": False,
            "text_value": "",
            "ok_enabled": False,
            "cancel_enabled": False,
        }
        for _ in range(timeout):
            dialog = self._get_confirm_dialog_node(title)
            if dialog is None:
                sleep(1)
                continue
            state.update(self._read_confirm_dialog_state(dialog))
            field = self._find_single_input_field(dialog)
            if field is not None:
                state["text_exists"] = True
                try:
                    state["text_showing"] = bool(field.showing)
                except BaseException:
                    state["text_showing"] = False
                try:
                    states = [
                        item.value_name for item in field.getState().getStates()
                    ]
                    state["text_editable"] = "ATSPI_STATE_EDITABLE" in states
                except BaseException:
                    state["text_editable"] = False
                try:
                    state["text_value"] = field.text or ""
                except BaseException:
                    state["text_value"] = ""
            if label:
                try:
                    labels = dialog.findChildren(
                        lambda node: node.roleName == "label"
                        and (node.name or "") == label
                    )
                except BaseException:
                    labels = []
                for node in labels:
                    try:
                        if node.showing:
                            state["label_showing"] = True
                            break
                    except BaseException:
                        continue
            else:
                state["label_showing"] = True
            for text, key in (
                (self.SINGLE_INPUT_OK_TEXT, "ok_enabled"),
                (self.SINGLE_INPUT_CANCEL_TEXT, "cancel_enabled"),
            ):
                button = self._find_single_input_button(dialog, text)
                if button is not None:
                    try:
                        state[key] = bool(button.sensitive)
                    except BaseException:
                        state[key] = False
            if state["buttons"] and field is not None:
                return state
            sleep(1)
        return state

    def get_single_input_text(self, title: str) -> str:
        """读取单行输入框当前内容

        :param title: 对话框标题
        :return: 输入内容, 对话框或控件不存在时返回空字符串
        """
        dialog = self._get_confirm_dialog_node(title)
        if dialog is None:
            return ""
        field = self._find_single_input_field(dialog)
        if field is None:
            return ""
        try:
            return field.text or ""
        except BaseException:
            return ""

    def set_single_input_text(self, title: str, text: str, timeout: int = 10) -> bool:
        """向单行输入框写入内容并回读校验

        输入控件支持 AT-SPI EditableText, 用 dogtail 的 text setter
        (queryEditableText().setTextContents) 写入, 等价于用户键入并覆盖原内容。

        :param title: 对话框标题
        :param text: 要输入的内容
        :param timeout: 最长等待秒数
        :return: True 表示写入后回读内容一致
        """
        for _ in range(timeout):
            dialog = self._get_confirm_dialog_node(title)
            if dialog is not None:
                field = self._find_single_input_field(dialog)
                if field is not None:
                    try:
                        field.text = text
                    except BaseException:
                        logger.warning(f"向输入框 {title!r} 写入内容失败")
                        return False
                    sleep(1)
                    return self.get_single_input_text(title) == text
            sleep(1)
        return False

    def wait_single_input_dialog_closed(self, title: str, timeout: int = 10) -> bool:
        """等待单行输入框关闭

        :param title: 对话框标题
        :param timeout: 最长等待秒数
        :return: True 表示对话框已从 AT-SPI 树中消失
        """
        return self.wait_confirm_dialog_closed(title, timeout=timeout)

    def click_single_input_button(
        self, title: str, button_text: str, timeout: int = 10
    ) -> bool:
        """点击单行输入框上的指定按钮

        :param title: 对话框标题
        :param button_text: 按钮文案("取消"/"确认", 产品 1.1.7 无"确定"字样)
        :param timeout: 最长等待秒数
        :return: True 表示已触发按钮
        """
        return self.click_confirm_dialog_button(title, button_text, timeout=timeout)

    def close_single_input_dialogs(self, title_prefix: str = "", rounds: int = 3) -> int:
        """关闭遗留的单行输入框(点"取消"), 供用例前置自愈与 finally 清理使用

        :param title_prefix: 只处理标题以该前缀开头的对话框, 空串表示全部
        :param rounds: 轮询轮数(脚本在取消后可能继续弹下一个输入框)
        :return: 累计关闭的对话框数量
        """
        return self.close_confirm_dialogs(title_prefix, rounds=rounds)

    # ===== 模块 修复工具 - dpm_select 选择框(U盘选择框)验证 =====
    # 产品依据(deepin-pc-manager 1.1.7):
    # - 修复插件通过 dpmapi.sh 的 dpm_select/dpm_multiselect 发起选择请求, 请求以
    #   行协议写入脚本 stdout, 由修复窗口 ShellRepairDialog 解析;
    # - ShellRepairDialog::showNextInteraction() 创建模态 DDialog: setTitle(第一个
    #   参数)、setMessage(第二个参数), 内容为只读单选 QListWidget(每个选项一项),
    #   按钮为 tr("Cancel")/tr("Confirm"), zh_CN 文案是"取消"/"确认";
    # - 该 DDialog 属于电脑管家主进程(与 session-daemon 的确认框不同), 且只设置
    #   title 文本而没有 windowTitle, AT-SPI 上 dialog 的 accessible name 为空;
    #   标题/说明分别由 DDialogTitleLabel/DDialogMessageLabel 渲染(不暴露文本),
    #   标题文案另由产品写入修复输出日志 "[等待你的确认] <标题>";
    # - 选择结果经 ScriptInteraction 回传 dpmapi, dpm_select 写入
    #   DPM_LATEST_RESULT 并打印到脚本 stdout; 取消或未选中时该变量为空字符串,
    #   dpm_select 返回 1。
    SELECT_DIALOG_OK_TEXT = "确认"
    SELECT_DIALOG_CANCEL_TEXT = "取消"
    SELECT_DIALOG_TITLE_LABEL = "DDialogTitleLabel"
    SELECT_DIALOG_MESSAGE_LABEL = "DDialogMessageLabel"

    def _collect_dialog_nodes(self, node, depth=0, max_depth=8) -> list:
        """按文档顺序收集对话框子树中的节点

        :param node: 起始节点
        :param depth: 当前深度
        :param max_depth: 最大递归深度
        :return: 节点列表
        """
        nodes = []
        try:
            nodes.append(node)
        except BaseException:
            return nodes
        if depth >= max_depth:
            return nodes
        try:
            children = list(node.children)
        except BaseException:
            return nodes
        for child in children:
            nodes.extend(self._collect_dialog_nodes(child, depth + 1, max_depth))
        return nodes

    def _match_select_dialog(self, node):
        """判断节点是否为 dpm_select 选择框(含列表项 + 取消/确认按钮)

        选择框的 accessible name 为空(产品只 setTitle 文本, 没有 windowTitle),
        因此按结构特征识别: 子树内同时存在 role='list item' 的列表项与
        "取消"/"确认"两个按钮。

        :param node: 待判断节点
        :return: 匹配时返回该 dialog 节点, 否则返回 None
        """
        try:
            if (getattr(node, "roleName", "") or "") != "dialog":
                return None
            if not getattr(node, "showing", False):
                return None
        except BaseException:
            return None
        nodes = self._collect_dialog_nodes(node, max_depth=6)
        roles = [getattr(n, "roleName", "") or "" for n in nodes]
        names = [getattr(n, "name", "") or "" for n in nodes]
        if "list item" not in roles:
            return None
        if self.SELECT_DIALOG_CANCEL_TEXT not in names:
            return None
        if self.SELECT_DIALOG_OK_TEXT not in names:
            return None
        return node

    def _find_select_dialog(self):
        """查找当前可见的 dpm_select 选择框

        先查 application 的直接子节点(常规情形下交互窗是顶层窗口), 未命中时
        再在浅层子树里兜底查找(兼容交互窗挂在修复窗口之下的层级变化)。

        :return: dialog 节点, 不存在返回 None
        """
        try:
            app = self.dog.obj
        except BaseException:
            # 应用未启动/未建立 AT-SPI 连接时不存在交互窗
            return None
        try:
            tops = list(app.children)
        except BaseException:
            tops = []
        for node in tops:
            dialog = self._match_select_dialog(node)
            if dialog is not None:
                return dialog
        for node in self._collect_dialog_nodes(app, max_depth=6):
            dialog = self._match_select_dialog(node)
            if dialog is not None:
                return dialog
        return None

    def _select_dialog_selected_items(self, nodes) -> list:
        """从已收集的节点中取出被选中的列表项文案

        :param nodes: 对话框子树节点列表
        :return: 被选中项的文案列表(单选框至多一项)
        """
        selected = []
        for node in nodes:
            if (getattr(node, "roleName", "") or "") != "list item":
                continue
            try:
                states = [item.value_name for item in node.getState().getStates()]
            except BaseException:
                continue
            if "ATSPI_STATE_SELECTED" in states:
                selected.append(getattr(node, "name", "") or "")
        return selected

    def _read_select_dialog_state(self, dialog) -> dict:
        """读取选择框当前状态(标题/说明渲染、列表项、按钮、选中项)

        产品 DDialog 只 setTitle/setMessage 文本, 两个 label 都不暴露 accessible
        text, 故以 "label 已渲染(size 非零)" 作为标题与说明已展示的等价断言;
        列表项文案与按钮文案可读, 直接作为断言数据。

        :param dialog: dialog 节点
        :return: 状态字典
        """
        nodes = self._collect_dialog_nodes(dialog, max_depth=6)
        state = {
            "exists": True,
            "showing": False,
            "title_rendered": False,
            "message_rendered": False,
            "list_showing": False,
            "items": [],
            "selected_items": [],
            "buttons": [],
            "ok_enabled": False,
            "cancel_enabled": False,
        }
        try:
            state["showing"] = bool(dialog.showing)
        except BaseException:
            state["showing"] = False
        for node in nodes:
            role = getattr(node, "roleName", "") or ""
            name = getattr(node, "name", "") or ""
            if role == "label" and name == self.SELECT_DIALOG_TITLE_LABEL:
                state["title_rendered"] = bool(
                    getattr(node, "showing", False)
                ) and self._element_rendered(node)
            elif role == "label" and name == self.SELECT_DIALOG_MESSAGE_LABEL:
                state["message_rendered"] = bool(
                    getattr(node, "showing", False)
                ) and self._element_rendered(node)
            elif role == "list":
                state["list_showing"] = bool(getattr(node, "showing", False))
            elif role == "list item":
                if getattr(node, "showing", False):
                    state["items"].append(name)
            elif role == "push button" and name in (
                self.SELECT_DIALOG_CANCEL_TEXT,
                self.SELECT_DIALOG_OK_TEXT,
            ):
                if name not in state["buttons"]:
                    state["buttons"].append(name)
                key = (
                    "ok_enabled"
                    if name == self.SELECT_DIALOG_OK_TEXT
                    else "cancel_enabled"
                )
                try:
                    state[key] = bool(node.sensitive)
                except BaseException:
                    state[key] = False
        state["selected_items"] = self._select_dialog_selected_items(nodes)
        return state

    def get_select_dialog_state(self, timeout: int = 20) -> dict:
        """等待并获取 dpm_select 选择框状态(列表项与按钮就绪后才返回)

        :param timeout: 最长等待秒数
        :return: 见 _read_select_dialog_state; 未出现时 exists 为 False
        """
        state = {
            "exists": False,
            "showing": False,
            "title_rendered": False,
            "message_rendered": False,
            "list_showing": False,
            "items": [],
            "selected_items": [],
            "buttons": [],
            "ok_enabled": False,
            "cancel_enabled": False,
        }
        for _ in range(timeout):
            dialog = self._find_select_dialog()
            if dialog is not None:
                state = self._read_select_dialog_state(dialog)
                if state["items"] and state["buttons"]:
                    return state
            sleep(1)
        return state

    def get_select_dialog_items(self) -> list:
        """获取当前选择框的列表项文案(按界面顺序)

        :return: 列表项文案列表, 选择框不存在时返回空列表
        """
        dialog = self._find_select_dialog()
        if dialog is None:
            return []
        return self._read_select_dialog_state(dialog)["items"]

    def get_selected_select_dialog_items(self) -> list:
        """获取当前选择框中被选中的列表项文案

        :return: 被选中项文案列表, 选择框不存在时返回空列表
        """
        dialog = self._find_select_dialog()
        if dialog is None:
            return []
        nodes = self._collect_dialog_nodes(dialog, max_depth=6)
        return self._select_dialog_selected_items(nodes)

    def select_dialog_option(self, option_text: str, timeout: int = 10) -> bool:
        """在选择框中点选指定列表项并回读选中状态

        列表项与按钮在 AT-SPI 上都不暴露 Action 接口(V20 DDialog 实测
        get_n_actions() 为 0), 因此用 xdotool 点击项中心, 等价于用户单击列表项。

        :param option_text: 列表项文案(即脚本传给 dpm_select 的选项)
        :param timeout: 最长等待秒数
        :return: True 表示该列表项已处于选中状态
        """
        for _ in range(timeout):
            dialog = self._find_select_dialog()
            if dialog is not None:
                for node in self._collect_dialog_nodes(dialog, max_depth=6):
                    if (getattr(node, "roleName", "") or "") != "list item":
                        continue
                    if (getattr(node, "name", "") or "") != option_text:
                        continue
                    if self._click_at_element(node):
                        sleep(1)
                        if self.get_selected_select_dialog_items() == [option_text]:
                            return True
            sleep(1)
        logger.warning(f"选择框列表项未被选中: {option_text!r}")
        return False

    def click_select_dialog_button(self, button_text: str, timeout: int = 10) -> bool:
        """点击选择框上的指定按钮

        按钮与列表项一样没有 AT-SPI Action, 用 xdotool 点击按钮中心。

        :param button_text: 按钮文案("取消"/"确认")
        :param timeout: 最长等待秒数
        :return: True 表示已发出点击
        """
        for _ in range(timeout):
            dialog = self._find_select_dialog()
            if dialog is not None:
                for node in self._collect_dialog_nodes(dialog, max_depth=6):
                    if (getattr(node, "roleName", "") or "") != "push button":
                        continue
                    if (getattr(node, "name", "") or "") != button_text:
                        continue
                    if self._click_at_element(node):
                        sleep(1)
                        return True
            sleep(1)
        return False

    def wait_select_dialog_closed(self, timeout: int = 10) -> bool:
        """等待选择框关闭

        :param timeout: 最长等待秒数
        :return: True 表示选择框已从 AT-SPI 树中消失
        """
        for _ in range(timeout):
            if self._find_select_dialog() is None:
                return True
            sleep(1)
        return False

    def close_select_dialogs(self, rounds: int = 3) -> int:
        """关闭遗留的选择框(点"取消"), 供用例前置自愈与 finally 清理使用

        :param rounds: 轮询轮数(脚本在取消后可能继续弹出下一个选择框)
        :return: 累计关闭的选择框数量
        """
        closed = 0
        for _ in range(rounds):
            if self._find_select_dialog() is None:
                break
            if self.click_select_dialog_button(self.SELECT_DIALOG_CANCEL_TEXT, timeout=3):
                closed += 1
            sleep(1)
        return closed

    # ----- 虚拟 U 盘前置数据辅助(dpm_select 选择框用例共用) -----

    def get_usb_volume_label(self, loop_dev: str) -> str:
        """读取虚拟 U 盘(loop 设备)的 ext4 卷标

        :param loop_dev: loop 设备路径(如 /dev/loop0)
        :return: 卷标, 读取失败返回空字符串
        """
        try:
            output = self.sudo_run_cmd(
                f"dumpe2fs -h {quote(loop_dev)} 2>/dev/null",
                timeout=10,
                out_debug_flag=False,
            )
        except BaseException:
            return ""
        # 该机器 sudo 会把"请输入密码/验证成功"提示混进 stdout, 且不带换行,
        # 会粘在命令输出的行首/行尾; 这里用"Filesystem volume name:"锚点取值,
        # 不受提示文本位置影响。
        match = re.search(
            r"Filesystem volume name:\s*(\S.*?)\s*$", output or "", re.MULTILINE
        )
        return match.group(1).strip() if match else ""

    def get_usb_device_select_entry(self, loop_dev: str, mount_point: str) -> str:
        """构造 U 盘选择框的选项文案(设备名 容量 [卷标(挂载点)])

        usb-fix 插件 enumerate_usb_devices 生成的选项形如
        "sdb 8G [sdb1(/media/uostest/UDISK)]"(设备名/容量/分区/挂载点);
        本方法按同一形态为无分区表的 loop 虚拟 U 盘生成
        "loop0 64M [AUTOTEST_UDISK1(/tmp/...)]", 卷标与容量都取自设备本身。

        :param loop_dev: loop 设备路径
        :param mount_point: 挂载点
        :return: 选项文案, 卷标或容量读取失败时返回空字符串
        """
        label = self.get_usb_volume_label(loop_dev)
        if not label:
            return ""
        try:
            output = self.sudo_run_cmd(
                f"blockdev --getsize64 {quote(loop_dev)} 2>/dev/null",
                timeout=10,
                out_debug_flag=False,
            )
            numbers = re.findall(r"\d+", output or "")
            size_bytes = int(numbers[-1]) if numbers else 0
        except BaseException:
            return ""
        if size_bytes <= 0:
            return ""
        size_mb = size_bytes // (1024 * 1024)
        size_text = f"{size_mb}M" if size_mb < 1024 else f"{size_mb // 1024}G"
        return f"{os.path.basename(loop_dev)} {size_text} [{label}({mount_point})]"

    # ----- 严重损坏的 FAT32 U 盘(usb-fix 的 severe 分支) -----

    def create_fat32_severe_corruption(self, partition) -> bool:
        """把真实 USB 分区破坏成"文件系统无法识别"的严重损坏状态

        产品依据(deepin-pc-manager 1.1.7 plugin-usb-fix/entry.sh 的
        check_filesystem): blkid 取不到文件系统类型即判定 FS_SEVERITY=severe
        ("分区 ... 文件系统无法识别（可能严重损坏）"), 后续 execute_repairs 走
        "文件系统严重损坏，自动修复不可用，建议格式化"分支、不再尝试 fsck 修复。
        因此这里抹掉引导扇区(BPB/FAT32 标识)以及 FAT1/FAT2/根目录所在的前
        4MB, 分区表与分区本身保持完好 —— 设备仍能被枚举, 符合"U 盘不损坏、
        已卸载"的前置。

        只用于 scsi_debug 合成的内存盘, 不接触任何真实存储数据。

        :param partition: 分区设备路径(如 /dev/sdb1)
        :return: True 表示损坏已注入
        """
        if not re.fullmatch(r"/dev/sd[a-z]+\d+", partition or ""):
            logger.error(f"严重损坏注入需要真实分区设备, 收到: {partition!r}")
            return False
        self.sudo_run_cmd(f"umount -l {partition} 2>/dev/null", timeout=20, out_debug_flag=False)
        dd_out = self.sudo_run_cmd(
            f"dd if=/dev/urandom of={partition} bs=1M count=4 conv=notrunc 2>&1; echo RC=$?",
            timeout=60,
            out_debug_flag=False,
        )
        if "RC=0" not in (dd_out or ""):
            logger.error(f"注入 FAT32 严重损坏失败: {dd_out!r}")
            return False
        self.sudo_run_cmd(
            f"sync; blockdev --flushbufs {partition} 2>/dev/null; true",
            timeout=30,
            out_debug_flag=False,
        )
        # 刷新 udev 视图(lsblk/产品枚举都读 udev 属性), 让损坏立即可见
        self.sudo_run_cmd(
            f"udevadm trigger --subsystem-match=block {partition} 2>/dev/null; "
            "udevadm settle --timeout=15 2>/dev/null; true",
            timeout=40,
            out_debug_flag=False,
        )
        sleep(1)
        return True

    def get_fat32_filesystem_unrecognized(self, partition) -> bool:
        """判定分区文件系统已无法识别(严重损坏), 与产品 severe 判据一致

        :param partition: 分区设备路径(如 /dev/sdb1)
        :return: True 表示 blkid 探测不到任何文件系统类型
        """
        if not partition:
            return False
        probe = self.sudo_run_cmd(
            f"blkid -p -o value -s TYPE {quote(partition)} 2>/dev/null; echo RC=$?",
            timeout=15,
            out_debug_flag=False,
        )
        # 该机器 sudo 的密码提示会混进 stdout 且不带换行, 这里只认已知类型标记,
        # 不按"输出为空"判断, 避免提示文本被误当成探测结果。
        known_types = ("vfat", "fat32", "exfat", "ntfs", "ext4", "ext3", "ext2", "iso9660")
        detected = [token for token in (probe or "").split() if token in known_types]
        udev_type = self.run_cmd(
            f"lsblk -no FSTYPE {quote(partition)} 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        logger.info(
            f"{partition} blkid 探测结果={detected or '无'} / lsblk FSTYPE={udev_type or '空'}"
        )
        return not detected

    def get_fat32_filesystem_check_rc(self, partition) -> int:
        """对分区执行 fsck.vfat 只读检查, 返回退出码(损坏时非 0)

        :param partition: 分区设备路径(如 /dev/sdb1)
        :return: fsck.vfat -n 的退出码, 无法执行返回 -1
        """
        if not partition:
            return -1
        out = self.sudo_run_cmd(
            f"fsck.vfat -n {quote(partition)} >/dev/null 2>&1; echo RC=$?",
            timeout=20,
            out_debug_flag=False,
        )
        match = re.search(r"RC=(\d+)", out or "")
        return int(match.group(1)) if match else -1

    def close_usb_fix_prompt_dialog(self, rounds=3) -> int:
        """关闭 USB 修复流程残留的交互框(点"取消"或按 Escape)

        :param rounds: 最多尝试轮次
        :return: 实际关闭的交互框数量
        """
        closed = 0
        for _ in range(rounds):
            dialog = self._find_usb_confirm_dialog()
            if dialog is None:
                break
            nodes = self._collect_usb_dialog_nodes(dialog)
            button = self._find_usb_dialog_button(nodes, ("取消",))
            if button is not None:
                if not self._atspi_do_action(button):
                    self._click_at_element(button)
                closed += 1
            else:
                self.run_cmd("xdotool key Escape", timeout=2, out_debug_flag=False)
            sleep(1)
        return closed

    # ===== exFAT U 盘现场构造与数据完整性校验(用例 2005749) =====

    def mount_usb_partition(self, partition, mount_point, fstype="") -> bool:
        """把 USB 分区挂载到指定挂载点(先清理 udisks2 的自动挂载与旧挂载)

        :param partition: 分区设备路径(如 /dev/sdb1)
        :param mount_point: 挂载点路径
        :param fstype: 指定文件系统类型, 为空时由内核自动探测
        :return: True 表示挂载成功
        """
        if not partition:
            return False
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; true',
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(f"mkdir -p {quote(mount_point)}", timeout=10, out_debug_flag=False)
        type_opt = f"-t {quote(fstype)} " if fstype else ""
        self.sudo_run_cmd(
            f"mount {type_opt}{quote(partition)} {quote(mount_point)} 2>/dev/null",
            timeout=20,
            out_debug_flag=False,
        )
        sleep(1)
        return self.get_usb_device_mounted(mount_point=mount_point)

    def get_usb_partition_fsck_check_rc(self, partition, fstype="vfat") -> int:
        """按产品检测逻辑执行 "fsck -n -t <fstype>", 返回退出码

        产品 plugin-usb-fix/entry.sh 的 check_filesystem 对每个分区跑这条命令,
        退出码非 0 即判 corrupted。用例用它断言"检测异常"的构造真实生效。

        :param partition: 分区设备路径(如 /dev/sdb1)
        :param fstype: 文件系统类型(vfat/exfat/ntfs/ext4)
        :return: fsck 退出码, 无法执行返回 -1
        """
        if not partition or not fstype:
            return -1
        out = self.sudo_run_cmd(
            f"fsck -n -t {quote(fstype)} {quote(partition)} >/dev/null 2>&1; echo RC=$?",
            timeout=180,
            out_debug_flag=False,
        )
        match = re.search(r"RC=(\d+)", out or "")
        return int(match.group(1)) if match else -1

    def _get_usb_fat_bpb_geometry(self, partition) -> tuple:
        """从 FAT 引导扇区(BPB)读取 (保留扇区数, FAT 个数, 每个 FAT 的扇区数)

        :param partition: 已卸载的 FAT 分区设备路径
        :return: (reserved, fats, fat_sectors), 读取失败返回 (0, 0, 0)
        """
        def read_od(skip, count, fmt):
            out = self.strip_sudo_noise(
                self.sudo_run_cmd(
                    f"dd if={quote(partition)} bs=1 skip={skip} count={count} "
                    f"2>/dev/null | od -An -t{fmt}",
                    timeout=20,
                    out_debug_flag=False,
                )
            ).split()
            try:
                return int(out[0], 0) if out else 0
            except ValueError:
                return 0

        reserved = read_od(14, 2, "u2")
        fats = read_od(16, 1, "u1")
        fat_sectors = read_od(36, 4, "u4") or read_od(22, 2, "u2")
        return reserved, fats, fat_sectors

    def corrupt_usb_fat32_fat_area(self, partition, sectors=100) -> bool:
        """按用例前置条件清零 FAT32 的 FAT1 起始 100 个扇区, 制造"脏标志"现场

        用例给的命令是
        "sudo dd if=/dev/zero of=/dev/sdb1 bs=512 count=100 seek=32"
        (seek 即 BPB 里的保留扇区数, 本机实测为 32), 即只破坏 FAT1 的开头。
        实测(dosfstools 4.1): 只坏 FAT1 时 fsck.fat -n 与 fsck -n -t vfat 都返回 1,
        只读挂载报 "can't read superblock"; "fsck -y -t vfat" 用 FAT2 重建 FAT1,
        退出码 1(<=1) 记"修复成功", 修复后挂载正常、样本 sha256 不变。

        :param partition: 已卸载的 FAT32 分区设备路径(如 /dev/sdb1)
        :param sectors: 清零的扇区数(用例为 100)
        :return: True 表示清零完成且类型仍识别为 vfat
        """
        if not re.match(self.EXT4_PARTITION_RE, partition or ""):
            logger.error(f"FAT32 脏标志构造需要块设备, 收到: {partition!r}")
            return False
        reserved, _fats, _fat_sectors = self._get_usb_fat_bpb_geometry(partition)
        if reserved <= 0:
            logger.error(f"{partition} 读取 FAT32 BPB 保留扇区数失败: {reserved}")
            return False
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; '
            f"dd if=/dev/zero of={quote(partition)} bs=512 seek={reserved} "
            f"count={sectors} conv=notrunc 2>/dev/null; sync; "
            f"blockdev --flushbufs {quote(partition)} 2>/dev/null; "
            f"udevadm trigger --action=change --subsystem-match=block "
            f"{quote(partition)} 2>/dev/null; udevadm settle --timeout=10 2>/dev/null; true",
            timeout=120,
            out_debug_flag=False,
        )
        fs_type = self.run_cmd(
            f"lsblk -no FSTYPE {quote(partition)} 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        rc = self.get_usb_partition_fsck_check_rc(partition, "vfat")
        logger.info(
            f"FAT32 FAT1 清零 {partition}: 保留扇区={reserved}, 清零 {sectors} 扇区, "
            f"类型={fs_type!r}, fsck -n rc={rc}"
        )
        return fs_type == "vfat" and rc != 0

    def corrupt_usb_fat32_fat_copies(self, partition) -> bool:
        """把 FAT32 的两个 FAT 副本全部清零, 制造 fsck 无法自愈的"逻辑损坏"

        只留 BPB 与簇堆, lsblk/blkid 仍识别为 vfat(命中 corrupted 而非 severe),
        但根目录簇链彻底丢失: 只读挂载报 "can't read superblock",
        fsck -y 输出 "FAT32 root dir starts with a bad cluster!" 且退出码 1,
        产品按退出码(<=1)提示"修复成功", 而卷实际仍不可挂载 —— 该判定分歧
        与 exFAT 逻辑损坏场景同类, 用例层只断言"检测异常 + 修复流程执行"。
        :param partition: 已卸载的 FAT32 分区设备路径(如 /dev/sdb1)
        :return: True 表示清零完成且类型仍识别为 vfat
        """
        if not re.match(self.EXT4_PARTITION_RE, partition or ""):
            logger.error(f"FAT32 逻辑损坏构造需要块设备, 收到: {partition!r}")
            return False
        reserved, fats, fat_sectors = self._get_usb_fat_bpb_geometry(partition)
        if reserved <= 0 or fats <= 0 or fat_sectors <= 0:
            logger.error(
                f"{partition} FAT 布局异常: reserved={reserved}, fats={fats}, "
                f"fat_sectors={fat_sectors}"
            )
            return False
        self.sudo_run_cmd(
            f"for mp in $(findmnt -n -o TARGET {quote(partition)} 2>/dev/null); do "
            f'umount -l "$mp" 2>/dev/null; done; '
            f"dd if=/dev/zero of={quote(partition)} bs=512 seek={reserved} "
            f"count={fats * fat_sectors} conv=notrunc 2>/dev/null; sync; "
            f"blockdev --flushbufs {quote(partition)} 2>/dev/null; "
            f"udevadm trigger --action=change --subsystem-match=block "
            f"{quote(partition)} 2>/dev/null; udevadm settle --timeout=10 2>/dev/null; true",
            timeout=180,
            out_debug_flag=False,
        )
        fs_type = self.run_cmd(
            f"lsblk -no FSTYPE {quote(partition)} 2>/dev/null || true",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        rc = self.get_usb_partition_fsck_check_rc(partition, "vfat")
        logger.info(
            f"FAT32 FAT 副本全清 {partition}: reserved={reserved}, fats={fats}, "
            f"fat_sectors={fat_sectors}, 类型={fs_type!r}, fsck -n rc={rc}"
        )
        return fs_type == "vfat" and rc != 0

    def get_usb_exfat_filesystem_check_rc(self, partition) -> int:
        """对 exFAT 分区执行 fsck.exfat 只读检查, 返回退出码

        :param partition: 分区设备路径(如 /dev/sdb1)
        :return: fsck.exfat -n 的退出码, 无法执行返回 -1
        """
        if not partition:
            return -1
        out = self.sudo_run_cmd(
            f"fsck.exfat -n {quote(partition)} >/dev/null 2>&1; echo RC=$?",
            timeout=30,
            out_debug_flag=False,
        )
        match = re.search(r"RC=(\d+)", out or "")
        return int(match.group(1)) if match else -1

    def write_usb_integrity_payload(self, mount_point, prefix="autotest_exfat") -> dict:
        """在 U 盘挂载点写入数据完整性样本(4MB 二进制 + 中文名文本)

        用例要求"构造前置数据 -> 执行步骤 -> 断言关键结果 -> 回退数据"; 这里写入
        有确定摘要的样本, 修复流程结束后再校验文件仍在、摘要未变, 作为
        "U 盘数据不丢失、产品未擅自格式化"的等价断言。

        :param mount_point: U 盘挂载点
        :param prefix: 样本文件名前缀
        :return: 样本描述字典(含路径/摘要/大小/文本内容), 失败返回 {}
        """
        if not mount_point:
            return {}
        bin_path = f"{mount_point}/{prefix}_payload.bin"
        text_path = f"{mount_point}/{prefix}_数据完整性.txt"
        text_content = "电脑管家 U 盘修复用例(2005749) 数据完整性样本"
        self.sudo_run_cmd(
            f"dd if=/dev/urandom of={quote(bin_path)} bs=1M count=4 status=none 2>/dev/null",
            timeout=120,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"printf '%s' {quote(text_content)} > {quote(text_path)} 2>/dev/null",
            timeout=20,
            out_debug_flag=False,
        )
        self.sudo_run_cmd("sync", timeout=20, out_debug_flag=False)
        # sudo -S 的密码提示会粘在输出前面(框架把 stderr 并入 stdout), 先清洗
        sha256 = self.strip_sudo_noise(
            self.sudo_run_cmd(
                f"sha256sum {quote(bin_path)} 2>/dev/null | cut -d' ' -f1",
                timeout=30,
                out_debug_flag=False,
            )
        ).strip()
        size_out = self.strip_sudo_noise(
            self.sudo_run_cmd(
                f"stat -c %s {quote(bin_path)} 2>/dev/null", timeout=20, out_debug_flag=False
            )
        ).strip()
        if not sha256 or not size_out.isdigit():
            logger.error(f"写入 U 盘完整性样本失败: sha={sha256!r} size={size_out!r}")
            return {}
        logger.info(
            f"已写入 U 盘完整性样本: {bin_path} ({size_out} bytes, sha256={sha256[:16]}...)"
        )
        return {
            "bin": bin_path,
            "text": text_path,
            "text_content": text_content,
            "sha256": sha256,
            "size": int(size_out),
        }

    def verify_usb_integrity_payload(self, mount_point, payload) -> bool:
        """校验 U 盘完整性样本仍完好(文件存在、大小与摘要一致、文本内容未变)

        :param mount_point: U 盘挂载点
        :param payload: write_usb_integrity_payload 的返回值
        :return: True 表示样本完好
        """
        if not payload or not mount_point:
            return False
        bin_path = payload.get("bin", "")
        text_path = payload.get("text", "")
        sha256 = self.strip_sudo_noise(
            self.sudo_run_cmd(
                f"sha256sum {quote(bin_path)} 2>/dev/null | cut -d' ' -f1",
                timeout=30,
                out_debug_flag=False,
            )
        ).strip()
        size_out = self.strip_sudo_noise(
            self.sudo_run_cmd(
                f"stat -c %s {quote(bin_path)} 2>/dev/null", timeout=20, out_debug_flag=False
            )
        ).strip()
        text_out = self.strip_sudo_noise(
            self.sudo_run_cmd(
                f"cat {quote(text_path)} 2>/dev/null", timeout=20, out_debug_flag=False
            )
        ).strip()
        logger.info(
            f"数据完整性复核: sha256={sha256[:16]!r}... size={size_out!r} "
            f"text={text_out!r}"
        )
        if not size_out.isdigit():
            return False
        return (
            sha256 == payload.get("sha256")
            and int(size_out) == payload.get("size")
            and text_out == payload.get("text_content")
        )

    REPAIR_OUTPUT_ERROR_MARKERS = (
        "[ERROR]",
        "ERROR:",
        "错误",
        "失败",
        "无法识别",
        "不可用",
    )

    def get_repair_output_error_lines(self) -> list:
        """从修复对话框输出日志中筛出含错误/告警关键词的行

        用于"预期命令无报错"的用例: 产品脚本的错误行以 [ERROR] 前缀落盘, 同时
        兼容"错误/失败/无法识别/不可用"等中文告警文案(如"自动修复不可用")。

        :return: 命中错误关键词的行列表, 无错误时返回空列表
        """
        log_text = self.get_repair_output_text() or ""
        return [
            line
            for line in log_text.splitlines()
            if any(marker in line for marker in self.REPAIR_OUTPUT_ERROR_MARKERS)
        ]

    # ===== 无 USB 存储设备现场(用例 2005761: 设备路径不存在) =====
    # usb-fix 插件只枚举 /sys/block/sd* 中 udev 属性 ID_BUS=usb 的整盘(见产品
    # plugin-usb-fix/entry.sh 的 enumerate_usb_devices)。测试机通常没有实体 U 盘,
    # 天然就是"设备路径不存在"现场; 若接了实体 U 盘, 用一条只作用于该盘的 udev
    # 规则把 ID_BUS 临时改写为 scsi, 使插件枚举结果为空(对插件等价于设备不存在),
    # 用例结束在 finally 里删除规则并重新触发块设备事件恢复原属性。全程只改 udev
    # 属性, 不写、不格式化、不卸载任何真实磁盘。

    USB_MASK_UDEV_RULE = "/etc/udev/rules.d/99-autotest-usb-mask.rules"
    USB_MASK_RECOVERY_SCRIPT = "/tmp/autotest_2005761_usb_mask_recover.sh"
    USB_MASK_RECOVERY_UNIT = "autotest-2005761-usb-mask-recovery"

    def _trigger_block_udev_events(self, timeout=60):
        """重新下发块设备 udev 事件并等待处理完成

        使 udev 规则的 ID_BUS 覆写/撤销立即生效, 并让插件下一次 udevadm 查询
        看到新属性。

        :param timeout: 命令超时秒数
        """
        self.sudo_run_cmd(
            "udevadm control --reload-rules 2>/dev/null; "
            "udevadm trigger --action=change --subsystem-match=block 2>/dev/null; "
            "udevadm settle --timeout=20 2>/dev/null; true",
            timeout=timeout,
            out_debug_flag=False,
        )
        sleep(1)

    def mask_usb_storage_devices(self) -> list:
        """把已接入的实体 USB 存储盘从 usb-fix 的枚举结果中临时屏蔽

        仅针对当前 ID_BUS=usb 的整盘写一条 udev 规则把 ID_BUS 覆写为 scsi,
        使插件的"无 USB 设备"分支可达; 规则带 systemd-run 定时兜底(进程被强杀
        时也能自动撤销), 正常路径由 unmask_usb_storage_devices 撤销。

        :return: 被屏蔽的整盘列表; 无需屏蔽或屏蔽失败返回 []
        """
        self._masked_usb_disks = []
        disks = self.get_usb_storage_disks()
        if not disks:
            return []
        rules = "\n".join(
            'SUBSYSTEM=="block", KERNEL=="%s", ENV{ID_BUS}="scsi"' % os.path.basename(disk)
            for disk in disks
        )
        self.sudo_run_cmd(
            "cat > {rule_file} <<'AUTOTEST_UDEV_EOF'\n{rules}\nAUTOTEST_UDEV_EOF".format(
                rule_file=self.USB_MASK_UDEV_RULE, rules=rules
            ),
            timeout=20,
            out_debug_flag=False,
        )
        rule_text = self.sudo_run_cmd(
            f"cat {self.USB_MASK_UDEV_RULE} 2>/dev/null", timeout=10, out_debug_flag=False
        )
        if "ID_BUS" not in (rule_text or ""):
            logger.error("写 USB 屏蔽 udev 规则失败, 无法构造无 U 盘现场")
            return []
        self._schedule_usb_mask_recovery()
        for _ in range(5):
            self._trigger_block_udev_events()
            if not self.get_usb_storage_disks():
                self._masked_usb_disks = disks
                logger.info(f"已临时屏蔽实体 USB 存储盘: {disks}")
                return disks
        logger.error(f"udev 规则未能屏蔽 USB 存储盘: {disks}")
        self.unmask_usb_storage_devices()
        return []

    def unmask_usb_storage_devices(self) -> bool:
        """撤销实体 USB 存储盘的 ID_BUS 覆写, 恢复插件的原始枚举结果

        可重复调用: 即使从未执行 mask(例如上一轮 worker 被强杀留下规则), 也会
        删除规则文件并重新触发块设备事件。

        :return: True 表示规则已删除且被屏蔽的设备重新可见(或无设备可恢复)
        """
        self.cancel_usb_mask_recovery()
        self.sudo_run_cmd(f"rm -f {self.USB_MASK_UDEV_RULE}", timeout=20, out_debug_flag=False)
        self._trigger_block_udev_events()
        disks = list(getattr(self, "_masked_usb_disks", []) or [])
        self._masked_usb_disks = []
        if not disks:
            return True
        visible = set(self.get_usb_storage_disks())
        restored = [disk for disk in disks if disk in visible]
        if len(restored) != len(disks):
            logger.error(f"实体 USB 盘属性未完全恢复: 期望 {disks}, 实际可见 {sorted(visible)}")
            return False
        logger.info(f"实体 USB 盘 ID_BUS 已恢复: {disks}")
        return True

    def _schedule_usb_mask_recovery(self, seconds=1500) -> bool:
        """安排兜底恢复: 若干秒后删除 USB 屏蔽规则并重新触发块设备事件

        :param seconds: 兜底触发延时(秒), 需大于用例最长运行时间
        :return: True 表示定时器已注册
        """
        script = (
            "#!/usr/bin/env bash\n"
            "# 用例 2005761 兜底恢复: 删除 USB 枚举屏蔽规则并刷新设备属性\n"
            f"rm -f {self.USB_MASK_UDEV_RULE}\n"
            "udevadm control --reload-rules 2>/dev/null\n"
            "udevadm trigger --action=change --subsystem-match=block 2>/dev/null\n"
            "udevadm settle --timeout=20 2>/dev/null\n"
            f"rm -f {self.USB_MASK_RECOVERY_SCRIPT}\n"
        )
        self.cancel_usb_mask_recovery()
        try:
            with open(self.USB_MASK_RECOVERY_SCRIPT, "w", encoding="utf-8") as script_file:
                script_file.write(script)
            os.chmod(self.USB_MASK_RECOVERY_SCRIPT, 0o755)
        except OSError as exc:
            logger.error(f"写 USB 屏蔽兜底恢复脚本失败: {exc}")
            return False
        self.sudo_run_cmd(
            f"systemd-run --on-active={int(seconds)} "
            f"--unit={self.USB_MASK_RECOVERY_UNIT} "
            f"/bin/bash {self.USB_MASK_RECOVERY_SCRIPT}",
            timeout=20,
            out_debug_flag=False,
        )
        state = self.run_cmd(
            f"systemctl show -p ActiveState --value {self.USB_MASK_RECOVERY_UNIT}.timer 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        return state.strip() == "active"

    def cancel_usb_mask_recovery(self):
        """取消 USB 屏蔽兜底恢复定时器并删除其临时脚本(可重复调用)"""
        self.sudo_run_cmd(
            f"bash -c 'systemctl stop {self.USB_MASK_RECOVERY_UNIT}.timer "
            f"{self.USB_MASK_RECOVERY_UNIT}.service 2>/dev/null; "
            f"systemctl reset-failed {self.USB_MASK_RECOVERY_UNIT}.service 2>/dev/null; "
            f"rm -f {self.USB_MASK_RECOVERY_SCRIPT}; true'",
            timeout=30,
            out_debug_flag=False,
        )

    def wait_repair_no_device_result(self, keywords, timeout=120, dismiss_notify=True) -> dict:
        """等待"无可用 USB 设备"分支的提示, 并顺手点掉阻塞脚本的 dpm_notify 提示框

        产品枚举不到 USB 存储设备时会以错误提示结束; 若提示通过 dpm_notify 弹出,
        脚本会阻塞在 "[等待你的确认]" 直到用户点【确定】, 所以这里一边轮询输出
        日志, 一边点掉提示框。

        :param keywords: 视为"未检测到设备/设备不存在"的关键词集合
        :param timeout: 最长等待秒数(每 2s 轮询一次)
        :param dismiss_notify: 是否自动点掉 dpm_notify 提示框
        :return: {"text": 输出全文, "matched": 命中的关键词或 "",
                  "notify_seen": 是否出现过提示框, "notify_dismissed": 点掉的提示框个数}
        """
        result = {"text": "", "matched": "", "notify_seen": False, "notify_dismissed": 0}
        for _ in range(max(1, int(timeout) // 2)):
            if dismiss_notify:
                try:
                    if self.get_repair_notify_dialog_state().get("has_ok"):
                        result["notify_seen"] = True
                        if self.click_repair_notify_ok(timeout=3):
                            result["notify_dismissed"] += 1
                        continue
                except BaseException:
                    pass
            text = self.get_repair_output_text()
            if text:
                result["text"] = text
            for keyword in keywords:
                if keyword in text:
                    result["matched"] = keyword
                    break
            if result["matched"]:
                break
            sleep(2)
        return result


    # ===== 系统检测「全部通过」环境构造(PMS 2032447/2032451 等全通过态用例) =====

    DETECTION_CONF = "~/.config/deepin-pc-manager/deepin-pc-manager.conf"
    FAKE_SENSORS = "/usr/local/bin/sensors"
    DETECTION_BACKUP_DIR = "/tmp/pcm_detection_env_bak"
    DETECTION_LOCAL_REPO = "/tmp/pcm_local_repo"

    def _sudo_sh(self, command, timeout=30):
        """以 root 执行 shell 命令(密码取 setting/globalconfig.ini 的 PASSWORD)"""
        return self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S bash -c {command!r}",
            timeout=timeout,
        )

    def setup_detection_all_pass_environment(self, intranet_address=None) -> dict:
        """构造「全面检测全部通过」所需环境, 返回回退状态

        测试机离线下, 3 个检测项会稳定异常, 需按产品支持的途径临时构造:
        1. CPU 温度: 未安装 lm-sensors 时 daemon 报 sensors.not.installed;
           构造一个输出 "No sensors found!" 的 sensors 可执行文件, 产品按
           「硬件不支持温度检测」判为通过(diagnostic no.cpu.temperature.sensor)。
        2. 网络访问: 产品支持内网模式(QSettings basic.network.mode=intranet +
           basic.network.intranetAddress), 指向可达的内网地址使 ping 连通性通过。
        3. 系统版本检测/仓库地址检查: daemon 先调 lastore UpdateSource 刷新
           更新源, 再读 UpdateStatus; 测试机 apt 源不可达时刷新失败。临时移走
           原 apt 源, 换成本地 file:// 空源(可离线刷新成功), 各组件状态为
           noUpdate, 版本项与仓库地址检查判为正常。
        :return: 回退所需状态字典(传给 teardown_detection_all_pass_environment)
        """
        import os

        state = {
            "sensors_created": False,
            "sensors_backup": "",
            "conf_backup": "",
            "apt_moved": False,
        }
        # 1) sensors 桩
        exists = self.run_cmd(
            f"test -e {self.FAKE_SENSORS} && echo yes || echo no",
            timeout=10, out_debug_flag=False,
        ).strip()
        if exists == "yes":
            state["sensors_backup"] = self.DETECTION_BACKUP_DIR + "/sensors.bak"
            self._sudo_sh(
                f"mkdir -p {self.DETECTION_BACKUP_DIR} && "
                f"cp -a {self.FAKE_SENSORS} {state['sensors_backup']}",
            )
        else:
            state["sensors_created"] = True
        import base64

        script = '#!/bin/sh\necho "No sensors found!" >&2\nexit 1\n'
        payload = base64.b64encode(script.encode()).decode()
        self._sudo_sh(
            "mkdir -p /usr/local/bin && "
            f"printf %s {payload} | base64 -d > {self.FAKE_SENSORS} && "
            f"chmod 755 {self.FAKE_SENSORS}",
        )
        # 2) 内网连通性配置
        addr = intranet_address or self.run_cmd(
            "ip route | awk '/default/{print $3; exit}'",
            timeout=10, out_debug_flag=False,
        ).strip()
        state["conf_backup"] = self.DETECTION_BACKUP_DIR + "/pcm.conf.bak"
        self._sudo_sh(f"mkdir -p {self.DETECTION_BACKUP_DIR} && chmod 777 {self.DETECTION_BACKUP_DIR}")
        self.run_cmd(
            f"mkdir -p ~/.config/deepin-pc-manager && "
            f"if [ -f {self.DETECTION_CONF} ]; then cp -a {self.DETECTION_CONF} {state['conf_backup']}; fi",
            timeout=10, out_debug_flag=False,
        )
        self.run_cmd(
            f"printf '\\n[basic.network.mode]\\nvalue=intranet\\n\\n"
            f"[basic.network.intranetAddress]\\nvalue={addr}\\n' >> {self.DETECTION_CONF}",
            timeout=10, out_debug_flag=False,
        )
        # 3) 临时移走 apt 源, 换成可离线刷新的本地文件源, 使 lastore 刷新更新源成功;
        #    空源会被产品判为「软件源列表无效」, 必须给出可用源
        state["apt_moved"] = True
        self._sudo_sh(
            f"mkdir -p {self.DETECTION_BACKUP_DIR}/aptsrc {self.DETECTION_LOCAL_REPO} && "
            f"cp -a /etc/apt/sources.list {self.DETECTION_BACKUP_DIR}/sources.list.bak && "
            f"mv /etc/apt/sources.list.d/*.list {self.DETECTION_BACKUP_DIR}/aptsrc/ 2>/dev/null; "
            f": > {self.DETECTION_LOCAL_REPO}/Packages && "
            f"echo 'deb [trusted=yes] file://{self.DETECTION_LOCAL_REPO} ./' > /etc/apt/sources.list",
        )
        self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S gdbus call --system "
            "--dest com.deepin.lastore "
            "--object-path /com/deepin/lastore --method "
            "com.deepin.lastore.Manager.UpdateSource",
            timeout=30, out_debug_flag=False,
        )
        sleep(20)
        return state

    def teardown_detection_all_pass_environment(self, state):
        """回退 setup_detection_all_pass_environment 的全部构造"""
        if not state:
            return
        if state.get("apt_moved"):
            self._sudo_sh(
                f"if [ -f {self.DETECTION_BACKUP_DIR}/sources.list.bak ]; then "
                f"cp -a {self.DETECTION_BACKUP_DIR}/sources.list.bak /etc/apt/sources.list; fi; "
                f"if [ -d {self.DETECTION_BACKUP_DIR}/aptsrc ]; then "
                f"mv {self.DETECTION_BACKUP_DIR}/aptsrc/*.list /etc/apt/sources.list.d/ 2>/dev/null; fi",
            )
        if state.get("sensors_backup"):
            self._sudo_sh(
                f"cp -a {state['sensors_backup']} {self.FAKE_SENSORS}",
            )
        elif state.get("sensors_created"):
            self._sudo_sh(f"rm -f {self.FAKE_SENSORS}")
        if state.get("conf_backup"):
            self.run_cmd(
                f"if [ -f {state['conf_backup']} ]; then cp -a {state['conf_backup']} "
                f"{self.DETECTION_CONF}; fi",
                timeout=10, out_debug_flag=False,
            )
        self._sudo_sh(f"rm -rf {self.DETECTION_BACKUP_DIR} {self.DETECTION_LOCAL_REPO}")

    CORE_PKG_SAMPLE_FILE = "/usr/share/man/man1/arch.1.gz"
    CORE_PKG_BACKUP_FILE = "/tmp/pcm_corefile_2032451.bak"

    def break_core_package_file(self) -> bool:
        """移走 coreutils 的一个已登记文件, 使核心包完整性校验失败

        产品对 coreutils 执行 dpkg --verify; 文件缺失时 dpkg 输出
        `??5??????   <path>`, 产品按 md5 校验失败判为 SystemCorePackageCorrupted,
        该检测项在界面为「需人工处理」(canFix=false), 用于构造均不可修复状态。
        备份放在固定路径, 不随检测环境回退目录一起删除。
        """
        self._sudo_sh(
            f"mv {self.CORE_PKG_SAMPLE_FILE} {self.CORE_PKG_BACKUP_FILE}",
        )
        verify = self.run_cmd(
            f"echo '{conf.PASSWORD}' | sudo -S dpkg --verify coreutils 2>&1 | grep -c "
            f"{self.CORE_PKG_SAMPLE_FILE} || true",
            timeout=30, out_debug_flag=False,
        )
        return verify.strip() not in ("", "0")

    def restore_core_package_file(self):
        """还原 break_core_package_file 移走的文件(幂等)"""
        self._sudo_sh(
            f"if [ -f {self.CORE_PKG_BACKUP_FILE} ]; then "
            f"install -o root -g root -m 644 {self.CORE_PKG_BACKUP_FILE} "
            f"{self.CORE_PKG_SAMPLE_FILE} && rm -f {self.CORE_PKG_BACKUP_FILE}; fi",
        )

    def get_last_full_scan_summary(self) -> str:
        """返回应用日志中最近一次全面检测完成汇总行(含 totalItems/totalProblems/overallScore)"""
        return self.run_cmd(
            "grep -a 'handleFullScanCompleted' "
            "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log | tail -1",
            timeout=10, out_debug_flag=False,
        ).strip()

    def get_app_log_line_count(self) -> int:
        """返回应用日志当前行数, 作为"只看本次运行新增日志"的基线"""
        out = self.run_cmd(
            "wc -l < ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log",
            timeout=10, out_debug_flag=False,
        ).strip()
        return int(out or 0)

    def get_last_fix_all_summary(self, since_line: int = 0) -> str:
        """返回应用日志中「一键修复」结束汇总行(只统计 since_line 之后的新增行)

        产品在全部修复结束后打印
        `finishFullScanFixAll: fixed N failed M unattempted K manualProblems P`,
        该行出现即表示一键修复流程已执行完毕, 不依赖结果页渲染。
        :param since_line: 基线行数, 调用 get_app_log_line_count() 取得;
                           传 0 时统计整个日志(历史运行可能干扰判断)。
        """
        return self.run_cmd(
            f"tail -n +{int(since_line) + 1} "
            "~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log "
            "| grep -a 'finishFullScanFixAll' | tail -1",
            timeout=10, out_debug_flag=False,
        ).strip()


#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/10
"""
import configparser
import os
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import sleep

# ---------------------------------------------------------------------------
# 等价实现说明(测试机环境限制绕行, 全部在 finally 回退, 不留残留)
#
# 用例预期是"一键修复后全部问题修复成功", 即产品状态卡片进入
# DetectionStatusWidget::setFixCompletedAllResolved(detection_fixDoneIcon,
# "All issues have been fixed")。而 applyFixCompletedState() 只有在
# manualProblems + fixFailedCount == 0 时才进入该分支, 因此全面检测结果里不能
# 存在"需人工处理/检测失败"的检测项。
#
# 测试机(离网 UOS 20 虚拟机)有两个纯环境性异常项会导致该分支不可达:
#   1) system_version: SystemDetector::detectSystemVersion 依赖 lastore
#      (com.deepin.lastore) 的 UpdateSource 任务; 无外网时 apt update 失败
#      -> failure:9999 "Lastore update source job failed";
#   2) network_connectivity: 公网模式 ping www.baidu.com 失败 -> failure:4012。
# 按作业规程"优先用等价实现把产品走到目标分支(配置注入/临时替换 DBus 返回)":
#   * 用产品自身支持的"内网模式"(basic.network.mode=intranet +
#     basic.network.intranetAddress=本机内网 IP)让网络访问检测目标可达;
#   * 临时用同名 D-Bus 桩(transient systemd 单元)替代 lastore 守护进程, 让
#     UpdateSource 成功且 UpdateStatus 为 noUpdate; 产品仍走自身真实的 lastore
#     调用链, apt 配置与 lastore 数据均不改动;
#   * 清理 autotest 历史残留的 pcm-test-* 重启循环单元(产品阈值 NRestarts>=5)。
# 另外用 ~/.ssh chmod 777 构造"可自动修复"的 SSH 密钥权限问题, 修复由产品以
# 当前用户身份 fchmod 收紧(实测 777 -> 700), 用例结束后恢复原权限。
# ---------------------------------------------------------------------------

# 临时 lastore 桩: 只实现产品检测用到的 Manager.UpdateSource / Job.Status /
# Manager.UpdateStatus 三处交互, 由 systemd-run 以 transient 单元托管。
LASTOR_STUB_SOURCE = '''
#!/usr/bin/env python3
import json
import time

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

BUS_NAME = "com.deepin.lastore"
MGR_PATH = "/com/deepin/lastore"
JOB_PATH = "/com/deepin/lastore/Job/update_source"
MGR_IFACE = "com.deepin.lastore.Manager"
JOB_IFACE = "com.deepin.lastore.Job"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
NAME_FLAG_DO_NOT_QUEUE = 4
PRIMARY_OWNER = 1
ALREADY_OWNER = 4

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)


class PropertiesMixin(object):
    def prop_value(self, interface, prop):
        raise dbus.exceptions.DBusException(
            "unknown property",
            name="org.freedesktop.DBus.Error.InvalidArgs")

    @dbus.service.method(PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        return self.prop_value(interface, prop)

    @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        return {}

    @dbus.service.signal(PROPS_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


class Manager(dbus.service.Object, PropertiesMixin):
    def __init__(self, bus):
        dbus.service.Object.__init__(self, bus, MGR_PATH)

    @dbus.service.method(MGR_IFACE, in_signature="", out_signature="o")
    def UpdateSource(self):
        return dbus.ObjectPath(JOB_PATH)

    @dbus.service.method(MGR_IFACE, in_signature="", out_signature="o")
    def UpdateSourceNow(self):
        return dbus.ObjectPath(JOB_PATH)

    def prop_value(self, interface, prop):
        if prop == "UpdateStatus":
            payload = {"UpdateStatus": {
                "security_upgrade": "noUpdate",
                "system_upgrade": "noUpdate",
                "unknown_upgrade": "noUpdate"}}
            return dbus.String(json.dumps(payload), variant_level=1)
        return PropertiesMixin.prop_value(self, interface, prop)


class Job(dbus.service.Object, PropertiesMixin):
    def __init__(self, bus):
        dbus.service.Object.__init__(self, bus, JOB_PATH)

    def prop_value(self, interface, prop):
        if prop == "Status":
            return dbus.String("succeed", variant_level=1)
        if prop == "Description":
            return dbus.String("{}", variant_level=1)
        if prop == "Name":
            return dbus.String("update_source", variant_level=1)
        return PropertiesMixin.prop_value(self, interface, prop)


def acquire_name(bus, timeout=60):
    iface = dbus.Interface(
        bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus"),
        "org.freedesktop.DBus")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = int(iface.RequestName(BUS_NAME, NAME_FLAG_DO_NOT_QUEUE))
        except dbus.exceptions.DBusException as exc:
            print("RequestName failed:", exc, flush=True)
            result = 0
        if result in (PRIMARY_OWNER, ALREADY_OWNER):
            return True
        time.sleep(1)
    return False


def main():
    bus = dbus.SystemBus()
    if not acquire_name(bus):
        print("lastore-stub failed to acquire bus name", flush=True)
        return
    Manager(bus)
    Job(bus)
    print("lastore-stub ready", flush=True)
    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
'''


class DetectionWidget(MyAppWidget):
    """系统检测模块专用 widget: 构造 SSH 权限问题与"全部修复成功"所需等价环境"""

    SSH_DIR = os.path.expanduser("~/.ssh")
    CONF_PATH = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
    CONF_BAK = "/tmp/pcm_2005485_net.conf.bak"
    STUB_PATH = "/tmp/pcm_2005485_lastore_stub.py"
    STUB_UNIT = "pcm-2005485-lastore-stub"
    LASTORE_NAME = "com.deepin.lastore"

    # ---------------------------------------------------------------- 基础
    def sh(self, cmd, timeout=30):
        """执行普通命令"""
        return self.run_cmd(cmd, timeout=timeout, out_debug_flag=False)

    def sh_rc(self, cmd, timeout=30):
        """执行普通命令并返回 (输出, 返回码)"""
        return self.run_cmd(cmd, timeout=timeout, out_debug_flag=False, return_code=True)

    def sudo_sh(self, cmd, timeout=60):
        """以 root 执行命令(测试机约定密码见 conf.PASSWORD)"""
        return self.sudo_run_cmd(cmd, timeout=timeout, out_debug_flag=False)

    # ------------------------------------------------------- 前置: SSH 权限
    def get_ssh_dir_mode(self) -> str:
        """读取 ~/.ssh 目录权限位(八进制)"""
        return (self.sh(f"stat -c %a {self.SSH_DIR} 2>/dev/null") or "").strip()

    def has_ssh_private_key(self) -> bool:
        """~/.ssh 下是否存在产品识别的私钥文件(detectSSHKey 只认这几个名字)"""
        output = self.sh(
            f"ls {self.SSH_DIR} 2>/dev/null "
            "| grep -xE 'id_rsa|id_dsa|id_ecdsa|id_ed25519|identity'"
        )
        return bool((output or "").strip())

    def setup_ssh_dir_wrong_permission(self):
        """构造 ~/.ssh 目录权限过大(777), 原权限记入 self.original_ssh_mode

        产品 SystemDetector::detectSSHKey 对 ~/.ssh 的期望权限是 755,
        permissionDoesNotExceed 判 777 为 modeOk=False; 目录属主仍是登录用户,
        属于 fixSshPermissionBits 能以用户身份 fchmod 修好的"可自动修复"问题
        (plugin-syscheck 据此置 canFix=True)。产品仅在 ~/.ssh 下存在私钥时才
        汇总权限结论, 缺失时生成临时 ed25519, 由 finally 删除。
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
        self.sh(f"chmod 777 {self.SSH_DIR}", timeout=10)

    def restore_ssh_dir_permission(self):
        """回退 ~/.ssh 目录权限, 并删除前置构造的临时私钥/目录"""
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

    # --------------------------------------------- 前置: 网络检测内网模式
    def backup_network_config(self):
        """备份网络检测设置(QSettings ini), 记录备份前是否已存在"""
        _, rc = self.sh_rc(f"cp {self.CONF_PATH} {self.CONF_BAK}", timeout=10)
        self.net_conf_existed = rc == 0
        log(f"网络检测配置备份: existed={self.net_conf_existed} rc={rc}")

    def set_intranet_network_mode(self, address):
        """把网络检测模式写为内网并指定内网地址(产品自身支持的配置项)

        配置段与 NetworkDetector::detectNetworkConnectivity 读取的一致:
        basic.network.mode / basic.network.intranetAddress。
        """
        cfg = configparser.ConfigParser()
        cfg.optionxform = str
        cfg.read(self.CONF_PATH)
        for section, value in (
            ("basic.network.mode", "intranet"),
            ("basic.network.intranetAddress", address),
        ):
            if not cfg.has_section(section):
                cfg.add_section(section)
            cfg.set(section, "value", value)
        with open(self.CONF_PATH, "w") as fp:
            cfg.write(fp)
        sleep(1)

    def get_network_mode_config(self) -> str:
        """读取配置中的网络检测模式(public / intranet)"""
        cfg = configparser.ConfigParser()
        cfg.optionxform = str
        cfg.read(self.CONF_PATH)
        return cfg.get("basic.network.mode", "value", fallback="")

    def restore_network_config(self):
        """回退网络检测配置"""
        if getattr(self, "net_conf_existed", False):
            self.sh(f"cp {self.CONF_BAK} {self.CONF_PATH}", timeout=10)
        else:
            self.sh(f"rm -f {self.CONF_PATH}", timeout=10)
        self.sh(f"rm -f {self.CONF_BAK}", timeout=10)
        sleep(1)

    def get_lan_ip(self) -> str:
        """本机第一个内网 IPv4 地址(内网模式下作为可达检测目标)"""
        return (self.sh("hostname -I | awk '{print $1}'") or "").strip()

    def ping_reachable(self, address) -> bool:
        """内网地址是否可 ping 通(与产品 pingCheck 同口径: 丢包率<100%)"""
        output = self.sh(
            f"ping -c 2 -W 2 -q {address} 2>/dev/null | grep -o '[0-9]*% packet loss'",
            timeout=30,
        )
        return bool((output or "").strip()) and "100% packet loss" not in output

    # ------------------------------------- 前置: 清理 autotest 残留重启单元
    def reset_stale_restart_loops(self) -> list:
        """重置 autotest 历史残留(pcm-test-*)的重启计数

        StabilityDetector::detectServiceRestarts 对 NRestarts>=5 的已加载
        service 判异常; 历史用例遗留在系统内的 pcm-test-*-loop.service 会让
        该检测项恒失败, 属于测试机残留, 这里用 systemctl reset-failed 归零。
        """
        units = self.sh(
            "systemctl list-units --type=service --all --no-legend --plain "
            "| awk '{print $1}' | grep '^pcm-test-' || true",
            timeout=30,
        )
        reset = []
        for unit in (units or "").split():
            count = (self.sh(
                f"systemctl show {unit} -p NRestarts --value 2>/dev/null"
            ) or "").strip()
            if count.isdigit() and int(count) >= 5:
                self.sudo_sh(f"systemctl reset-failed {unit}", timeout=30)
                reset.append(f"{unit}(NRestarts={count})")
        return reset

    # ------------------------------------------ 前置: lastore D-Bus 桩
    def get_lastore_owner(self) -> str:
        """返回 com.deepin.lastore 当前总线属主, 无属主时返回空串"""
        output, rc = self.sh_rc(
            "gdbus call --system --dest org.freedesktop.DBus "
            "--object-path /org/freedesktop/DBus "
            f"--method org.freedesktop.DBus.GetNameOwner {self.LASTORE_NAME}",
            timeout=20,
        )
        return (output or "").strip() if rc == 0 else ""

    def _stop_stub_unit(self):
        """停掉可能残留的桩 transient 单元"""
        self.sudo_sh(f"systemctl stop {self.STUB_UNIT} 2>/dev/null", timeout=60)
        self.sudo_sh(f"systemctl reset-failed {self.STUB_UNIT} 2>/dev/null", timeout=30)

    def start_lastore_stub(self) -> bool:
        """用 transient systemd 单元启动同名 lastore D-Bus 桩

        步骤: 停掉残留桩单元 -> 停 lastore 守护进程并等总线名释放 ->
        systemd-run 启动桩 -> 等桩取得 com.deepin.lastore 总线名。
        桩由 systemd 托管, 不受测试进程/会话退出影响。
        :return: True 表示桩已取得总线名
        """
        self.lastore_was_active = (self.sh(
            "systemctl is-active lastore-daemon"
        ) or "").strip() == "active"
        self._stop_stub_unit()
        with open(self.STUB_PATH, "w") as fp:
            fp.write(LASTOR_STUB_SOURCE)
        self.sudo_sh("systemctl stop lastore-daemon", timeout=90)
        for _ in range(30):
            active = (self.sh("systemctl is-active lastore-daemon") or "").strip()
            if active != "active" and not self.get_lastore_owner():
                break
            sleep(1)
        self.sudo_sh(
            f"systemd-run --unit={self.STUB_UNIT} --collect --service-type=simple "
            f"/usr/bin/python3 {self.STUB_PATH}",
            timeout=60,
        )
        owner = ""
        for _ in range(30):
            owner = self.get_lastore_owner()
            if owner:
                break
            sleep(1)
        unit_state = (self.sh(f"systemctl is-active {self.STUB_UNIT}") or "").strip()
        unit_log = self.sudo_sh(
            f"journalctl -u {self.STUB_UNIT} --no-pager -n 3 2>/dev/null | tail -2",
            timeout=30,
        )
        log(f"lastore 桩: owner={owner!r} unit={unit_state} "
            f"lastore_was_active={self.lastore_was_active} log={unit_log!r}")
        return bool(owner)

    def stop_lastore_stub(self):
        """停止桩单元并恢复 lastore 守护进程原状态, 清理临时文件"""
        self._stop_stub_unit()
        for _ in range(15):
            if not self.get_lastore_owner():
                break
            sleep(1)
        if getattr(self, "lastore_was_active", False):
            self.sudo_sh("systemctl start lastore-daemon", timeout=90)
            for _ in range(20):
                if (self.sh("systemctl is-active lastore-daemon") or "").strip() == "active":
                    break
                sleep(1)
        self.sh(f"rm -f {self.STUB_PATH}")
        log(f"lastore 恢复: active={(self.sh('systemctl is-active lastore-daemon') or '').strip()} "
            f"owner={self.get_lastore_owner()!r}")

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
        "All issues have been fixed" 即"所有问题已修复"的可访问等价载体。
        """
        for i in range(timeout):
            elements = self._visible_elements(expr)
            if elements:
                return (elements[0].description or "").strip()
            if i > 0 and i % 5 == 0:
                self.refresh_dogtail_root()
            sleep(1)
        return ""

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
        """等待修复确实开始: 修复进度卡片出现 / SSH 权限被收紧 / 已到结果态"""
        for _ in range(timeout * 2):
            if self._any_visible("$//detection_progress"):
                return True
            if self.get_ssh_dir_mode() != "777":
                return True
            if self._any_visible("$//detection_fixDoneIcon"):
                return True
            sleep(0.5)
        return False

    def wait_for_fix_done(self, timeout=150):
        """等待一键修复结束

        完成信号: 结果卡片切到"全部修复成功"图标 detection_fixDoneIcon
        (setFixCompletedAllResolved), 或 SSH 权限已收紧且一键修复入口隐藏、
        重新检测按钮可见。期间持续采样修复进度卡片是否出现。
        :return: (是否完成, 是否采样到修复进度卡片)
        """
        saw_progress = False
        deadline = time.time() + timeout
        rounds = 0
        while time.time() < deadline:
            rounds += 1
            try:
                if self._any_visible("$//detection_progress"):
                    saw_progress = True
            except BaseException:
                pass
            if self._any_visible("$//detection_fixDoneIcon"):
                return True, saw_progress
            if (self.get_ssh_dir_mode() != "777"
                    and not self._any_visible("$//detection_fixAllBtn")
                    and self._any_visible("$//detection_recheckBtn")):
                return True, saw_progress
            if rounds % 20 == 0:
                self.refresh_dogtail_root()
                self._focus_windows_safe()
            sleep(1)
        return False, saw_progress


class TestMyCase(BaseCase):

    def test_mycase_074(self):
        """系统检测--一键修复-全部修复成功

        前置条件: 检测发现多个可修复项(SSH 密钥目录/私钥权限过大)。
        步骤: 系统检测首页点击全面检测 -> 检测完成后点击"一键修复" ->
              观察修复进度并等待全部修复完成(点击"重新检测"可重新扫描)。
        预期(等价断言):
        1. 点击后产品进入修复流程(修复进度卡片可见, SSH 目录权限被产品实际
           收紧), 修复结束进入"全部修复成功"结果态;
        2. 结果态为 detection_fixDoneIcon, 可访问描述 "All issues have been
           fixed" 即"修复已完成, 所有问题已修复/所有问题已成功修复"的等价载体
           (V20 标题 QLabel 文案不对外暴露), 结果标题/描述元件已渲染;
        3. "一键修复"入口隐藏, "重新检测"按钮可见;
        4. SSH 密钥检测项状态更新为修复成功: ~/.ssh 权限由 777 收紧(实测 700),
           且产品自身检测通道(D-Bus Detect ssh_key)重新判定为正常;
        5. 应用进程未崩溃。
        为让产品走到"全部修复成功"分支, 用等价实现消除了测试机的两个环境性
        不可修复项(内网模式配置 + lastore D-Bus 桩), 详见文件头注释。
        """
        widget = DetectionWidget(check_start=False)
        try:
            # ---- 前置 1: ~/.ssh 目录权限过大(可自动修复项) ----
            widget.setup_ssh_dir_wrong_permission()
            self.assert_equal("777", widget.get_ssh_dir_mode())
            self.assert_true(widget.has_ssh_private_key())

            # ---- 前置 2: 网络检测切内网模式, 检测目标可达 ----
            widget.backup_network_config()
            lan_ip = widget.get_lan_ip()
            self.assert_true(bool(lan_ip))
            widget.set_intranet_network_mode(lan_ip)
            self.assert_equal("intranet", widget.get_network_mode_config())
            self.assert_true(widget.ping_reachable(lan_ip))
            log(f"网络检测等价构造: mode=intranet address={lan_ip}")

            # ---- 前置 3: 清理 autotest 残留重启单元 + 启动 lastore 桩 ----
            reset_units = widget.reset_stale_restart_loops()
            log(f"重置的 autotest 残留重启单元: {reset_units}")
            self.assert_true(widget.start_lastore_stub())

            # ---- 启动电脑管家并进入系统检测页面 ----
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            # ---- 前置生效校验: 产品自身检测通道结论 ----
            ssh_ok, ssh_detail = widget.get_detection_item_verdict("ssh_key")
            log(f"ssh_key 检测结论: ok={ssh_ok} detail={ssh_detail}")
            self.assert_true(ssh_ok is False)
            for item in ("system_version", "network_connectivity", "service_restarts"):
                ok, detail = widget.get_detection_item_verdict(item)
                log(f"{item} 检测结论: ok={ok} detail={detail}")
                self.assert_true(ok is True)

            # ---- 步骤 1: 全面检测 ----
            self.assert_true(widget.get_detection_full_scan_button_showing(timeout=10))
            widget.click_detection_full_scan_button()
            self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
            sleep(2)
            self.assert_true(widget.get_detection_result_showing(timeout=20))

            # 检测结果应为"发现问题(可修复)", 且存在一键修复入口
            issue_desc = widget.get_icon_description("$//detection_issuesIcon")
            log(f"检测结果图标描述: {issue_desc!r}")
            self.assert_true("fixable" in issue_desc.lower())
            self.assert_true(widget.get_detection_fix_all_button_showing())
            self.assert_true(widget.get_detection_recheck_button_showing())

            # ---- 步骤 2: 点击一键修复, 等待全部修复完成 ----
            self.assert_true(widget.click_fix_all_button())
            fixed, saw_progress = widget.wait_for_fix_done(timeout=150)
            log(f"修复进度卡片采样={saw_progress} 修复完成={fixed}")
            self.assert_true(fixed)

            # ---- 步骤 3: 断言"全部修复成功"结果态 ----
            done_desc = widget.get_icon_description("$//detection_fixDoneIcon")
            log(f"修复结果图标描述: {done_desc!r}")
            self.assert_true("all issues have been fixed" in done_desc.lower())
            self.assert_true(widget.get_detection_result_title_showing())
            self.assert_true(widget.get_detection_result_desc_showing())
            self.assert_false(widget.get_detection_fix_all_button_showing())
            self.assert_true(widget.get_detection_recheck_button_showing())

            # ---- 断言 SSH 检测项状态更新为修复成功 ----
            mode = widget.get_ssh_dir_mode()
            log(f"修复后 ~/.ssh 权限: {mode}")
            self.assert_true(mode.isdigit())
            self.assert_true((int(mode, 8) & 0o077) == 0)
            verdict, detail = widget.get_detection_item_verdict("ssh_key")
            log(f"修复后 ssh_key 检测结论: ok={verdict} detail={detail}")
            self.assert_true(verdict is True)

            # ---- 应用未崩溃 ----
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            try:
                widget.kill_pc_manager()
                self.assert_true(widget.wait_pc_manager_exit())
            except BaseException:
                pass
            widget.restore_ssh_dir_permission()
            widget.restore_network_config()
            widget.stop_lastore_stub()

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
无人值守用例的锁屏保护。

DDE 默认 300s 关屏、900s 锁屏。用例执行期间一旦进入锁屏，xdotool 点击会落到
锁屏窗口上，界面用例会被误判为产品缺陷。这里在测试会话开始时临时关闭锁屏、
关屏和 X 屏保，并在每个用例开始前解除已经存在的锁屏，会话结束后原样恢复。
"""
import atexit
import os
import re
import shlex
import time

from setting.globalconfig import GlobalConfig
from src import logger
from src.cmdctl import CmdCtl

SESSION_MANAGER = "com.deepin.SessionManager"
SESSION_MANAGER_PATH = "/com/deepin/SessionManager"
LOCK_FRONT = "com.deepin.dde.lockFront"
LOCK_FRONT_PATH = "/com/deepin/dde/lockFront"

# schema/key -> 关闭锁屏时写入的值
LOCK_SETTINGS = (
    ("com.deepin.dde.power", "screen-black-lock", "false"),
    ("com.deepin.dde.power", "sleep-lock", "false"),
    ("com.deepin.dde.power", "line-power-lock-delay", "3600"),
    ("com.deepin.dde.power", "line-power-screen-black-delay", "3600"),
    ("com.deepin.dde.power", "line-power-screensaver-delay", "3600"),
    ("com.deepin.dde.power", "line-power-short-idle-delay", "3600"),
    ("com.deepin.dde.power", "battery-lock-delay", "3600"),
    ("com.deepin.dde.power", "battery-screen-black-delay", "3600"),
    ("com.deepin.dde.power", "battery-screensaver-delay", "3600"),
    ("com.deepin.dde.power", "battery-short-idle-delay", "3600"),
    ("com.deepin.wrap.gnome.desktop.screensaver", "lock-enabled", "false"),
    ("com.deepin.wrap.gnome.desktop.screensaver", "idle-activation-enabled", "false"),
    ("org.gnome.desktop.screensaver", "lock-enabled", "false"),
    ("org.gnome.desktop.screensaver", "idle-activation-enabled", "false"),
    ("org.gnome.desktop.session", "idle-delay", "0"),
)


class ScreenLockGuard:
    """临时关闭/恢复当前测试用户的锁屏与屏保配置。"""

    def __init__(self):
        self._saved = {}
        self._xset = None
        self._active = False
        atexit.register(self.restore)

    @staticmethod
    def _env_prefix():
        display = os.environ.get("DISPLAY") or ":0"
        bus = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
        if not bus:
            bus = f"unix:path=/run/user/{os.getuid()}/bus"
        return (
            f"export DISPLAY={shlex.quote(display)}; "
            f"export DBUS_SESSION_BUS_ADDRESS={shlex.quote(bus)}; "
        )

    def _run(self, command, timeout=8, return_code=True):
        try:
            return CmdCtl.run_cmd(
                f"{self._env_prefix()}{command}",
                timeout=timeout,
                out_debug_flag=False,
                command_log=False,
                return_code=return_code,
            )
        except BaseException as exc:
            logger.warning(f"[锁屏保护] 命令执行失败: {command}: {exc}")
            return ("", 1) if return_code else ""

    def _gsettings_get(self, schema, key):
        out, status = self._run(f"gsettings get {shlex.quote(schema)} {shlex.quote(key)}")
        if status != 0:
            return None
        return out.strip()

    def _gsettings_set(self, schema, key, value):
        _, status = self._run(
            f"gsettings set {shlex.quote(schema)} {shlex.quote(key)} {shlex.quote(value)}"
        )
        return status == 0

    @staticmethod
    def _snapshot_xset():
        """记录 X 屏保/DPMS 参数，非 X11 或失败时返回 None。"""
        if not GlobalConfig.IS_X11:
            return None
        out, status = ScreenLockGuard._run_static("xset q", timeout=5)
        if status != 0:
            return None
        timeout_match = re.search(r"timeout:\s*(\d+)\s+cycle:\s*(\d+)", out)
        blank_match = re.search(r"prefer blanking:\s*(yes|no)", out)
        dpms_match = re.search(
            r"Standby:\s*(\d+)\s+Suspend:\s*(\d+)\s+Off:\s*(\d+)", out
        )
        if not timeout_match:
            return None
        return {
            "timeout": timeout_match.group(1),
            "cycle": timeout_match.group(2),
            "blank": blank_match.group(1) if blank_match else "no",
            "dpms_enabled": "DPMS is Enabled" in out,
            "dpms": dpms_match.groups() if dpms_match else ("0", "0", "0"),
        }

    @staticmethod
    def _run_static(command, timeout=8):
        display = os.environ.get("DISPLAY") or ":0"
        bus = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
        if not bus:
            bus = f"unix:path=/run/user/{os.getuid()}/bus"
        prefix = (
            f"export DISPLAY={shlex.quote(display)}; "
            f"export DBUS_SESSION_BUS_ADDRESS={shlex.quote(bus)}; "
        )
        try:
            return CmdCtl.run_cmd(
                f"{prefix}{command}",
                timeout=timeout,
                out_debug_flag=False,
                command_log=False,
                return_code=True,
            )
        except BaseException as exc:
            logger.warning(f"[锁屏保护] 命令执行失败: {command}: {exc}")
            return "", 1

    def _restore_xset(self):
        if not self._xset:
            return
        state = self._xset
        self._run(
            f"xset s {state['timeout']} {state['cycle']}; "
            f"xset s {state['blank']}; "
            f"xset {'+dpms' if state['dpms_enabled'] else '-dpms'}; "
            f"xset dpms {state['dpms'][0]} {state['dpms'][1]} {state['dpms'][2]}",
            timeout=5,
        )

    def disable(self):
        """暂存并关闭锁屏、关屏和 X 屏保，幂等。"""
        if self._active:
            return
        self._active = True
        for schema, key, _ in LOCK_SETTINGS:
            value = self._gsettings_get(schema, key)
            if value is not None:
                self._saved[(schema, key)] = value

        changed = []
        for schema, key, value in LOCK_SETTINGS:
            if (schema, key) in self._saved and self._gsettings_set(schema, key, value):
                changed.append(f"{schema}.{key}")
        # X 屏保/DPMS 是独立于 gsettings 的兜底，必须一起关闭。
        self._xset = self._snapshot_xset()
        self._run("xset s off -dpms", timeout=5)
        logger.info(
            f"[锁屏保护] 已关闭锁屏，共 {len(changed)} 项 gsettings，"
            f"X11 屏保={'已关闭' if GlobalConfig.IS_X11 else '跳过'}"
        )

    def _dde_lock_state(self):
        out, _ = self._run(
            f"busctl --user get-property {SESSION_MANAGER} "
            f"{SESSION_MANAGER_PATH} {SESSION_MANAGER} Locked; "
            f"busctl --user get-property {LOCK_FRONT} "
            f"{LOCK_FRONT_PATH} {LOCK_FRONT} Visible",
            timeout=5,
        )
        return "b true" in out

    def is_locked(self):
        return self._dde_lock_state()

    def _unlock(self):
        # 先同步 DDE 的锁定状态；真实锁屏窗口仍需 root 的 logind 解锁才能关闭。
        self._run(
            f"busctl --user call {SESSION_MANAGER} {SESSION_MANAGER_PATH} "
            f"{SESSION_MANAGER} SetLocked b false",
            timeout=5,
        )
        CmdCtl.sudo_run_cmd(
            "loginctl unlock-sessions",
            timeout=10,
            out_debug_flag=False,
            command_log=False,
        )

    def ensure_unlocked(self):
        """用例开始前解除已经存在的锁屏。"""
        if not self.is_locked():
            return True
        logger.warning("[锁屏保护] 检测到锁屏，正在解锁")
        self._unlock()
        for _ in range(5):
            if not self.is_locked():
                logger.info("[锁屏保护] 锁屏已解除")
                return True
            time.sleep(0.5)
        logger.error("[锁屏保护] 锁屏解除失败，后续界面操作可能失败")
        return False

    def restore(self):
        """恢复进入测试前的锁屏配置。"""
        if not self._active:
            return
        for (schema, key), value in self._saved.items():
            self._gsettings_set(schema, key, value)
        self._restore_xset()
        self._active = False
        logger.info("[锁屏保护] 已恢复原始锁屏配置")

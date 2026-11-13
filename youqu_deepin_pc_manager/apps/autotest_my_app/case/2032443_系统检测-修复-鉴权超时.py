#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep

PKLA = "/etc/polkit-1/localauthority/50-local.d/49-pcmanager-test.pkla"
PKLA_BAK = "/tmp/49-pcmanager-test.pkla.2032443.bak"


class TestMyCase(BaseCase):

    def _pkla_disable(self):
        """临时移除测试机自建的 polkit 免密规则(恢复鉴权框), 并重启 polkitd"""
        rc = self.widget.sudo_run_cmd(
            f"cp -a {PKLA} {PKLA_BAK} && rm -f {PKLA} && systemctl restart polkit",
            timeout=30, out_debug_flag=False)
        logger.info(f"[2032443] pkla disable: {rc}")

    def _pkla_restore(self):
        """恢复测试机自建的 polkit 免密规则文件与 polkitd"""
        rc = self.widget.sudo_run_cmd(
            f"if [ -f {PKLA_BAK} ]; then chown root:root {PKLA_BAK} && chmod 644 {PKLA_BAK} && "
            f"mv -f {PKLA_BAK} {PKLA}; fi; systemctl restart polkit",
            timeout=30, out_debug_flag=False)
        logger.info(f"[2032443] pkla restore: {rc}")

    def _walk_find(self, node, target, depth=0):
        """递归查找指定 name 的 AT-SPI 节点(避开 pyatspi.utils 的 None 迭代问题)"""
        if node is None or depth > 8:
            return None
        try:
            if getattr(node, "name", "") == target:
                return node
            count = node.childCount
        except BaseException:
            return None
        for i in range(count):
            try:
                child = node.getChildAtIndex(i)
            except BaseException:
                continue
            found = self._walk_find(child, target, depth + 1)
            if found is not None:
                return found
        return None

    def _polkit_dialog_showing(self) -> bool:
        """pyatspi 遍历应用树，查找 dde-polkit-agent 的鉴权对话框"""
        try:
            import pyatspi
            for app in pyatspi.Registry.getDesktop(0):
                try:
                    if app is None or app.name != "dde-polkit-agent":
                        continue
                    node = self._walk_find(app, "Dialog_authdialog")
                    if node is not None:
                        return node.getState().contains(
                            pyatspi.state.STATE_SHOWING)
                except BaseException:
                    continue
        except BaseException:
            pass
        return False

    def _pkla_present(self) -> bool:
        out = self.widget.sudo_run_cmd(
            f"test -f {PKLA} && echo present || echo absent",
            timeout=10, out_debug_flag=False)
        return "present" in (out or "")

    def _input_sensitive(self) -> bool:
        try:
            el = self.widget.dog.find_element_by_attr("$//shellRepair_inputEdit")
            return bool(el and el.sensitive)
        except BaseException:
            return False

    def test_mycase_022(self):
        """系统检测-修复-鉴权超时

        产品依据: daemon 对 root 修复工具执行 polkit 鉴权, 请求 5 分钟超时
        (pc_manager1_adapter.h: repairAuthTimeoutMs = 5*60*1000), 超时后取消
        polkit 鉴权并下发 RepairToolState::TimedOut, 界面输出
        "Authorization timed out" (shell_repair_dialog.cpp:1025)。

        等价实现: 现版本检测修复免鉴权(ADR-0014), 唯一会弹鉴权框的是修复工具
        的 root 脚本; 测试机存在自建的 polkit 免密规则
        (49-pcmanager-test.pkla) 会吞掉鉴权框, 用例期间临时移除、结束后恢复。
        流程: 打印机修复 -> 开始修复 -> 弹鉴权框 -> 5 分钟不操作,
        校验: 鉴权框自动关闭、修复取消(未执行)、界面提示鉴权超时、无残留。
        """
        self.widget = widget = MyAppWidget(check_start=False)

        # 前置: 用户无 lpadmin 权限, 使修复若执行则必然改变系统状态
        self.assert_true(widget.get_lpadmin_group_exists())
        widget.remove_lpadmin_permission()
        sleep(1)
        self.assert_false(widget.get_lpadmin_permission_status())

        # 临时恢复鉴权: 移除测试机免密 polkit 规则
        self._pkla_disable()
        sleep(2)

        try:
            # 1) 启动应用 -> 修复工具 -> 打印机修复 -> 开始修复
            # 必须从桌面启动器拉起: ssh 会话启动的进程无 polkit 认证代理,
            # 鉴权请求会一直挂起(实测 340s 无框、无超时提示)。
            self.assert_true(widget.start_pc_manager_in_desktop_session())
            self.assert_true(widget.get_pc_manager_process_status())
            scope = widget.get_pc_manager_session_scope()
            sid = scope.replace("session-", "").replace(".scope", "")
            seat = widget.run_cmd(
                f"loginctl show-session {sid} -p Seat", timeout=5,
                out_debug_flag=False) or ""
            logger.info(f"[2032443] app scope={scope} seat={seat.strip()!r}")
            self.assert_true("seat0" in seat)
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))
            self.assert_true(widget.get_repair_cards_view_showing())
            widget.click_repair_card_by_name("打印机修复")
            self.assert_true(widget.get_repair_detail_showing())
            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=30))
            start_ts = time.time()
            logger.info(f"[2032443] 修复对话框已打开, 输出={widget.get_shell_repair_output_text()!r}")

            # 2) 等待鉴权框出现(最多 30s)
            polkit_seen = False
            deadline = start_ts + 30
            while time.time() < deadline:
                if self._polkit_dialog_showing():
                    polkit_seen = True
                    break
                sleep(1)
            logger.info(f"[2032443] polkit auth dialog seen={polkit_seen} "
                        f"elapsed={time.time() - start_ts:.1f}s")

            # 3) 5 分钟不操作, 观察鉴权框关闭 / 超时提示 / 修复是否取消
            keywords = ("Authorization timed out", "鉴权已超时", "鉴权超时")
            polkit_closed = False
            lpadmin_changed = False
            last_text = ""
            wait_deadline = start_ts + 340
            while time.time() < wait_deadline:
                showing = self._polkit_dialog_showing()
                if polkit_seen and not showing:
                    polkit_closed = True
                try:
                    cur = widget.get_shell_repair_output_text() or ""
                    if cur:
                        last_text = cur
                except BaseException:
                    cur = last_text
                if widget.get_lpadmin_permission_status():
                    lpadmin_changed = True
                if polkit_closed and any(kw in cur for kw in keywords):
                    break
                if widget.get_repair_completion_status(timeout=1):
                    break
                sleep(10)
            elapsed = time.time() - start_ts
            logger.info(f"[2032443] after wait: polkit_seen={polkit_seen} "
                        f"polkit_closed={polkit_closed} lpadmin_changed={lpadmin_changed} "
                        f"elapsed={elapsed:.1f}s text={last_text!r}")

            # 4) 断言: 鉴权框出现 -> 自动关闭 -> 提示鉴权超时 -> 修复未执行
            self.assert_true(polkit_seen)
            self.assert_true(polkit_closed)
            self.assert_true(any(kw in last_text for kw in keywords))
            self.assert_false(lpadmin_changed)
            self.assert_false(self._input_sensitive())
        finally:
            # 5) 回退: 关闭对话框、退出应用、恢复 lpadmin 与 polkit 免密规则
            # 修复在本用例被鉴权超时中断, 主流程无法保证脚本走完; 这里兜底点掉
            # 可能残留的完成提示框(openinfobox timeoutMs=0 不会自动消失)
            try:
                widget.finish_repair_flow()
            except BaseException:
                pass
            try:
                widget.close_repair_dialog()
            except BaseException:
                pass
            if widget.get_lpadmin_permission_status() is False:
                widget.restore_lpadmin_permission()
            try:
                widget.kill_pc_manager()
            except BaseException:
                pass
            self._pkla_restore()
            for _ in range(20):
                if not self._polkit_dialog_showing():
                    break
                sleep(1)
            logger.info(f"[2032443] teardown lpadmin={widget.get_lpadmin_permission_status()} "
                        f"polkit={self._polkit_dialog_showing()} "
                        f"app={widget.get_pc_manager_process_status()} "
                        f"pkla={self._pkla_present()}")
            self.assert_false(self._polkit_dialog_showing())
            self.assert_false(widget.get_pc_manager_process_status())
            self.assert_true(self._pkla_present())

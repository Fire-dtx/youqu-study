#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
from os.path import expanduser

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep

HOME_DIR = expanduser("~")
DUP_TEST_DIR = f"{HOME_DIR}/autotest_dup_file_batch"
TRASH_DIR = f"{HOME_DIR}/.local/share/Trash/files"


def _create_dup_test_files_for_batch(self):
    """创建多组重复文件, 用于验证重复文件清理批量彻底删除功能

    创建 2 组重复文件(每组 2 个内容相同、大小 2MB 的文件),
    重复文件扫描器要求文件大小 >= 1MB 才进入候选集,
    4 个文件分属不同子目录, 扫描器将它们归为 2 个重复组。
    """
    self.run_cmd(f"rm -rf {DUP_TEST_DIR}", timeout=5, out_debug_flag=False)
    dirs = [
        f"{DUP_TEST_DIR}/g1_a", f"{DUP_TEST_DIR}/g1_b",
        f"{DUP_TEST_DIR}/g2_a", f"{DUP_TEST_DIR}/g2_b",
    ]
    for d in dirs:
        self.run_cmd(f"mkdir -p {d}", timeout=5, out_debug_flag=False)
    self.run_cmd(
        f"dd if=/dev/zero bs=1M count=2 2>/dev/null | tr '\\0' 'A' > {dirs[0]}/dup_group1.bin",
        timeout=10, out_debug_flag=False,
    )
    self.run_cmd(
        f"cp {dirs[0]}/dup_group1.bin {dirs[1]}/dup_group1.bin",
        timeout=5, out_debug_flag=False,
    )
    self.run_cmd(
        f"dd if=/dev/zero bs=1M count=2 2>/dev/null | tr '\\0' 'B' > {dirs[2]}/dup_group2.bin",
        timeout=10, out_debug_flag=False,
    )
    self.run_cmd(
        f"cp {dirs[2]}/dup_group2.bin {dirs[3]}/dup_group2.bin",
        timeout=5, out_debug_flag=False,
    )
    sleep(1)


def _remove_dup_test_files_for_batch(self):
    """清理批量彻底删除测试创建的测试文件(包括回收站中的副本)"""
    self.run_cmd(f"rm -rf {DUP_TEST_DIR}", timeout=5, out_debug_flag=False)
    for name in ("dup_group1.bin", "dup_group2.bin"):
        self.run_cmd(
            f"rm -f '{TRASH_DIR}/{name}' 2>/dev/null || true",
            timeout=5, out_debug_flag=False,
        )


def _get_dup_file_result_showing(self) -> bool:
    """检查重复文件清理结果页是否显示(检测到重复文件)"""
    return self._any_visible("$//dupFile_resultTitle")


def _click_dup_file_smart_select(self, timeout=15):
    """点击重复文件清理结果页的"智能选择"按钮

    智能选择自动从每组重复文件中选中需要清理的文件,
    无需手动滚动表格逐个勾选复选框。

    :param timeout: 最长等待秒数
    :return: True 如果点击成功
    """
    self._safe_focus_windows()
    for attempt in range(timeout):
        self._refresh_app()
        try:
            btn = self.dog.find_element_by_attr("$//dupFile_smartSelectBtn")
            if btn:
                w, h = btn.size
                if w > 0 and h > 0:
                    if not self._click_at_element(btn):
                        self._atspi_do_action(btn)
                    sleep(1)
                    return True
        except BaseException:
            pass
        if attempt == 4:
            self.reconnect_dogtail()
        sleep(1)
    return False


def _confirm_smart_select_dialog(self, timeout=10):
    """在智能选择确认对话框中点击"继续选择"按钮

    点击"智能选择"后会弹出 DDialog 确认对话框,
    对话框包含"取消"和"继续选择"两个按钮, 需点击"继续选择"确认。

    :param timeout: 最长等待秒数
    :return: True 如果点击成功
    """
    for _ in range(timeout):
        try:
            buttons = self.dog.obj.findChildren(
                lambda n: n.roleName == "push button"
                and "继续选择" in (n.text or n.name or ""),
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


def _get_dup_file_execute_button_enabled(self, retries=10) -> bool:
    """检查重复文件清理执行按钮是否可用"""
    for _ in range(retries):
        try:
            self._refresh_app()
            btn = self.dog.find_element_by_attr("$//dupFile_executeBtn")
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


def _click_dup_file_execute_button(self):
    """点击重复文件清理结果页的执行按钮"""
    try:
        self.reconnect_dogtail()
        btn = self.dog.find_element_by_attr("$//dupFile_executeBtn")
        if btn and btn.showing:
            if not self._click_at_element(btn):
                self._atspi_do_action(btn)
            sleep(2)
            return
    except BaseException:
        pass
    try:
        self.reconnect_dogtail()
        btn = self.dog.find_element_by_attr("$//dupFile_executeBtn")
        if btn:
            bx, by = btn.position
            bw, bh = btn.size
            cx, cy = int(bx + bw / 2), int(by + bh / 2)
            self._safe_focus_windows()
            self.run_cmd(
                f"xdotool mousemove --sync {cx} {cy} click 1",
                timeout=10, out_debug_flag=False,
            )
            sleep(2)
            return
    except BaseException:
        pass
    raise RuntimeError("无法找到重复文件清理执行按钮")


def _select_dup_file_action(self, action_text):
    """在重复文件清理结果页的操作下拉框中选择指定操作

    操作下拉框(dupFile_actionCombo)包含"移至回收站"(默认)和"彻底删除"两项。
    先点击下拉框展开列表, 再点击目标操作项;
    若列表项无法通过 AT-SPI 点击, 则用键盘导航选择。

    :param action_text: 目标操作文本("移至回收站"或"彻底删除")
    """
    self._safe_focus_windows()
    self.reconnect_dogtail()
    combo = None
    for _ in range(15):
        try:
            self._refresh_app()
            combos = self.dog.obj.findChildren(
                lambda n: n.roleName == "combo box",
                recursive=True,
            )
            if combos:
                combo = combos[0]
                break
        except BaseException:
            pass
        self._safe_focus_windows()
        sleep(1)
    if combo is None:
        raise RuntimeError("无法找到重复文件清理操作下拉框(combo box)")
    if (combo.name or "") == action_text:
        return
    self._click_at_element(combo)
    sleep(1)
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
        self._key_to_app("Home")
        sleep(0.3)
        actions_order = ["移至回收站", "彻底删除"]
        tgt_idx = actions_order.index(action_text)
        for _ in range(tgt_idx):
            self._key_to_app("Down")
            sleep(0.3)
        self._key_to_app("Return")
        sleep(1)
    self.reconnect_dogtail()
    for _ in range(5):
        try:
            self._refresh_app()
            combos = self.dog.obj.findChildren(
                lambda n: n.roleName == "combo box",
                recursive=True,
            )
            if combos and (combos[0].name or "") == action_text:
                return
        except BaseException:
            pass
        sleep(1)
    raise RuntimeError(
        f"切换重复文件清理操作下拉框失败, 期望: {action_text}"
    )


def _get_dup_file_delete_confirm_dialog_showing(self, timeout=10) -> bool:
    """检测重复文件彻底删除确认对话框是否可见

    点击执行按钮后, 选择"彻底删除"操作会弹出 DDialog 确认对话框,
    对话框包含警告文本(如"文件彻底删除后无法恢复")和"取消"/"彻底删除"按钮。
    """
    for _ in range(timeout):
        try:
            dialogs = self.dog.obj.findChildren(
                lambda n: n.roleName in ("dialog", "alert dialog"),
                recursive=True,
            )
            if dialogs:
                for d in dialogs:
                    children = d.findChildren(
                        lambda n: n.roleName in ("label", "text"),
                        recursive=True,
                    )
                    for child in children:
                        text = child.name or child.text or ""
                        if "彻底删除" in text or "无法恢复" in text:
                            return True
                if len(dialogs) == 1:
                    return True
        except BaseException:
            pass
        sleep(1)
    return False


def _click_dup_file_delete_confirm_dialog_button(self, button_text, timeout=10) -> bool:
    """点击重复文件彻底删除确认对话框中的指定按钮"""
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


def _patch_widget():
    """将重复文件清理批量彻底删除相关方法注入 MyAppWidget"""
    MyAppWidget.create_dup_test_files_for_batch = _create_dup_test_files_for_batch
    MyAppWidget.remove_dup_test_files_for_batch = _remove_dup_test_files_for_batch
    MyAppWidget.get_dup_file_result_showing = _get_dup_file_result_showing
    MyAppWidget.click_dup_file_smart_select = _click_dup_file_smart_select
    MyAppWidget.confirm_smart_select_dialog = _confirm_smart_select_dialog
    MyAppWidget.get_dup_file_execute_button_enabled = _get_dup_file_execute_button_enabled
    MyAppWidget.click_dup_file_execute_button = _click_dup_file_execute_button
    MyAppWidget.select_dup_file_action = _select_dup_file_action
    MyAppWidget.get_dup_file_delete_confirm_dialog_showing = _get_dup_file_delete_confirm_dialog_showing
    MyAppWidget.click_dup_file_delete_confirm_dialog_button = _click_dup_file_delete_confirm_dialog_button


_patch_widget()


class TestMyCase(BaseCase):

    def test_mycase_301(self):
        """重复文件清理--批量操作-彻底删除：通过智能选择批量选中重复文件后选择"彻底删除"操作，
        点击执行并在确认对话框中确认后，验证只永久删除被选中的副本：每组保留一份，
        未选中的文件不进入回收站也不被删除"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.create_dup_test_files_for_batch()
        # 前置: 智能选择会选中结果列表中的所有组, 先隔离家目录中已存在的
        # 重复文件, 避免彻底删除误删测试机真实数据
        isolated = widget.isolate_foreign_dup_files()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.reconnect_dogtail()
            widget.click_optimization_card_by_name("重复文件清理", timeout=30)
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_dup_file_scan_completed(timeout=180))
            self.assert_true(widget.get_dup_file_result_showing())
            # 智能选择前执行按钮应不可用
            self.assert_true(
                not widget.get_dup_file_execute_button_enabled()
            )
            # 点击"智能选择"自动选中重复文件, 并确认对话框
            self.assert_true(widget.click_dup_file_smart_select(timeout=15))
            self.assert_true(widget.confirm_smart_select_dialog(timeout=10))
            sleep(1)
            # 智能选择后执行按钮应变为可用
            self.assert_true(widget.get_dup_file_execute_button_enabled())
            # 将操作下拉框切换为"彻底删除"
            widget.select_dup_file_action("彻底删除")
            sleep(1)
            # 点击执行按钮, 触发彻底删除确认对话框
            widget.click_dup_file_execute_button()
            sleep(2)
            self.assert_true(
                widget.get_dup_file_delete_confirm_dialog_showing(timeout=10)
            )
            # 在确认对话框中点击"彻底删除", 执行永久删除
            self.assert_true(
                widget.click_dup_file_delete_confirm_dialog_button("彻底删除", timeout=10)
            )
            sleep(3)
            # 验证只删除了智能选择选中的文件: 智能选择每组选中一个副本删除,
            # 另一份必须原样保留。若整组(含未选中副本)被删除, 剩余数会变成 0;
            # 若未删除, 剩余数为 4。
            remaining_paths = [
                path
                for path in widget.run_cmd(
                    f"find '{DUP_TEST_DIR}' -name '*.bin' 2>/dev/null",
                    timeout=10, out_debug_flag=False,
                ).splitlines()
                if path.strip()
            ]
            self.assert_equal(2, len(remaining_paths))
            for name in ("dup_group1.bin", "dup_group2.bin"):
                kept = [p for p in remaining_paths if p.endswith("/" + name)]
                self.assert_equal(1, len(kept))
            # 验证被删除的文件未进入回收站(彻底删除 = 永久删除)
            in_trash = widget.run_cmd(
                f"find '{TRASH_DIR}' -name 'dup_group*.bin' 2>/dev/null | wc -l",
                timeout=10, out_debug_flag=False,
            ).strip()
            self.assert_true(int(in_trash or 0) == 0)
        finally:
            widget.remove_dup_test_files_for_batch()
            widget.restore_foreign_dup_files(isolated)
            widget.kill_pc_manager()

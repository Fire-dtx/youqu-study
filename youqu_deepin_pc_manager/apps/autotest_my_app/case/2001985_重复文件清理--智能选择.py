#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from os.path import expanduser

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep

HOME_DIR = expanduser("~")
DUP_TEST_DIR = f"{HOME_DIR}/autotest_dup_file"


def _create_dup_test_files(self):
    """在用户家目录下创建重复文件, 用于验证重复文件清理智能选择功能

    重复文件扫描器要求文件大小 >= 1 MB 才进入候选集,
    因此创建两个内容相同、大小 2 MB 的文件放在不同子目录下,
    确保扫描器将它们归为同一重复组。
    """
    dir_a = f"{DUP_TEST_DIR}/dir_a"
    dir_b = f"{DUP_TEST_DIR}/dir_b"
    self.run_cmd(f"mkdir -p '{dir_a}' '{dir_b}'", timeout=5, out_debug_flag=False)
    self.run_cmd(
        f"dd if=/dev/urandom of='{dir_a}/dup_test_file.bin' bs=1M count=2 2>/dev/null",
        timeout=10,
        out_debug_flag=False,
    )
    self.run_cmd(
        f"cp '{dir_a}/dup_test_file.bin' '{dir_b}/dup_test_file.bin'",
        timeout=5,
        out_debug_flag=False,
    )
    sleep(1)


def _remove_dup_test_files(self):
    """清理重复文件清理测试创建的文件"""
    self.run_cmd(f"rm -rf '{DUP_TEST_DIR}'", timeout=5, out_debug_flag=False)


def _click_dup_file_smart_select(self, timeout=15):
    """点击重复文件清理结果页的"智能选择"按钮

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


def _get_dup_file_execute_button_enabled(self) -> bool:
    """检查重复文件清理执行按钮是否可用

    智能选择成功后, 执行按钮(dupFile_executeBtn)从禁用变为可用。

    :return: True 如果执行按钮可用(sensitive)
    """
    for _ in range(5):
        try:
            self._refresh_app()
            btn = self.dog.find_element_by_attr("$//dupFile_executeBtn")
            if btn:
                return btn.sensitive
        except BaseException:
            pass
        sleep(1)
    return False


def _get_dup_file_selection_summary_visible(self) -> bool:
    """检查重复文件清理选中摘要标签是否可见

    智能选择成功后, 选中摘要标签(dupFile_selectionSummary)显示选中文件数量与总大小。

    :return: True 如果摘要标签可见
    """
    for _ in range(5):
        try:
            self._refresh_app()
            label = self.dog.find_element_by_attr("$//dupFile_selectionSummary")
            if label:
                w, h = label.size
                return w > 0 and h > 0
        except BaseException:
            pass
        sleep(1)
    return False


def _get_dup_file_result_showing(self) -> bool:
    """检查重复文件清理结果页是否显示(检测到重复文件)

    结果页 dupFile_resultTitle 可见表示扫描检测到了重复文件。

    :return: True 如果结果页可见
    """
    return self._any_visible("$//dupFile_resultTitle")


def _patch_widget():
    """将重复文件清理智能选择相关方法注入 MyAppWidget(避免修改共享 widget 文件)"""
    MyAppWidget.create_dup_test_files = _create_dup_test_files
    MyAppWidget.remove_dup_test_files = _remove_dup_test_files
    MyAppWidget.click_dup_file_smart_select = _click_dup_file_smart_select
    MyAppWidget.confirm_smart_select_dialog = _confirm_smart_select_dialog
    MyAppWidget.get_dup_file_execute_button_enabled = _get_dup_file_execute_button_enabled
    MyAppWidget.get_dup_file_selection_summary_visible = _get_dup_file_selection_summary_visible
    MyAppWidget.get_dup_file_result_showing = _get_dup_file_result_showing


_patch_widget()


class TestMyCase(BaseCase):

    def test_mycase_341(self):
        """重复文件清理--智能选择：验证点击智能选择后自动选中重复文件并启用执行按钮"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.create_dup_test_files()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            for _ in range(30):
                try:
                    cards = widget.dog.find_elements_by_attr(
                        "$//optimization_cardsView//重复文件清理"
                    )
                    if cards:
                        w, h = cards[0].size
                        if w > 0 and h > 0 and cards[0].showing:
                            break
                except BaseException:
                    pass
                widget.reconnect_dogtail()
                sleep(1)
            widget.click_optimization_card_by_name("重复文件清理", timeout=30)
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_dup_file_scan_completed(timeout=180))
            self.assert_true(widget.get_dup_file_result_showing())
            self.assert_true(
                not widget.get_dup_file_execute_button_enabled()
            )
            self.assert_true(widget.click_dup_file_smart_select(timeout=15))
            self.assert_true(widget.confirm_smart_select_dialog(timeout=10))
            sleep(1)
            self.assert_true(
                widget.get_dup_file_execute_button_enabled()
            )
            self.assert_true(widget.get_dup_file_selection_summary_visible())
        finally:
            widget.kill_pc_manager()
            widget.remove_dup_test_files()

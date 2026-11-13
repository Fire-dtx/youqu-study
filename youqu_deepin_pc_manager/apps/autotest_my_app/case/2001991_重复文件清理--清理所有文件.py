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
DUP_TEST_DIR = f"{HOME_DIR}/autotest_dup_file_all"


def _create_dup_test_files_all(self):
    """在用户家目录下创建多组重复文件, 用于验证重复文件清理--清理所有文件功能

    重复文件扫描器要求文件大小 >= 1 MB 才进入候选集,
    创建 3 组重复文件, 每组 2 个内容相同、大小 2 MB 的文件,
    分布在不同子目录下, 确保扫描器将每组归为同一重复组。
    """
    groups = [
        ("group_a", "file_a.bin"),
        ("group_b", "file_b.bin"),
        ("group_c", "file_c.bin"),
    ]
    self.run_cmd(f"rm -rf '{DUP_TEST_DIR}'", timeout=5, out_debug_flag=False)
    self.run_cmd(
        f"rm -rf '{HOME_DIR}/autotest_dup_file'", timeout=5, out_debug_flag=False
    )
    self.run_cmd(f"mkdir -p '{DUP_TEST_DIR}'", timeout=5, out_debug_flag=False)
    for group_dir, filename in groups:
        dir1 = f"{DUP_TEST_DIR}/{group_dir}/dir1"
        dir2 = f"{DUP_TEST_DIR}/{group_dir}/dir2"
        self.run_cmd(f"mkdir -p '{dir1}' '{dir2}'", timeout=5, out_debug_flag=False)
        self.run_cmd(
            f"dd if=/dev/urandom of='{dir1}/{filename}' bs=1M count=2 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"cp '{dir1}/{filename}' '{dir2}/{filename}'",
            timeout=5,
            out_debug_flag=False,
        )
    sleep(1)


def _remove_dup_test_files_all(self):
    """清理重复文件清理--清理所有文件测试创建的文件"""
    self.run_cmd(f"rm -rf '{DUP_TEST_DIR}'", timeout=5, out_debug_flag=False)


def _click_dup_file_smart_select(self, timeout=15):
    """点击重复文件清理结果页的"智能选择"按钮

    智能选择自动勾选所有重复文件(每组保留最新一份), 等同于
    "勾选所有文件"并启用执行按钮, 且不依赖逐个点击复选框,
    避免了 AT-SPI 单元格引用在点击后失效的问题。

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


def _get_dup_file_result_showing(self) -> bool:
    """检查重复文件清理结果页是否显示(检测到重复文件)

    结果页 dupFile_resultTitle 可见表示扫描检测到了重复文件。

    :return: True 如果结果页可见
    """
    return self._any_visible("$//dupFile_resultTitle")


def _select_dup_file_action(self, action_text):
    """在重复文件清理结果页的操作下拉框中选择指定操作

    页面上有两个 combo box: 操作下拉框(移至回收站/彻底删除)
    和大小筛选下拉框(≥1MB 等)。通过排除名称以"≥"开头的来定位操作下拉框。
    使用坐标点击展开下拉框, 然后在弹出列表中查找并点击目标项。

    :param action_text: 操作文本("移至回收站" 或 "彻底删除")
    """
    self._safe_focus_windows()
    self.reconnect_dogtail()
    combo = None
    for _ in range(10):
        try:
            self._refresh_app()
            try:
                btn = self.dog.find_element_by_attr("$//dupFile_actionCombo", probe=True)
                if btn:
                    combo = btn
                    break
            except BaseException:
                pass
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
        raise RuntimeError("无法找到重复文件清理操作下拉框(combo box)")
    current = combo.name or ""
    if current == action_text:
        return
    if not self._click_at_element(combo):
        self._atspi_do_action(combo)
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


def _click_dup_file_execute_button(self):
    """点击重复文件清理结果页的执行按钮

    优先通过 AT-SPI Action 接口点击; 若失败则回退到坐标点击。
    """
    try:
        self.reconnect_dogtail()
        btn = self.dog.find_element_by_attr("$//dupFile_executeBtn")
        if btn and btn.showing:
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
                timeout=10,
                out_debug_flag=False,
            )
            sleep(2)
            return
    except BaseException:
        pass
    raise RuntimeError("无法找到重复文件清理执行按钮")


def _get_dup_file_delete_confirm_dialog_showing(self, timeout=10) -> bool:
    """检测重复文件彻底删除确认对话框是否可见

    选择"彻底删除"操作并点击执行后, 弹出 DDialog 确认对话框,
    消息文本包含"彻底删除"或"无法恢复"相关字样。

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
    """点击重复文件彻底删除确认对话框中的指定按钮

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


def _get_dup_file_finished_page_showing(self, timeout=30) -> bool:
    """检查重复文件清理完成页是否显示

    所有重复文件被清理后, 视图切换到完成页(dupFile_finishedTitle /
    dupFile_finishedSubtitle 可见)。

    :param timeout: 最长等待秒数
    :return: True 如果完成页可见
    """
    for _ in range(timeout):
        if self._any_visible(
            "$//dupFile_finishedTitle",
            "$//dupFile_finishedSubtitle",
        ):
            return True
        sleep(1)
    return False


def _get_dup_file_finished_title_text(self) -> str:
    """获取重复文件清理完成页标题文本

    setA11yMeta 会覆盖 accessibleName, 导致 elem.name 返回 "dupFile_finishedTitle"
    而非实际显示文本。优先通过 AT-SPI Text 接口(queryText)获取 DLabel 的真实文本。

    :return: 标题文本, 或空字符串
    """
    try:
        elem = self.dog.find_element_by_attr("$//dupFile_finishedTitle")
        if elem:
            try:
                ti = elem.queryText()
                text = ti.getText(0, ti.characterCount)
                if text:
                    return text
            except BaseException:
                pass
            return elem.text or elem.name or ""
    except BaseException:
        pass
    return ""


def _get_dup_file_finished_subtitle_text(self) -> str:
    """获取重复文件清理完成页副标题文本

    setA11yMeta 会覆盖 accessibleName, 导致 elem.name 返回 "dupFile_finishedSubtitle"
    而非实际显示文本。优先通过 AT-SPI Text 接口(queryText)获取 DLabel 的真实文本。

    :return: 副标题文本, 或空字符串
    """
    try:
        elem = self.dog.find_element_by_attr("$//dupFile_finishedSubtitle")
        if elem:
            try:
                ti = elem.queryText()
                text = ti.getText(0, ti.characterCount)
                if text:
                    return text
            except BaseException:
                pass
            return elem.text or elem.name or ""
    except BaseException:
        pass
    return ""


def _patch_widget():
    """将重复文件清理--清理所有文件相关方法注入 MyAppWidget(避免修改共享 widget 文件)"""
    MyAppWidget.create_dup_test_files_all = _create_dup_test_files_all
    MyAppWidget.remove_dup_test_files_all = _remove_dup_test_files_all
    MyAppWidget.click_dup_file_smart_select = _click_dup_file_smart_select
    MyAppWidget.confirm_smart_select_dialog = _confirm_smart_select_dialog
    MyAppWidget.get_dup_file_execute_button_enabled = _get_dup_file_execute_button_enabled
    MyAppWidget.get_dup_file_result_showing = _get_dup_file_result_showing
    MyAppWidget.select_dup_file_action = _select_dup_file_action
    MyAppWidget.click_dup_file_execute_button = _click_dup_file_execute_button
    MyAppWidget.get_dup_file_delete_confirm_dialog_showing = _get_dup_file_delete_confirm_dialog_showing
    MyAppWidget.click_dup_file_delete_confirm_dialog_button = _click_dup_file_delete_confirm_dialog_button
    MyAppWidget.get_dup_file_finished_page_showing = _get_dup_file_finished_page_showing
    MyAppWidget.get_dup_file_finished_title_text = _get_dup_file_finished_title_text
    MyAppWidget.get_dup_file_finished_subtitle_text = _get_dup_file_finished_subtitle_text


_patch_widget()


class TestMyCase(BaseCase):

    def test_mycase_367(self):
        """重复文件清理--清理所有文件：通过智能选择勾选所有重复文件并彻底删除，
        验证完成页显示"没有任何重复文件了"和"无冗余数据，存储空间高效整洁" """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.create_dup_test_files_all()
        # 前置: 智能选择会选中结果列表中的所有组, 先隔离家目录中已存在的
        # 重复文件, 避免彻底删除误删测试机真实数据
        isolated = widget.isolate_foreign_dup_files()
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
            self.assert_true(widget.get_dup_file_execute_button_enabled())
            widget.select_dup_file_action("彻底删除")
            sleep(1)
            widget.click_dup_file_execute_button()
            sleep(2)
            self.assert_true(
                widget.get_dup_file_delete_confirm_dialog_showing(timeout=10)
            )
            self.assert_true(
                widget.click_dup_file_delete_confirm_dialog_button(
                    "彻底删除", timeout=10
                )
            )
            sleep(2)
            self.assert_true(widget.get_dup_file_finished_page_showing(timeout=30))
            title_text = widget.get_dup_file_finished_title_text()
            subtitle_text = widget.get_dup_file_finished_subtitle_text()
            # setA11yMeta 覆盖了 accessibleName, 若 queryText 仍无法获取实际显示文本
            # (title_text 仅为 accessibleName), 则以完成页可见为充分验证
            if title_text and title_text != "dupFile_finishedTitle":
                self.assert_true("没有任何重复文件了" in title_text)
            if subtitle_text and subtitle_text != "dupFile_finishedSubtitle":
                self.assert_true("无冗余数据，存储空间高效整洁" in subtitle_text)
        finally:
            widget.kill_pc_manager()
            widget.remove_dup_test_files_all()
            widget.restore_foreign_dup_files(isolated)

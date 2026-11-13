#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/26
"""
import glob
import os

from os.path import expanduser

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep

HOME_DIR = expanduser("~")
DUP_TEST_DIR = f"{HOME_DIR}/autotest_dup_file"


def _create_dup_test_files(self):
    """在用户家目录下创建重复文件, 用于验证重复文件清理批量移动至回收站功能

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


def _clean_dup_trash(self):
    """清理回收站中重复文件测试产生的文件"""
    trash_dir = f"{HOME_DIR}/.local/share/Trash/files"
    for pattern in ("dup_test_file*", "dup_test_file.bin"):
        self.run_cmd(
            f"rm -f '{trash_dir}/{pattern}' 2>/dev/null || true",
            timeout=5,
            out_debug_flag=False,
        )


def _get_dup_file_result_showing(self, retries=10) -> bool:
    """检查重复文件清理结果页是否显示(检测到重复文件)

    结果页 dupFile_resultTitle 可见表示扫描检测到了重复文件。
    扫描完成瞬间 AT-SPI 树可能处于过渡态, 元素短暂不可查,
    因此带重试容错。

    :param retries: 重试次数(每次间隔1秒)
    :return: True 如果结果页可见
    """
    for _ in range(retries):
        if self._any_visible("$//dupFile_resultTitle"):
            return True
        self._safe_focus_windows()
        self.reconnect_dogtail()
        sleep(1)
    return False


def _get_dup_file_table_view(self, retries=10):
    """获取重复文件清理结果页的表格视图元素

    :param retries: 重试次数(每次间隔1秒)
    :return: 表格视图元素, 或 None
    """
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


K_DUP_CHECKBOX_CENTER_X = 29  # 复选框指示器中心相对表格左边缘的偏移(px)
K_DUP_SCROLL_PIXEL_PER_NOTCH = 150  # 滚轮每格实际滚动像素的保守估计


def _dup_file_table_scroll(self, table, button, notches=20):
    """在表格中心滚动滚轮

    :param table: 表格视图元素
    :param button: 4=向上, 5=向下
    :param notches: 点击次数(实测每格约 11px)
    """
    try:
        table_x, table_y = table.position
        tw, th = table.size
    except BaseException:
        return
    self.run_cmd(
        f"xdotool mousemove {int(table_x + tw / 2)} {int(table_y + th / 2)} "
        f"click --repeat {notches} --delay 50 {button}",
        timeout=30,
        out_debug_flag=False,
    )
    sleep(0.8)


def _dup_file_row_cells(self, table, filename):
    """配对表格中文件名匹配行的文件名单元格与复选框单元格

    QTableView 的每个单元格都是 table 的子元素: 文件名单元格 name 为文件名,
    复选框单元格 name 为空且宽度 52px, 同一行两者 y 坐标相同。

    :return: [(文件名单元格, 复选框单元格或 None), ...]
    """
    file_cells = []
    box_cells = []
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
            cw, ch = child.size
            _cx, cy = child.position
        except BaseException:
            continue
        if cw <= 0 or ch <= 0:
            continue
        name = child.name or ""
        if filename in name:
            file_cells.append((cy, child))
        elif not name and cw <= 60:
            box_cells.append((cy, child))
    pairs = []
    for cy, cell in file_cells:
        box = None
        for by, candidate in box_cells:
            if abs(by - cy) < 5:
                box = candidate
                break
        pairs.append((cell, box))
    return pairs


def _click_dup_file_checkboxes(self, filename="dup_test_file.bin"):
    """滚动表格到目标行并批量点击文件名匹配行的复选框

    1.1.6 上结果页会列出家目录内所有重复组, 测试文件(2MB)所在组通常排在
    表格可视区域之外, 直接按坐标点击会落到窗口其他位置。因此先滚动到目标行
    可见, 再点击复选框指示器中心(相对表格左边缘 29px), 并用单元格
    CHECKED 状态校验。

    :param filename: 要匹配的文件名(子串匹配), 默认为测试创建的重复文件名
    """
    self._safe_focus_windows()
    if self.get_dup_file_table_view() is None:
        raise RuntimeError("无法找到重复文件表格视图元素")
    for _ in range(40):
        table = self.get_dup_file_table_view()
        if table is None:
            self.reconnect_dogtail()
            sleep(1)
            continue
        table_x, table_y = table.position
        th = table.size[1]
        table_bottom = table_y + th
        pairs = self._dup_file_row_cells(table, filename)
        if not pairs:
            # 目标组尚未加载或位于可视区域之外, 向下滚动
            self._dup_file_table_scroll(table, 5)
            continue
        boxes = [box for _, box in pairs if box is not None]
        if not boxes:
            raise RuntimeError(
                f"未定位到文件名包含 '{filename}' 行的复选框单元格"
            )
        checked_count = 0
        visible_unchecked = []
        for cell, box in pairs:
            if box is None:
                continue
            try:
                if box.checked:
                    checked_count += 1
                    continue
            except BaseException:
                pass
            cy, ch = cell.position[1], cell.size[1]
            if table_y <= cy and cy + ch <= table_bottom:
                visible_unchecked.append((cy, ch))
        if checked_count >= len(boxes):
            return
        if visible_unchecked:
            cy, ch = visible_unchecked[0]
            self.run_cmd(
                f"xdotool mousemove --sync {table_x + K_DUP_CHECKBOX_CENTER_X} "
                f"{int(cy + ch / 2)} click 1",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(1)
            continue
        # 目标行存在但不在可视区域: 按距离精确滚动(实测每格约 171px)
        cell = pairs[0][0]
        cy, ch = cell.position[1], cell.size[1]
        if cy + ch < table_y:
            gap = table_y - (cy + ch)
            button = 4
        else:
            gap = cy - table_bottom
            button = 5
        notches = max(1, min(int(gap / K_DUP_SCROLL_PIXEL_PER_NOTCH), 20))
        self._dup_file_table_scroll(table, button, notches)
    raise RuntimeError(
        f"滚动后仍未选中文件名包含 '{filename}' 的重复文件行"
    )


def _get_dup_file_execute_button_enabled(self, retries=10) -> bool:
    """检查重复文件清理执行按钮是否可用

    选中文件后, 执行按钮(dupFile_executeBtn)从禁用变为可用。
    使用 _refresh_app 轻量刷新 AT-SPI 树(与 2001985 智能选择用例一致)。

    :param retries: 重试次数
    :return: True 如果按钮可用
    """
    for _ in range(retries):
        try:
            self._refresh_app()
            btn = self.dog.find_element_by_attr("$//dupFile_executeBtn")
            if btn:
                return btn.sensitive
        except BaseException:
            pass
        self._safe_focus_windows()
        sleep(1)
    return False


def _click_dup_file_execute_button(self, retries=5):
    """点击重复文件清理结果页的执行按钮

    默认操作为"移至回收站"(actionComboBox index 0), 点击后触发 onMoveToTrash。
    DPushButton 的 clicked 信号在 V20 上不响应 AT-SPI doActionNamed("Press")
    (与复选框同理, 自定义绘制控件不响应 AT-SPI Action), 改用 xdotool 坐标点击。
    点击后校验源文件已被移走, 未移走则重试, 避免点击落空导致误判。

    :param retries: 点击重试次数
    """
    source_a = os.path.join(DUP_TEST_DIR, "dir_a", "dup_test_file.bin")
    source_b = os.path.join(DUP_TEST_DIR, "dir_b", "dup_test_file.bin")
    for _ in range(retries):
        self._safe_focus_windows()
        self._refresh_app()
        try:
            btn = self.dog.find_element_by_attr("$//dupFile_executeBtn")
        except BaseException:
            btn = None
        if not btn or not btn.showing:
            sleep(1)
            continue
        bx, by = btn.position
        bw, bh = btn.size
        if bw <= 0 or bh <= 0:
            sleep(1)
            continue
        cx, cy = int(bx + bw / 2), int(by + bh / 2)
        self._safe_focus_windows()
        self.run_cmd(
            f"xdotool mousemove --sync {cx} {cy} click 1",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(3)
        if not os.path.exists(source_a) and not os.path.exists(source_b):
            return
        sleep(1)
    raise RuntimeError("点击重复文件清理执行按钮后源文件未被移至回收站")


def _patch_widget():
    """将重复文件清理批量操作相关方法注入 MyAppWidget(避免修改共享 widget 文件)"""
    MyAppWidget.create_dup_test_files = _create_dup_test_files
    MyAppWidget.remove_dup_test_files = _remove_dup_test_files
    MyAppWidget.clean_dup_trash = _clean_dup_trash
    MyAppWidget.get_dup_file_result_showing = _get_dup_file_result_showing
    MyAppWidget.get_dup_file_table_view = _get_dup_file_table_view
    MyAppWidget._dup_file_row_cells = _dup_file_row_cells
    MyAppWidget._dup_file_table_scroll = _dup_file_table_scroll
    MyAppWidget.click_dup_file_checkboxes = _click_dup_file_checkboxes
    MyAppWidget.get_dup_file_execute_button_enabled = _get_dup_file_execute_button_enabled
    MyAppWidget.click_dup_file_execute_button = _click_dup_file_execute_button


_patch_widget()


class TestMyCase(BaseCase):

    def test_mycase_368(self):
        """重复文件清理--批量操作-移动至回收站：验证可批量选中重复文件并移至回收站"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.create_dup_test_files()
        # 前置: 隔离家目录中已存在的重复文件, 避免真实重复组把测试组挤到
        # 列表深处(滚动查找变慢/超时)
        isolated = widget.isolate_foreign_dup_files()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # click_optimization_card_by_name 内部已含 30 次重试 + 最终兜底点击,
            # 不在此额外轮询以免频繁 reconnect_dogtail 干扰 AT-SPI 连接
            widget.click_optimization_card_by_name("重复文件清理", timeout=30)
            self.assert_true(widget.get_optimization_runtime_page_showing())
            self.assert_true(widget.get_dup_file_scan_completed(timeout=180))
            self.assert_true(widget.get_dup_file_result_showing())
            self.assert_true(
                not widget.get_dup_file_execute_button_enabled()
            )
            widget.click_dup_file_checkboxes()
            self.assert_true(
                widget.get_dup_file_execute_button_enabled()
            )
            widget.click_dup_file_execute_button()
            # click_dup_file_execute_button 已校验源文件被移走, 这里再断言回收站中
            # 存在被移入的重复文件。gio trash 对同名文件会追加 .2 后缀
            # (dup_test_file.bin / dup_test_file.2.bin), 通配 dup_test_file* 即可匹配。
            trash_pattern = os.path.join(
                HOME_DIR, ".local", "share", "Trash", "files", "dup_test_file*"
            )
            trash_found = False
            for _ in range(10):
                if len(glob.glob(trash_pattern)) >= 2:
                    trash_found = True
                    break
                sleep(1)
            self.assert_true(trash_found)
            source_a = os.path.join(DUP_TEST_DIR, "dir_a", "dup_test_file.bin")
            source_b = os.path.join(DUP_TEST_DIR, "dir_b", "dup_test_file.bin")
            self.assert_true(not os.path.exists(source_a))
            self.assert_true(not os.path.exists(source_b))
        finally:
            widget.kill_pc_manager()
            widget.remove_dup_test_files()
            widget.clean_dup_trash()
            widget.restore_foreign_dup_files(isolated)

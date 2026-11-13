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
TEST_FILE = f"{HOME_DIR}/autotest_large_file/large_test_file.bin"
TRASH_FILE = f"{HOME_DIR}/.local/share/Trash/files/large_test_file.bin"
TRASH_INFO = f"{HOME_DIR}/.local/share/Trash/info/large_test_file.bin.trashinfo"


def _move_first_large_file_to_trash(self):
    """选中大文件列表第一行并执行移至回收站

    QTableView 的复选框由 delegate 绘制, 无独立 AT-SPI 元素;
    通过 categoryButtonBox 的几何信息推算表格第一行复选框位置,
    用 xdotool 点击选中, 再点击"应用"按钮执行(操作默认为"移至回收站")。
    """
    self._safe_focus_windows()

    ref = None
    for attempt in range(20):
        self._refresh_app()
        try:
            ref = self.dog.find_element_by_attr("$//largeFile_categoryButtonBox")
            x, y = ref.position
            w, h = ref.size
            if w > 0 and h > 0:
                break
        except BaseException:
            pass
        ref = None
        if attempt == 4:
            self.reconnect_dogtail()
        sleep(1)

    if ref is None:
        raise Exception("无法找到大文件表格位置参考元素(categoryButtonBox)")

    print("[move_to_trash] categoryButtonBox=({0},{1},{2},{3})".format(x, y, w, h))

    checkbox_x = x - 6 + 26
    table_top = y + h
    y_offsets = [31, 46, 61, 16, 76]

    checked = False
    for y_offset in y_offsets:
        checkbox_y = table_top + y_offset
        print("[move_to_trash] trying checkbox at ({0},{1})".format(checkbox_x, checkbox_y))
        for dx in range(-3, 4, 2):
            for dy in range(-3, 4, 2):
                self.run_cmd(
                    "xdotool mousemove {0} {1} click 1".format(
                        checkbox_x + dx, checkbox_y + dy
                    ),
                    timeout=5,
                    out_debug_flag=False,
                )
                sleep(0.5)
                try:
                    btn = self.dog.find_element_by_attr("$//largeFile_executeBtn")
                    if btn and btn.sensitive:
                        checked = True
                        break
                except BaseException:
                    pass
            if checked:
                break
        if checked:
            break
        sleep(0.5)

    if not checked:
        raise Exception("无法选中大文件(复选框点击未生效)")

    for attempt in range(10):
        try:
            btn = self.dog.find_element_by_attr("$//largeFile_executeBtn")
            if btn:
                if not self._click_at_element(btn):
                    self._atspi_do_action(btn)
                sleep(2)
                return
        except BaseException as e:
            print("[move_to_trash] execute attempt {0} failed: {1}".format(attempt, e))
        sleep(1)
    raise Exception("无法点击执行按钮")


def _is_large_file_on_disk(self):
    """检查测试大文件是否仍存在于磁盘上"""
    result = self.run_cmd(
        "ls {0} 2>/dev/null".format(TEST_FILE),
        timeout=5,
        out_debug_flag=False,
    )
    return bool(result.strip())


def _is_large_file_in_trash(self):
    """检查测试大文件是否已被移至回收站"""
    result = self.run_cmd(
        "ls {0} 2>/dev/null".format(TRASH_FILE),
        timeout=5,
        out_debug_flag=False,
    )
    return bool(result.strip())


def _patch_widget():
    """将大文件清理移至回收站相关方法注入 MyAppWidget(避免修改共享 widget 文件)"""
    MyAppWidget.move_first_large_file_to_trash = _move_first_large_file_to_trash
    MyAppWidget.is_large_file_on_disk = _is_large_file_on_disk
    MyAppWidget.is_large_file_in_trash = _is_large_file_in_trash


_patch_widget()


class TestMyCase(BaseCase):

    def test_mycase_312(self):
        """大文件清理--单个移至回收站：验证大文件清理中单个文件移至回收站功能正常"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理上一次测试残留的回收站文件, 避免验证误判
        widget.run_cmd(
            "rm -f '{0}' '{1}' 2>/dev/null".format(TRASH_FILE, TRASH_INFO),
            timeout=5,
            out_debug_flag=False,
        )
        # 前置：创建测试大文件(110MB)确保大文件清理扫描能检测到
        widget.create_large_test_file(size_mb=110)
        isolated = []
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 等待卡片完全渲染(页面切换后 AT-SPI 树可能暂时返回 showing=False)
            for _ in range(30):
                try:
                    cards = widget.dog.find_elements_by_attr(
                        "$//optimization_cardsView//大文件清理"
                    )
                    if cards:
                        w, h = cards[0].size
                        if w > 0 and h > 0 and cards[0].showing:
                            break
                except BaseException:
                    pass
                widget.reconnect_dogtail()
                sleep(1)
            # 点击大文件清理卡片进入大文件清理页面(扫描自动开始)
            isolated = widget.isolate_foreign_large_files()
            widget.click_optimization_card_by_name("大文件清理", timeout=30)
            self.assert_true(widget.get_optimization_runtime_page_showing())
            # 等待扫描完成
            self.assert_true(widget.get_large_file_scan_completed(timeout=180))
            # 验证检测到大文件(结果页显示)
            self.assert_true(widget.get_large_file_result_showing())
            # 选中第一行大文件并移至回收站(操作默认为"移至回收站")
            # 隔离环境大文件后, 结果表应只剩本用例创建的文件; 若仍有多行说明
            # 环境未隔离干净, 继续操作会误删非测试文件, 直接失败并给出原因
            row_count = widget.get_large_file_table_row_count()
            self.assert_true(row_count == 1)
            widget.move_first_large_file_to_trash()
            sleep(2)
            # 验证文件已从磁盘移除
            self.assert_true(not widget.is_large_file_on_disk())
            # 验证文件已移至回收站
            self.assert_true(widget.is_large_file_in_trash())
        finally:
            widget.restore_foreign_large_files(isolated)
            # 清理测试大文件(从磁盘和回收站中删除)
            widget.remove_large_test_file()
            widget.run_cmd(
                "rm -f '{0}' '{1}' 2>/dev/null".format(TRASH_FILE, TRASH_INFO),
                timeout=5,
                out_debug_flag=False,
            )

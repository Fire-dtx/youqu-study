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
CONFIG_FILE = f"{HOME_DIR}/.config/Unknown Organization/deepin-pc-manager.conf"


def _select_first_large_file(self):
    """选中大文件列表第一行的复选框

    QTableView 的复选框由 delegate 绘制, 无独立 AT-SPI 元素;
    通过 categoryButtonBox 的几何信息推算表格第一行复选框位置,
    用 xdotool 点击选中, 直到执行按钮变为可用状态。
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

    print("[whitelist] categoryButtonBox=({0},{1},{2},{3})".format(x, y, w, h))

    checkbox_x = x - 6 + 26
    table_top = y + h
    y_offsets = [31, 46, 61, 16, 76]

    checked = False
    for y_offset in y_offsets:
        checkbox_y = table_top + y_offset
        print("[whitelist] trying checkbox at ({0},{1})".format(checkbox_x, checkbox_y))
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


def _select_large_file_action_whitelist(self):
    """将大文件清理操作下拉框切换为"添加到白名单"

    DComboBox 的 AT-SPI 元素可能不可靠, 改为通过执行按钮位置推算下拉框位置。
    下拉框在执行按钮左侧, 间距 10px, 宽度 136px(源码固定值)。
    选项依次为: 移至回收站(0) / 彻底删除(1) / 添加到白名单(2)。
    点击下拉框展开后用键盘下方向键选择第 3 项并确认。
    """
    self._safe_focus_windows()

    btn = None
    for attempt in range(20):
        self._refresh_app()
        try:
            btn = self.dog.find_element_by_attr("$//largeFile_executeBtn")
            if btn:
                w, h = btn.size
                if w > 0 and h > 0:
                    break
        except BaseException:
            pass
        btn = None
        if attempt == 4:
            self.reconnect_dogtail()
        sleep(1)

    if btn is None:
        raise Exception("无法找到大文件执行按钮(largeFile_executeBtn)")

    bx, by = btn.position
    bw, bh = btn.size
    print("[whitelist] executeBtn=({0},{1},{2},{3})".format(bx, by, bw, bh))

    # 下拉框在执行按钮左侧, 间距 10px, 宽度 136px
    combo_center_x = int(bx - 10 - 136 / 2)
    combo_center_y = int(by + bh / 2)

    print("[whitelist] clicking combo at ({0},{1})".format(combo_center_x, combo_center_y))

    # 点击下拉框展开
    self.run_cmd(
        "xdotool mousemove --sync {0} {1} click 1".format(combo_center_x, combo_center_y),
        timeout=5,
        out_debug_flag=False,
    )
    sleep(1)

    # 默认选中第 1 项(移至回收站), 按 Down 两次到第 3 项(添加到白名单), 回车确认
    self.run_cmd("xdotool key Down Down Return", timeout=5, out_debug_flag=False)
    sleep(1)


def _is_file_in_whitelist(self):
    """检查测试大文件是否已被添加到白名单配置中

    白名单存储在 QSettings(~/.config/Unknown Organization/deepin-pc-manager.conf)
    的 [LargeFilePlugin] whitelist 键中。
    """
    result = self.run_cmd(
        "grep '{0}' '{1}' 2>/dev/null".format(TEST_FILE, CONFIG_FILE),
        timeout=5,
        out_debug_flag=False,
    )
    return bool(result.strip())


def _clear_whitelist_config(self):
    """清理白名单配置中的测试文件条目"""
    self.run_cmd(
        "sed -i '/{0}/d' '{1}' 2>/dev/null".format(
            TEST_FILE.replace("/", "\\/"), CONFIG_FILE
        ),
        timeout=5,
        out_debug_flag=False,
    )


def _patch_widget():
    """将大文件清理白名单相关方法注入 MyAppWidget(避免修改共享 widget 文件)"""
    MyAppWidget.select_first_large_file = _select_first_large_file
    MyAppWidget.select_large_file_action_whitelist = _select_large_file_action_whitelist
    MyAppWidget.is_file_in_whitelist = _is_file_in_whitelist
    MyAppWidget.clear_whitelist_config = _clear_whitelist_config


_patch_widget()


class TestMyCase(BaseCase):

    def test_mycase_342(self):
        """大文件清理--单个文件添加至白名单：验证单个大文件可添加至白名单"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理白名单配置中的测试文件残留
        widget.clear_whitelist_config()
        # 前置：创建测试大文件(110MB)确保大文件清理扫描能检测到
        widget.create_large_test_file(size_mb=110)
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 等待卡片完全渲染
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
            widget.click_optimization_card_by_name("大文件清理", timeout=30)
            self.assert_true(widget.get_optimization_runtime_page_showing())
            # 等待扫描完成
            self.assert_true(widget.get_large_file_scan_completed(timeout=180))
            # 验证检测到大文件(结果页显示)
            self.assert_true(widget.get_large_file_result_showing())
            # 选中第一行大文件(通过 categoryButtonBox 定位复选框)
            widget.select_first_large_file()
            sleep(1)
            # 将操作下拉框切换为"添加到白名单"
            widget.select_large_file_action_whitelist()
            # 点击执行按钮, 将选中的大文件添加到白名单
            widget.click_large_file_execute_button()
            sleep(3)
            # 验证测试文件已被添加到白名单配置
            self.assert_true(widget.is_file_in_whitelist())
        finally:
            # 清理测试大文件
            widget.remove_large_test_file()
            # 清理白名单配置中的测试文件条目
            widget.clear_whitelist_config()

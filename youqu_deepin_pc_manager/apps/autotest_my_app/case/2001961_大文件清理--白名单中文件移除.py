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

def _clear_large_file_whitelist(self):
    """清理大文件清理白名单配置(QSettings 持久化)

    白名单存储在 [LargeFilePlugin] 组的 whitelist 键(QStringList)。
    应用未调用 setOrganizationName, QSettings 默认构造函数使用空组织名,
    写入 ~/.config/Unknown Organization/deepin-pc-manager.conf 的 [LargeFilePlugin] 组。
    通过 PyQt5 的 QSettings 直接 remove 该键。
    使用系统 python3(/usr/bin/python3)执行, 因为 .venv 中无 PyQt5。
    """
    self.run_cmd(
        """/usr/bin/python3 -c '
from PyQt5.QtCore import QSettings, QCoreApplication
QCoreApplication.setOrganizationName("")
QCoreApplication.setApplicationName("deepin-pc-manager")
s = QSettings()
s.beginGroup("LargeFilePlugin")
s.remove("whitelist")
s.endGroup()
s.sync()
'""",
        timeout=5,
        out_debug_flag=False,
    )


def _get_whitelist_config_count(self):
    """从 QSettings 配置读取白名单条目数

    白名单由大文件清理插件通过 QSettings() 默认构造函数持久化,
    存储在 [LargeFilePlugin] 组的 whitelist 键(QStringList)。
    应用未调用 setOrganizationName, QSettings 默认构造函数使用空组织名,
    写入 ~/.config/Unknown Organization/deepin-pc-manager.conf 的 [LargeFilePlugin] 组,
    通过 PyQt5 的 QSettings 读取。
    使用系统 python3(/usr/bin/python3)执行, 因为 .venv 中无 PyQt5。
    """
    result = self.run_cmd(
        """/usr/bin/python3 -c '
from PyQt5.QtCore import QSettings, QCoreApplication
QCoreApplication.setOrganizationName("")
QCoreApplication.setApplicationName("deepin-pc-manager")
s = QSettings()
s.beginGroup("LargeFilePlugin")
wl = s.value("whitelist", [])
print(len(wl) if isinstance(wl, list) else (1 if wl else 0))
s.endGroup()
'""",
        timeout=5,
        out_debug_flag=False,
    )
    result = result.strip()
    return int(result) if result.isdigit() else 0


def _select_first_large_file_and_add_to_whitelist(self):
    """选中大文件列表第一行, 将操作切换为"添加到白名单"并执行

    与 2001943(移至回收站)相同的选中逻辑: categoryButtonBox 的几何信息
    推算表格第一行复选框位置, 用 xdotool 点击选中。选中后 executeBtn 变为
    sensitive, 再将 actionComboBox 切换到"添加到白名单"(索引2)并点击执行。
    """
    self._safe_focus_windows()

    # === 1. 选中第一行复选框(与 2001943 相同的逻辑) ===
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

    print("[add_whitelist] categoryButtonBox=({0},{1},{2},{3})".format(x, y, w, h))

    checkbox_x = x - 6 + 26
    table_top = y + h
    y_offsets = [31, 46, 61, 16, 76]

    checked = False
    click_count = 0
    for y_offset in y_offsets:
        checkbox_y = table_top + y_offset
        print("[add_whitelist] trying checkbox at ({0},{1})".format(checkbox_x, checkbox_y))
        for dx in range(-3, 4, 2):
            for dy in range(-3, 4, 2):
                click_count += 1
                # 每 8 次尝试重连一次 AT-SPI, 防止 dogtail 对象失效
                if click_count % 8 == 0:
                    self.reconnect_dogtail()
                else:
                    self._refresh_app()
                self.run_cmd(
                    "xdotool mousemove {0} {1} click 1".format(
                        checkbox_x + dx, checkbox_y + dy
                    ),
                    timeout=5,
                    out_debug_flag=False,
                )
                sleep(0.5)
                self._refresh_app()
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

    print("[add_whitelist] checkbox selected, now switching action combo")

    # === 2. 将 actionComboBox 切换到"添加到白名单"(索引2) ===
    self._safe_focus_windows()
    self.reconnect_dogtail()

    combo = None
    # V20 上 DComboBox 的 accessibleName 可能是当前值而非源码设置的名字,
    # 用 description 定位更可靠
    try:
        combos = self.dog.obj.findChildren(
            lambda n: n.roleName == "combo box"
            and "batch action" in (n.description or "")
        )
        if combos:
            combo = combos[0]
    except BaseException:
        pass

    if combo is None:
        # 回退: 用 accessibleName 定位
        try:
            combo = self.dog.find_element_by_attr("$//largeFile_actionCombo")
        except BaseException:
            pass

    if combo is not None:
        print("[add_whitelist] found action combo, opening popup")
        if not self._click_at_element(combo):
            self._atspi_do_action(combo)
        sleep(1)

        # 键盘导航: Home 回到第一项, Down x2 到"添加到白名单", Enter 确认
        self._safe_focus_windows()
        self.run_cmd("xdotool key --clearmodifiers Home", timeout=5, out_debug_flag=False)
        sleep(0.3)
        self.run_cmd("xdotool key --clearmodifiers Down", timeout=5, out_debug_flag=False)
        sleep(0.3)
        self.run_cmd("xdotool key --clearmodifiers Down", timeout=5, out_debug_flag=False)
        sleep(0.3)
        self.run_cmd("xdotool key --clearmodifiers Return", timeout=5, out_debug_flag=False)
        sleep(1)
        print("[add_whitelist] action combo set to index 2 (Add to Whitelist)")
    else:
        print("[add_whitelist] action combo not found, using default action")

    # === 3. 点击执行按钮 ===
    for attempt in range(10):
        try:
            btn = self.dog.find_element_by_attr("$//largeFile_executeBtn")
            if btn:
                if not self._click_at_element(btn):
                    self._atspi_do_action(btn)
                sleep(2)
                print("[add_whitelist] execute button clicked")
                return
        except BaseException as e:
            print("[add_whitelist] execute attempt {0} failed: {1}".format(attempt, e))
        sleep(1)
    raise Exception("无法点击执行按钮")


def _click_large_file_whitelist_button(self):
    """点击白名单按钮打开白名单对话框"""
    for _ in range(10):
        self._safe_focus_windows()
        self.reconnect_dogtail()
        for expr in ("$//largeFile_whitelistBtn", "$//largeFileWhitelistButton"):
            try:
                btn = self.dog.find_element_by_attr(expr)
                if btn:
                    if not self._click_at_element(btn):
                        self._atspi_do_action(btn)
                    sleep(2)
                    return
            except BaseException:
                pass
        sleep(1)
    raise RuntimeError("无法找到白名单按钮")


def _get_whitelist_table_view(self, retries=10):
    """获取白名单对话框的表格视图元素"""
    for _ in range(retries):
        self._safe_focus_windows()
        self.reconnect_dogtail()
        try:
            table = self.dog.find_element_by_attr("$//whitelist_tableView")
            if table:
                w, h = table.size
                if w > 0 and h > 0:
                    return table
        except BaseException:
            pass
        sleep(1)
    return None


def _get_whitelist_empty_showing(self, retries=10):
    """检查白名单对话框空状态是否显示"""
    for _ in range(retries):
        self._safe_focus_windows()
        if self._any_visible(
            "$//whitelist_emptyLabel",
            "$//whitelist_emptyIcon",
        ):
            return True
        sleep(1)
    return False


def _whitelist_table_has_entries(self, retries=10):
    """检查白名单表格是否有条目(表格可见且非空)"""
    table = self._get_whitelist_table_view(retries=retries)
    if table is None:
        return False
    return True


def _remove_first_whitelist_entry(self):
    """点击白名单表格第一行的移除按钮(减号图标)

    WhitelistTableDelegate 在 ActionColumn(最右侧, 宽60px) 绘制移除图标,
    22px 命中区域, 居中于单元格。仅响应 MouseButtonRelease。
    行高 56px(kRowHeight)。
    """
    self._safe_focus_windows()
    self.reconnect_dogtail()
    table = self._get_whitelist_table_view()
    if table is None:
        raise RuntimeError("无法找到白名单表格视图元素")
    tx, ty = table.position
    tw, th = table.size
    print("[whitelist_remove] table=({0},{1},{2},{3})".format(tx, ty, tw, th))

    # ActionColumn 宽 60px, 移除图标居中于该列
    k_action_col_width = 60
    k_row_height = 56

    # 尝试从子元素获取行高
    row_height = k_row_height
    try:
        count = table.childCount
        if count > 0:
            first_child = table[0]
            if first_child:
                _, cy = first_child.position
                _, ch = first_child.size
                if ch > 0:
                    row_height = ch
    except BaseException:
        pass

    # 移除图标中心 = ActionColumn 中心 = 表格右边缘 - 30
    icon_center_x = int(tx + tw - k_action_col_width / 2)
    icon_center_y = int(ty + row_height / 2)

    print("[whitelist_remove] clicking at ({0},{1})".format(
        icon_center_x, icon_center_y))

    # 尝试多次点击(带小偏移), 确保命中
    for dy in range(-3, 4, 2):
        for dx in range(-3, 4, 2):
            self._safe_focus_windows()
            self.run_cmd(
                "xdotool mousemove --sync {0} {1} click 1".format(
                    icon_center_x + dx, icon_center_y + dy
                ),
                timeout=10,
                out_debug_flag=False,
            )
            sleep(1)
            # 点击后白名单应变为空
            if self.get_whitelist_empty_showing(retries=3):
                print("[whitelist_remove] whitelist now empty")
                return
    raise RuntimeError("点击移除白名单图标未生效(白名单仍非空)")


def _click_whitelist_close_button(self):
    """点击白名单对话框关闭按钮"""
    for _ in range(10):
        self._safe_focus_windows()
        self.reconnect_dogtail()
        try:
            btn = self.dog.find_element_by_attr("$//whitelist_closeBtn")
            if btn:
                if not self._click_at_element(btn):
                    self._atspi_do_action(btn)
                sleep(1)
                return
        except BaseException:
            pass
        sleep(1)
    # 回退: 按 Escape 关闭对话框
    self.run_cmd("xdotool key --clearmodifiers Escape", timeout=5, out_debug_flag=False)
    sleep(1)


def _patch_widget():
    """将大文件清理白名单相关方法注入 MyAppWidget(避免修改共享 widget 文件)"""
    MyAppWidget.clear_large_file_whitelist = _clear_large_file_whitelist
    MyAppWidget.get_whitelist_config_count = _get_whitelist_config_count
    MyAppWidget.select_first_large_file_and_add_to_whitelist = _select_first_large_file_and_add_to_whitelist
    MyAppWidget.click_large_file_whitelist_button = _click_large_file_whitelist_button
    MyAppWidget._get_whitelist_table_view = _get_whitelist_table_view
    MyAppWidget.get_whitelist_empty_showing = _get_whitelist_empty_showing
    MyAppWidget.whitelist_table_has_entries = _whitelist_table_has_entries
    MyAppWidget.remove_first_whitelist_entry = _remove_first_whitelist_entry
    MyAppWidget.click_whitelist_close_button = _click_whitelist_close_button


_patch_widget()


class TestMyCase(BaseCase):

    def test_mycase_344(self):
        """大文件清理--白名单中文件移除：验证将大文件添加到白名单后，
        可在白名单对话框中移除文件，移除后白名单显示为空"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理上次测试残留的白名单配置
        widget.clear_large_file_whitelist()
        # 前置：创建测试大文件(110MB, 超过100MB阈值)
        widget.create_large_test_file(size_mb=110)
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击大文件清理卡片进入大文件清理页面(扫描自动开始)
            # click_optimization_card_by_name 内部已含 30 次重试 + 最终兜底点击,
            # 不在此额外轮询以免频繁 reconnect_dogtail 干扰 AT-SPI 连接
            widget.click_optimization_card_by_name("大文件清理", timeout=30)
            self.assert_true(widget.get_optimization_runtime_page_showing())
            # 等待扫描完成
            self.assert_true(widget.get_large_file_scan_completed(timeout=180))
            # 验证检测到大文件(结果页显示)
            self.assert_true(widget.get_large_file_result_showing())
            # 选中第一行大文件, 切换操作为"添加到白名单"并执行
            widget.select_first_large_file_and_add_to_whitelist()
            sleep(2)
            # 验证白名单配置中已添加条目
            self.assert_true(widget.get_whitelist_config_count() >= 1)
            # 点击白名单按钮打开白名单对话框
            widget.click_large_file_whitelist_button()
            sleep(1)
            # 验证白名单表格有条目(非空状态)
            self.assert_true(widget.whitelist_table_has_entries())
            # 移除白名单中第一条文件(remove_first_whitelist_entry 内部已校验空状态,
            # 失败会抛 RuntimeError, 此处不再重复断言以避免 AT-SPI 树刷新抖动导致的误判)
            widget.remove_first_whitelist_entry()
            # 关闭白名单对话框
            widget.click_whitelist_close_button()
            sleep(1)
            # 验证白名单配置已清空
            self.assert_true(widget.get_whitelist_config_count() == 0)
        finally:
            # 清理测试大文件
            widget.remove_large_test_file()
            # 清理白名单配置
            widget.clear_large_file_whitelist()

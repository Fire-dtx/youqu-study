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
TEST_DIR = f"{HOME_DIR}/autotest_dup_file"
# 同一组内放置 3 个内容完全相同的文件, 删除其中一个后组内仍剩余 2 个,
# 重复组不会被整体移除, 从而验证"同组内删除文件"的行为。
DUP_FILE_PATHS = [
    f"{TEST_DIR}/dir_a/dup_test_file.txt",
    f"{TEST_DIR}/dir_b/dup_test_file.txt",
    f"{TEST_DIR}/dir_c/dup_test_file.txt",
]
TRASH_FILE = f"{HOME_DIR}/.local/share/Trash/files/dup_test_file.txt"
TRASH_INFO = f"{HOME_DIR}/.local/share/Trash/info/dup_test_file.txt.trashinfo"

# 重复文件表格列宽/行高(与产品源码 duplicate_file_table_delegate.cpp 对齐)
K_CHECK_COLUMN_WIDTH = 52
K_HEADER_ROW_HEIGHT = 40
K_FILE_ROW_HEIGHT = 62
# CheckColumn 复选框中心 x 相对表格左上角的偏移:
# left(kHorizontalMargin=10) + kFileIconLeftPadding(10) + indicator(18)/2
K_CHECKBOX_CENTER_OFFSET_X = 29


def _create_dup_test_files_group(self):
    """创建 3 个内容完全相同的文件, 构成一个含 3 个文件的重复组

    分属 dir_a / dir_b / dir_c 三个子目录, 重复文件扫描器按内容哈希将它们
    归为同一重复组。删除其中一个后组内仍剩余 2 个文件, 重复组保留,
    便于验证"同组内删除文件"后组与剩余文件的状态。

    注意: 重复文件扫描器(duplicate_file_detector.cpp)的最小文件大小阈值
    kMinFileSize = 1 MB, 小于 1 MB 的文件会被直接跳过, 因此测试文件必须
    >= 1 MB 才能被扫描器检测到。此处创建 2 MB 的随机内容文件确保被检测。
    """
    self.run_cmd(f"rm -rf {TEST_DIR}", timeout=5, out_debug_flag=False)
    self.run_cmd(f"mkdir -p {TEST_DIR}/dir_a {TEST_DIR}/dir_b {TEST_DIR}/dir_c",
                 timeout=5, out_debug_flag=False)
    # 用随机内容生成 2 MB 文件, 再复制到另外两个目录, 保证三份内容完全相同
    self.run_cmd(
        f"dd if=/dev/urandom of={DUP_FILE_PATHS[0]} bs=1M count=2 2>/dev/null",
        timeout=15,
        out_debug_flag=False,
    )
    self.run_cmd(
        f"cp {DUP_FILE_PATHS[0]} {DUP_FILE_PATHS[1]}",
        timeout=5,
        out_debug_flag=False,
    )
    self.run_cmd(
        f"cp {DUP_FILE_PATHS[0]} {DUP_FILE_PATHS[2]}",
        timeout=5,
        out_debug_flag=False,
    )
    sleep(1)


def _remove_dup_test_files_group(self):
    """清理同组删除测试创建的测试文件(含回收站中的副本)"""
    self.run_cmd(f"rm -rf {TEST_DIR}", timeout=5, out_debug_flag=False)
    self.run_cmd(
        f"rm -f '{TRASH_FILE}' '{TRASH_INFO}' 2>/dev/null",
        timeout=5,
        out_debug_flag=False,
    )


def _count_dup_test_files_on_disk(self):
    """统计 3 个测试文件中仍存在于磁盘上的数量"""
    count = 0
    for file_path in DUP_FILE_PATHS:
        result = self.run_cmd(
            f"ls '{file_path}' 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        if result.strip():
            count += 1
    return count


def _is_dup_file_in_trash(self):
    """检查测试文件是否已被移至回收站"""
    result = self.run_cmd(
        f"ls '{TRASH_FILE}' 2>/dev/null",
        timeout=5,
        out_debug_flag=False,
    )
    return bool(result.strip())


def _get_dup_file_table_view(self, retries=15):
    """获取重复文件清理结果页的表格视图元素(dupFile_tableView)"""
    for _ in range(retries):
        try:
            table = self.dog.find_element_by_attr("$//dupFile_tableView")
            if table:
                w, h = table.size
                if w > 0 and h > 0:
                    return table
        except BaseException:
            pass
        self._safe_focus_windows()
        sleep(1)
    return None


def _get_dup_file_execute_button(self):
    """获取重复文件清理结果页的执行按钮元素(dupFile_executeBtn)"""
    try:
        return self.dog.find_element_by_attr("$//dupFile_executeBtn")
    except BaseException:
        return None


def _get_dup_file_execute_button_enabled(self, retries=10) -> bool:
    """检查重复文件清理执行按钮是否可用(选中文件后应启用)"""
    for _ in range(retries):
        try:
            self.reconnect_dogtail()
            btn = self.get_dup_file_execute_button()
            if btn:
                w, h = btn.size
                if w > 0 and h > 0:
                    return btn.sensitive
        except BaseException:
            pass
        self._safe_focus_windows()
        sleep(1)
    return False


def _dump_table_debug(self, table, tag=""):
    """将表格子元素信息写入 /tmp/dup_table_debug.txt 便于排查"""
    try:
        with open("/tmp/dup_table_debug.txt", "a", encoding="utf-8") as f:
            f.write("=== {0} ===\n".format(tag))
            count = table.childCount
            f.write("childCount={0}\n".format(count))
            tx, ty = table.position
            tw, th = table.size
            f.write("table pos=({0},{1}) size=({2},{3})\n".format(tx, ty, tw, th))
            for i in range(count):
                try:
                    child = table[i]
                    if not child:
                        f.write("[{0}] None\n".format(i))
                        continue
                    cname = (child.name or "").strip()
                    cdesc = (child.description or "").strip()
                    crole = child.role
                    try:
                        cx, cy = child.position
                        cw, ch = child.size
                    except Exception:
                        cx, cy, cw, ch = 0, 0, 0, 0
                    f.write("[{0}] name={1!r} desc={2!r} role={3} pos=({4},{5}) size=({6},{7})\n".format(
                        i, cname, cdesc, crole, cx, cy, cw, ch))
                except Exception as e:
                    f.write("[{0}] ERROR: {1}\n".format(i, e))
            f.write("=== END {0} ===\n\n".format(tag))
    except Exception:
        pass


def _select_dup_test_file_in_group(self):
    """在重复文件表格中选中包含 dup_test_file 的行的复选框

    重复文件表格的复选框由 delegate 绘制, 无独立 AT-SPI 元素, 仅响应鼠标点击。
    系统中可能存在大量重复文件组, 测试文件所在组可能不在表格可视区域内,
    需要先滚动表格直至目标行可见, 再点击该行复选框选中。
    """
    self._safe_focus_windows()
    table = self.get_dup_file_table_view()
    if table is None:
        raise RuntimeError("无法找到重复文件表格视图元素(dupFile_tableView)")

    self.dump_table_debug(table, "select_dup_test_file")

    def _find_target_child(tbl):
        """在表格子元素中查找名称包含 dup_test_file 的行"""
        try:
            count = tbl.childCount
            for i in range(count):
                child = tbl[i]
                if not child:
                    continue
                cname = (child.name or "").strip()
                if "dup_test_file" in cname:
                    cw, ch = child.size
                    if cw > 0 and ch > 0:
                        return child
        except BaseException:
            pass
        return None

    # 阶段1: 滚动表格直至目标行进入可视区域
    # 系统中存在大量重复文件组, 测试文件所在组可能远在表格可视区域之下。
    # 实测每个滚轮刻度约移动 11px, 但 xdotool --repeat 不带 --delay 时点击过快,
    # Qt 事件循环来不及处理, 大量点击丢失。因此:
    # 1) 用 --delay 50 确保 --repeat 的每次点击都被 Qt 接收
    # 2) 按目标与可视区域的间距精确计算所需点击数(~11px/click)
    # 3) 每次最多 40 次点击(约 440px 移动), 多轮收敛
    PIXELS_PER_CLICK = 11
    target = None
    cx = cy = cw = ch = 0
    table_x = table_y = tw = th = 0
    for scroll_attempt in range(30):
        table = self.get_dup_file_table_view()
        if table is None:
            self.reconnect_dogtail()
            sleep(1)
            continue
        table_x, table_y = table.position
        tw, th = table.size
        table_bottom = table_y + th

        found = _find_target_child(table)
        if found is not None:
            cx, cy = found.position
            cw, ch = found.size
            if table_y <= cy and cy + ch <= table_bottom:
                print("[select_dup] target visible at ({0},{1}) size=({2},{3}) "
                      "scroll_attempt={4}".format(cx, cy, cw, ch, scroll_attempt))
                target = found
                break
            # 目标存在但未完全可见: 按方向精确计算点击数
            if cy + ch < table_y:
                # 目标在可视区域上方 -> 向上滚动(button 4)
                gap = table_y - (cy + ch)
                button = 4
            else:
                # 目标在可视区域下方 -> 向下滚动(button 5)
                gap = cy - table_bottom
                button = 5
            notches = max(2, min(int(gap / PIXELS_PER_CLICK) + 2, 40))
        else:
            # 未找到目标(表格尚未加载完成), 向下滚动并等待
            button = 5
            notches = 40

        center_x = int(table_x + tw / 2)
        center_y = int(table_y + th / 2)
        self.run_cmd(
            f"xdotool mousemove {center_x} {center_y} "
            f"click --repeat {notches} --delay 50 {button}",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(0.8)

    if target is None:
        # 滚动失败: 导出当前表格状态便于排查
        tbl = self.get_dup_file_table_view(retries=3)
        if tbl is not None:
            self.dump_table_debug(tbl, "select_dup_test_file_SCROLL_FAIL")
        raise RuntimeError("无法滚动到目标行(滚动30次后仍未可见)")

    # 阶段2: 目标行已可见, 点击复选框
    checkbox_x = int(table_x) + K_CHECKBOX_CENTER_OFFSET_X
    checkbox_y = int(cy + ch / 2)

    for dx in range(-5, 6, 2):
        for dy in range(-5, 6, 2):
            self.run_cmd(
                f"xdotool mousemove --sync {checkbox_x + dx} {checkbox_y + dy} click 1",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(0.4)
            if self.get_dup_file_execute_button_enabled(retries=1):
                print("[select_dup] checkbox selected at ({0},{1})".format(
                    checkbox_x + dx, checkbox_y + dy))
                return
        sleep(0.2)

    # 扩大 x 扫描范围重试
    for dx in range(-15, 16, 3):
        self.run_cmd(
            f"xdotool mousemove --sync {checkbox_x + dx} {checkbox_y} click 1",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(0.4)
        if self.get_dup_file_execute_button_enabled(retries=1):
            print("[select_dup] checkbox selected (wide scan) at ({0},{1})".format(
                checkbox_x + dx, checkbox_y))
            return

    raise RuntimeError("无法选中重复文件(复选框点击未生效)")


def _click_dup_file_execute_button(self):
    """点击重复文件清理结果页的执行按钮

    操作下拉框默认为"移至回收站", 点击执行即将所选文件移至回收站(无确认对话框)。
    优先 AT-SPI Action, 失败回退坐标点击。
    """
    for attempt in range(10):
        try:
            self.reconnect_dogtail()
            btn = self.get_dup_file_execute_button()
            if btn:
                w, h = btn.size
                if w > 0 and h > 0:
                    if not self._click_at_element(btn):
                        self._atspi_do_action(btn)
                    sleep(2)
                    return
        except BaseException as e:
            print("[dup_execute] attempt {0} failed: {1}".format(attempt, e))
        sleep(1)
    raise RuntimeError("无法点击重复文件清理执行按钮")


def _get_dup_file_result_showing(self) -> bool:
    """检查重复文件清理结果页是否显示(检测到重复文件)

    结果页 dupFile_resultTitle 可见表示扫描检测到了重复文件。
    """
    return self._any_visible("$//dupFile_resultTitle")


def _patch_widget():
    """将同组内删除文件相关方法注入 MyAppWidget(避免修改共享 widget 文件)"""
    MyAppWidget.get_dup_file_result_showing = _get_dup_file_result_showing
    MyAppWidget.create_dup_test_files_group = _create_dup_test_files_group
    MyAppWidget.remove_dup_test_files_group = _remove_dup_test_files_group
    MyAppWidget.count_dup_test_files_on_disk = _count_dup_test_files_on_disk
    MyAppWidget.is_dup_file_in_trash = _is_dup_file_in_trash
    MyAppWidget.get_dup_file_table_view = _get_dup_file_table_view
    MyAppWidget.get_dup_file_execute_button = _get_dup_file_execute_button
    MyAppWidget.get_dup_file_execute_button_enabled = _get_dup_file_execute_button_enabled
    MyAppWidget.dump_table_debug = _dump_table_debug
    MyAppWidget.select_dup_test_file_in_group = _select_dup_test_file_in_group
    MyAppWidget.click_dup_file_execute_button = _click_dup_file_execute_button


_patch_widget()


class TestMyCase(BaseCase):

    def test_mycase_345(self):
        """重复文件清理--同组内删除文件：在重复文件清理结果页选中同一重复组内的
        一个文件并移至回收站，验证该文件从组内删除、磁盘移除并进入回收站，
        而重复组因仍剩余文件而保留、结果页继续显示"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：创建含 3 个相同文件的重复组(删除一个后组内仍剩 2 个, 组保留)
        widget.create_dup_test_files_group()
        # 前置：清理回收站中可能残留的同名文件, 避免验证误判
        widget.run_cmd(
            f"rm -f '{TRASH_FILE}' '{TRASH_INFO}' 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        )
        # 前置: 隔离家目录中已存在的重复文件, 避免真实重复组把测试组挤到
        # 列表深处(滚动查找超时), 也避免干扰组保留判定
        isolated = widget.isolate_foreign_dup_files()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击"重复文件清理"卡片, 进入重复文件清理页面(扫描自动开始)
            widget.click_optimization_card_by_name("重复文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            # 等待扫描完成
            self.assert_true(widget.get_dup_file_scan_completed(timeout=180))
            # 验证检测到重复文件(结果页显示)
            self.assert_true(widget.get_dup_file_result_showing())
            # 选中测试文件所在行(同组内一个文件)的复选框
            widget.select_dup_test_file_in_group()
            # 验证执行按钮已启用(选中文件后按钮应可用)
            self.assert_true(widget.get_dup_file_execute_button_enabled())
            # 点击执行按钮, 将所选文件移至回收站(默认操作, 无确认对话框)
            widget.click_dup_file_execute_button()
            sleep(2)
            # 验证被选文件已从磁盘移除(3 个测试文件中应剩余 2 个)
            self.assert_true(widget.count_dup_test_files_on_disk() == 2)
            # 验证被选文件已进入回收站
            self.assert_true(widget.is_dup_file_in_trash())
            # 验证重复组因仍剩余文件而保留(结果页继续显示, 未切换到完成页)
            self.assert_true(widget.get_dup_file_result_showing())
        finally:
            # 清理测试文件(磁盘 + 回收站)
            widget.remove_dup_test_files_group()
            widget.restore_foreign_dup_files(isolated)
            widget.kill_pc_manager()

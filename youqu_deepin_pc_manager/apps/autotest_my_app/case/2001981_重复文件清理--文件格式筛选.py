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
DUP_MULTI_DIR = f"{HOME_DIR}/autotest_dup_file_multi"

# 重复文件清理分类按钮顺序与索引(与产品 DButtonBox 一致):
# 0 → 全部, 1 → 文档, 2 → 图片, 3 → 视频, 4 → 音频, 5 → 压缩包, 6 → 其他
DUP_FILE_CATEGORY_INDEX = {
    "all": 0,
    "document": 1,
    "image": 2,
    "video": 3,
    "audio": 4,
    "archive": 5,
    "other": 6,
}


def _create_multi_type_dup_files(self):
    """创建多类型重复文件, 用于验证重复文件清理文件格式筛选

    重复文件扫描器要求文件大小 >= 1 MB 才进入候选集,
    并按文件内容哈希将相同内容的文件归为同一重复组。

    为文档/图片/视频/音频/压缩包/其他 6 个分类各创建一对内容相同、
    大小 2 MB 的文件(分属不同子目录), 确保每个分类都有重复文件。
    文件放在 ~/autotest_dup_file_multi/ 目录下。
    """
    self.run_cmd(
        f"rm -rf '{DUP_MULTI_DIR}'", timeout=5, out_debug_flag=False
    )
    dir_a = f"{DUP_MULTI_DIR}/dir_a"
    dir_b = f"{DUP_MULTI_DIR}/dir_b"
    self.run_cmd(
        f"mkdir -p '{dir_a}' '{dir_b}'", timeout=5, out_debug_flag=False
    )
    # 每个分类一个文件扩展名, 内容相同的成对文件
    typed_files = [
        "doc_dup.txt",      # document
        "img_dup.jpg",      # image
        "video_dup.mp4",    # video
        "audio_dup.mp3",    # audio
        "archive_dup.zip",  # archive
        "other_dup.bin",    # other
    ]
    for name in typed_files:
        self.run_cmd(
            f"dd if=/dev/urandom of='{dir_a}/{name}' bs=1M count=2 2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"cp '{dir_a}/{name}' '{dir_b}/{name}'",
            timeout=5,
            out_debug_flag=False,
        )
    sleep(1)


def _remove_multi_type_dup_files(self):
    """清理多类型重复文件测试创建的文件"""
    self.run_cmd(
        f"rm -rf '{DUP_MULTI_DIR}'", timeout=5, out_debug_flag=False
    )


def _get_dup_file_category_buttons(self):
    """获取重复文件清理结果页的全部格式分类筛选按钮(按从左到右排序)

    所有分类按钮的 accessibleName 均为 dupFile_catBtn,
    通过 find_elements_by_attr 查找后按 x 坐标排序。
    :return: 按钮元素列表(从左到右), 空列表表示未找到
    """
    self._safe_focus_windows()
    try:
        buttons = self.dog.find_elements_by_attr("$//dupFile_catBtn")
        if buttons:
            buttons.sort(key=lambda b: b.position[0])
            return buttons
    except BaseException:
        pass
    return []


def _get_dup_file_category_checked(self, category_id) -> bool:
    """检查重复文件清理指定格式分类筛选按钮是否处于选中(checked)状态

    :param category_id: 分类标识符(all/document/image/video/audio/archive/other)
    :return: True 如果该按钮当前被选中
    """
    self._safe_focus_windows()
    buttons = self._get_dup_file_category_buttons()
    try:
        idx = DUP_FILE_CATEGORY_INDEX[category_id]
    except KeyError:
        return False
    if idx >= len(buttons):
        return False
    try:
        states = buttons[idx].states
        if "checked" in states:
            return True
    except BaseException:
        pass
    try:
        return bool(buttons[idx].checked)
    except BaseException:
        return False


def _click_dup_file_category(self, category_id):
    """点击重复文件清理结果页的格式分类筛选按钮

    DButtonBoxButton 的 AT-SPI doAction 不触发 buttonClicked 信号,
    使用 xdotool 坐标点击激活分类筛选逻辑。

    :param category_id: 分类标识符(all/document/image/video/audio/archive/other)
    :return: True 如果点击成功
    """
    self._safe_focus_windows()
    buttons = self._get_dup_file_category_buttons()
    try:
        idx = DUP_FILE_CATEGORY_INDEX[category_id]
    except KeyError:
        return False
    if idx >= len(buttons):
        return False
    try:
        bx, by = buttons[idx].position
        bw, bh = buttons[idx].size
        click_x = int(bx + bw / 2)
        click_y = int(by + bh / 2)
        self._safe_focus_windows()
        self.run_cmd(
            f"xdotool mousemove --sync {click_x} {click_y} click 1",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)
        return True
    except BaseException:
        pass
    return False


def _patch_widget():
    """将重复文件清理格式筛选相关方法注入 MyAppWidget(避免修改共享 widget 文件)"""
    MyAppWidget.create_multi_type_dup_files = _create_multi_type_dup_files
    MyAppWidget.remove_multi_type_dup_files = _remove_multi_type_dup_files
    MyAppWidget._get_dup_file_category_buttons = _get_dup_file_category_buttons
    MyAppWidget.get_dup_file_category_checked = _get_dup_file_category_checked
    MyAppWidget.click_dup_file_category = _click_dup_file_category


_patch_widget()


class TestMyCase(BaseCase):

    def test_mycase_349(self):
        """重复文件清理--文件格式筛选：验证扫描出多类型重复文件后，
        默认选中【全部】分类，依次切换各分类 Tab 可正常筛选"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：创建多类型重复文件(文档/图片/视频/音频/压缩包/其他各一对)
        widget.create_multi_type_dup_files()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击"重复文件清理"卡片，进入重复文件清理页面(扫描自动开始)
            widget.click_optimization_card_by_name("重复文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            # 等待扫描完成
            self.assert_true(widget.get_dup_file_scan_completed(timeout=180))
            # 验证检测到重复文件(结果页显示)
            self.assert_true(widget.get_dup_file_result_showing())

            # 验证默认选中【全部】分类
            self.assert_true(widget.get_dup_file_category_checked("all"))

            # 依次切换各分类 Tab，验证切换后对应分类被选中且结果页正常显示
            for category in (
                "document",
                "image",
                "video",
                "audio",
                "archive",
                "other",
            ):
                self.assert_true(widget.click_dup_file_category(category))
                sleep(1)
                self.assert_true(
                    widget.get_dup_file_category_checked(category)
                )
                # 每个分类都有重复文件，结果页应正常显示(非无匹配)
                self.assert_true(widget.get_dup_file_result_showing())

            # 切换回【全部】，验证恢复选中且结果正常显示
            self.assert_true(widget.click_dup_file_category("all"))
            sleep(1)
            self.assert_true(widget.get_dup_file_category_checked("all"))
            self.assert_true(widget.get_dup_file_result_showing())
        finally:
            # 清理测试文件
            widget.remove_multi_type_dup_files()
            widget.kill_pc_manager()

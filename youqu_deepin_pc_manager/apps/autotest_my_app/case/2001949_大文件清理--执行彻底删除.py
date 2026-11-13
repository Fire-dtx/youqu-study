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
TEST_FILE = f"{HOME_DIR}/autotest_large_file/large_test_file.bin"
TRASH_FILE = f"{HOME_DIR}/.local/share/Trash/files/large_test_file.bin"
TRASH_INFO = f"{HOME_DIR}/.local/share/Trash/info/large_test_file.bin.trashinfo"


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
    """将大文件彻底删除验证方法注入 MyAppWidget(避免修改共享 widget 文件)"""
    MyAppWidget.is_large_file_on_disk = _is_large_file_on_disk
    MyAppWidget.is_large_file_in_trash = _is_large_file_in_trash


_patch_widget()


class TestMyCase(BaseCase):

    def test_mycase_347(self):
        """大文件清理--执行彻底删除：选中大文件后选择"彻底删除"操作，
        点击执行按钮并在确认对话框中点击"彻底删除"，验证文件被永久删除
        (既不在磁盘上也不在回收站中)"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清理上一次测试残留的回收站文件, 避免验证误判
        widget.run_cmd(
            "rm -f '{0}' '{1}' 2>/dev/null".format(TRASH_FILE, TRASH_INFO),
            timeout=5,
            out_debug_flag=False,
        )
        # 前置：创建测试大文件(110MB, 满足大文件清理>=100MB阈值)
        widget.create_large_test_file()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 刷新 AT-SPI 树(页面切换后旧引用可能失效)
            widget.reconnect_dogtail()
            # 点击大文件清理卡片, 进入大文件清理页面(插件自动开始扫描)
            widget.click_optimization_card_by_name("大文件清理")
            self.assert_true(widget.get_optimization_runtime_page_showing())
            # 等待扫描完成并验证结果页面显示
            self.assert_true(widget.get_large_file_result_page_showing(timeout=180))
            # 验证检测到大文件(结果页而非空状态页)
            self.assert_true(widget.get_large_file_has_results(timeout=15))
            # 选中第一行大文件
            widget.click_large_file_table_checkbox(0)
            # 验证执行按钮可用(选中文件后按钮应启用)
            self.assert_true(widget.get_large_file_execute_button_enabled())
            # 将操作下拉框切换为"彻底删除"
            widget.select_large_file_action("彻底删除")
            sleep(1)
            # 点击执行按钮, 触发彻底删除确认对话框(刷新 AT-SPI 树后重试)
            for attempt in range(5):
                try:
                    widget.click_large_file_execute_button()
                    break
                except RuntimeError:
                    widget.reconnect_dogtail()
                    sleep(1)
            else:
                raise RuntimeError("无法找到大文件清理执行按钮")
            sleep(2)
            # 验证彻底删除确认对话框弹出
            self.assert_true(widget.get_large_file_delete_confirm_dialog_showing(timeout=10))
            # 点击"彻底删除"按钮, 确认永久删除文件
            self.assert_true(
                widget.click_large_file_delete_confirm_dialog_button("彻底删除", timeout=10)
            )
            sleep(3)
            # 验证文件已从磁盘永久删除(彻底删除不经过回收站)
            self.assert_true(not widget.is_large_file_on_disk())
            # 验证文件未被移至回收站(彻底删除应直接删除, 而非移至回收站)
            self.assert_true(not widget.is_large_file_in_trash())
        finally:
            # 清理测试大文件(包括磁盘残留和回收站残留)
            widget.remove_large_test_file()
            widget.run_cmd(
                "rm -f '{0}' '{1}' 2>/dev/null".format(TRASH_FILE, TRASH_INFO),
                timeout=5,
                out_debug_flag=False,
            )

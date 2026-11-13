#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/09/28
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_010(self):
        """发送到任务栏：启动器右键发送到任务栏, 检查一致性, 再从启动器移除"""
        widget = MyAppWidget(check_start=False)
        # 确保启动器已收录电脑管家(安装后索引可能未刷新)
        self.assert_true(widget.ensure_app_in_launcher("deepin-pc-manager"))
        # 前置：确保任务栏没有残留的电脑管家图标
        if widget.get_dock_has_app_icon():
            self.assert_true(widget.open_launcher_and_search("电脑管家"))
            self.assert_true(widget.right_click_launcher_result())
            self.assert_true(widget.click_launcher_menu("从任务栏上移除"))
            sleep(1)
        # 打开启动器并搜索电脑管家
        self.assert_true(widget.open_launcher_and_search("电脑管家"))
        # 右键搜索结果, 在弹出菜单中点击"发送到任务栏"
        self.assert_true(widget.right_click_launcher_result())
        self.assert_true(widget.click_launcher_menu("发送到任务栏"))
        sleep(1)
        # 断言任务栏上已存在电脑管家图标
        self.assert_true(widget.get_dock_has_app_icon())
        # 从启动器右键菜单"从任务栏上移除"
        self.assert_true(widget.open_launcher_and_search("电脑管家"))
        self.assert_true(widget.right_click_launcher_result())
        self.assert_true(widget.click_launcher_menu("从任务栏上移除"))
        sleep(1)
        # 断言任务栏上已不存在电脑管家图标
        self.assert_false(widget.get_dock_has_app_icon())

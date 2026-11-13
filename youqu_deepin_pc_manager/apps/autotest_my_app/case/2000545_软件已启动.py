#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/09/28
"""
import logging

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep

logger = logging.getLogger(__name__)


class TestMyCase(BaseCase):

    def test_mycase_013(self):
        """软件已启动：dock 图标显示与右键菜单操作

        1. 启动器中运行软件后, dock 上自动显示软件窗口图标
        2. 右键 dock 图标, 菜单显示: 电脑管家、驻留/移除驻留、强制退出、关闭所有
           (V25 菜单另含"所有窗口")
        3. 强制退出: 软件窗口关闭, 进程退出
        4. 所有窗口: 展示软件所有窗口(单窗口应用无此项时跳过)
        5. 移除驻留: 取消 dock 驻留, 进程仍在运行
        6. 关闭所有: 关闭软件所有窗口, 进程退出
        """
        widget = MyAppWidget(check_start=False)

        # 前置: 关闭软件并取消 dock 驻留
        widget.kill_pc_manager()
        if widget.get_dock_has_app_icon():
            widget.remove_from_dock_via_launcher()
        sleep(1)

        # 1. 启动器中运行软件, dock 自动显示运行图标
        self.assert_true(widget.launch_app_from_launcher("电脑管家"))
        self.assert_true(widget.get_pc_manager_process_status())
        self.assert_true(widget.get_dock_has_running_icon())

        # 2. 右键 dock 图标, 校验菜单内容
        menu_items = widget.get_dock_menu_items()
        self.assert_true("电脑管家" in menu_items)
        self.assert_true("强制退出" in menu_items)
        self.assert_true("关闭所有" in menu_items)
        self.assert_true("驻留" in menu_items or "移除驻留" in menu_items)
        self.assert_true(widget.open_dock_app_menu() is not None)
        widget.close_dock_menu()

        # 3. 强制退出
        self.assert_true(widget.click_dock_menu_item("强制退出"))
        self.assert_true(widget.wait_pc_manager_exit())
        self.assert_false(widget.get_dock_has_running_icon())

        # 4. 所有窗口
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        if "所有窗口" in widget.get_dock_menu_items():
            self.assert_true(widget.click_dock_menu_item("所有窗口"))
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_dock_has_running_window())
            widget.close_dock_menu()
        else:
            logger.info("当前 dock 菜单无 '所有窗口' 菜单项(单窗口应用), 跳过该步骤")

        # 5. 移除驻留
        if not widget.get_dock_has_app_icon():
            widget.send_to_dock_via_launcher()
        self.assert_true(widget.get_dock_has_app_icon())
        self.assert_true("移除驻留" in widget.get_dock_menu_items())
        self.assert_true(widget.click_dock_menu_item("移除驻留"))
        self.assert_false(widget.get_dock_has_app_icon())
        self.assert_true(widget.get_pc_manager_process_status())

        # 6. 关闭所有
        self.assert_true(widget.click_dock_menu_item("关闭所有"))
        self.assert_true(widget.wait_pc_manager_exit())
        self.assert_false(widget.get_dock_has_running_icon())

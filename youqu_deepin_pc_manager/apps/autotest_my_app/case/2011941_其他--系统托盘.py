#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_272(self):
        """其他--系统托盘：任务栏图标右键菜单与单击均可唤出主页面

        前置条件: 电脑管家运行并最小化到系统任务栏。V20 无独立托盘图标,
        运行中的应用图标即出现在 dock(任务栏)上, 最小化后窗口进入
        _NET_WM_STATE_HIDDEN 状态。

        步骤与断言:
        1. 最小化主窗口后, 在任务栏图标右键菜单中选择"电脑管家",
           窗口取消 HIDDEN 状态并重新聚焦, 主界面模块正常显示;
        2. 再次最小化后, 单击任务栏图标, 窗口同样恢复并显示主界面;
        3. 结束后关闭应用, 关闭残留菜单。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        self.assert_true(widget.get_main_page_modules_showing())
        try:
            window_id = widget.get_main_window_id()
            logger.info(f"[2011941] 主窗口 ID: {window_id}")
            self.assert_true(bool(window_id))

            # 运行中的应用应出现在任务栏条目中, 右键菜单包含"电脑管家"
            self.assert_true(widget.get_dock_has_running_icon())
            menu_items = widget.get_dock_menu_items()
            logger.info(f"[2011941] 任务栏右键菜单: {menu_items}")
            self.assert_true("电脑管家" in menu_items)

            # 1. 最小化 -> 右键菜单选择"电脑管家" -> 主页面弹出
            self.assert_true(widget.minimize_main_window(window_id))
            self.assert_true(widget.is_main_window_hidden(window_id))
            self.assert_true(widget.click_dock_menu_item("电脑管家"))
            state = widget.get_main_window_wm_state(window_id)
            logger.info(f"[2011941] 右键菜单唤出后窗口状态: {state}")
            self.assert_true(not widget.is_main_window_hidden(window_id))
            self.assert_true(widget.get_main_page_modules_showing())

            # 2. 再次最小化 -> 单击任务栏图标 -> 主页面弹出
            self.assert_true(widget.minimize_main_window(window_id))
            self.assert_true(widget.is_main_window_hidden(window_id))
            self.assert_true(widget.click_dock_icon())
            state = widget.get_main_window_wm_state(window_id)
            logger.info(f"[2011941] 单击任务栏图标后窗口状态: {state}")
            self.assert_true(not widget.is_main_window_hidden(window_id))
            self.assert_true(widget.get_main_page_modules_showing())

            # 3. 全程进程存活
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            widget.close_dock_menu()
            widget.kill_pc_manager()

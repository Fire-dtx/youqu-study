#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_297(self):
        """自启动应用--开机自启动与启动器一致：在启动器中为"浏览器"设置
        开机自启动, 打开电脑管家在"启动管理器"中查看浏览器的自启动状态,
        验证与启动器(系统 autostart)状态一致"""
        widget = MyAppWidget(check_start=False)
        browser_desktop = widget.get_browser_desktop_path()
        self.assert_true(browser_desktop)
        browser_name = browser_desktop.rsplit("/", 1)[-1]
        # 前置: 取消浏览器开机自启动
        if widget.is_autostart_enabled(browser_name):
            self.assert_true(
                widget.set_autostart_via_launcher(
                    False, app_name="浏览器", desktop_name=browser_name
                )
            )
            widget.close_launcher_ui()
        self.assert_false(widget.is_autostart_enabled(browser_name))
        # 启动器右键"开机自动启动", 为浏览器开启开机自启动
        self.assert_true(
            widget.set_autostart_via_launcher(
                True, app_name="浏览器", desktop_name=browser_name
            )
        )
        self.assert_true(widget.is_autostart_enabled(browser_name))
        self.assert_true(widget.get_startmanager_autostart_status(browser_desktop))
        widget.close_launcher_ui()
        # 打开电脑管家, 进入 系统优化 → 启动管理器
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        self.assert_true(widget.navigate_to_startup_management())
        # 查看浏览器自启动状态, 应与启动器一致(已开启)
        switch_checked = widget.get_startup_item_switch_checked("浏览器")
        self.assert_true(switch_checked is not None)
        self.assert_true(switch_checked)
        # 清理: 启动器中取消浏览器开机自启动
        self.assert_true(
            widget.set_autostart_via_launcher(
                False, app_name="浏览器", desktop_name=browser_name
            )
        )
        self.assert_false(widget.is_autostart_enabled(browser_name))
        widget.close_launcher_ui()
        # 返回系统优化页面
        widget.click_back_button()

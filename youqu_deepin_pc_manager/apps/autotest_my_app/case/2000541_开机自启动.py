#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/09/28
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_011(self):
        """开机自启动：启动器右键设置/取消开机自启动

        开机自启动由 desktop 文件(~/.config/autostart)决定, 与电脑管家
        进程是否运行无关, 用例只操作启动器右键菜单。
        V25 启动器设置开机自启动时会弹出确认框, 默认选中"禁用"并开始
        30 秒倒计时(超时按"禁用"执行), 用例内自动选择"启用"。
        V20(dde-launcher 5.9.5)无确认框, 直接写入 autostart 文件。
        """
        widget = MyAppWidget(check_start=False)
        # 前置：确保未启用开机自启动
        if widget.is_autostart_enabled():
            self.assert_true(widget.set_autostart_via_launcher(False))
        self.assert_false(widget.is_autostart_enabled())
        # 启动器右键"开机自动启动", 自动处理确认弹窗
        self.assert_true(widget.set_autostart_via_launcher(True))
        self.assert_true(widget.is_autostart_enabled())
        # 清理：启动器右键"取消开机自启动"
        self.assert_true(widget.set_autostart_via_launcher(False))
        self.assert_false(widget.is_autostart_enabled())

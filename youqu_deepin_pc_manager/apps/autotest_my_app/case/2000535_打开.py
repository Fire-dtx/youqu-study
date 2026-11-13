#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/09/28
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_008(self):
        """打开：在启动器中右键"打开"启动电脑管家"""
        widget = MyAppWidget(check_start=False)
        # 确保先关闭已运行的电脑管家
        widget.kill_pc_manager()
        # 确保启动器已收录电脑管家(安装后索引可能未刷新)
        self.assert_true(widget.ensure_app_in_launcher("deepin-pc-manager"))
        # 打开启动器并搜索电脑管家
        self.assert_true(widget.open_launcher_and_search("电脑管家"))
        # 右键搜索结果, 在弹出菜单中点击"打开"
        self.assert_true(widget.right_click_launcher_result())
        self.assert_true(widget.click_launcher_menu("打开"))
        # 断言电脑管家主进程已启动
        self.assert_true(widget.get_pc_manager_process_status())

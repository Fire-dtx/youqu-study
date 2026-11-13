#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/09/28
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_007(self):
        """启动器中启动：软件安装成功后查看启动器图标, 点击启动

        前置处理:UOS 20 的启动器索引只在 dde-session-daemon 启动时扫描
        /usr/share/applications, deb 安装后新应用不会自动出现, 启动器里
        看不到图标。因此先校验索引是否收录, 未收录则重启索引服务与启动器
        UI 刷新, 确保"安装后图标可见"这一前提成立。
        """
        widget = MyAppWidget(check_start=False)
        # 确保先关闭已运行的电脑管家
        widget.kill_pc_manager()
        # 安装后确保启动器已收录并显示电脑管家
        self.assert_true(widget.ensure_app_in_launcher("deepin-pc-manager"))
        # 从启动器搜索并启动电脑管家
        self.assert_true(widget.launch_app_from_launcher("电脑管家"))
        # 断言电脑管家主进程已启动
        self.assert_true(widget.get_pc_manager_process_status())
        # 断言主界面四大模块已显示
        self.assert_true(widget.get_main_page_modules_showing())

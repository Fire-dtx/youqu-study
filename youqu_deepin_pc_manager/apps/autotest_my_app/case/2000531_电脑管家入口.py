#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/09/28
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_006(self):
        """电脑管家入口：从启动器搜索"电脑管家"并点击启动, 进入主界面

        前置处理:UOS 20 的启动器索引只在 dde-session-daemon 启动时扫描
        /usr/share/applications, deb 安装后新应用不会自动出现, 启动器里
        看不到图标。因此先校验索引是否收录, 未收录则重启索引服务与启动器
        UI 刷新, 避免用例因环境缓存问题误判。
        """
        widget = MyAppWidget(check_start=False)
        # 确保先关闭已运行的电脑管家
        widget.kill_pc_manager()
        # 确保启动器已收录电脑管家(安装后索引可能未刷新)
        self.assert_true(widget.ensure_app_in_launcher("deepin-pc-manager"))
        # 从启动器搜索并启动电脑管家
        self.assert_true(widget.launch_app_from_launcher("电脑管家"))
        # 断言电脑管家主进程已启动
        self.assert_true(widget.get_pc_manager_process_status())
        # 断言主界面四大模块已显示
        self.assert_true(widget.get_main_page_modules_showing())

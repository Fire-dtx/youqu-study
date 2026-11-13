#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_226(self):
        """兼容性--LOGO图标

        描述: 启动电脑管家, 检查帮助手册、任务栏、桌面的图标;
        预期: 图标与设计 logo 一致。

        实现:
        - 桌面/启动器: .desktop 的 Icon 指向系统图标文件, 校验存在且为 SVG;
        - 任务栏: dde-dock 条目中存在 deepin-pc-manager 运行图标, 窗口
          _NET_WM_ICON 已设置(dock/窗口取图来源);
        - 帮助手册: 手册 common 目录的 deepin_pc_manager.svg 与系统图标
          图形结构一致(路径数、渐变数、填充色集合相同, 仅标称尺寸不同);
        - 回退: 关闭电脑管家。

        闭环: 只读校验, 无环境改动。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        self.assert_true(widget.get_main_page_modules_showing())

        # 桌面/启动器图标
        icon_name = widget.get_desktop_icon_name()
        icon_path = widget.get_app_icon_path()
        self.assert_true(bool(icon_name))
        self.assert_true(bool(icon_path))
        self.assert_true(widget.get_app_icon_exists())
        self.assert_true(icon_path.lower().endswith(".svg"))

        icon_stats = widget.get_svg_logo_stats(icon_path)
        logger.info(f"[2011933] 系统图标结构: {icon_stats}")
        self.assert_true(int(icon_stats.get("paths", "0")) > 0)
        self.assert_true(int(icon_stats.get("gradients", "0")) > 0)

        # 任务栏图标
        dock_entries = widget.get_dock_entry_ids()
        logger.info(f"[2011933] dock 条目: {dock_entries}")
        self.assert_true(icon_name in dock_entries)
        self.assert_true(widget.get_dock_icon_showing_when_running())
        self.assert_true(widget.get_window_net_wm_icon_present())

        # 帮助手册 LOGO
        manual_logo = widget.get_help_manual_logo_path("zh_CN")
        logger.info(f"[2011933] 手册 LOGO: {manual_logo}")
        self.assert_true(bool(manual_logo))
        manual_stats = widget.get_svg_logo_stats(manual_logo)
        logger.info(f"[2011933] 手册 LOGO 结构: {manual_stats}")
        self.assert_true(manual_stats.get("paths") == icon_stats.get("paths"))
        self.assert_true(
            manual_stats.get("gradients") == icon_stats.get("gradients")
        )
        self.assert_true(manual_stats.get("fills") == icon_stats.get("fills"))

        widget.kill_pc_manager()

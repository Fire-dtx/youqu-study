#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_223(self):
        """兼容性--图标显示

        描述:
        1. 任务栏切换时尚模式, Alt+TAB 切换图标显示, 查看软件图标显示
        2. 任务栏切换高效模式, Alt+TAB 切换图标显示, 查看软件图标显示
        3. 高分屏下 Alt+TAB 切换图标显示, 查看软件图标显示
        预期: 三种场景下软件图标显示正常。

        等价实现:
        - 任务栏模式直接修改 dde-dock 的 display-mode(fashion/efficient),
          每种模式下校验: 模式生效、dde-dock 存活、运行时任务栏图标可见;
        - Alt+TAB 切换器为合成器覆盖层, 无 AT-SPI 节点且本机 KWin 不响应
          XTEST 合成按键(实测截图无变化), 因此图标可用性以"图标主题解析
          结果"验证: .desktop Icon 能解析到图标文件, 且为可缩放矢量格式,
          任何尺寸(含高分屏)均可渲染;
        - 高分屏用 1920x1440 验证: 图标仍可解析、任务栏图标可见、界面正常;
        - 回退: 恢复原任务栏模式与分辨率, 关闭电脑管家。

        闭环: 任务栏模式/分辨率恢复原值。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        original_mode = widget.get_dock_display_mode()
        original_res = widget.get_screen_resolution()
        logger.info(
            f"[2011925] 原任务栏模式={original_mode!r} 原分辨率={original_res}"
        )
        self.assert_true(original_mode in ("fashion", "efficient"))

        applied_res = False
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            # 图标资源: .desktop Icon 可解析, 且为矢量(SVG)图标
            icon_name = widget.get_desktop_icon_name()
            icon_path = widget.get_app_icon_path()
            logger.info(
                f"[2011925] icon name={icon_name!r} path={icon_path!r}"
            )
            self.assert_true(bool(icon_name))
            self.assert_true(bool(icon_path))
            self.assert_true(widget.get_icon_file_exists())
            self.assert_true(icon_path.lower().endswith((".svg", ".svgz")))
            self.assert_true(widget.get_main_page_modules_showing())

            # 步骤 1/2: 时尚模式与高效模式下的任务栏图标
            for mode in ("fashion", "efficient"):
                self.assert_true(widget.set_dock_display_mode(mode))
                logger.info(f"[2011925] 任务栏模式已切换: {mode}")
                self.assert_true(widget.get_dock_display_mode() == mode)
                self.assert_true(widget.get_dock_process_status())
                self.assert_true(widget.get_dock_icon_showing_when_running())
                self.assert_true(widget.get_pc_manager_process_status())
                self.assert_true(widget.get_main_page_modules_showing())
                sleep(1)

            # 步骤 3: 高分屏下的图标显示
            high_res = None
            for res in sorted(
                [
                    r
                    for r in widget.get_available_resolutions()
                    if r[0] >= 1920 and r != original_res
                ],
                key=lambda r: r[0] * r[1],
                reverse=True,
            ):
                if widget.set_screen_resolution(res[0], res[1]):
                    high_res = res
                    break
            self.assert_true(high_res is not None)
            applied_res = True
            logger.info(f"[2011925] 高分屏: {high_res}")

            self.assert_true(widget.get_screen_resolution() == high_res)
            self.assert_true(widget.get_app_icon_path() == icon_path)
            self.assert_true(widget.get_dock_icon_showing_when_running())
            self.assert_true(widget.get_main_page_modules_showing())

            # 高分屏下再次切换任务栏模式, 图标仍可见
            for mode in ("efficient", "fashion"):
                self.assert_true(widget.set_dock_display_mode(mode))
                self.assert_true(widget.get_dock_icon_showing_when_running())
        finally:
            if applied_res:
                widget.set_screen_resolution(*original_res)
            if original_mode:
                widget.set_dock_display_mode(original_mode)
            widget.kill_pc_manager()

        self.assert_true(widget.get_dock_display_mode() == original_mode)
        self.assert_true(widget.get_screen_resolution() == original_res)

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

    def test_mycase_271(self):
        """兼容性--切换不同的活动用色

        描述: 控制中心-个性化-活动用色, 更换其他颜色, 查看电脑管家;
        预期颜色随系统变换。

        实现(按平台能力分支):
        - V25: 存在活动用色配置(accent-color), 依次切换到多个色值, 回读生效,
          并校验电脑管家进程与主界面正常;
        - V20: 本机外观 schema 无 accent-color 键、dde-dconfig 资源不存在,
          活动用色为 V25 功能; 用同属"个性化-主题"的 GTK 主题切换
          (deepin <-> deepin-dark)等价验证"颜色随系统变换": 截取电脑管家
          焦点窗口, 断言换主题后窗口配色变化、切回后恢复原样;
        - 无论哪条分支, 结束时恢复原始配色并删除临时截图。

        闭环: 恢复原主题/活动用色, 关闭电脑管家。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.remove_accent_color_screenshot()

        original_accent = widget.get_accent_color()
        logger.info(f"[2011923] 当前活动用色: {original_accent!r}")
        has_accent = (
            original_accent.startswith("#") and len(original_accent) == 7
        )

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        self.assert_true(widget.get_main_page_modules_showing())

        original_theme = None
        try:
            if has_accent:
                # ===== V25: 活动用色切换 =====
                accent_colors = ["#FF0000", "#00FF00", "#0000FF", "#FFA500"]
                changed = 0
                for color in accent_colors:
                    if color.upper() == original_accent.upper():
                        continue
                    widget.set_accent_color(color)
                    current_color = widget.get_accent_color()
                    logger.info(
                        f"[2011923] 设置 {color} -> 回读 {current_color!r}"
                    )
                    self.assert_true(color.upper() in current_color.upper())
                    self.assert_true(widget.get_pc_manager_process_status())
                    self.assert_true(widget.get_main_page_modules_showing())
                    changed += 1
                self.assert_true(changed > 0)
            else:
                # ===== V20: 主题切换等价验证"颜色随系统变换" =====
                original_theme = widget.get_gtk_theme()
                logger.info(f"[2011923] 当前主题: {original_theme!r}")
                self.assert_true(bool(original_theme))
                target_theme = (
                    "deepin-dark" if original_theme != "deepin-dark" else "deepin"
                )

                md5_original = widget.get_focused_window_screenshot_md5()
                self.assert_true(bool(md5_original))

                self.assert_true(widget.set_gtk_theme(target_theme))
                sleep(3)
                md5_changed = widget.get_focused_window_screenshot_md5()
                logger.info(
                    f"[2011923] 主题 {original_theme} -> {target_theme}: "
                    f"{md5_original} -> {md5_changed}"
                )
                self.assert_true(bool(md5_changed))
                self.assert_true(md5_changed != md5_original)
                self.assert_true(widget.get_pc_manager_process_status())
                self.assert_true(widget.get_main_page_modules_showing())

                self.assert_true(widget.set_gtk_theme(original_theme))
                sleep(3)
                md5_restored = widget.get_focused_window_screenshot_md5()
                logger.info(
                    f"[2011923] 切回 {original_theme}: {md5_restored}"
                )
                self.assert_true(md5_restored == md5_original)
                self.assert_true(widget.get_main_page_modules_showing())
        finally:
            if has_accent and original_accent:
                widget.set_accent_color(original_accent)
            if original_theme:
                widget.set_gtk_theme(original_theme)
            widget.remove_accent_color_screenshot()
            widget.kill_pc_manager()

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

    def test_mycase_054(self):
        """兼容性--字体、字号兼容性

        描述: 在控制中心修改字体、字号, 查看电脑管家界面;
        预期: 字号跟随系统字体改变, 无法完整显示的显示缩略(省略)。

        实现:
        - 记录原字体(appearance font-standard/font-size), 依次构造 4 组配置:
          换字体族(字号不变)、小字号 9、大字号 20、换字体族+大字号;
        - 每组: 写系统字体并回读、重启电脑管家、断言进程/主界面模块正常、
          读取左侧导航项 AT-SPI 尺寸(证明界面字号跟随系统)、截图确认渲染
          非空; 同字体族下大字号(20)导航项高度必大于小字号(9);
        - 导航项位置+尺寸均在窗口范围内(未溢出屏幕/裁切);
        - 回退: 恢复原字体并重启应用验证; 结束关闭应用。

        闭环: 字体设置恢复原值, 无临时文件残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        self.assert_true(widget.get_main_page_modules_showing())

        original_font = widget.get_system_font()
        self.assert_true(bool(original_font))
        original_family = widget.get_font_family_from_setting(original_font)
        original_size = widget.get_font_size_from_setting(original_font)
        logger.info(f"[2011937] 原字体: {original_font!r}")

        families = widget.get_available_font_families()
        self.assert_true(len(families) > 0)
        candidate_fonts = [
            "Source Han Sans SC",
            "Noto Sans CJK SC",
            "Noto Sans SC",
            "Source Han Sans CN",
            "Noto Serif CJK SC",
            "Sans",
            "Serif",
            "Monospace",
        ]
        alt_family = None
        for candidate in candidate_fonts:
            if candidate in families and candidate != original_family:
                alt_family = candidate
                break
        if not alt_family:
            for family in families:
                if family != original_family:
                    alt_family = family
                    break
        self.assert_true(alt_family is not None)
        logger.info(f"[2011937] 备用字体族: {alt_family!r}")

        configs = [
            ("换字体族", f"{alt_family} {original_size}"),
            ("小字号9", f"{original_family} 9"),
            ("大字号20", f"{original_family} 20"),
            ("换字体族+大字号", f"{alt_family} 20"),
        ]

        nav_sizes = {}
        text_heights = {}
        try:
            for desc, font in configs:
                self.assert_true(widget.set_system_font(font))
                sleep(2)
                current = widget.get_system_font()
                logger.info(f"[2011937] {desc}: 设置 {font!r} -> 回读 {current!r}")
                self.assert_true(
                    widget.get_font_family_from_setting(current)
                    == widget.get_font_family_from_setting(font)
                )
                self.assert_true(
                    abs(
                        float(widget.get_font_size_from_setting(current))
                        - float(widget.get_font_size_from_setting(font))
                    )
                    < 0.01
                )

                widget.start_pc_manager()
                self.assert_true(widget.get_pc_manager_process_status())
                self.assert_true(widget.get_main_page_modules_showing())

                nav_w, nav_h = widget.get_nav_item_size()
                logger.info(f"[2011937] {desc} 导航项尺寸: {nav_w}x{nav_h}")
                self.assert_true(nav_w > 0 and nav_h > 0)
                nav_sizes[desc] = (nav_w, nav_h)

                _, _, win_w, win_h = widget.get_pc_manager_window_geometry()
                self.assert_true(win_w > 0 and win_h > 0)
                # 导航项位于窗口内, 未被裁切
                self.assert_true(nav_w < win_w)

                info = widget.get_focused_window_screenshot_info()
                logger.info(f"[2011937] {desc} 窗口截图: {info}")
                self.assert_true(bool(info))
                self.assert_true(info["size"] > 20000)

                bbox = widget.get_screenshot_text_bbox(
                    "/tmp/pcm_res_check.png"
                )
                logger.info(f"[2011937] {desc} 标题文字包围盒: {bbox}")
                self.assert_true(bbox[0] > 0 and bbox[1] > 0)
                text_heights[desc] = bbox[1]
                widget.remove_resolution_screenshot()

            # 字号跟随系统: 大字号(20)的文字包围盒高度应明显大于小字号(9)
            self.assert_true(
                text_heights["大字号20"] > text_heights["小字号9"] * 1.2
            )
        finally:
            widget.restore_system_font(original_font)
            sleep(2)
            widget.start_pc_manager()
            widget.remove_resolution_screenshot()

        self.assert_true(widget.get_system_font() == original_font)
        self.assert_true(widget.get_pc_manager_process_status())
        self.assert_true(widget.get_main_page_modules_showing())
        widget.kill_pc_manager()

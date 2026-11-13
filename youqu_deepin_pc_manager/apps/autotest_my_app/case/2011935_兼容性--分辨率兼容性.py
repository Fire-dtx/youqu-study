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

    def test_mycase_227(self):
        """兼容性--分辨率兼容性

        描述: 在控制中心, 在 1366x768 ~ 2560x1600 之间切换分辨率;
        预期: 电脑管家界面显示正常。

        实现:
        - 从当前输出的可用模式中筛选 1366x768~2560x1600 区间(本机虚拟屏无
          1366x768 用最近的 1360x768; 2560x1600 在 VM 上 crtc 配置失败会自动
          跳过), 逐一切换并记录真正生效的模式);
        - 每个分辨率下校验: 切换真正生效、进程存活、主界面模块可见、窗口
          几何在屏幕范围内、窗口渲染截图非空且尺寸合理(界面显示正常);
        - 回退: try/finally 中恢复原始分辨率并校验; 结束关闭电脑管家。

        闭环: 分辨率恢复原值。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        original_res = widget.get_screen_resolution()
        self.assert_true(original_res[0] > 0 and original_res[1] > 0)
        logger.info(f"[2011935] 原始分辨率: {original_res}")

        applied = False
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            resolutions = widget.get_available_resolutions()
            in_range = sorted(
                {
                    (w, h)
                    for (w, h) in resolutions
                    if 1360 <= w <= 2560
                    and 768 <= h <= 1600
                    and (w, h) != original_res
                },
                key=lambda r: r[0] * r[1],
            )
            logger.info(f"[2011935] 区间内可用分辨率: {in_range}")
            self.assert_true(len(in_range) >= 1)

            verified = []
            for res in in_range:
                if not widget.set_screen_resolution(*res):
                    logger.info(f"[2011935] 模式 {res} 本机无法配置, 跳过")
                    continue
                sleep(3)
                if widget.get_screen_resolution() != res:
                    logger.info(f"[2011935] 模式 {res} 未生效, 跳过")
                    continue
                applied = True
                logger.info(f"[2011935] 已切换 {res}")

                self.assert_true(
                    widget.check_ui_displayed_at_resolution(res[0], res[1])
                )
                win_x, win_y, win_w, win_h = widget.get_pc_manager_window_geometry()
                logger.info(
                    f"[2011935] {res} 窗口=({win_x},{win_y},{win_w},{win_h})"
                )
                self.assert_true(win_w > 0 and win_h > 0)
                self.assert_true(win_x + win_w <= res[0] + 2)
                self.assert_true(win_y + win_h <= res[1] + 2)
                # 界面渲染校验: 焦点窗口截图非空且尺寸合理(分辨率切换后
                # AT-SPI 元素树偶发不同步, 以实际渲染结果为准)
                info = widget.get_focused_window_screenshot_info()
                logger.info(f"[2011935] {res} 窗口截图: {info}")
                self.assert_true(bool(info))
                self.assert_true(info["width"] > 400 and info["height"] > 300)
                self.assert_true(info["size"] > 20000)
                widget.remove_resolution_screenshot()
                verified.append(res)

            self.assert_true(len(verified) >= 2)
            logger.info(f"[2011935] 已验证分辨率: {verified}")
        finally:
            if applied:
                widget.set_screen_resolution(*original_res)
                sleep(2)
            widget.kill_pc_manager()

        self.assert_true(widget.get_screen_resolution() == original_res)

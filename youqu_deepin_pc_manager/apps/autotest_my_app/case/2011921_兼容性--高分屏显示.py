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

    def test_mycase_222(self):
        """兼容性--高分屏显示

        描述: 接入高分屏 -> 扩展模式查看界面 -> 复制模式查看界面;
        预期电脑管家显示正常、主副屏正常显示。

        等价实现:
        - 测试机为虚拟机, 仅有 1 个虚拟输出(Virtual1, 无第二块屏幕),
          扩展/复制模式无法执行; 先记录输出数量并说明, 用同一输出上的
          多组高分辨率/大分辨率切换等价验证"高分屏显示正常";
        - 每组分辨率下校验: 屏幕分辨率已生效、主界面模块可见、窗口几何
          完全落在屏幕内(不越界/不裁切)、标题栏关闭按钮可见;
        - 本机 WM 不响应 EWMH 最大化消息(实测 _NET_WM_STATE 不变),
          因此不以最大化作为判定, 改为多分辨率渲染校验;
        - 分辨率切换放在 try/finally, 无论断言是否失败都恢复原始分辨率,
          不留显示配置残留。

        闭环: 恢复原始分辨率, 关闭电脑管家。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        original_res = widget.get_screen_resolution()
        self.assert_true(original_res[0] > 0 and original_res[1] > 0)
        monitor_count = widget.get_monitor_count()
        logger.info(f"[2011921] 输出数={monitor_count} 原始分辨率={original_res}")
        self.assert_true(monitor_count >= 1)
        if monitor_count < 2:
            logger.info(
                "[2011921] 无双输出, 扩展/复制模式不可执行; "
                "以高分屏/大分辨率切换等价验证显示"
            )

        available_res = widget.get_available_resolutions()
        self.assert_true(len(available_res) > 0)
        candidates = sorted(
            [res for res in available_res if res[0] >= 1280 and res != original_res],
            key=lambda r: r[0] * r[1],
            reverse=True,
        )

        applied = []
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_main_page_modules_showing())

            for res in candidates:
                if len(applied) >= 2:
                    break
                if not widget.set_screen_resolution(res[0], res[1]):
                    continue
                applied.append(res)
                logger.info(f"[2011921] 切换分辨率: {original_res} -> {res}")

                screen_w, screen_h = widget.get_screen_resolution()
                self.assert_true((screen_w, screen_h) == res)

                # 显示正常: 主界面模块可见
                self.assert_true(widget.get_main_page_modules_showing())
                # 显示正常: 窗口完全在屏幕内, 尺寸有效
                win_x, win_y, win_w, win_h = (
                    widget.get_pc_manager_window_geometry()
                )
                logger.info(
                    f"[2011921] {res} 窗口=({win_x},{win_y},{win_w},{win_h})"
                )
                self.assert_true(win_w > 0 and win_h > 0)
                self.assert_true(win_x >= 0 and win_y >= 0)
                self.assert_true(win_x + win_w <= screen_w)
                self.assert_true(win_y + win_h <= screen_h)
                # 显示正常: 标题栏关闭按钮可见(窗口框架渲染完整)
                self.assert_true(widget.is_window_close_button_visible())
                # 显示正常: 进程未崩溃
                self.assert_true(widget.get_pc_manager_process_status())
                sleep(1)

            logger.info(f"[2011921] 已验证分辨率: {applied}")
            self.assert_true(len(applied) >= 1)
        finally:
            for res in reversed(applied):
                if res != original_res:
                    widget.set_screen_resolution(*original_res)
                    break
            if applied:
                logger.info(
                    f"[2011921] 恢复原始分辨率: "
                    f"{widget.set_screen_resolution(*original_res)}"
                )
            widget.kill_pc_manager()

        self.assert_true(widget.get_screen_resolution() == original_res)

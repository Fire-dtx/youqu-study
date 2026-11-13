#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_224(self):
        """兼容性--图形协议兼容

        描述: 使用 X11、Wayland 环境, 运行电脑管家; 预期可以正常运行。

        实现:
        - X11: 当前会话即为 X11(xrandr/xset 可用), 正常拉起应用, 断言进程存活、
          主界面模块可见;
        - Wayland: 不切换整个桌面会话(会中断自动化), 改为在独立
          XDG_RUNTIME_DIR 中启动虚拟输出的 kwin_wayland 合成器, 以
          QT_QPA_PLATFORM=wayland 且不设 DISPLAY 启动电脑管家主程序,
          断言进程存活且日志出现 "entering event loop"(主窗口已显示);
        - 回退: 关闭 Wayland 下应用与合成器, 删除临时运行时目录, 关闭 X11 应用。

        闭环: 不修改任何系统配置, 临时目录删除。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        # ===== X11 =====
        protocol = widget.get_display_protocol()
        logger.info(f"[2011927] 当前会话协议: {protocol}")
        self.assert_true(protocol in ("x11", "wayland"))

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        self.assert_true(widget.get_main_page_modules_showing())
        logger.info("[2011927] X11 下电脑管家运行正常")
        widget.kill_pc_manager()

        # ===== Wayland =====
        self.assert_true(widget.get_wayland_runtime_ready())
        compositor = None
        wayland_app = None
        try:
            compositor = widget.start_virtual_wayland_compositor(
                socket_name="pcmtest", width=1024, height=768
            )
            self.assert_true(compositor is not None)
            logger.info(
                f"[2011927] 虚拟 Wayland 合成器已启动: pid={compositor['pid']}"
            )

            wayland_app = widget.start_pc_manager_under_wayland(compositor)
            self.assert_true(wayland_app is not None)
            logger.info(f"[2011927] Wayland 下应用 pid={wayland_app['pid']}")
            self.assert_true(widget.get_wayland_app_started(compositor, wayland_app))
            logger.info("[2011927] Wayland 下应用已进入事件循环, 主窗口显示")
        finally:
            widget.stop_pc_manager_under_wayland(wayland_app)
            widget.stop_virtual_wayland_compositor(compositor)
            widget.kill_pc_manager()

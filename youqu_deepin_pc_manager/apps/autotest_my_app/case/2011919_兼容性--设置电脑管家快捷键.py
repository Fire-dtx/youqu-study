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

    def test_mycase_221(self):
        """兼容性--设置电脑管家快捷键

        描述:
        1. 控制中心-键盘与语言-快捷键, 点击添加
        2. 名称: 电脑管家, 命令: deepin-pc-manager, 快捷键: ctrl+m, 点击保存
        3. 使用快捷键 ctrl+m
        预期: 添加界面 -> 创建成功 -> 打开电脑管家界面

        等价实现:
        - 控制中心"添加快捷键"最终调用 dde-daemon 的
          com.deepin.daemon.Keybinding.AddCustomShortcut(name, exec, accel),
          用例直接走同一 D-Bus 接口(accel 用 X 键盘格式 "<Control>m");
        - 描述命令 "deepin-pc-manager" 在本版本不在 PATH 中, 桌面文件 Exec 为
          deepin-pc-manager-launch, 因此命令取该启动器;
        - "使用快捷键"用 xdotool XTEST 发送 ctrl+m, 验证电脑管家进程启动、
          界面模块显示;
        - 回退: 只删除本次新增的快捷键(先查列表再删; 对不存在的 Id 调
          DeleteCustomShortcut 会让 dde-session-daemon 异常), 结束后校验
          ctrl+m 键位已释放、电脑管家已退出。
        """
        widget = MyAppWidget(check_start=False)
        shortcut_name = "电脑管家"
        shortcut_command = "deepin-pc-manager-launch"
        shortcut_accel = "<Control>m"

        widget.kill_pc_manager()
        self.assert_false(widget.get_pc_manager_process_status())

        # 前置: 释放可能被历史数据占用的同名/同键位自定义快捷键
        for stale in (
            widget.get_custom_keybinding(shortcut_name),
            widget.get_custom_keybinding_by_accel(shortcut_accel),
        ):
            if stale:
                logger.info(f"[2011919] 清理历史快捷键: {stale}")
                widget.delete_custom_keybinding(stale["Id"])
                sleep(2)
        self.assert_true(widget.get_custom_keybinding_by_accel(shortcut_accel) is None)

        shortcut_id = None
        try:
            # 步骤 2: 添加自定义快捷键(创建成功), 键位释放有延迟时重试
            raw = ""
            for attempt in range(1, 4):
                shortcut_id, flags, raw = widget.add_custom_keybinding(
                    shortcut_name, shortcut_command, shortcut_accel
                )
                logger.info(
                    f"[2011919] AddCustomShortcut 第 {attempt} 次: "
                    f"id={shortcut_id} flags={flags} raw={raw!r}"
                )
                if shortcut_id:
                    break
                sleep(3)
            self.assert_true(bool(shortcut_id))

            created = widget.get_custom_keybinding(shortcut_name)
            logger.info(f"[2011919] 列表回读: {created}")
            self.assert_true(created is not None)
            self.assert_true(created["Id"] == shortcut_id)
            self.assert_true(created["Exec"] == shortcut_command)
            self.assert_true(shortcut_accel in created["Accels"])

            # 步骤 3: 使用快捷键 ctrl+m 打开电脑管家
            self.assert_true(widget.press_key_combo("ctrl+m"))
            started = False
            for _ in range(30):
                if widget.get_pc_manager_process_status():
                    started = True
                    break
                sleep(1)
            self.assert_true(started)

            self.assert_true(widget.reconnect_dogtail())
            self.assert_true(widget.get_main_page_modules_showing())
            logger.info("[2011919] ctrl+m 已拉起电脑管家主界面")
        finally:
            if shortcut_id and widget.get_custom_keybinding_by_accel(shortcut_accel):
                widget.delete_custom_keybinding(shortcut_id)
            widget.kill_pc_manager()
            self.assert_true(
                widget.get_custom_keybinding_by_accel(shortcut_accel) is None
            )
            self.assert_false(widget.get_pc_manager_process_status())

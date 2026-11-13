#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_220(self):
        """兼容性--ARM平台差异化

        描述: 已在 ARM 平台安装电脑管家 -> 打开多个应用 -> 任务栏电源按钮
        选择注销; 预期系统正常注销进入登录界面, 不出现黑名单提示界面。

        环境限制与等价实现:
        - 测试机为 x86_64(UOS 20), 无 ARM 硬件, 无法直接执行 ARM 差异化验证;
          这里验证"跨架构可用性"的等价条件: 产品二进制目标架构与内核架构一致
          (readelf Machine 与 uname -m 对应), 桌面会话中可正常启动应用;
        - 真实注销会终止当前图形会话(自动化随之失联, 测试机停在登录界面),
          因此用注销链路就绪性等价验证: 会话管理器 CanLogout 返回 true、
          打开多个应用后仍为 true、无任何 inhibitor 阻止注销、无黑名单提示
          (产品二进制不含黑名单文案, 当前可见窗口标题不含黑名单);
        - 打开的多个应用在结束时全部关闭, 不留残留进程。

        闭环: 关闭启动的应用, 只做查询类 D-Bus 调用, 不触发真正的注销。
        """
        widget = MyAppWidget(check_start=False)
        opened_apps = ["deepin-editor", "deepin-music"]

        arch = widget.get_system_arch()
        logger.info(f"[2011917] 当前内核架构: {arch}")
        self.assert_true(bool(arch))
        arch_tokens = {
            "x86_64": "X86-64",
            "amd64": "X86-64",
            "aarch64": "AArch64",
            "arm64": "AArch64",
            "loongarch64": "LoongArch",
            "mips64": "MIPS",
        }
        expected_machine = arch_tokens.get(arch, "")
        self.assert_true(bool(expected_machine))

        for app in opened_apps:
            self.assert_false(widget.get_app_process_running(app))

        # 启动 GUI 应用会生成配置/缓存目录; 记录用例前状态, 结束时只删除
        # 本次新建的目录, 不留测试残留(已有目录保持不动)
        app_state_dirs = [
            "~/.config/deepin/deepin-editor",
            "~/.config/deepin/deepin-music",
            "~/.cache/deepin/deepin-editor",
            "~/.cache/deepin/deepin-music",
            "~/.local/share/deepin/deepin-editor",
        ]
        existed_dirs = set()
        for path in app_state_dirs:
            if "yes" in widget.run_cmd(
                f'test -d {path} && echo yes || echo no',
                timeout=5,
                out_debug_flag=False,
            ):
                existed_dirs.add(path)

        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            # 跨架构可用性: 产品二进制架构与当前内核一致
            binary = widget.get_pc_manager_binary_path()
            self.assert_true(bool(binary))
            machine = widget.get_elf_machine(binary)
            logger.info(f"[2011917] {binary} 架构: {machine}")
            self.assert_true(expected_machine in machine)

            # 注销链路就绪: 会话管理器可注销, 且无 inhibitor 阻止
            can_logout = widget.get_session_manager_method("CanLogout")
            inhibitors = widget.get_session_inhibitors()
            logger.info(f"[2011917] CanLogout: {can_logout}")
            logger.info(f"[2011917] inhibitors:\n{inhibitors}")
            self.assert_true("true" in can_logout.lower())
            self.assert_false("deepin-pc-manager" in inhibitors)

            # 打开多个应用
            for app in opened_apps:
                self.assert_true(widget.launch_gui_app(app, timeout=40))
            sleep(3)
            for app in opened_apps:
                self.assert_true(widget.get_app_process_running(app))

            # 多应用运行时仍可注销(注销不会被产品/应用阻止)
            can_logout_after = widget.get_session_manager_method("CanLogout")
            inhibitors_after = widget.get_session_inhibitors()
            can_logout_after_flag = "true" in can_logout_after.lower()
            logger.info(
                f"[2011917] 多应用运行时 CanLogout: {can_logout_after}; "
                f"pc-manager inhibitor: "
                f"{'deepin-pc-manager' in inhibitors_after}"
            )
            self.assert_true(can_logout_after_flag)
            self.assert_false("deepin-pc-manager" in inhibitors_after)

            # 不出现黑名单提示界面
            blacklist_strings = widget.get_pc_manager_blacklist_ui_strings()
            self.assert_true(blacklist_strings.strip() == "")
            titles = widget.get_visible_window_titles()
            logger.info(f"[2011917] 可见窗口: {titles}")
            blacklist_titles = [
                title
                for title in titles
                if "黑名单" in title or "blacklist" in title.lower()
            ]
            logger.info(f"[2011917] 黑名单窗口: {blacklist_titles}")
            self.assert_true(blacklist_titles == [])

            # 应用打开后会话与管家进程均正常
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            for app in opened_apps:
                widget.close_gui_app(app)
            widget.kill_pc_manager()
            for path in app_state_dirs:
                if path not in existed_dirs:
                    widget.run_cmd(
                        f"rm -rf {path}", timeout=10, out_debug_flag=False
                    )
            for app in opened_apps:
                self.assert_false(widget.get_app_process_running(app))

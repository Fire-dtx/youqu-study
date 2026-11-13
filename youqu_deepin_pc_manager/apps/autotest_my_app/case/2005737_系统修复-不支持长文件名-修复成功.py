#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    CASE_ID = "2005737"
    CONFIRM_TITLE = "长文件名修复"
    CARD_KEYWORD = "长文件名"
    DLNFS_WARNING = "当前版本目录支持范围有限"
    ENABLED_TEXT = "长文件名功能已开启，重启电脑后生效"
    CANCEL_TEXT = "用户选择稍后手动重启"

    def _log(self, message):
        print(f"[{self.CASE_ID}] {message}")

    def _find_long_filename_card(self, widget):
        """在修复工具列表中找到"长文件名支持修复"卡片(允许列表异步渲染)"""
        for _ in range(12):
            names = []
            try:
                names = widget.get_repair_visible_card_names()
            except BaseException:
                names = []
            if not names:
                try:
                    names = widget.get_repair_card_names()
                except BaseException:
                    names = []
            hits = [name for name in names if self.CARD_KEYWORD in name]
            if hits:
                return hits[0]
            sleep(1)
        return ""

    def _wait_output(self, widget, keywords, timeout=120):
        """轮询修复输出, 命中任一关键词时返回该关键词"""
        for _ in range(timeout):
            text = widget.get_repair_output_text()
            for keyword in keywords:
                if keyword in text:
                    return keyword
            sleep(1)
        return ""

    def _handle_repair_dialog(self, widget):
        """等待并处理脚本的确认框/信息框

        本脚本成功开启长文件名后会调用 dpmapi openconfirm("长文件名修复",
        "重启生效，是否现在重启"); 点【确认】会立刻 reboot, 因此必须点
        【取消】。若走到"已处于开启状态/失败"分支, 产品弹的是只有【确定】
        的信息框, 这里也一并识别。
        :return: ("confirm"|"info"|"none", 弹框状态字典)
        """
        for _ in range(60):
            state = widget.get_confirm_dialog_state(self.CONFIRM_TITLE, timeout=1)
            if state.get("showing"):
                return "confirm", state
            info = widget.get_info_dialog_state(self.CONFIRM_TITLE, timeout=1)
            if info.get("exists") and info.get("showing"):
                return "info", info
            text = widget.get_repair_output_text()
            if any(
                marker in text
                for marker in ("[ERROR]", "修复失败", "Repair failed")
            ):
                return "none", {}
            if any(
                marker in text
                for marker in ("修复完成", "Repair complete")
            ):
                return "none", {}
            sleep(1)
        return "none", {}

    def test_mycase_150(self):
        """系统修复-不支持长文件名-修复成功

        用例描述: 1074 之前的 V20 默认只支持"桌面/视频/音乐/图片/文档/下载/
        回收站"目录的长文件名, 不支持配置的扩展目录; 运行修复脚本后创建
        255 个中文 / 255 个字符的文件名应成功。

        产品依据(deepin-pc-manager 1.1.7, plugins/plugin-long-filename/entry.sh):
        - V20 有效版本 = MinorVersion + (OsBuild 第二段 - 100);
          1063~1073 走 dlnfs 方案(dfm.mount.dlnfs), >=1074 走 ulnfs 方案
          (dfm.mount.ulnfs, 缺包时先 apt install ulnfs); 两者都只写
          dde-dconfig, 提示"重启电脑后生效"并弹确认框询问是否立即重启;
        - 用例按测试机真实版本选择方案, 不修改 /etc/os-version。若测试机已是
          1074+, 描述中"仅默认目录支持"的差异由 dlnfs 专属告警
          "当前版本目录支持范围有限"等价覆盖, 修复目标(长文件名可用)一致;
        - 配置生效依赖登录时的官方自动挂载脚本, 用例用同一脚本 / 同一
          MountControl 接口等效应用, 不重启系统。

        步骤与断言:
        1. 前置: 关闭长文件名开关并卸载验证目录(构造"不支持长文件名"), 先在
           ~/Documents 创建 255 个中文(765 字节)文件名, 断言失败;
        2. 电脑管家 -> 修复工具 -> 长文件名支持修复 -> 开始修复;
        3. 断言输出出现本机方案、开启成功、无 [ERROR]/失败文案;
        4. 断言弹出"长文件名修复"确认框并点【取消】(禁止 reboot), 输出出现
           "用户选择稍后手动重启", 脚本以"修复完成"收尾;
        5. 断言 dde-dconfig 开关变为 true(修复的真实系统效果);
        6. 用官方自动挂载等效生效后, 创建 '哈'*255 与 'a'*255 均成功;
        7. 回退: 删除文件、卸载本次挂载、恢复开关与原有挂载状态, 退出管家。
        """
        widget = MyAppWidget(check_start=False)
        branch = widget.get_long_filename_branch()
        self._log(f"/etc/os-version: {branch['fields']}")
        self._log(
            f"方案={branch['branch']} 有效版本={branch['effective_version']} "
            f"fs={branch['fs_type']} key={branch['config_app']}/"
            f"{branch['config_key']}"
        )
        assert branch["branch"] in ("dlnfs", "ulnfs", "v25pro"), (
            f"本机 /etc/os-version 不满足长文件名修复场景: {branch['fields']}"
        )

        target_dir = widget.get_long_filename_probe_dir(branch)
        default_dirs = widget.get_long_filename_default_dirs(branch)
        self._log(f"验证目录={target_dir} 默认目录={default_dirs}")
        assert os.path.isdir(target_dir)

        config_app = branch["config_app"]
        config_key = branch["config_key"]
        config_dashes = branch["config_use_dashes"]
        fs_type = branch["fs_type"]
        original_config = widget.get_long_filename_config_value(branch)
        self._log(f"修复前开关 {config_key}={original_config!r}")
        assert original_config in ("true", "false"), (
            f"无法读取长文件名开关 {config_app}/{config_key}"
        )
        original_mount_points = widget.get_long_filename_mount_points(
            default_dirs + [target_dir], fs_type
        )
        boot_before = widget.run_cmd(
            "uptime -s", timeout=5, out_debug_flag=False
        ).strip()

        created_files = []
        mounted_by_case = []
        try:
            # 自愈: 清理上次执行可能遗留的弹框
            widget.close_confirm_dialogs(self.CONFIRM_TITLE)
            widget.close_info_dialogs(self.CONFIRM_TITLE)

            # 前置: 长文件名组件已安装(缺包时产品脚本会 apt 安装, 需要网络)
            if branch["branch"] == "ulnfs":
                assert widget.is_package_installed("ulnfs"), "ulnfs 包未安装"
            if fs_type == "dlnfs":
                dlnfs_path = widget.run_cmd(
                    "command -v dlnfs", timeout=5, out_debug_flag=False
                ).strip()
                assert dlnfs_path, "dlnfs 命令不存在"

            # 构造"不支持长文件名"的初始状态
            assert widget.set_dde_config(
                config_app, config_key, "false", config_dashes
            ), f"关闭 {config_key} 失败"
            assert widget.wait_long_filename_config(
                branch, "false", timeout=15
            ), f"{config_key} 未变为 false"
            for path in original_mount_points:
                self._log(f"卸载前置挂载 {path}")
                widget.unmount_long_filename_fs(path, fs_type)
            still_mounted = widget.get_long_filename_mount_points(
                default_dirs + [target_dir], fs_type
            )
            if still_mounted:
                self._log(
                    f"环境已启用长文件名且卸载失败, 跳过负向断言: {still_mounted}"
                )
            else:
                pre_supported = widget.long_filename_create_supported(target_dir)
                self._log(f"修复前长文件名创建: {pre_supported}")
                assert not pre_supported, (
                    "修复前已能创建 255 个中文的文件名, 前置状态不成立"
                )

            # 步骤1: 打开电脑管家 -> 修复工具
            widget.clear_sudo_credentials()
            widget.start_pc_manager()
            assert widget.get_pc_manager_process_status()
            widget.click_repair_nav()
            assert widget.get_repair_page_showing()
            if widget.get_offline_filter_switch_checked():
                widget.click_offline_filter_switch()
                assert not widget.get_offline_filter_switch_checked()

            card_name = self._find_long_filename_card(widget)
            self._log(f"修复卡片={card_name!r}")
            assert card_name, "修复工具列表中没有长文件名支持修复卡片"
            widget.click_repair_card_by_name(card_name)
            assert widget.get_repair_detail_showing()
            widget.click_repair_start_button()
            assert widget.get_repair_dialog_showing(timeout=20)

            password_submitted = False
            for _ in range(30):
                if widget.is_shell_repair_input_enabled():
                    widget.handle_shell_repair_dialog()
                    password_submitted = True
                    break
                if widget.get_repair_output_text().strip():
                    break
                sleep(1)
            self._log(f"是否提交提权密码={password_submitted}")

            opened = self._wait_output(
                widget,
                (
                    f"使用 {branch['scheme']} 方案开启长文件名",
                    "长文件名功能已处于开启状态",
                ),
                timeout=120,
            )
            self._log(f"方案输出命中={opened!r}")
            assert opened, "修复脚本未输出长文件名开启方案"

            dialog_kind, dialog_state = self._handle_repair_dialog(widget)
            self._log(f"弹框类型={dialog_kind} 状态={dialog_state}")
            assert dialog_kind != "none", (
                "修复未弹出重启确认框/信息框, 当前输出: "
                f"{widget.get_repair_output_text()[-1200:]!r}"
            )
            if dialog_kind == "confirm":
                buttons = dialog_state.get("buttons", [])
                assert "取消" in buttons, f"确认框按钮异常: {buttons}"
                assert widget.click_confirm_dialog_button(
                    self.CONFIRM_TITLE, "取消", timeout=15
                ), "点击确认框【取消】失败"
                assert widget.wait_confirm_dialog_closed(
                    self.CONFIRM_TITLE, timeout=15
                ), "确认框未关闭"
                assert widget.get_repair_output_contains(
                    self.CANCEL_TEXT, timeout=60
                ), "未看到取消重启后的'用户选择稍后手动重启'"
            else:
                assert widget.click_confirm_dialog_button(
                    self.CONFIRM_TITLE, widget.INFOBOX_OK_TEXT, timeout=15
                ), "点击信息框【确定】失败"
                assert widget.wait_info_dialog_closed(
                    self.CONFIRM_TITLE, timeout=15
                ), "信息框未关闭"
                info_text = widget.get_repair_output_text()
                assert "设置长文件名失败" not in info_text, (
                    f"产品报告设置长文件名失败: {info_text[-800:]!r}"
                )
                assert "ulnfs 包安装失败" not in info_text, (
                    f"产品报告 ulnfs 包安装失败: {info_text[-800:]!r}"
                )

            completion = self._wait_output(
                widget, ("修复完成", "Repair complete"), timeout=60
            )
            assert completion, "修复脚本未以成功状态结束"
            output = widget.get_repair_output_text()
            self._log(f"修复输出尾部={output[-1500:]!r}")

            # 预期1: 脚本执行无报错, 且命中本机方案
            assert "[ERROR]" not in output, "修复输出包含 [ERROR]"
            assert "设置长文件名失败" not in output
            assert "ulnfs 包安装失败" not in output
            assert "Repair failed" not in output and "修复失败" not in output
            assert f"使用 {branch['scheme']} 方案开启长文件名" in output
            assert self.ENABLED_TEXT in output, "未出现开启成功提示"
            func_name = (
                "enable_v25_pro"
                if branch["branch"] == "v25pro"
                else "enable_v20_long_filename"
            )
            assert f"{func_name} 返回值: 2" in output
            if branch["scheme"] == "dlnfs":
                assert self.DLNFS_WARNING in output, "未出现 dlnfs 目录范围告警"

            # 预期: 开关已真实打开
            assert widget.wait_long_filename_config(
                branch, "true", timeout=20
            ), f"{config_key} 未变为 true"
            assert widget.get_long_filename_config_value(branch) == "true"
            assert widget.get_pc_manager_process_status()
            boot_after = widget.run_cmd(
                "uptime -s", timeout=5, out_debug_flag=False
            ).strip()
            assert boot_after == boot_before, "系统发生了重启"

            # 等效应用: 官方登录自动挂载脚本(无需真重启)
            mounted_before_apply = widget.get_long_filename_mount_points(
                default_dirs + [target_dir], fs_type
            )
            applied = widget.apply_long_filename_mounts(branch, target_dir)
            mounted_by_case = [
                path for path in applied if path not in mounted_before_apply
            ]
            self._log(f"本次挂载={mounted_by_case} 当前挂载={applied}")
            assert widget.wait_long_filename_mounted(
                target_dir, fs_type, timeout=60
            ), f"{target_dir} 未进入 {fs_type} 挂载"

            # 步骤2/3: 创建 255 个中文与 255 个 a 的文件名
            ok_zh, path_zh, err_zh = widget.create_long_filename_file(
                target_dir, "哈", 255
            )
            if ok_zh:
                created_files.append(path_zh)
            ok_ascii, path_ascii, err_ascii = widget.create_long_filename_file(
                target_dir, "a", 255
            )
            if ok_ascii:
                created_files.append(path_ascii)
            self._log(
                f"中文名={ok_zh} err={err_zh} "
                f"ascii名={ok_ascii} err={err_ascii}"
            )
            assert ok_zh, f"255 个中文文件名创建失败: {err_zh}"
            assert ok_ascii, f"255 个 a 文件名创建失败: {err_ascii}"
            assert os.path.basename(path_zh) == "哈" * 255
            assert len(os.path.basename(path_zh).encode("utf-8")) == 765
            assert os.path.basename(path_ascii) == "a" * 255
            assert len(os.path.basename(path_ascii)) == 255
            assert os.path.getsize(path_zh) == 0
            assert os.path.getsize(path_ascii) == 0
            assert os.path.exists(path_zh) and os.path.exists(path_ascii)
            assert widget.get_pc_manager_process_status()
        finally:
            # 回退1: 删除挂载视图内的长文件名文件
            for path in created_files:
                widget.remove_long_filename_file(path)
            widget.remove_long_filename_file(os.path.join(target_dir, "哈" * 255))
            widget.remove_long_filename_file(os.path.join(target_dir, "a" * 255))

            # 回退2: 关闭弹框/修复窗口并退出电脑管家
            widget.close_confirm_dialogs(self.CONFIRM_TITLE)
            widget.close_info_dialogs(self.CONFIRM_TITLE)
            widget.close_repair_completion_dialog()
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

            # 回退3: 卸载本用例新挂载的目录
            for path in mounted_by_case:
                self._log(f"回退卸载 {path}")
                widget.unmount_long_filename_fs(path, fs_type)

            # 回退4: 恢复长文件名开关原值
            if original_config in ("true", "false"):
                widget.set_dde_config(
                    config_app, config_key, original_config, config_dashes
                )
                widget.wait_long_filename_config(
                    branch, original_config, timeout=15
                )

            # 回退5: 恢复前置阶段被卸载的原有挂载
            for path in original_mount_points:
                if not widget.is_path_long_filename_mount_point(path, fs_type):
                    self._log(f"恢复原挂载 {path}")
                    widget.mount_long_filename_fs(path, fs_type)

            widget.clear_sudo_credentials()
            self._log(
                f"结束时开关={widget.get_long_filename_config_value(branch)!r} "
                f"挂载点="
                f"{widget.get_long_filename_mount_points(default_dirs + [target_dir], fs_type)}"
            )
            sleep(1)

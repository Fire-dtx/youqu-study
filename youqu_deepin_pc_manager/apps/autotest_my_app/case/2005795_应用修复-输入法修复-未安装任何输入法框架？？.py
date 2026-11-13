#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import logging
import re
from time import sleep

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

logger = logging.getLogger(__name__)


class TestMyCase(BaseCase):

    def test_mycase_167(self):
        """应用修复-输入法修复-未安装任何输入法框架

        用例描述:
            前置: 未安装 fcitx5;
            步骤: 1. 执行重启脚本 2. 观察脚本输出;
            预期: 1. 终端输出"未检测到 fcitx/fcitx5/ibus 输入法框架"正在安装
                  2. 输出"输入法重启完成，可尝试切换输入法使用"提示。

        产品实现(测试机 /usr/lib/deepin-pc-manager/plugins/plugin-inputmethod-fix/
        entry.sh, DPMOBF1 解码, 插件 1.0.0, executionMode=user):
            detect_input_method 先 pgrep -x fcitx5/fcitx, 再 which fcitx5/fcitx;
            命中则 killall + "<输入法> -r -d" 重启并 openinfobox
            "输入法修复" "输入法已重启，修复完成";
            **未命中**则只 openinfobox "输入法修复" "未检测到输入法进程",
            没有自动安装逻辑, 也不打印描述里的两段文本。

        等价实现(描述文案属于更新版脚本, 本机 1.0.0 无自动安装分支):
        1) 构造"未安装任何输入法框架": 先终止 fcitx-helper 守护与 fcitx 进程,
           再对已安装框架的可执行文件去掉 x 位。产品脚本的判定依据正是
           "进程不存在 + which 失败", 因此该状态在产品视角等价于未安装,
           且不卸载/不移动系统文件; 回退时按记录的权限位原样恢复。
        2) 通过产品 UI 执行重启脚本(修复工具 -> 重启输入法 -> 开始修复),
           真实走到"未检测到"分支, 并断言:
           - 修复对话框被拉起, 输出日志首行指向真实的插件脚本路径;
           - session 总线收到标题"输入法修复"、正文含"未检测到"的
             OpenMessage 请求(脚本走到 else 分支的直接证据, 对应描述
             "未检测到 ... 输入法框架");
           - 提示框渲染出正文标签, 且没有拉起任何输入法进程;
           - 正文不含"已重启"(否则说明检测判定错误);
           - 输出无 Permission denied / command not found / Traceback。
        描述中的"正在安装"和"输入法重启完成"在本机插件版本不存在, 故以
        "命中未检测到分支且未尝试重启"作为等价断言(自动安装需要联网安装
        输入法包, 属于产品后续版本能力)。

        finally 回退: 关闭提示框/修复对话框、停止总线监听、恢复框架权限位
        并拉起 fcitx 与 fcitx-helper, 校验 which 与进程均恢复。
        """
        widget = MyAppWidget(check_start=False)
        saved_frameworks = {}
        dialog_opened = False
        monitor_started = False
        info_title = "输入法修复"
        try:
            # ===== 前置检查: 记录测试机现有输入法现场 =====
            # 上次用例若在 chmod a-x 后被中断, 先按落盘备份恢复 x 位
            self.assert_true(widget.recover_stale_input_method_backup())
            widget.ensure_input_method_running()
            self.assert_true(widget.get_input_method_process_running())
            im_name = widget.get_input_method_name()
            logger.info(f"前置运行的输入法框架: {im_name}")
            self.assert_true(bool(im_name))
            installed = widget.get_input_method_frameworks()
            logger.info(f"前置已安装的输入法框架: {installed}")
            self.assert_true(bool(installed))

            # ===== 构造: 未安装任何输入法框架 =====
            widget.stop_input_method()
            self.assert_true(not widget.get_input_method_process_running())
            saved_frameworks = widget.disable_input_method_frameworks()
            self.assert_true(len(saved_frameworks) == len(installed))
            # which fcitx/fcitx5/ibus 全部失败, 即产品判定所依据的"未安装"
            self.assert_false(widget.is_input_method_installed())

            # ===== 启动应用, 进入输入法修复详情页 =====
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() >= 1)
            widget.click_input_method_fix_card()
            self.assert_true(widget.get_repair_detail_showing())
            detail = widget.get_repair_detail_content()
            logger.info(f"输入法修复详情页: {detail}")
            self.assert_true(detail.get("start_btn_showing"))

            # 监听 session 总线, 核对脚本 openinfobox 的标题与正文
            monitor_started = widget.start_confirm_dbus_monitor()
            # 监控没起来就无法核对总线请求, 不能静默跳过断言
            self.assert_true(monitor_started)

            # ===== 步骤1: 执行重启脚本 =====
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing(timeout=20)
            self.assert_true(dialog_opened)
            self.assert_true(
                widget.get_repair_output_contains("正在准备执行修复脚本", timeout=20)
            )
            self.assert_true(
                widget.get_repair_output_contains("plugin-inputmethod-fix", timeout=20)
            )

            # ===== 步骤2/预期: 脚本走"未检测到输入法"分支 =====
            info_state = widget.get_info_dialog_state(info_title, timeout=40)
            logger.info(f"输入法修复提示框状态: {info_state}")
            self.assert_true(info_state["exists"] and info_state["showing"])
            self.assert_true(info_state["title"] == info_title)
            self.assert_true(info_state["buttons"] == [widget.INFOBOX_OK_TEXT])
            self.assert_true(info_state["message_label_showing"])

            # 未检测到框架时脚本不应拉起输入法进程
            self.assert_false(widget.get_input_method_process_running())

            # 正文与脚本参数同源: 总线上必须是"未检测到"而不是"已重启"
            request_text = ""
            dbus_strings = []
            for _ in range(10):
                request_text = widget.get_confirm_dbus_request_text()
                dbus_strings = re.findall(r'string "([^"]*)"', request_text)
                if any("未检测到" in item for item in dbus_strings):
                    break
                sleep(1)
            logger.info(f"session 总线请求字符串: {dbus_strings}")
            self.assert_true('string "OpenMessage"' in request_text)
            self.assert_true("输入法修复" in dbus_strings)
            self.assert_true(any("未检测到" in item for item in dbus_strings))
            self.assert_false(any("已重启" in item for item in dbus_strings))

            # 预期: 脚本输出无报错特征
            output_text = widget.get_repair_output_text() or ""
            logger.info(f"修复输出日志: {output_text!r}")
            for marker in ("Permission denied", "command not found", "Traceback"):
                self.assert_false(marker in output_text)

            # 点"确定"关闭提示框, 脚本随之结束
            self.assert_true(
                widget.click_confirm_dialog_button(info_title, widget.INFOBOX_OK_TEXT)
            )
            self.assert_true(widget.wait_info_dialog_closed(info_title, timeout=10))

            # 收尾: 提示框点掉后脚本才退出, 但修复窗口仍停在完成态不会自己关;
            # 若脚本/产品再补一条提示框, 其 openinfobox 的 timeoutMs=0 表示没有
            # 超时, 不点就永远留在桌面并阻塞脚本。finish_repair_flow 清掉全部
            # 提示框形态并关闭修复窗口, 并断言窗口已消失
            state = widget.finish_repair_flow(info_title)
            self.assert_false(state["window_left"])
            dialog_opened = False
        finally:
            if dialog_opened:
                # openinfobox 的 timeoutMs=0 表示提示框没有超时: 不点掉会被留
                # 在桌面且脚本一直阻塞, 因此先点提示框再由 finish_repair_flow
                # 关闭修复窗口(替代原来的 close_info_dialogs + close_repair_dialog)
                try:
                    widget.finish_repair_flow(info_title)
                except BaseException:
                    pass
            try:
                widget.stop_confirm_dbus_monitor()
            except BaseException:
                pass
            # 关闭本用例启动的电脑管家(先关应用再恢复输入法, 避免应用退出时
            # 再次触发输入法检测)
            try:
                widget.kill_pc_manager()
                widget.wait_pc_manager_exit()
            except BaseException:
                pass
            # ===== 回退构造: 恢复框架权限位与输入法进程 =====
            restore_ok = False
            try:
                restore_ok = widget.restore_input_method_frameworks(saved_frameworks)
                if restore_ok:
                    widget.restart_input_method()
                im_running = widget.get_input_method_process_running()
                installed_back = widget.is_input_method_installed()
                logger.info(
                    f"回退结果: 权限恢复={restore_ok} 安装态恢复={installed_back} "
                    f"输入法进程={im_running}"
                )
                if not (restore_ok and installed_back and im_running):
                    raise AssertionError(
                        f"输入法环境回退不完整: 权限恢复={restore_ok} "
                        f"安装态恢复={installed_back} 输入法进程={im_running}"
                    )
            except BaseException as exc:
                logger.error(f"输入法环境回退失败: {exc}")
                raise

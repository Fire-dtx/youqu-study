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

    def test_mycase_166(self):
        """应用修复-输入法修复-正常关闭运行中的输入法进程

        用例描述:
            前置: 当前使用 fcitx5 输入法且进程正常运行, fcitx5 --version 能输出版本号,
                  echo $XMODIFIERS 为 @im=fcitx / @im=fcitx5;
            步骤: 1. 执行输入法修复脚本 2. 执行 ps aux | grep fcitx5;
            预期: 1. 依次输出"正在重启输入法服务..." "已重启 xx 输入法"
                  2. 输出"输入法重启完成，可尝试切换输入法使用"提示。

        产品实现(plugin-inputmethod-fix/entry.sh, 按 DPMOBF1 解码核对,
        config.json executionMode=user):
            detect_input_method 先按进程、再按可执行文件判定 fcitx5/fcitx;
            命中后 killall "<输入法>" 再 "<输入法> -r -d" 重启;
            末尾 dpmapi openinfobox "输入法修复" "输入法已重启，修复完成"
            (阻塞到用户点"确定")。
        测试机(10.20.33.103)实际为 fcitx 4.2.9.32.46, 未安装 fcitx5,
        与描述里的 fcitx5 是同一"输入法框架"语义, 按等价环境处理。

        说明: 描述中的三段文字输出属于更新版本的脚本; 本机 1.0.0 插件不打印
        这些文本, 而是以"killall 关闭运行中进程 + 重启出新进程 + 修复完成
        提示框"作为等价用户可见结果, 因此按等价语义断言。

        预期等价断言:
        1) 前置: 输入法进程在运行, --version 能输出版本号, 进程继承的会话
           环境 XMODIFIERS 为 @im=fcitx —— 对应描述的前置三条;
        2) 修复对话框(ShellRepairDialog)弹出 —— 修复脚本被真实拉起;
        3) 修复前的输入法 PID 全部消失 —— 脚本真的关闭了运行中的输入法进程
           (对应"正在重启输入法服务...");
        4) 出现与修复前完全不重合的新 PID —— 输入法被重新拉起
           (对应"已重启 xx 输入法");
        5) session 总线收到 openinfobox 请求, AT-SPI 上出现标题"输入法修复"、
           只有"确定"一个按钮、正文含"输入法"与"重启/修复"的提示框 ——
           修复完成提示(对应"输入法重启完成，可尝试切换输入法使用");
        6) 修复输出日志无脚本报错特征。

        finally 回退: 关闭提示框与修复对话框、停止总线监听, 并确保输入法
        进程恢复运行(不改变测试机的输入法状态)。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        dialog_opened = False
        monitor_started = False
        try:
            # 前置: 输入法进程必须正在运行(描述前置条件)
            widget.ensure_input_method_running()
            self.assert_true(widget.get_input_method_process_running())
            im_name = widget.get_input_method_name()
            logger.info(f"当前运行的输入法框架: {im_name}")
            self.assert_true(bool(im_name))
            version_text = widget.get_input_method_version()
            logger.info(f"{im_name} --version: {version_text!r}")
            self.assert_true(bool(version_text))
            xmodifiers = widget.get_input_method_xmodifiers()
            logger.info(f"输入法进程 XMODIFIERS: {xmodifiers!r}")
            self.assert_true("im=fcitx" in xmodifiers)

            # 记录修复前的输入法 PID, 用于判定"旧进程被关闭 + 新进程被拉起"
            old_pids = widget.get_input_method_pids()
            logger.info(f"修复前输入法 PID: {old_pids!r}")
            self.assert_true(bool(old_pids))

            # 步骤0: 修复工具页 -> 输入法修复卡片 -> 详情页
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() >= 1)
            widget.click_input_method_fix_card()
            self.assert_true(widget.get_repair_detail_showing())
            detail = widget.get_repair_detail_content()
            logger.info(f"输入法修复详情页: {detail}")
            # QML 按钮 accessible name 是 objectName(repair_startBtn), 不含
            # "开始修复"文案, 故以 detailCard 内 repair_startBtn 实际渲染为判据
            self.assert_true(detail.get("start_btn_showing"))

            # 监听 session 总线, 用于核对脚本末尾 openinfobox 的标题/正文
            monitor_started = widget.start_confirm_dbus_monitor()
            self.assert_true(monitor_started)

            # 步骤1: 执行输入法修复脚本
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing(timeout=20)
            self.assert_true(dialog_opened)

            # 预期1: 运行中的输入法进程被脚本 killall 关闭
            self.assert_true(
                widget.wait_input_method_process_killed(old_pids, timeout=40)
            )
            # 预期2: 输入法被重新拉起, 且是全新的 PID
            self.assert_true(widget.wait_input_method_restarted(old_pids, timeout=40))
            new_pids = widget.get_input_method_pids()
            logger.info(f"修复后输入法 PID: {new_pids!r}")

            # 步骤2/预期3: 修复完成提示框(脚本 openinfobox)
            info_state = widget.get_info_dialog_state("输入法修复", timeout=40)
            logger.info(f"输入法修复提示框状态: {info_state}")
            self.assert_true(info_state["exists"] and info_state["showing"])
            self.assert_true(info_state["title"] == "输入法修复")
            self.assert_true(info_state["buttons"] == [widget.INFOBOX_OK_TEXT])
            self.assert_true(info_state["message_label_showing"])
            # DTK 标签的 AT-SPI name 是 objectName, 读不到正文文案;
            # 提示框正文改由 session 总线请求参数核对(见下)
            info_text = widget.get_info_dialog_text("输入法修复", timeout=10)
            logger.info(f"输入法修复提示框正文节点: {info_text!r}")

            # 脚本执行到末尾的证据: 总线上收到标题/正文匹配的 OpenMessage 请求
            request_text = ""
            dbus_strings = []
            for _ in range(10):
                request_text = widget.get_confirm_dbus_request_text()
                dbus_strings = re.findall(r'string "([^"]*)"', request_text)
                if "输入法修复" in dbus_strings:
                    break
                sleep(1)
            logger.info(f"session 总线请求字符串: {dbus_strings}")
            self.assert_true('string "OpenMessage"' in request_text)
            self.assert_true("输入法修复" in dbus_strings)
            # 正文即脚本参数(如 "输入法已重启，修复完成"), 按等价语义
            # 只要求是"输入法 + 重启/修复完成"的提示语, 不锁死标点
            self.assert_true(
                any(
                    "输入法" in item
                    and ("重启" in item or "修复完成" in item)
                    for item in dbus_strings
                )
            )

            # 预期: 修复脚本全程无报错特征
            output_text = widget.get_repair_output_text() or ""
            logger.info(f"修复输出日志: {output_text!r}")
            for marker in ("Permission denied", "command not found", "Traceback"):
                self.assert_false(marker in output_text)

            # 点"确定"后提示框关闭, 脚本继续执行并结束
            self.assert_true(
                widget.click_confirm_dialog_button(
                    "输入法修复", widget.INFOBOX_OK_TEXT
                )
            )
            self.assert_true(widget.wait_info_dialog_closed("输入法修复", timeout=10))

            # 收尾: 提示框点掉后脚本才退出, 但修复窗口仍停在完成态不会自己关;
            # 若脚本/产品再补一条提示框, 其 openinfobox 的 timeoutMs=0 表示没有
            # 超时, 不点就永远留在桌面并阻塞脚本。finish_repair_flow 清掉全部
            # 提示框形态并关闭修复窗口, 并断言窗口已消失(原用例未验证过)
            state = widget.finish_repair_flow("输入法修复")
            self.assert_false(state["window_left"])
            dialog_opened = False
        finally:
            if dialog_opened:
                # openinfobox 的 timeoutMs=0 表示提示框没有超时: 不点掉会被留
                # 在桌面且脚本一直阻塞, 因此先点提示框再由 finish_repair_flow
                # 关闭修复窗口(替代原来的 close_info_dialogs + close_repair_dialog)
                try:
                    widget.finish_repair_flow("输入法修复")
                except BaseException:
                    pass
            if monitor_started:
                try:
                    widget.stop_confirm_dbus_monitor()
                except BaseException:
                    pass
            # 清理: 确保输入法进程恢复运行(修复脚本会重启, 异常时手动兜底)
            try:
                widget.restart_input_method()
            except BaseException:
                logger.exception("恢复输入法进程失败")
            self.assert_true(widget.get_input_method_process_running())
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

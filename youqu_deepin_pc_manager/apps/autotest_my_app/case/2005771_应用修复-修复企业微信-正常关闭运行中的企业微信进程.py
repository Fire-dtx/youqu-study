#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import logging
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

logger = logging.getLogger(__name__)

# 修复脚本收尾文案(entry.sh: dpmapi openinfobox "企业微信修复" "企业微信缓存清理完成，修复完成")
COMPLETION_KEYWORDS = ("修复完成", "缓存清理完成")


class TestMyCase(BaseCase):

    @staticmethod
    def _require(condition, message):
        """构造/收尾断言: 失败信息直接带上现场(提示框正文、输出尾部)

        funnylog 包装的 assert_true 只接受一个位置参数, 这类"等弹窗/等输出"
        失败必须能直接看出弹窗正文与脚本输出处于什么状态。
        """
        if not condition:
            raise AssertionError(message)
        return True

    def test_mycase_156(self):
        """应用修复-修复企业微信-正常关闭运行中的企业微信进程

        前置条件: Wine 版企业微信(WeChat.exe)正在运行。
        步骤: 执行修复脚本(修复工具 -> 企业微信修复卡片 -> 开始修复)。
        预期: rm -rf 可正常删除缓存释放空间, 企业微信进程被强制终止。

        产品实现(deepin-pc-manager-plugins/plugins/plugin-wecom-fix/entry.sh):
            /opt/deepinwine/tools/kill.sh ~/.deepinwine/Deepin-WXWork/
            rm -rf ~/.deepinwine/Deepin-WXWork/
            dpmapi openinfobox "企业微信修复" "企业微信缓存清理完成，修复完成"
        kill.sh 按 bottle 路径匹配 WINEPREFIX 指向该 prefix 的 wineserver,
        再执行 `WINEPREFIX=<bottle> <wineserver> -k` 结束容器内全部进程。

        等价实现: 本机未安装真实 Wine 版企业微信, 用桩运行时构造等价现场 ——
        bottle 目录 ~/.deepinwine/Deepin-WXWork(含 user.reg, kill.sh 才认)、
        该 prefix 的桩 wineserver(收到 -k 时结束容器内 WeChat.exe)、以及
        运行中的模拟 WeChat.exe 进程; bottle 内写入 40MB 缓存作为可观测占用。
        断言:
            1) 修复对话框出现 —— 证明修复脚本被真实执行;
            2) bottle 内 40MB 缓存随目录被 rm -rf 删净 —— 缓存清理、空间释放;
               (测试机 /home 与 / 不同分区, df 口径不能反映释放量, 故以
               "40MB 目录由存在变为不存在"作为空间释放的等价断言)
            3) 模拟企业微信进程被终止 —— kill.sh -> wineserver -k 真实生效;
            4) 收尾 openinfobox("企业微信修复") 完成提示框(timeoutMs=0)出现
               被点掉, 修复窗口随之关闭 —— 弹窗不处理会让用例结束不了。
        finally 回退: 关闭完成提示框/修复窗口、终止模拟进程、移除 kill.sh 桩、
        删除桩运行时与 bottle 目录、退出应用。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        dialog_opened = False
        kill_helper = {}
        monitor_started = False
        teardown_errors = []
        try:
            # 清理上次异常退出可能遗留的桩进程/目录
            widget.cleanup_mock_wecom_wine()
            # 产品 entry.sh 用 /opt/deepinwine/tools/kill.sh 终止容器进程;
            # 测试机的 deepin-wine-runtime 不含该工具, 缺失时脚本静默跳过,
            # 故先补齐等价桩(系统自带则不动), 收尾删除
            kill_helper = widget.ensure_wecom_kill_helper()
            logger.info(f"产品 kill.sh 现场: {kill_helper}")
            self._require(
                kill_helper.get("helper") in ("existing", "stub"),
                f"产品依赖的 {widget.WECOM_KILL_HELPER} 不可用: {kill_helper}",
            )
            # 监听 session 总线, 用于核对完成提示框的标题/正文(AT-SPI 读不到)
            monitor_started = widget.start_confirm_dbus_monitor()
            self._require(monitor_started, "session 总线监听启动失败, 无法核对完成提示框正文")
            # 前置数据: 运行中的 Wine 企业微信 + bottle 内缓存
            self.assert_true(widget.setup_mock_wecom_wine())
            self.assert_true(widget.get_wecom_process_status())
            cache_kb = widget.create_wecom_wine_cache_payload(size_mb=40)
            logger.info(f"企业微信 bottle 缓存占用: {cache_kb}KB")
            self.assert_true(cache_kb >= 32 * 1024)
            self.assert_true(widget.get_wecom_wine_cache_exists())

            # 步骤: 进入修复工具 -> 企业微信修复卡片 -> 开始修复
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() >= 1)
            card_names = widget.get_repair_card_names()
            logger.info(f"修复卡片列表: {card_names}")
            card_name = next(
                (name for name in card_names if "企业微信" in name),
                "企业微信修复",
            )
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())
            self.assert_true(
                widget.click_start_repair_button_until_dialog(
                    attempts=3, timeout=20
                )
            )
            dialog_opened = True

            # 收尾弹窗: entry.sh 最后一步 openinfobox("企业微信修复", ...) 的
            # timeoutMs=0, 既不会自动消失, 脚本也会阻塞到用户点【确定】。
            # 不点掉它, 修复窗口一直停在完成态, 用例结束不了。
            # DTK 标签的 AT-SPI name 是 objectName, 读不到正文文案(与 2005793
            # 一致), 因此正文改用 session 总线上 OpenMessage 的请求参数核对。
            info_state = widget.get_info_dialog_state("企业微信修复", timeout=90)
            logger.info(f"企业微信修复完成提示框: {info_state}")
            self._require(
                info_state.get("exists") and info_state.get("showing"),
                f"修复脚本结束后未出现完成提示框: {info_state}",
            )
            self.assert_true(info_state.get("title") == "企业微信修复")
            self.assert_true(info_state.get("buttons") == [widget.INFOBOX_OK_TEXT])
            self.assert_true(info_state.get("message_label_showing"))
            request_text = widget.get_confirm_dbus_request_text()
            dbus_strings = re.findall(r'string "([^"]*)"', request_text)
            logger.info(f"session 总线请求字符串: {dbus_strings}")
            self._require(
                "企业微信修复" in dbus_strings
                and any(
                    keyword in item
                    for item in dbus_strings
                    for keyword in COMPLETION_KEYWORDS
                ),
                f"总线未捕获到完成提示框的标题/正文: {dbus_strings}",
            )

            output = widget.get_repair_output_text() or ""
            logger.info(f"修复输出({len(output)} 字符): {output!r}")
            self.assert_true("[ERROR]" not in output)

            # 点【确定】关掉完成提示框, 再关修复窗口
            widget.close_info_dialogs("企业微信修复")
            widget.close_repair_notify_dialog(rounds=2)
            self._require(
                widget.wait_info_dialog_closed("企业微信修复", timeout=10),
                "企业微信修复完成提示框点【确定】后仍未关闭",
            )
            widget.close_repair_completion_dialog()
            self._require(
                not widget.get_repair_dialog_showing(timeout=15),
                "修复窗口未被关闭, 用例无法正常结束",
            )

            # 预期1: rm -rf 删除 wine 企业微信缓存目录, 释放磁盘空间
            self.assert_true(widget.wait_wecom_wine_cache_cleaned(timeout=60))
            # 预期2: kill.sh -> wineserver -k 强制终止运行中的企业微信进程
            self.assert_true(widget.wait_wecom_process_killed(timeout=60))
            # 预期1 的补充证据: 被删掉的 40MB 缓存确实随目录一起释放
            self.assert_true(widget.get_wecom_bottle_size_kb() == 0)
        finally:
            teardown_errors = self._teardown(
                widget, kill_helper, dialog_opened, monitor_started
            )
        self._require(
            not teardown_errors,
            "收尾失败: " + "; ".join(teardown_errors),
        )

    def _teardown(self, widget, kill_helper, dialog_opened, monitor_started):
        """回退现场, 收尾失败只记录不抛(避免覆盖用例原始异常)

        :return: 失败描述列表, 空表示全部成功
        """
        errors = []

        def attempt(desc, func):
            try:
                func()
            except BaseException as exc:
                errors.append(f"{desc}: {exc.__class__.__name__}: {exc}")

        if dialog_opened:
            attempt(
                "关闭完成提示框",
                lambda: widget.close_info_dialogs("企业微信修复"),
            )
            attempt(
                "关闭通知弹窗", lambda: widget.close_repair_notify_dialog(rounds=2)
            )
            attempt("关闭修复窗口", widget.close_repair_completion_dialog)
            attempt(
                "提示框/修复窗口未关闭",
                lambda: self._require(
                    not widget.get_repair_dialog_showing(timeout=10),
                    "收尾后修复窗口仍处于显示状态",
                ),
            )
        if monitor_started:
            attempt("停止总线监听", widget.stop_confirm_dbus_monitor)
        # 回退构造数据: 桩进程 + 桩运行时 + bottle 目录
        attempt("回退桩运行时", widget.cleanup_mock_wecom_wine)
        # 删除本用例安装的 kill.sh 桩(系统自带的不动)
        attempt(
            "移除 kill.sh 桩", lambda: widget.remove_wecom_kill_helper(kill_helper)
        )
        # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
        attempt("关闭电脑管家", widget.kill_pc_manager)
        attempt("等待电脑管家退出", widget.wait_pc_manager_exit)
        return errors

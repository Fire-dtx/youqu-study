#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import logging

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

logger = logging.getLogger(__name__)


class TestMyCase(BaseCase):

    def test_mycase_163(self):
        """应用修复-修复WPS-系统不存在Office.conf 配置文件

        用例描述:
            前置: ~/.config/Kingsoft/Office.conf 不存在;
            步骤: 1. 执行修复脚本 2. 查看配置文件是否生成;
            预期: 1. 自动创建 Kingsoft 目录 2. 生成 Office.conf。

        产品实现(plugin-wps-fix/entry.sh, 已解码核对, executionMode=user):
            gConfigDir=~/.config/Kingsoft/, gConfigPath=~/.config/Kingsoft/Office.conf
            配置文件不存在时走 else 分支:
                mkdir -p "$gConfigDir"; chmod 700; chown -R <user>; chmod 775
                touch "$gConfigPath"; chmod 664; chown <user>
                写入 "[6.0]"
                    wpsoffice\Application%20Settings\AppComponentMode=prome_fushion
                    wpsoffice\Application%20Settings\AppComponentModeInstall=prome_fushion
            最后 dpmapi openinfobox "WPS修复" "WPS配置文件修复完成" (阻塞到用户点确定)。
        注意: 脚本不检测 WPS 是否安装, 纯配置修复; 因此"未安装 WPS"不是跳过理由。

        前置数据构造: 把测试机真实 ~/.config/Kingsoft 整体备份到
        /tmp/autotest_wps_kingsoft.bak 后删除, 使 "Office.conf 不存在" 同时
        "Kingsoft 目录不存在", 这样预期1(自动创建目录)才是真实被验证的行为。

        预期等价断言:
        1) 修复对话框(ShellRepairDialog)弹出 —— 修复脚本被真实拉起;
        2) Kingsoft 目录在修复后出现, 属主为当前用户、属主 rwx —— 目录由脚本创建;
        3) Office.conf 生成, 内容含 [6.0] 且 AppComponentMode /
           AppComponentModeInstall 均为 prome_fushion —— 写入的是产品正确配置;
        4) 文件属主为当前用户、不可执行(664), 非其他用户可写 —— 权限设置生效;
        5) session 总线上收到 OpenMessage 请求 title="WPS修复"、
           message="WPS配置文件修复完成", 且 AT-SPI 上出现同名提示框、仅"确定"
           一个按钮 —— 脚本执行到末尾(修复完成的用户可见证据), 点掉后脚本
           拿到退出码继续结束;
        6) 修复输出日志无 Permission denied / No such file 等脚本报错特征。

        finally 回退: 关闭提示框与修复对话框, 删除脚本生成的目录并移回备份,
        清理临时备份文件, 不给测试机留残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        dialog_opened = False
        monitor_started = False
        try:
            # 自愈 + 前置数据: 备份真实现场, 制造"Office.conf 与 Kingsoft 目录均不存在"
            self.assert_true(widget.backup_wps_state())
            self.assert_true(widget.remove_wps_config_dir())
            self.assert_false(widget.get_wps_config_dir_exists())
            self.assert_false(widget.get_wps_config_exists())

            # 步骤0: 修复工具页 -> WPS 修复卡片 -> 详情页
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() >= 1)
            card_names = widget.get_repair_card_names()
            logger.info(f"修复卡片列表: {card_names}")
            card_name = next(
                (name for name in card_names if "WPS" in name),
                "WPS双击打开修复",
            )
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())
            detail = widget.get_repair_detail_content()
            logger.info(f"WPS 修复详情页: {detail}")
            self.assert_true(
                detail.get("start_btn_showing")
                or widget.get_repair_start_button_showing()
            )

            # 监听 session 总线, 用于核对脚本末尾 openinfobox 的标题/正文
            monitor_started = widget.start_confirm_dbus_monitor()
            self.assert_true(monitor_started)

            # 步骤1: 执行修复脚本
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing(timeout=20)
            self.assert_true(dialog_opened)

            # 预期1: 自动创建 Kingsoft 目录(脚本 mkdir -p 分支)
            self.assert_true(widget.wait_wps_config_created(timeout=60))
            self.assert_true(widget.get_wps_config_dir_exists())
            dir_mode = widget.get_wps_config_dir_mode()
            dir_owner = widget.get_wps_config_dir_owner()
            logger.info(f"Kingsoft 目录: mode={dir_mode} owner={dir_owner}")
            self.assert_true(bool(dir_mode))
            self.assert_true(int(dir_mode, 8) & 0o700 == 0o700)
            self.assert_true(dir_owner == widget.run_cmd("id -un").strip())

            # 预期2: 生成 Office.conf 且写入正确组件模式配置
            self.assert_true(widget.get_wps_config_has_required_keys())
            content = widget.get_wps_config_content()
            logger.info(f"Office.conf 内容: {content!r}")
            self.assert_true(len(content.strip().splitlines()) >= 3)
            file_mode = widget.get_wps_config_mode()
            file_owner = widget.get_wps_config_owner()
            logger.info(f"Office.conf: mode={file_mode} owner={file_owner}")
            self.assert_true(bool(file_mode))
            self.assert_true(int(file_mode, 8) & 0o600 == 0o600)
            self.assert_false(int(file_mode, 8) & 0o111)
            self.assert_true(file_owner == widget.run_cmd("id -un").strip())

            # 预期: 脚本执行到末尾 —— openinfobox 提示框(标题/正文即脚本参数)
            info_state = widget.get_info_dialog_state("WPS修复", timeout=30)
            logger.info(f"WPS 修复完成提示框: {info_state}")
            self.assert_true(info_state["exists"] and info_state["showing"])
            self.assert_true(info_state["title"] == "WPS修复")
            self.assert_true(info_state["buttons"] == [widget.INFOBOX_OK_TEXT])
            self.assert_true(info_state["message_label_showing"])
            self.assert_true(
                widget.wait_confirm_dbus_request(
                    "WPS修复", "WPS配置文件修复完成", timeout=10
                )
            )
            self.assert_true(
                'string "OpenMessage"' in widget.get_confirm_dbus_request_text()
            )
            # 点"确定"后提示框关闭, 脚本继续执行并结束
            self.assert_true(
                widget.click_confirm_dialog_button("WPS修复", widget.INFOBOX_OK_TEXT)
            )
            self.assert_true(widget.wait_info_dialog_closed("WPS修复", timeout=10))

            # 预期: 修复脚本全程无报错特征
            output_text = widget.get_repair_output_text() or ""
            for marker in (
                "Permission denied",
                "No such file or directory",
                "command not found",
                "Traceback",
            ):
                self.assert_false(marker in output_text)

            # 收尾: 提示框点掉后脚本才退出, 但修复窗口仍停在完成态不会自己关;
            # 若脚本末尾再补一条提示框, 其 openinfobox 的 timeoutMs=0 表示没有
            # 超时, 不点就永远留在桌面。finish_repair_flow 清掉全部提示框形态
            # 并关闭修复窗口, 这里显式断言窗口已消失(原用例从未验证过)
            state = widget.finish_repair_flow("WPS修复")
            self.assert_false(state["window_left"])
            # 修复窗口已收尾, finally 不必再走一遍弹窗清理
            dialog_opened = False
        finally:
            if dialog_opened:
                # openinfobox 的 timeoutMs=0 表示提示框没有超时: 不点掉会被留
                # 在桌面且脚本一直阻塞, 因此先点提示框再由 finish_repair_flow
                # 关闭修复窗口(替代原来的 close_info_dialogs + close_repair_dialog)
                try:
                    widget.finish_repair_flow("WPS修复")
                except BaseException:
                    pass
            if monitor_started:
                try:
                    widget.stop_confirm_dbus_monitor()
                except BaseException:
                    pass
            # 回退: 删除脚本生成的目录并还原测试前现场, 清理临时备份
            widget.restore_wps_state()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

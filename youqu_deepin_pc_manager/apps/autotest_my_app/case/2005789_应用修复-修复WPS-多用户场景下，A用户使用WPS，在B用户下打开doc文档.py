#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import logging
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
# 桌面目录是 widget 模块级常量(xdg-user-dir DESKTOP), 不是 MyAppWidget 的属性
from apps.autotest_my_app.widget.my_app_widget import DESKTOP_DIR

logger = logging.getLogger(__name__)

# "多用户"前置: 测试机默认只有 uostest 一个普通用户, 需真实创建第二个普通用户 A
OTHER_USER = "autotestusera"
OTHER_WPS_CONFIG = f"/home/{OTHER_USER}/.config/Kingsoft/Office.conf"
# A 用户自己的组件模式取值(与修复脚本写入的 prome_fushion 不同), 便于断言 A 的配置未被改动
OTHER_WPS_MARKER = "autotestusera_personal_component_mode"
TEST_DOC_NAME = "test_wps_doc.docx"


class TestMyCase(BaseCase):

    def test_mycase_164(self):
        """应用修复-修复WPS-多用户场景下，A用户使用WPS，在B用户下打开doc文档

        用例描述:
            前置: 存在多用户, B 用户下 doc 文档打不开;
            步骤: 1. 登录 B 用户, 执行修复脚本;
            预期: 1. 修复成功(修复后 B 用户可正常打开 doc 文档)。

        产品依据(deepin-pc-manager 1.1.7 的 plugins/plugin-wps-fix):
            config.json: parent=repair/application, executionMode=user,
                requiresNetwork=false —— 修复脚本以"当前登录用户"身份执行,
                只写 <当前用户>/.config/Kingsoft, 天然按用户隔离;
            entry.sh 解码后: 配置缺失时 mkdir -p ~/.config/Kingsoft(chmod 700/775)、
                touch Office.conf(chmod 664)、写入 [6.0] 与
                AppComponentMode / AppComponentModeInstall = prome_fushion,
                最后 dpmapi openinfobox "WPS修复" "WPS配置文件修复完成"。
            因此"多用户场景"的产品语义是: 每个用户各有一份 Office.conf,
            在 B 的会话里修复只重建 B 的那份, 不得触碰 A 的配置。

        前置数据构造(真实多用户):
            1) useradd -m 创建第二个普通用户 A(autotestusera);
            2) 在 A 家目录写入 A 自己的 Office.conf(属主 A、权限 600、取值带 marker),
               代表"A 用户使用过 WPS"; A 家目录 750, B 用户读不到 A 的配置;
            3) 备份并删除 B(uostest) 的 ~/.config/Kingsoft, 制造"B 没有 WPS 配置"
               即"B 用户下 doc 文档打不开"的现场。

        等价实现(测试机未安装 WPS, 且无外网无法安装):
            - WPS 配置修复仍由产品脚本真实执行, 断言真实文件/权限/属主/弹框/DBus 请求;
            - "修复后 B 下 doc 能正常打开"以系统默认文档处理程序真实打开文档为等价断言
              (xdg-mime 查询 docx 默认打开方式为 deepin-reader), 断言查看器进程命令行
              带该文档; 同时结合修复后配置里的整合模式取值
              (AppComponentMode=prome_fushion)证明双击文档走的是 WPS 整合模式分支。

        预期等价断言:
            1) 机器上存在两个普通用户; A 的 Office.conf 属主 A、权限 600、B 不可读;
            2) 修复对话框(ShellRepairDialog)弹出 —— 修复脚本被真实拉起;
            3) B 的 Kingsoft 目录被重建(属主 B、属主位 rwx);
               Office.conf 生成, 内容含 [6.0] 与两条 prome_fushion 配置项,
               属主 B、664、不可执行;
            4) session 总线收到 openinfobox 请求(title="WPS修复"、
               message="WPS配置文件修复完成"), AT-SPI 上出现同名提示框且只有"确定",
               说明脚本执行到末尾;
            5) A 的 Office.conf 仍存在、属主仍是 A、md5 与修复前一致 —— 多用户隔离;
            6) B 桌面上的 docx 文档被系统默认处理程序真实打开(查看器进程含该文档);
            7) 修复输出日志无 Permission denied / No such file 等报错特征。

        finally 回退: 关闭提示框/修复框/文档查看器, 删除测试文档,
        还原 B 的 Kingsoft 目录, 删除临时用户 A 及其家目录, 不在测试机留任何人造对象。
        """
        widget = MyAppWidget(check_start=False)
        fixture_created = False
        backup_ready = False
        doc_created = False
        dialog_opened = False
        monitor_started = False
        other_config_md5 = ""
        try:
            # 前置1: 真实多用户 —— 构造第二个普通用户 A
            users_before = widget.get_normal_user_names()
            logger.info(f"构造前的普通用户: {users_before}")
            self.assert_true(widget.create_fixture_user(OTHER_USER))
            fixture_created = True
            users_after = widget.get_normal_user_names()
            logger.info(f"构造后的普通用户: {users_after}")
            self.assert_true(len(users_after) >= 2)
            self.assert_true(OTHER_USER in users_after)
            current_user = widget.run_cmd(
                "id -un", timeout=5, out_debug_flag=False
            ).strip()
            self.assert_true(current_user in users_after)
            self.assert_true(os.path.isdir(f"/home/{OTHER_USER}"))

            # 前置2: A 用过 WPS(家目录下有自己的 Office.conf), 且 B 读不到
            self.assert_true(
                widget.setup_other_user_wps_config(OTHER_USER, OTHER_WPS_MARKER)
            )
            other_state = widget.get_path_stat(OTHER_WPS_CONFIG)
            logger.info(f"A 用户的 WPS 配置: {other_state}")
            self.assert_true(other_state["exists"])
            self.assert_true(other_state["owner"] == OTHER_USER)
            self.assert_true(other_state["mode"] == "600")
            self.assert_false(widget.get_current_user_can_read(OTHER_WPS_CONFIG))
            other_config_md5 = widget.get_path_md5_as_root(OTHER_WPS_CONFIG)
            self.assert_true(len(other_config_md5) == 32)

            # 前置3: B 没有 WPS 配置 —— "B 用户下 doc 文档打不开"的现场
            self.assert_true(widget.backup_wps_state())
            backup_ready = True
            self.assert_true(widget.remove_wps_config_dir())
            self.assert_false(widget.get_wps_config_dir_exists())
            self.assert_false(widget.get_wps_config_exists())
            logger.warning(
                "测试机 WPS 安装状态: %s(WPS 未安装且无外网, "
                "doc 打开以系统默认处理程序等价验证)",
                widget.is_wps_installed(),
            )

            # 步骤0: 启动电脑管家, 进入修复工具页并打开 WPS 修复详情
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))
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

            # 步骤1: 在 B 用户下执行修复脚本
            monitor_started = widget.start_confirm_dbus_monitor()
            self.assert_true(monitor_started)
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing(timeout=20)
            self.assert_true(dialog_opened)

            # 预期: B 的配置被重建(目录 + 文件 + 正确内容 + 属主/权限)
            self.assert_true(widget.wait_wps_config_created(timeout=90))
            self.assert_true(widget.get_wps_config_dir_exists())
            dir_mode = widget.get_wps_config_dir_mode()
            dir_owner = widget.get_wps_config_dir_owner()
            logger.info(f"B 的 Kingsoft 目录: mode={dir_mode} owner={dir_owner}")
            self.assert_true(bool(dir_mode))
            self.assert_true(int(dir_mode, 8) & 0o700 == 0o700)
            self.assert_true(dir_owner == current_user)
            self.assert_true(widget.get_wps_config_has_required_keys())
            content = widget.get_wps_config_content()
            logger.info(f"B 的 Office.conf: {content!r}")
            self.assert_true(len(content.strip().splitlines()) >= 3)
            self.assert_true("prome_fushion" in content)
            file_mode = widget.get_wps_config_mode()
            file_owner = widget.get_wps_config_owner()
            logger.info(f"B 的 Office.conf: mode={file_mode} owner={file_owner}")
            self.assert_true(bool(file_mode))
            self.assert_true(int(file_mode, 8) & 0o600 == 0o600)
            self.assert_false(int(file_mode, 8) & 0o111)
            self.assert_true(file_owner == current_user)

            # 预期: 脚本执行到末尾 —— openinfobox(WPS修复 / WPS配置文件修复完成)
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
            self.assert_true(
                widget.click_confirm_dialog_button("WPS修复", widget.INFOBOX_OK_TEXT)
            )
            self.assert_true(widget.wait_info_dialog_closed("WPS修复", timeout=10))

            # 预期: 修复脚本全程无报错特征(输出日志随修复窗口关闭而消失,
            # 必须在收尾前读取)
            output_text = widget.get_repair_output_text() or ""

            # 收尾: 提示框点掉后脚本才退出, 但修复窗口仍停在完成态不会自己关;
            # 若脚本末尾再补一条提示框, 其 openinfobox 的 timeoutMs=0 表示没有
            # 超时, 不点就永远留在桌面。finish_repair_flow 清掉全部提示框形态
            # 并关闭修复窗口(放在后续文档/界面操作之前, 避免遗留窗口干扰)
            state = widget.finish_repair_flow("WPS修复")
            self.assert_false(state["window_left"])
            dialog_opened = False

            # 预期: 多用户隔离 —— A 的配置未被修复脚本改动
            other_after = widget.get_path_stat(OTHER_WPS_CONFIG)
            logger.info(f"修复后 A 用户的 WPS 配置: {other_after}")
            self.assert_true(other_after["exists"])
            self.assert_true(other_after["owner"] == OTHER_USER)
            self.assert_true(other_after["mode"] == "600")
            self.assert_true(
                widget.get_path_md5_as_root(OTHER_WPS_CONFIG) == other_config_md5
            )
            self.assert_true(
                OTHER_WPS_MARKER in widget.get_path_content_as_root(OTHER_WPS_CONFIG)
            )

            # 预期: 修复后 B 下 doc 文档可以正常打开
            widget.create_test_doc_file()
            doc_created = True
            doc_path = f"{DESKTOP_DIR}/{TEST_DOC_NAME}"
            self.assert_true(os.path.isfile(doc_path))
            widget.open_test_doc_file()
            self.assert_true(widget.wait_document_opened(doc_path, timeout=45))
            logger.info(
                f"打开 doc 的查看器进程: {widget.get_document_viewer_processes()}"
            )
            self.assert_true(TEST_DOC_NAME in widget.get_document_viewer_processes())

            # 预期: 修复脚本全程无报错特征(输出已在关闭修复窗口前读取)
            for marker in (
                "Permission denied",
                "No such file or directory",
                "command not found",
                "Traceback",
            ):
                self.assert_false(marker in output_text)
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
            try:
                widget.close_document_viewer()
            except BaseException:
                pass
            if doc_created:
                try:
                    widget.remove_test_doc_file()
                except BaseException:
                    pass
            # 回退: 删除修复脚本生成的配置并还原 B 测试前现场
            if backup_ready:
                widget.restore_wps_state()
            # 回退: 删除临时用户 A 及其家目录, 恢复单用户环境
            if fixture_created:
                if not widget.remove_fixture_user(OTHER_USER):
                    logger.error(
                        f"临时用户 {OTHER_USER} 未清理干净, 需要人工确认"
                    )
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

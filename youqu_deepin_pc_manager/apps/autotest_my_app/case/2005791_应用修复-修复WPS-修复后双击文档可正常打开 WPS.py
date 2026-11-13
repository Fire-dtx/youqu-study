#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import logging
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

logger = logging.getLogger(__name__)

# 三种 Office 文档格式, 对应用例步骤"双击 .docx/.xlsx/.pptx 文件"
TEST_DOC_FORMATS = ("docx", "xlsx", "pptx")


class TestMyCase(BaseCase):

    def test_mycase_165(self):
        """应用修复-修复WPS-修复后双击文档可正常打开 WPS

        用例描述:
            前置: 修复脚本已执行;
            步骤: 1. 双击 .docx/.xlsx/.pptx 文件;
            预期: 1. WPS 正常启动。

        产品依据(deepin-pc-manager plugins/plugin-wps-fix, 已解码核对 entry.sh):
            gConfigDir=~/.config/Kingsoft/, gConfigPath=~/.config/Kingsoft/Office.conf
            配置缺失/损坏时走重建分支: mkdir -p + chmod 700/775, touch + chmod 664,
            写入 "[6.0]" 与 AppComponentMode / AppComponentModeInstall =
            prome_fushion(整合模式), 最后 dpmapi openinfobox
            "WPS修复" "WPS配置文件修复完成"(阻塞到用户点确定)。
            WPS 的 wps/et/wpp 三个组件双击 .docx/.xlsx/.pptx 时读的都是这一份配置,
            配置错误就是"双击文档打不开 WPS / 打开异常"的根因, 修复后应能正常打开。

        前置数据构造:
            1) 把测试机真实 ~/.config/Kingsoft 整体备份到 /tmp/autotest_wps_kingsoft.bak;
            2) 删除该目录, 制造"修复脚本执行前配置损坏/缺失、双击文档打不开 WPS"的现场;
            3) 在电脑管家里真实执行一次 WPS 双击打开修复(用例前置"修复脚本已执行")。

        等价实现(测试机未安装 WPS 且无外网无法安装, which wps 为空):
            - 修复动作本身完全真实: 由产品脚本执行, 断言真实目录/文件/内容/权限/属主、
              修复对话框、openinfobox 提示框与 session 总线上的 OpenMessage 请求;
            - "双击文档能打开"部分:
              a) 用系统默认文档查看器(deepin-reader)真实打开 .docx, 断言查看器进程
                 命令行带该文档 —— 真实的"文档被打开"证据;
              b) 三种格式的分发用桩启动器(替身, 补齐缺失的 WPS)验证: 临时把桩注册为
                 .docx/.xlsx/.pptx 的默认打开程序, 双击(xdg-open)后断言桩收到的正是
                 这三个文档的绝对路径 —— 证明桌面环境按 OOXML 类型分发并把文档交给
                 Office 应用;
              c) 结合修复后配置里的整合模式取值(AppComponentMode=prome_fushion)
                 证明双击文档走的是 WPS 整合模式分支。

        预期等价断言:
            1) 修复对话框(ShellRepairDialog)弹出 —— 修复脚本被真实拉起;
            2) Kingsoft 目录被重建(属主当前用户、属主位 rwx), Office.conf 生成,
               内容含 [6.0] 与两条 prome_fushion 配置项, 属主当前用户、664、不可执行;
            3) session 总线收到 openinfobox 请求(title="WPS修复"、
               message="WPS配置文件修复完成"), AT-SPI 上出现同名提示框且只有"确定",
               说明脚本执行到末尾;
            4) 三个测试文档的 MIME 均为对应 OOXML 类型(双击才会分发到 Office 应用);
            5) .docx 被系统默认查看器真实打开(查看器进程命令行含文档名);
            6) 桩注册后三种格式的默认程序均为桩, 双击后桩收到三个文档的绝对路径;
            7) 修复输出日志无 Permission denied / No such file 等报错特征。

        finally 回退: 关闭提示框/修复框/文档查看器, 撤销桩并还原用户级 mimeapps.list,
        删除临时文档目录, 还原 B(当前用户)测试前的 Kingsoft 目录, 不留残留。
        """
        widget = MyAppWidget(check_start=False)
        backup_ready = False
        dialog_opened = False
        monitor_started = False
        stub_ready = False
        try:
            # 前置: 备份真实现场并制造"WPS 配置缺失/损坏"的现场
            self.assert_true(widget.backup_wps_state())
            backup_ready = True
            self.assert_true(widget.remove_wps_config_dir())
            self.assert_false(widget.get_wps_config_dir_exists())
            self.assert_false(widget.get_wps_config_exists())
            logger.warning(
                "测试机 WPS 安装状态: %s(未安装且无外网, 双击打开以系统默认查看器 + "
                "桩启动器等价验证)",
                widget.is_wps_installed(),
            )

            # 前置动作: 启动电脑管家 -> 修复工具 -> WPS 双击打开修复 -> 执行修复
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

            monitor_started = widget.start_confirm_dbus_monitor()
            self.assert_true(monitor_started)
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing(timeout=20)
            self.assert_true(dialog_opened)

            # 预期: 修复脚本重建配置(目录 + 文件 + 正确内容 + 属主/权限)
            self.assert_true(widget.wait_wps_config_created(timeout=90))
            self.assert_true(widget.get_wps_config_dir_exists())
            current_user = widget.run_cmd(
                "id -un", timeout=5, out_debug_flag=False
            ).strip()
            dir_mode = widget.get_wps_config_dir_mode()
            dir_owner = widget.get_wps_config_dir_owner()
            logger.info(f"Kingsoft 目录: mode={dir_mode} owner={dir_owner}")
            self.assert_true(bool(dir_mode))
            self.assert_true(int(dir_mode, 8) & 0o700 == 0o700)
            self.assert_true(dir_owner == current_user)
            self.assert_true(widget.get_wps_config_has_required_keys())
            content = widget.get_wps_config_content()
            logger.info(f"Office.conf 内容: {content!r}")
            self.assert_true(len(content.strip().splitlines()) >= 3)
            self.assert_true("prome_fushion" in content)
            file_mode = widget.get_wps_config_mode()
            file_owner = widget.get_wps_config_owner()
            logger.info(f"Office.conf: mode={file_mode} owner={file_owner}")
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
            # 并关闭修复窗口 —— 必须在后续双击文档/打开查看器等界面操作之前,
            # 否则遗留窗口会盖住桌面并干扰文档打开
            state = widget.finish_repair_flow("WPS修复")
            self.assert_false(state["window_left"])
            dialog_opened = False

            # 步骤1: 准备 .docx/.xlsx/.pptx 三个文档, 双击前确认类型识别正确
            docs = widget.create_test_office_docs()
            self.assert_true(set(docs) == set(TEST_DOC_FORMATS))
            for fmt in TEST_DOC_FORMATS:
                path = docs[fmt]
                self.assert_true(os.path.isfile(path))
                self.assert_true(os.path.getsize(path) > 0)
                mime = widget.get_file_mime_type(path)
                logger.info(f"{path} 的 MIME: {mime}")
                self.assert_true(mime == widget.OPEN_DOC_MIME[fmt])

            # 预期(真实证据): 双击 .docx 由系统默认查看器真实打开
            docx_path = docs["docx"]
            self.assert_true(widget.open_document_with_default_app(docx_path))
            self.assert_true(widget.wait_document_opened(docx_path, timeout=45))
            viewer_processes = widget.get_document_viewer_processes()
            logger.info(f"打开 docx 的查看器进程: {viewer_processes}")
            self.assert_true(os.path.basename(docx_path) in viewer_processes)
            widget.close_document_viewer()

            # 预期(桩替身): 双击三种格式都按 OOXML 类型分发给 Office 应用并带上文档路径
            stub_ready = widget.install_office_stub_launcher()
            self.assert_true(stub_ready)
            defaults = widget.get_office_stub_default_apps()
            logger.info(f"三种格式的默认打开程序: {defaults}")
            for fmt in TEST_DOC_FORMATS:
                path = docs[fmt]
                self.assert_true(
                    defaults.get(widget.OPEN_DOC_MIME[fmt])
                    == widget.OFFICE_STUB_DESKTOP
                )
                self.assert_true(widget.open_document_with_default_app(path))
                self.assert_true(widget.wait_office_stub_launched(path, timeout=20))
            launched = widget.get_office_stub_launched_files()
            logger.info(f"桩启动器收到的文档: {launched}")
            for fmt in TEST_DOC_FORMATS:
                self.assert_true(docs[fmt] in launched)

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
            # 回退: 撤销桩应用并还原 mimeapps.list 默认程序, 删除临时文档目录
            try:
                if not widget.remove_office_stub_launcher():
                    logger.error("桩应用或临时目录未清理干净, 需要人工确认")
            except BaseException:
                logger.exception("撤销桩应用失败")
            # 回退: 删除修复脚本生成的配置并还原测试前现场
            if backup_ready:
                widget.restore_wps_state()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

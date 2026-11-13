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

    def test_mycase_185(self):
        """音频修复-异常-jq 缺失

        前置(按用例库描述): 系统缺少 jq 工具。等价实现: 临时将 /usr/bin/jq
        移走(不卸载软件包, 避免 apt 网络依赖), 使 `command -v jq` 失败,
        修复结束后原样移回并校验。
        执行音频修复, 断言详情页输出出现
        "[警告] 无法读取 DDE Cards 状态或未检测到 jq 工具, 跳过动态端口启用",
        且修复流程仍能完成、应用不崩溃, 结束后关闭应用。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        jq_path = "/usr/bin/jq"
        jq_backup = "/usr/bin/jq.autotest_bak"
        hidden = False
        try:
            dependency = widget.ensure_package_installed("jq", probe_cmd="jq")
            self.assert_true(dependency["installed"])
            widget.sudo_run_cmd(
                f"mv -f {jq_path} {jq_backup}", timeout=15, out_debug_flag=False
            )
            self.assert_true(
                not str(
                    widget.run_cmd(
                        "command -v jq", timeout=5, out_debug_flag=False
                    )
                ).strip()
            )
            hidden = True

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            widget.click_repair_card_by_name("音频设备修复")
            self.assert_true(widget.get_repair_detail_showing())
            widget.click_repair_start_button()
            widget.handle_shell_repair_dialog()

            self.assert_true(widget.get_repair_completion_status())
            output_text = widget.get_shell_repair_output_text()
            logger.info(f"[2032343] 详情页输出尾部: {output_text[-400:]!r}")
            self.assert_true("未检测到 jq 工具" in output_text)

            # 应用在异常场景下不崩溃, 页面保持稳定
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_repair_detail_showing())
            # 异常场景也要点掉脚本末尾无超时提示框, 否则修复窗口关不掉
            state = widget.finish_repair_flow("音频修复")
            self.assert_false(state["window_left"])
        finally:
            # 失败路径同样清理: 提示框无超时, 不点掉会阻塞脚本且窗口关不掉
            widget.finish_repair_flow("音频修复")
            widget.kill_pc_manager()
            sleep(2)
            if hidden:
                widget.sudo_run_cmd(
                    f"mv -f {jq_backup} {jq_path}", timeout=15, out_debug_flag=False
                )
            self.assert_true(widget.is_jq_installed())
            self.assert_true(
                str(
                    widget.run_cmd(
                        "command -v jq", timeout=5, out_debug_flag=False
                    )
                ).strip()
                == jq_path
            )

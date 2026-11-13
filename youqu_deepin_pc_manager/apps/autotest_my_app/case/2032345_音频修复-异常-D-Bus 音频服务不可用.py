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

    def test_mycase_040(self):
        """音频修复-异常-D-Bus 音频服务不可用

        前置(按用例库描述, 附件脚本使 D-Bus 音频服务不可读)。等价实现:
        临时把 /usr/bin/gdbus 换成"exit 1"桩(原二进制备份), 使修复脚本对
        com.deepin.daemon.Audio 的 gdbus 查询全部失败(CARDS_JSON 为空,
        且不产生 command-not-found 级噪声), 与"D-Bus 音频服务不可读"走
        同一跳过分支; 结束后删除桩并移回原二进制校验。

        断言: 详情页输出出现
        "[警告] 无法读取 DDE Cards 状态或未检测到 jq 工具, 跳过动态端口启用",
        修复流程不报错且能完成, 应用/详情页保持稳定。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        gdbus_path = "/usr/bin/gdbus"
        gdbus_backup = "/usr/bin/gdbus.autotest_bak"
        hidden = False
        try:
            self.assert_true(
                str(
                    widget.run_cmd(
                        "command -v gdbus", timeout=5, out_debug_flag=False
                    )
                ).strip()
                == gdbus_path
            )
            widget.sudo_run_cmd(
                f"mv -f {gdbus_path} {gdbus_backup} && "
                f"printf '#!/bin/sh\\nexit 1\\n' > {gdbus_path} && "
                f"chmod +x {gdbus_path}",
                timeout=15,
                out_debug_flag=False,
            )
            hidden = True
            self.assert_true(
                str(
                    widget.run_cmd(
                        "command -v gdbus", timeout=5, out_debug_flag=False
                    )
                ).strip()
                == gdbus_path
            )
            self.assert_true(
                str(
                    widget.run_cmd(
                        "head -1 /usr/bin/gdbus", timeout=5, out_debug_flag=False
                    )
                ).strip()
                == "#!/bin/sh"
            )
            self.assert_true(
                "RC=1"
                in str(
                    widget.run_cmd(
                        "gdbus --version >/dev/null 2>&1; echo RC=$?",
                        timeout=5,
                        out_debug_flag=False,
                    )
                )
            )

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
            logger.info(f"[2032345] 详情页输出尾部: {output_text[-400:]!r}")
            self.assert_false("gdbus：未找到命令" in output_text)
            self.assert_true("无法读取 DDE Cards 状态" in output_text)
            self.assert_true("跳过动态端口启用" in output_text)

            # 不可用场景下应用不崩溃, 详情页保持稳定
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
                    f"rm -f {gdbus_path} && mv -f {gdbus_backup} {gdbus_path}",
                    timeout=15,
                    out_debug_flag=False,
                )
            self.assert_true(
                str(
                    widget.run_cmd(
                        "command -v gdbus", timeout=5, out_debug_flag=False
                    )
                ).strip()
                == gdbus_path
            )

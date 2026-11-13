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

    def test_mycase_186(self):
        """音频修复-异常-PipeWire 未运行

        前置(按用例库描述): PipeWire 未运行。实测测试机(V20)未安装
        PipeWire, 全局自启链接不存在、用户服务为 inactive, 本身即该异常
        场景; 用例先断言该状态, 再执行音频修复。
        断言: 详情页输出出现跳过提示——"[OK] PipeWire 全局自启已处于禁用
        状态, 跳过配置修改。" 与 "[OK] PipeWire 用户服务与套接字已处于停止
        状态。"; 修复完成且应用稳定。结束后关闭应用。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        try:
            widget.stop_pipewire()
            self.assert_false(widget.get_pipewire_running_status())

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
            logger.info(f"[2032347] 详情页输出尾部: {output_text[-400:]!r}")
            self.assert_true("跳过配置修改" in output_text)
            self.assert_true("已处于停止状态" in output_text)
            self.assert_false(widget.get_pipewire_running_status())

            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_repair_detail_showing())
            # 异常场景也要点掉脚本末尾无超时提示框, 否则修复窗口关不掉
            state = widget.finish_repair_flow("音频修复")
            self.assert_false(state["window_left"])
        finally:
            # 失败路径同样清理: 提示框无超时, 不点掉会阻塞脚本且窗口关不掉
            widget.finish_repair_flow("音频修复")
            widget.start_pipewire()
            widget.kill_pc_manager()
            sleep(2)

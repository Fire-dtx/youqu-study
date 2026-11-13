#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):

    def setup_method(self):
        """用例前置: 确保当前用户已拥有 lpadmin 权限"""
        widget = MyAppWidget(check_start=False)
        if not widget.get_lpadmin_permission_status():
            widget.restore_lpadmin_permission()
            sleep(1)

    def teardown_method(self):
        """用例后置: 恢复用户原始 lpadmin 权限状态并关闭电脑管家"""
        widget = MyAppWidget(check_start=False)
        if not widget.get_lpadmin_permission_status():
            widget.restore_lpadmin_permission()
            sleep(1)
        # 收尾兜底(等价 finally, 用例无 try/finally): 插件末尾 openinfobox
        # timeoutMs=0 不自动消失, 必须点掉再关应用, 否则弹窗残留
        try:
            widget.finish_repair_flow()
        except BaseException:
            pass
        widget.kill_pc_manager()

    def test_mycase_172(self):
        """打印机修复--lpadmin 权限检查与修复-用户已有 lpadmin 权限

        描述: 前置"用户已有 lpadmin 权限", 步骤"确保当前用户在 lpadmin 组中,
        执行脚本", 预期输出"[INFO] 用户...已拥有 lpadmin 权限"。

        产品依据(plugin-printer-fix/config.json + entry.sh):
        - 修复步骤第 1 条"检查并添加 lpadmin 权限", 脚本以 root 身份运行;
        - 用户在组内时直接给出 [INFO] 已拥有权限, 不再重复 usermod。

        等价判定: 修复对话框输出出现"已拥有 lpadmin 权限"的 [INFO] 行,
        同时系统事实仍是用户在 lpadmin 组内, 且流程未执行"添加权限"动作。
        """
        widget = MyAppWidget(check_start=False)

        # 1) 前置: 用户已在 lpadmin 组内(用例前置条件本身被验证)
        self.assert_true(widget.get_lpadmin_group_exists())
        self.assert_true(widget.get_lpadmin_permission_status())
        logger.info(f"前置确认: 用户已在 lpadmin 组 (user={widget.get_current_user()})")

        # 2) 启动电脑管家并进入修复工具页面
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_repair_nav()
        self.assert_true(widget.get_repair_page_showing(timeout=30))
        self.assert_true(widget.get_repair_cards_view_showing())

        # 3) 进入打印机修复详情并点击开始修复
        widget.click_repair_card_by_name("打印机修复")
        self.assert_true(widget.get_repair_detail_showing())
        widget.click_repair_start_button()
        self.assert_true(widget.get_repair_dialog_showing(timeout=30))
        widget.handle_shell_repair_dialog()

        # 4) 预期: 输出 [INFO] 用户 ... 已拥有 lpadmin 权限
        self.assert_true(
            widget.wait_repair_output_contains("检查并添加 lpadmin 权限", timeout=180)
        )
        self.assert_true(
            widget.wait_repair_output_contains("已拥有 lpadmin 权限", timeout=120)
        )
        self.assert_true(widget.get_repair_output_contains("[INFO]", timeout=10))

        output = widget.get_repair_output_text()
        logger.info(f"[2010551] 打印机修复输出: {output!r}")

        # 5) 已拥有权限时不应再执行"添加"动作
        if "[OK] 已为用户" in output:
            logger.error("用户已有权限, 产品仍输出了重新添加权限的结果行")
        self.assert_false("[OK] 已为用户" in output)

        # 6) 系统事实: 权限仍在, 流程正常结束
        self.assert_true(widget.get_lpadmin_permission_status())
        self.assert_true(widget.get_repair_completion_status())
        # 收尾: 点掉无超时的完成提示框并关闭修复窗口
        state = widget.finish_repair_flow()
        self.assert_false(state["window_left"])

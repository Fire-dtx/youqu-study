#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):

    def setup_method(self):
        """用例前置: 移除当前用户的 lpadmin 权限"""
        widget = MyAppWidget(check_start=False)
        widget.remove_lpadmin_permission()
        sleep(1)

    def teardown_method(self):
        """用例后置: 确保用户 lpadmin 权限已恢复"""
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

    def test_mycase_171(self):
        """打印机修复--lpadmin 权限检查与修复-用户无 lpadmin 权限

        描述: 前置/步骤为"将当前用户从 lpadmin 组移除(gpasswd -d uos lpadmin)",
        预期输出"[OK] 已为用户...添加 lpadmin 权限"及
        "[WARN] 用户需重新登录后权限生效"。

        产品依据(plugin-printer-fix/config.json + entry.sh):
        - 修复步骤第 1 条就是"检查并添加 lpadmin 权限", 脚本以 root 身份运行;
        - 脚本把用户加回 lpadmin 组后输出 [OK]/[WARN] 两类结果行。

        等价判定: 除了修复对话框输出里的两条文案, 同时以系统事实校验闭环 ——
        用例开始时用户确实不在 lpadmin 组, 修复后 getent group lpadmin 里出现
        当前用户(权限真的加上了), 修复流程正常结束。
        """
        widget = MyAppWidget(check_start=False)

        # 1) 前置: 当前用户确实没有 lpadmin 权限, 且 lpadmin 组存在
        self.assert_true(widget.get_lpadmin_group_exists())
        self.assert_false(widget.get_lpadmin_permission_status())
        logger.info(f"前置确认: 用户当前不在 lpadmin 组 (user={widget.get_current_user()})")

        # 2) 启动电脑管家并进入修复工具页面
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_repair_nav()
        self.assert_true(widget.get_repair_page_showing(timeout=30))
        self.assert_true(widget.get_repair_cards_view_showing())

        # 3) 点击打印机修复卡片, 确认详情页(描述里的修复入口)
        widget.click_repair_card_by_name("打印机修复")
        self.assert_true(widget.get_repair_detail_showing())

        # 4) 点击开始修复; 该插件 executionMode=root, 会弹鉴权框, 需提交密码
        widget.click_repair_start_button()
        self.assert_true(widget.get_repair_dialog_showing(timeout=30))
        widget.handle_shell_repair_dialog()

        # 5) 预期 1: 输出 [OK] 已为用户 ... 添加 lpadmin 权限
        self.assert_true(
            widget.wait_repair_output_contains("添加 lpadmin 权限", timeout=180)
        )
        self.assert_true(widget.get_repair_output_contains("[OK] 已为用户", timeout=30))

        # 6) 预期 2: 提示重新登录后权限生效
        self.assert_true(
            widget.wait_repair_output_contains("重新登录后权限生效", timeout=60)
        )
        self.assert_true(widget.get_repair_output_contains("[WARN]", timeout=10))

        output = widget.get_repair_output_text()
        logger.info(f"[2010549] 打印机修复输出: {output!r}")

        # 7) 系统事实校验: 权限真的被加回 lpadmin 组
        self.assert_true(widget.wait_lpadmin_permission_restored(timeout=60))

        # 8) 修复流程正常结束
        self.assert_true(widget.get_repair_completion_status())
        # 收尾: 点掉无超时的完成提示框并关闭修复窗口
        state = widget.finish_repair_flow()
        self.assert_false(state["window_left"])

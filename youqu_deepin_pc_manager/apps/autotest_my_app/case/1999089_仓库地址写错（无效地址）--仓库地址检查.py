#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/04
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep, logger


class TestMyCase(BaseCase):

    def test_mycase_319(self):
        """仓库地址写错（无效地址）--仓库地址检查：
        将 apt 源指向不可达的保留地址后，点击"更新环境检测"卡片，
        "仓库地址检查"项存在、该分项检出问题，且单项结论为异常；
        用例结束后恢复 apt 源。"""
        widget = MyAppWidget(check_start=False)

        widget.backup_apt_sources()
        widget.set_unreachable_repo()

        try:
            self.assert_false(widget.get_repo_address_reachable())

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            # 点击"更新环境检测"卡片, 真实触发该分项检测
            self.assert_true(widget.run_detection_item("更新环境检测"))

            self.assert_true(widget.get_detection_item_present("更新环境检测", "仓库地址检查"))
            # 只点了"更新环境检测", 其它分项不应被检查(区别于全面检测)
            self.assert_true(widget.is_only_group_detected("更新环境检测"))

            state = widget.get_detection_group_state("更新环境检测")
            self.assert_true(state["total"] > 0)
            self.assert_true(state["issues"] > 0)

            verdict, detail = widget.get_detection_item_verdict("repository_url")
            logger.info(f"仓库地址检查单项结论(无效地址): {verdict}, 原始结果: {detail}")
            self.assert_false(verdict)

            sleep(2)
        finally:
            widget.kill_pc_manager()
            self.assert_true(widget.restore_apt_sources())

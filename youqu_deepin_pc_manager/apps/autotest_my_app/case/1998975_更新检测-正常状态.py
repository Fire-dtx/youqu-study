#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/04
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_017(self):
        """更新检测-正常状态：点击"更新环境检测"卡片真实执行检测，
        该分项的 4 个检测项均存在、整组跑完且无问题，单项结论均为正常。"""
        widget = MyAppWidget(check_start=False)

        # 前置: sources.list 不得残留 immutable 属性, 否则仓库地址权限检查会报异常
        if widget.get_source_file_immutable_status():
            widget.remove_source_file_immutable()
        self.assert_false(widget.get_source_file_immutable_status())

        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        self.assert_true(widget.get_detection_functional_modules_showing())

        # 点击"更新环境检测"卡片, 真实触发该分项检测
        self.assert_true(widget.run_detection_item("更新环境检测"))

        for item in ("boot分区空间检测", "仓库地址检查", "仓库地址权限检查", "本地环境检查"):
            self.assert_true(widget.get_detection_item_present("更新环境检测", item))

        # 只点了"更新环境检测", 其它分项不应被检查(区别于全面检测)
        self.assert_true(widget.is_only_group_detected("更新环境检测"))

        state = widget.get_detection_group_state("更新环境检测")
        self.assert_true(state["total"] > 0)
        self.assert_equal(state["total"], state["checked"])
        self.assert_equal(0, state["issues"])

        for item_id in ("boot_partition_space", "repository_url", "repository_permission",
                        "local_environment"):
            verdict, detail = widget.get_detection_item_verdict(item_id)
            logger.info(f"更新环境检测/{item_id} 单项结论: {verdict}, 原始结果: {detail}")
            self.assert_true(verdict)

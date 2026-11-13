#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_286(self):
        """软件包状态检查正常：点击"更新环境检测"分项卡片真实执行检测。

        1.1.7 界面中"更新环境检测"分项包含 boot分区空间检测/仓库地址检查/
        仓库地址权限检查/本地环境检查 4 项，"软件包状态检查"的判定已并入
        "本地环境检查"(会话守护进程 local_environment 任务)。
        断言：该分项跑完且 0 项问题，本地环境检查结论为正常。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        # 导航到系统检测页面
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())
        # 验证电脑管家软件包已正确安装(包状态正常)
        self.assert_true(widget.get_pc_manager_installed())
        # 验证软件包版本号可正常获取
        self.assert_true(bool(widget.get_pc_manager_version()))

        # 点击"更新环境检测"卡片, 真实触发该分项检测
        self.assert_true(widget.run_detection_item("更新环境检测"))

        self.assert_true(widget.get_detection_item_present("更新环境检测", "本地环境检查"))
        # 只点了"更新环境检测", 其它分项不应被检查(区别于全面检测)
        self.assert_true(widget.is_only_group_detected("更新环境检测"))
        state = widget.get_detection_group_state("更新环境检测")
        self.assert_true(state["total"] > 0)
        self.assert_equal(state["total"], state["checked"])
        self.assert_equal(0, state["issues"])

        verdict, detail = widget.get_detection_item_verdict("local_environment")
        logger.info(f"本地环境检查单项结论: {verdict}, 原始结果: {detail}")
        self.assert_true(verdict)

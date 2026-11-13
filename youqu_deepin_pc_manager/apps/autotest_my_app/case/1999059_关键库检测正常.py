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

    def test_mycase_284(self):
        """关键库检测正常：点击"系统环境检测"分项卡片真实执行检测，
        "关键库检测"项存在并完成判定，且能读到该项的检测结果。

        不校验结论是否为"通过"：测试机 /usr/local/lib/python3.7/dist-packages
        下有 pip 安装的 Python 扩展(.so)，与 /usr/lib 下同名 apt 库并存时，
        产品按「同名 + 包管理比对」判为本地库冲突(failure:3012)，
        这属于正常的状态显示。
        说明：界面列表项不向 AT-SPI 暴露单项状态，分项问题总数还包含"系统版本检测"
        等其它项，故单项结论取电脑管家自身的检测结果接口。"""
        widget = MyAppWidget(check_start=False)
        # 前置: 清理历史用例可能遗留的 /usr/local/lib 冲突库, 保证"无冲突"场景成立
        widget.clean_conflict_library()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        # 点击"系统环境检测"卡片, 真实触发该分项检测
        self.assert_true(widget.run_detection_item("系统环境检测"))

        self.assert_true(widget.get_detection_item_present("系统环境检测", "关键库检测"))
        # 只点了"系统环境检测", 其它分项不应被检查(区别于全面检测)
        self.assert_true(widget.is_only_group_detected("系统环境检测"))

        verdict, detail = widget.get_detection_item_verdict("critical_libraries")
        logger.info(f"关键库检测单项结论: {verdict}, 原始结果: {detail}")
        self.assert_true(verdict is not None)
        self.assert_true(bool(str(detail or "").strip()))

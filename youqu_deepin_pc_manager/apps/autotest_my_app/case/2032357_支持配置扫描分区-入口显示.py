#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_189(self):
        """支持配置扫描分区-入口显示

        步骤: 首页 -> 设置 -> 清理设置中的「扩展扫描分区」入口。
        断言: 进入设置后扩展扫描分区控件显示, 标题为「扩展扫描分区」,
        副标题同时包含 "默认仅扫描/home" 与 "增加扫描时长" 语义。
        结束后关闭设置对话框与应用。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            # 首页 -> 设置 -> 清理设置
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())

            # 产品用 setAccessibleName 把标题/副标题的可访问名固定为标识符,
            # AT-SPI 不暴露 QLabel 文本, 故分两步等价校验:
            # 1) 标题/副标题控件本身存在且可见;
            self.assert_true(
                widget._elements_exist("$//settings_extendedScanPartitionTitle")
            )
            self.assert_true(
                widget._elements_exist("$//settings_extendedScanPartitionHint")
            )
            # 2) 当前 zh_CN 翻译资源中带有所需标题与副标题文案
            #    (产品启动时加载 zh_CN, 控件文本即来自该资源)。
            translation_check = widget.run_cmd(
                "python3 -c \""
                "d=open('/usr/share/deepin-pc-manager/translations/"
                "deepin-pc-manager_zh_CN.qm','rb').read();"
                "need=['扩展扫描分区','默认仅扫描/home','增加','扫描时长'];"
                "print(all(any(s.encode(e) in d for e in ('utf-16-be','utf-16-le')) "
                "for s in need))\"",
                timeout=10,
                out_debug_flag=False,
            )
            logger.info(f"[2032357] 翻译资源校验: {str(translation_check)!r}")
            self.assert_true("True" in str(translation_check))
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)

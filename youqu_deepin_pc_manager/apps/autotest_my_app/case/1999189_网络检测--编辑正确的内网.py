#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

# 正确的内网地址: www.uniontech.com 在测试环境可解析, ping 通(约 21ms),
# HTTP 返回 301, 可作为"正确的域名"场景。
# 备选的正确 IP 10.20.42.50 在测试环境 ping 100% 丢包、HTTP 无响应,
# 不能用于断言"检测正常", 故不使用。
VALID_INTRANET_ADDRESS = "www.uniontech.com"


class TestMyCase(BaseCase):

    def test_mycase_110(self):
        """网络检测--编辑正确的内网：在"设置-基础设置-网络设置检测"把网络模式
        切为内网, 内网地址填入可达的域名 www.uniontech.com, 断言:
        1. 输入框回显该值, 配置项 basic.network.intranetAddress 落盘为该值;
        2. 网络模式为 intranet;
        3. 点击"网络检测"卡片后 网络访问(network_connectivity) 结论正常,
           且检测目标就是该内网地址, 网络检测 0 项问题。
        用例结束恢复原始网络设置。"""
        widget = MyAppWidget(check_start=False)
        widget.backup_network_settings()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.open_basic_settings_page())

            # ===== 切内网并填入可达的正确地址 =====
            self.assert_equal("内网", widget.switch_network_mode("内网"))
            self.assert_true(widget.is_intranet_address_row_showing())
            widget.set_intranet_address(VALID_INTRANET_ADDRESS)
            self.assert_equal(
                VALID_INTRANET_ADDRESS, widget.get_intranet_address_text()
            )
            self.assert_equal("intranet", widget.get_network_mode())
            self.assert_equal(
                VALID_INTRANET_ADDRESS, widget.get_intranet_address_config()
            )
            widget.close_settings_dialog()

            # ===== 内网模式下检测目标为该地址, 网络访问项应正常 =====
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("网络检测"))
            self.assert_true(widget.get_detection_item_present("网络检测", "网络访问"))
            verdict, detail = widget.get_detection_item_verdict("network_connectivity")
            logger.info(
                f"正确内网地址 {VALID_INTRANET_ADDRESS} 的网络访问结论: "
                f"{verdict}, 原始结果: {detail}"
            )
            self.assert_true(verdict)
            self.assert_true(VALID_INTRANET_ADDRESS in str(detail))
            state = widget.get_detection_group_state("网络检测")
            self.assert_equal(state["total"], state["checked"])
            self.assert_equal(0, state["issues"])
        finally:
            try:
                widget.close_settings_dialog()
            except BaseException:
                pass
            widget.restore_network_settings()
            widget.kill_pc_manager()

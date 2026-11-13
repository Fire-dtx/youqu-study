#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

# 两种错误格式的内网地址:
# - www.uniontech: 缺少一级域名, DNS 无法解析;
# - 192.168.1.256: 256 超出 IPv4 单段范围, 不是合法 IP。
# 产品只对输入框做红框告警, 仍会把值写入配置, 连通性检测必然失败。
WRONG_INTRANET_ADDRESSES = ("www.uniontech", "192.168.1.256")


class TestMyCase(BaseCase):

    def test_mycase_109(self):
        """网络检测--编辑错误的内网：在"设置-基础设置-网络设置检测"把网络模式
        切为内网, 依次在内网地址输入框填入错误格式的域名 www.uniontech 和
        错误格式的 IP 192.168.1.256, 每个值断言:
        1. 输入框回显该值, 配置项 basic.network.intranetAddress 落盘为该值;
        2. 网络模式为 intranet;
        3. 点击"网络检测"卡片后 网络访问(network_connectivity) 结论异常。
        用例结束恢复原始网络设置。"""
        widget = MyAppWidget(check_start=False)
        widget.backup_network_settings()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.open_basic_settings_page())

            # ===== 切内网模式, 地址行出现 =====
            self.assert_equal("内网", widget.switch_network_mode("内网"))
            self.assert_true(widget.is_intranet_address_row_showing())

            for index, address in enumerate(WRONG_INTRANET_ADDRESSES):
                # 每轮检测前设置对话框已关闭, 第二轮重新打开并回到基础设置页
                if index:
                    widget.open_settings_dialog()
                    self.assert_true(widget.open_basic_settings_page())

                # ===== 填入错误格式地址, 断言回显与落盘 =====
                widget.set_intranet_address(address)
                self.assert_equal(address, widget.get_intranet_address_text())
                self.assert_equal("intranet", widget.get_network_mode())
                self.assert_equal(address, widget.get_intranet_address_config())
                widget.close_settings_dialog()

                # ===== 内网模式下检测目标为该错误地址, 网络访问项应异常 =====
                widget.click_detection_nav()
                self.assert_true(widget.get_detection_page_showing())
                self.assert_true(widget.run_detection_item("网络检测"))
                self.assert_true(
                    widget.get_detection_item_present("网络检测", "网络访问")
                )
                verdict, detail = widget.get_detection_item_verdict(
                    "network_connectivity"
                )
                logger.info(
                    f"错误内网地址 {address} 的网络访问结论: {verdict}, "
                    f"原始结果: {detail}"
                )
                self.assert_false(verdict)
                # 检测失败时 daemon 的单项结果只回错误码
                # (4012 NetworkConnectivityAbnormal), 不回探测目标;
                # 目标地址本身已在上面的配置断言中覆盖。
                self.assert_true("4012" in str(detail))
                state = widget.get_detection_group_state("网络检测")
                self.assert_true(state["issues"] >= 1)
        finally:
            try:
                widget.close_settings_dialog()
            except BaseException:
                pass
            widget.restore_network_settings()
            widget.kill_pc_manager()

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

INTRANET_ADDRESS = "127.0.0.1"


class TestMyCase(BaseCase):

    def test_mycase_111(self):
        """网络检测--网络环境切换：在"设置-基础设置-网络设置检测"依次切换
        公网 → 内网 → 公网 → 内网, 断言:
        1. 下拉框显示值与配置 basic.network.mode 同步变化(public/intranet);
        2. 内网地址行仅内网模式下可见, 公网模式隐藏;
        3. 内网地址在两模式间切换后保持不变, 不会随切换被清空。
        用例结束恢复原始网络设置。"""
        widget = MyAppWidget(check_start=False)
        widget.backup_network_settings()
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.open_basic_settings_page())

            # ===== 公网模式: 地址行隐藏 =====
            self.assert_equal("公网", widget.switch_network_mode("公网"))
            self.assert_equal("public", widget.get_network_mode())
            self.assert_false(widget.is_intranet_address_row_showing())

            # ===== 切内网: 地址行出现, 写入内网地址 =====
            self.assert_equal("内网", widget.switch_network_mode("内网"))
            self.assert_equal("intranet", widget.get_network_mode())
            self.assert_true(widget.is_intranet_address_row_showing())
            widget.set_intranet_address(INTRANET_ADDRESS)
            self.assert_equal(INTRANET_ADDRESS, widget.get_intranet_address_config())

            # ===== 切回公网: 地址行隐藏, 地址保留在配置中 =====
            self.assert_equal("公网", widget.switch_network_mode("公网"))
            self.assert_equal("public", widget.get_network_mode())
            self.assert_false(widget.is_intranet_address_row_showing())
            self.assert_equal(INTRANET_ADDRESS, widget.get_intranet_address_config())

            # ===== 再次切内网: 地址回显不变 =====
            self.assert_equal("内网", widget.switch_network_mode("内网"))
            self.assert_equal("intranet", widget.get_network_mode())
            self.assert_equal(INTRANET_ADDRESS, widget.get_intranet_address_text())
            logger.info(
                f"网络环境切换完成, 当前模式: {widget.get_network_mode_ui()}, "
                f"内网地址: {INTRANET_ADDRESS}"
            )
        finally:
            try:
                widget.close_settings_dialog()
            except BaseException:
                pass
            widget.restore_network_settings()
            widget.kill_pc_manager()

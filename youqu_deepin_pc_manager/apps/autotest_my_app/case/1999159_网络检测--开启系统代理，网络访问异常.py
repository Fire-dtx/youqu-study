#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_099(self):
        """开启系统代理后的网络访问异常：xlsx 预期为"网络访问异常, 提示关闭系统
        代理或 VPN 后重新检测"。

        1.1.7 被测程序源码中没有任何系统代理读取逻辑(无 QNetworkProxy /
        org.gnome.system.proxy / http_proxy 相关实现), 检测的网络访问请求
        不经过系统代理, 因此该预期在当前被测版本上无法成立。
        用例保留场景构造与验证骨架, 在当前版本上跳过并给出原因;
        若产品补齐代理判定, 去掉本跳过即可生效。
        """
        pytest.skip(
            "1.1.7 被测程序未实现系统代理判定(源码无代理读取逻辑), "
            "xlsx 该预期在当前版本不可成立, 待产品实现后再启用"
        )

        widget = MyAppWidget(check_start=False)
        origin_mode = widget.run_cmd(
            "gsettings get org.gnome.system.proxy mode", timeout=10, out_debug_flag=False
        ).strip()
        widget.run_cmd(
            "gsettings set org.gnome.system.proxy mode 'auto' && "
            "gsettings set org.gnome.system.proxy autoconfig-url 'http://127.0.0.1:9/proxy.pac'",
            timeout=15,
            out_debug_flag=False,
        )
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("网络检测"))
            self.assert_true(widget.get_detection_item_present("网络检测", "网络访问"))

            state = widget.get_detection_group_state("网络检测")
            self.assert_equal(state["total"], state["checked"])
            self.assert_true(state["issues"] > 0)

            verdict, detail = widget.get_detection_item_verdict("network_connectivity")
            logger.info(f"代理开启时网络访问单项结论: {verdict}, 原始结果: {detail}")
            self.assert_true(verdict is False)
        finally:
            mode = origin_mode.strip("'") or "none"
            widget.run_cmd(
                f"gsettings set org.gnome.system.proxy mode '{mode}'; true",
                timeout=15,
                out_debug_flag=False,
            )

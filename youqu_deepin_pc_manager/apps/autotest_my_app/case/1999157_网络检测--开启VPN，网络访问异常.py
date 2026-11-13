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

    def test_mycase_098(self):
        """开启 VPN 后的网络访问：前置要求测试机已连接 VPN 环境(xlsx 前置为
        连接手机热点后再连公司 VPN)。测试机无 VPN 服务端与账号,
        无法构造, 跳过并给出原因。"""
        pytest.skip("前置不满足: 测试机无 VPN 服务端/账号, 无法构造公司 VPN 连接场景")

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

    def test_mycase_105(self):
        """未检测到有效网络设备：需移除/禁用唯一网卡。该操作会中断
        管理链路且虚拟机无法在无网卡状态下被远程驱动, 跳过并给出原因。"""
        pytest.skip("前置需禁用唯一网卡, 会中断测试机管理链路")

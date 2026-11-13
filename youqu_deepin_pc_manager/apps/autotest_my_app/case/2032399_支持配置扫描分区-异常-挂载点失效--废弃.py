#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_254(self):
        """支持配置扫描分区-异常-挂载点失效--废弃：该用例已废弃，跳过执行"""
        import pytest
        pytest.skip("用例已废弃")

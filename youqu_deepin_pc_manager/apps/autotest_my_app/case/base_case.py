#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
::Author:ut000635
::Date  :2026/09/10 13:34:42
"""
from apps.autotest_my_app.my_app_assert import MyAppAssert


class BaseCase(MyAppAssert):
    """用例基类"""
    APP_NAME = "deepin-pc-manager"

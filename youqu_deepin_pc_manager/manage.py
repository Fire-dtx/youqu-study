#!/usr/bin/env python3
# _*_ coding:utf-8 _*_

# SPDX-FileCopyrightText: 2023 UnionTech Software Technology Co., Ltd.

# SPDX-License-Identifier: GPL-2.0-only
# pylint: disable=C0114
# pylint: disable=wrong-import-position
import os
import sys
import traceback
from argparse import ArgumentParser


def _reexec_in_project_venv():
    """框架依赖装在项目 .venv 中，不装系统 site-packages。

    非登录 shell（ssh 直接执行、cron、CI）不加载 ~/.profile，PATH 里没有
    .venv/bin；此时自动切到 .venv 解释器，避免用系统 python3 报缺包。
    """
    if os.environ.get("YOUQU_VENV_REEXEC") == "1":
        return
    venv_prefix = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")
    venv_python = os.path.join(venv_prefix, "bin", "python3")
    if not os.path.exists(venv_python):
        return
    if os.path.realpath(sys.prefix) == os.path.realpath(venv_prefix):
        return
    os.environ["YOUQU_VENV_REEXEC"] = "1"
    os.execv(venv_python, [venv_python, os.path.abspath(__file__), *sys.argv[1:]])


_reexec_in_project_venv()

from setting.globalconfig import GlobalConfig
from setting.globalconfig import SystemPath

# SSH 登录的会话里没有桌面的 XDG_* 变量，Qt/DTK 会按"无桌面"退化：
# 左侧栏不向 kwin 申请模糊区域、主题与图标回落到默认值，导致界面断言漂移。
# 这里按能力探测（已存在则尊重），而不是按 OS 版本写死。
os.environ.setdefault("DISPLAY", ":0")
os.environ.setdefault("XDG_CURRENT_DESKTOP", "DDE")
os.environ.setdefault("XDG_SESSION_DESKTOP", "deepin")
if os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("XDG_SESSION_TYPE", "wayland")
    os.environ.setdefault("GDMSESSION", "Wayland")
else:
    os.environ.setdefault("XDG_SESSION_TYPE", "x11")
    os.environ.setdefault("GDMSESSION", "deepin")
    # DTK 只有走 dxcb 平台插件才会创建模糊区域；显式指定 xcb 子插件。
    os.environ.setdefault("QT_QPA_PLATFORM", "dxcb;xcb")
os.environ["PIPENV_VERBOSITY"] = "-1"
os.environ["XAUTHORITY"] = f"{GlobalConfig.HOME}/.Xauthority"

for i in SystemPath:
    if i.value in sys.path:
        continue
    sys.path.append(i.value)

from funnylog import logger
from funnylog.conf import setting as log_setting

log_setting.LOG_FILE_PATH = GlobalConfig.REPORT_PATH


class Manage:
    __author__ = "mikigo<huangmingqiang@uniontech.com>"

    def __init__(self):
        from src.plugins.mng import trim
        from src.plugins.mng import help_tip
        from src.plugins.mng import SubCmd

        trim()
        logger(GlobalConfig.LOG_LEVEL)

        self.cmd_args = sys.argv[1:]
        if not self.cmd_args:
            print(help_tip())
            sys.exit(1)
        parser = ArgumentParser(epilog=self.__author__)
        subparsers = parser.add_subparsers(help="子命令")

        sub_parser_remote = subparsers.add_parser(SubCmd.remote.value)
        sub_parser_run = subparsers.add_parser(SubCmd.run.value)
        sub_parser_pms = subparsers.add_parser(SubCmd.pmsctl.value)
        sub_parser_csv = subparsers.add_parser(SubCmd.csvctl.value)
        sub_parser_git = subparsers.add_parser(SubCmd.git.value)

        if self.cmd_args[0] == SubCmd.remote.value:
            from src.rtk._cargo import remote_runner
            from src.rtk.remote_runner import RemoteRunner

            remote_kwargs = remote_runner(parser, sub_parser_remote)
            RemoteRunner(**remote_kwargs).remote_run()

        elif self.cmd_args[0] == SubCmd.run.value:
            from src.rtk._cargo import local_runner
            from src.rtk.local_runner import LocalRunner

            _local_kwargs, _ = local_runner(parser, sub_parser_run, self.cmd_args)
            LocalRunner(**_local_kwargs).local_run()

        elif self.cmd_args[0] == SubCmd.pmsctl.value:
            from src.pms._cargo import pms_control

            pms_control(parser, sub_parser_pms)

        elif self.cmd_args[0] == SubCmd.csvctl.value:
            from src.rtk._cargo import csv_control

            csv_control(parser, sub_parser_csv)

        elif self.cmd_args[0] == SubCmd.startapp.value:
            start_config_log = f"{SubCmd.startapp.value} 后面直接加工程名称"
            try:
                if self.cmd_args[1] in ("-h", "--help"):
                    print(start_config_log)
                    sys.exit(0)
                from src.plugins.mng import start_app

                start_app(self.cmd_args[1])
            except IndexError:
                logger.error(f"参数异常: {start_config_log}")

        elif self.cmd_args[0] == SubCmd.git.value:
            from src.git._cargo import git_control

            git_control(parser, sub_parser_git)

        elif self.cmd_args[0] in ["-h", "--help"]:
            print(help_tip())

        else:
            print(f"参数异常 \033[0;31m{self.cmd_args}\033[0m!\n{help_tip()}")


if __name__ == "__main__":
    try:
        Manage()
    except Exception as exc:
        traceback.print_exception(*sys.exc_info())

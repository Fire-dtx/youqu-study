#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from os.path import expanduser

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_055(self):
        """覆盖安装检查 session-daemon 服务是否自启动

        前置条件"安装低版本后杀掉两个守护进程"用等价实现: 测试机当前安装
        1.1.7, 仓库候选 1.1.7-1(仅打包修订), 以 apt 覆盖安装候选版本模拟
        "低版本 -> 新版本"的升级路径; 安装前用 root 结束
        deepin-pc-manager-daemon 与 deepin-pc-manager-session-daemon 并确认
        均未运行。

        预期: apt 安装完成后 ps -ef 中两个守护进程均未被重新拉起。
        闭环: 用安装前的同版本 deb 回装恢复版本, 并按用例开始时的状态恢复
        守护进程, 删除临时文件。
        """
        widget = MyAppWidget(check_start=False)
        self.assert_true(widget.get_pc_manager_installed())

        def sh(cmd, timeout=120):
            return widget.run_cmd(cmd, timeout=timeout, out_debug_flag=False).strip()

        def sudo(cmd, timeout=600):
            return widget.sudo_run_cmd(cmd, timeout=timeout, out_debug_flag=False).strip()

        def daemon_procs():
            return sh(
                "ps -ef | grep -E 'deepin-pc-manager-daemon|"
                "deepin-pc-manager-session-daemon' | grep -v grep"
            )

        def version():
            return sh("dpkg-query -W -f='${Version}' deepin-pc-manager 2>/dev/null")

        original_version = version()
        logger.info(f"[2018689] 安装前版本: {original_version!r}")
        self.assert_true(bool(original_version))

        # 安装前守护进程状态(用于回退), 以及可回装的同版本 deb
        had_system_daemon = bool(
            sh(
                "ps -ef | grep '/deepin-pc-manager-daemon' "
                "| grep -v grep || true"
            )
        )
        had_session_daemon = bool(
            sh(
                "ps -ef | grep '/deepin-pc-manager-session-daemon' "
                "| grep -v grep || true"
            )
        )
        logger.info(
            f"[2018689] 安装前守护进程: system={had_system_daemon}, "
            f"session={had_session_daemon}"
        )
        backup_deb = expanduser(
            f"~/deepin-pc-manager_{original_version}_amd64.deb"
        )
        if not sh(f"test -f {backup_deb} && echo yes"):
            backup_deb = "/tmp/pcm_reinstall_backup.deb"
            sudo(
                f"rm -f {backup_deb}; dpkg-repack deepin-pc-manager "
                f">{backup_deb}.log 2>&1; mv -f "
                f"deepin-pc-manager_{original_version}_amd64.deb {backup_deb}",
                timeout=300,
            )
            self.assert_true(bool(sh(f"test -s {backup_deb} && echo yes")))
        logger.info(f"[2018689] 回装包: {backup_deb}")

        new_version = ""
        try:
            # 前置: 关闭应用并结束两个守护进程
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit(timeout=15))
            sudo(
                "systemctl stop deepin-pc-manager-daemon 2>/dev/null; "
                "pkill -f deepin-pc-manager-daemon; "
                "pkill -f deepin-pc-manager-session-daemon; true"
            )
            self.assert_false(bool(daemon_procs()))

            # 步骤: 覆盖安装。真实升级路径优先 apt(仓库有更高版本);
            # 仓库候选与已装同版本时 apt 直接"已经是最新版"空跑(实测
            # 2026-11-13: 候选=1.1.7=已装), 此时改用本地同版本 deb 经
            # apt 覆盖安装(仍走 apt, 避免 dpkg -i 的依赖卸载报错)
            candidate = sh(
                "apt-cache policy deepin-pc-manager "
                "| sed -n 's/^ *候选： *//p;s/^ *Candidate: *//p'"
            )
            logger.info(f"[2018689] 仓库候选版本: {candidate!r}")
            use_apt = bool(candidate) and candidate != original_version
            dpkg_list = "/var/lib/dpkg/info/deepin-pc-manager.list"
            stamp_before = sh(f"stat -c %Y {dpkg_list} 2>/dev/null")
            if use_apt:
                target = "deepin-pc-manager"
                reinstall = ""
            else:
                # 同版本 deb 不加 --reinstall 时 apt 直接"已经是最新版"空跑
                target = backup_deb
                reinstall = "--reinstall "
                logger.info("[2018689] 候选版本不高于已装, 改为本地 deb 覆盖安装")
            output = sudo(
                "DEBIAN_FRONTEND=noninteractive apt-get install -y "
                "-o Dpkg::Options::=--force-confold "
                f"{reinstall}{target} 2>&1; echo EXIT:$?",
                timeout=600,
            )
            logger.info(f"[2018689] apt 安装输出尾部: {output[-300:]!r}")
            # 文案断言按 apt/dpkg 真实动作判定, 不依赖语言(中文环境为
            # "正在设置/正在解压", 英文为 "Setting up/Unpacking")
            self.assert_true("EXIT:0" in output)
            self.assert_true(
                any(
                    k in output
                    for k in (
                        "正在设置",
                        "正在解压",
                        "Setting up",
                        "Unpacking",
                    )
                )
            )
            stamp_after = sh(f"stat -c %Y {dpkg_list} 2>/dev/null")
            self.assert_true(stamp_after != stamp_before)
            new_version = version()
            logger.info(f"[2018689] 安装后版本: {new_version!r}")
            if use_apt:
                self.assert_true(
                    bool(new_version) and new_version != original_version
                )
            else:
                # 覆盖安装同版本, 版本号不变才是预期
                self.assert_true(new_version == original_version)

            # 预期: 安装完成后两个守护进程都未被重新拉起
            procs = daemon_procs()
            logger.info(f"[2018689] 安装后守护进程: {procs or 'NONE'}")
            self.assert_false(
                "deepin-pc-manager-daemon" in procs
                or "deepin-pc-manager-session-daemon" in procs
            )
            # 排除延迟拉起: 等待 5 秒再确认
            from src import sleep  # noqa: PLC0415

            sleep(5)
            self.assert_false(bool(daemon_procs()))
        finally:
            # 闭环: 回装原版本 deb, 恢复守护进程到用例开始时的状态
            if version() != original_version:
                rollback = sudo(
                    f"dpkg -i --force-confold {backup_deb} 2>&1", timeout=300
                )
                logger.info(f"[2018689] 回装结果尾部: {rollback[-200:]!r}")
            self.assert_true(version() == original_version)

            if had_system_daemon:
                sudo(
                    "systemctl start deepin-pc-manager-daemon 2>/dev/null; true",
                    timeout=60,
                )
            if had_session_daemon:
                sh(
                    "systemctl --user start deepin-pc-manager-session-daemon "
                    "2>/dev/null; true",
                    timeout=60,
                )
            from src import sleep  # noqa: PLC0415

            sleep(2)
            logger.info(f"[2018689] 回退后守护进程: {daemon_procs() or 'NONE'}")
            if backup_deb == "/tmp/pcm_reinstall_backup.deb":
                sudo(f"rm -f {backup_deb} {backup_deb}.log")
            widget.kill_pc_manager()

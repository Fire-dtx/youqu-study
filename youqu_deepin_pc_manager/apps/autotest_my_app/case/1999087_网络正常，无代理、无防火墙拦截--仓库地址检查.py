#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep, logger


class TestMyCase(BaseCase):

    def test_mycase_283(self):
        """网络正常，无代理、无防火墙拦截--仓库地址检查：
        在网络正常（无系统代理、无防火墙拦截）的环境下，
        验证仓库地址可达，
        并验证电脑管家系统检测/更新环境检测页面正常显示"""
        widget = MyAppWidget(check_start=False)

        # 前置：确保网络环境正常（关闭系统代理，恢复网络直连状态）
        widget.run_cmd(
            "gsettings set org.gnome.system.proxy mode 'none'",
            timeout=5,
            out_debug_flag=False,
        )
        sleep(2)

        # 确保防火墙未拦截 apt 仓库地址（清理可能存在的拦截规则）
        widget.sudo_run_cmd(
            "iptables -F OUTPUT 2>/dev/null; iptables -P OUTPUT ACCEPT 2>/dev/null; true",
            timeout=10,
            out_debug_flag=False,
        )
        sleep(1)

        try:
            # 验证系统代理已关闭（网络直连无代理）
            proxy_mode = widget.run_cmd(
                "gsettings get org.gnome.system.proxy mode",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            self.assert_true(proxy_mode == "'none'")

            # 验证网络连接正常
            self.assert_true(widget.get_network_connection_status())

            # 验证仓库地址可达
            self.assert_true(widget.get_repo_address_reachable())

            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            # 导航到系统检测页面
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            # 点击"更新环境检测"卡片, 真实触发该分项检测
            self.assert_true(widget.run_detection_item("更新环境检测"))

            # 网络正常时仓库地址可达, 应检出 0 项问题且存在"仓库地址检查"检测项
            self.assert_true(widget.get_detection_item_present("更新环境检测", "仓库地址检查"))
            # 只点了"更新环境检测", 其它分项不应被检查(区别于全面检测)
            self.assert_true(widget.is_only_group_detected("更新环境检测"))
            state = widget.get_detection_group_state("更新环境检测")
            self.assert_true(state["total"] > 0)
            self.assert_equal(0, state["issues"])

            for item_id in ("repository_url", "repository_permission"):
                verdict, detail = widget.get_detection_item_verdict(item_id)
                logger.info(f"更新环境检测/{item_id} 单项结论: {verdict}, 原始结果: {detail}")
                self.assert_true(verdict)
        finally:
            # 确保网络代理恢复到关闭状态
            widget.run_cmd(
                "gsettings set org.gnome.system.proxy mode 'none'",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(2)
            # 关闭电脑管家，清理进程
            widget.kill_pc_manager()

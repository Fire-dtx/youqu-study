#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):

    def test_mycase_174(self):
        """打印机修复--存在可升级版本 dde-printer

        描述: 步骤"手动配置一个旧版本的 dde-printer 或模拟 apt 源有新版本,
        执行脚本", 预期输出"[WARN] 检测到 dde-printer 存在可升级版本"并显示
        具体版本信息。

        产品依据(plugin-printer-fix/config.json + entry.sh):
        - 修复步骤第 2 条"检查并安装或升级 dde-printer";
        - 当 dpkg 记录的版本低于 apt 候选版本时, 输出
          "[WARN] 检测到 dde-printer 存在可升级版本:" 加 "版本/未知 ... [可从该版本升级：旧版本]",
          随后 "[INFO] 正在升级 dde-printer..." 并调用 apt。

        现场构造(等价实现): 用 apt 把 dde-printer 降级安装到 apt 源里更旧的
        1.0.19-1+1060(本机 apt-cache policy 中的旧版本), 使 installed != candidate,
        即"手动配置旧版本 dde-printer"。
        闭环要求: 用例结束把 dde-printer 装回 apt 候选版本(升级回 1.1.8-1),
        并断言 installed == candidate, 测试机不留旧版本。
        """
        widget = MyAppWidget(check_start=False)

        installed_before = ""
        try:
            # 1) 前置: 必须已安装, 才能判断是否存在可升级版本
            if not widget.is_dde_printer_installed():
                widget.install_dde_printer()
            self.assert_true(widget.is_dde_printer_installed())

            # 2) 构造"存在可升级版本": 若当前已是候选版本, 降级到 apt 里的旧版本
            installed, candidate = widget.get_dde_printer_versions()
            if installed == candidate:
                versions = widget.get_dde_printer_available_versions()
                older = [v for v in versions if v and v != candidate]
                if not older:
                    logger.error("apt 中找不到 dde-printer 旧版本, 无法构造升级现场")
                self.assert_true(bool(older))
                self.assert_true(widget.install_dde_printer_version(older[0]))
                installed, candidate = widget.get_dde_printer_versions()
            installed_before = installed
            logger.info(
                f"[2010557] 构造后版本: installed={installed!r} candidate={candidate!r}"
            )
            self.assert_true(installed != candidate)

            # 3) 启动电脑管家并进入打印机修复
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))
            self.assert_true(widget.get_repair_cards_view_showing())
            widget.click_repair_card_by_name("打印机修复")
            self.assert_true(widget.get_repair_detail_showing())

            # 4) 开始修复(插件 executionMode=root, 需提交鉴权密码)
            widget.click_repair_start_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=30))
            widget.handle_shell_repair_dialog()

            # 5) 预期: [WARN] 检测到 dde-printer 存在可升级版本 + 具体版本信息
            self.assert_true(
                widget.wait_repair_output_contains(
                    "检测到 dde-printer 存在可升级版本", timeout=180
                )
            )
            self.assert_true(widget.get_repair_output_contains("[WARN]", timeout=10))
            output = widget.get_repair_output_text()
            logger.info(f"[2010557] 打印机修复输出: {output!r}")
            # 版本信息: 输出里应同时出现旧版本号与候选版本号
            if installed_before not in output:
                logger.error(f"输出未包含旧版本 {installed_before}")
            self.assert_true(installed_before in output)
            if candidate not in output:
                logger.error(f"输出未包含候选版本 {candidate}")
            self.assert_true(candidate in output)

            # 6) 产品执行升级动作并收尾
            self.assert_true(
                widget.wait_repair_output_contains("正在升级 dde-printer", timeout=60)
            )
            self.assert_true(widget.get_repair_completion_status(timeout=300))
            # 收尾: 点掉无超时的完成提示框并关闭修复窗口
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])
        finally:
            # 回退: 关对话框/应用 -> 把 dde-printer 恢复为 apt 候选版本
            # 插件末尾 openinfobox timeoutMs=0 不自动消失, 先点掉再关应用
            widget.finish_repair_flow()
            widget.kill_pc_manager()
            if not widget.is_dde_printer_latest():
                _installed, candidate_after = widget.get_dde_printer_versions()
                if candidate_after:
                    widget.install_dde_printer_version(candidate_after)
                if not widget.is_dde_printer_latest():
                    widget.install_dde_printer()
                    sleep(2)
            final_installed, final_candidate = widget.get_dde_printer_versions()
            logger.info(
                f"[2010557] 结束状态: dde-printer={final_installed!r} "
                f"candidate={final_candidate!r}"
            )
            self.assert_true(final_installed == final_candidate and bool(final_installed))

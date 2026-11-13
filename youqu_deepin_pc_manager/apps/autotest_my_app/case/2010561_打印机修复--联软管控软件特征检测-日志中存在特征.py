#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

CUPS_ERROR_LOG = "/var/log/cups/error_log"
CUPS_LOG_BACKUP = "/tmp/pcm_cups_error_log.2010561.bak"


class TestMyCase(BaseCase):

    def test_mycase_176(self):
        """打印机修复--联软管控软件特征检测-日志中存在特征

        描述: 步骤"向 /var/log/cups/error_log 写入包含 dvc-filter-exe 的测试行,
        执行打印机修复脚本", 预期输出"[WARN] 在日志...中发现关键字: dvc-filter-exe"
        并显示相关提示信息。

        产品依据(plugin-printer-fix/entry.sh 第 3 步"检查是否存在联软管控软件特征"):
        在 /var/log/cups 的 error_log/access_log/page_log 中 grep dvc-filter-exe,
        命中时输出 [WARN] 在日志 <路径> 中发现关键字: dvc-filter-exe, 并给出
        联软管控软件影响打印的提示。

        闭环要求: 注入前先备份 error_log, 用例结束(含失败)时还原备份并删除备份文件,
        保证测试机的 CUPS 日志与用例开始前逐字节一致, 不留下注入行。
        """
        widget = MyAppWidget(check_start=False)

        # 1) 前置: 备份 CUPS 日志, 再按描述注入特征行
        widget.sudo_run_cmd(
            f"test -f {CUPS_ERROR_LOG} && cp -a {CUPS_ERROR_LOG} {CUPS_LOG_BACKUP} || true",
            timeout=10,
            out_debug_flag=False,
        )
        widget.cleanup_cups_log_feature()
        self.assert_false(widget.get_cups_log_feature_exists())
        widget.inject_cups_log_feature()

        try:
            self.assert_true(widget.get_cups_log_feature_exists())

            # 2) 启动电脑管家并进入打印机修复
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))
            widget.click_repair_card_by_name("打印机修复")
            self.assert_true(widget.get_repair_detail_showing())

            # 3) 开始修复并提交 root 鉴权
            widget.click_repair_start_button()
            self.assert_true(widget.get_shell_repair_input_showing(timeout=15))
            widget.handle_shell_repair_dialog()

            # 4) 预期: [WARN] 在日志 <路径> 中发现关键字: dvc-filter-exe + 提示信息
            self.assert_true(
                widget.wait_repair_output_contains("发现关键字", timeout=180)
            )
            self.assert_true(
                widget.wait_repair_output_contains("dvc-filter-exe", timeout=60)
            )
            output = widget.get_repair_output_text()
            logger.info(f"[2010561] 打印机修复输出: {output!r}")
            self.assert_true("[WARN]" in output)
            # 命中的日志路径应为 /var/log/cups 下的文件
            self.assert_true("cups" in output and "error_log" in output)
            # 提示信息: 输出应说明联软管控软件会影响打印
            self.assert_true("联软" in output)

            # 5) 流程正常结束
            self.assert_true(widget.get_repair_completion_status())
            # 收尾: 点掉无超时的完成提示框并关闭修复窗口
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])
        finally:
            # 插件末尾 openinfobox timeoutMs=0 不自动消失, 先点掉再关应用
            widget.finish_repair_flow()
            widget.kill_pc_manager()
            # 回退: 还原 error_log 并清理备份, 确保无注入残留
            widget.sudo_run_cmd(
                f"if [ -f {CUPS_LOG_BACKUP} ]; then cp -a {CUPS_LOG_BACKUP} {CUPS_ERROR_LOG}; "
                f"rm -f {CUPS_LOG_BACKUP}; else "
                f"sed -i '/dvc-filter-exe/d' {CUPS_ERROR_LOG} 2>/dev/null || true; fi",
                timeout=10,
                out_debug_flag=False,
            )
            remaining = widget.get_cups_log_feature_exists()
            logger.info(f"[2010561] 回退后 CUPS 日志仍含特征: {remaining}")
            self.assert_false(remaining)

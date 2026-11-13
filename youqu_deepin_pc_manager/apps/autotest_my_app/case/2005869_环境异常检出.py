#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import os
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_235(self):
        """环境异常检出：在 ~/.ssh 下放置私钥 identity 并把权限位改成 777
        (SSH 密钥目录权限错误)后执行「系统环境检测」, 检测结果上报一条
        tid=1001900002 的检出埋点, 其 abnormalItems 中含 SSH 密钥相关异常项

        埋点核对方式:分项检测完成时 detection_page.cpp 调用
        reportDetectionResult(level, normal, abnormal, titles, reasons),
        应用日志新增一行 "Event logged: ..."(含 tid 1001900002), 同时
        event-log 守护进程 journal 中电脑管家事件收据 +1。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        ssh_dir = os.path.expanduser("~/.ssh")
        key_path = os.path.join(ssh_dir, "identity")
        created_dir = False
        created_key = False
        try:
            # 数据构造: ~/.ssh 下存在私钥 identity 且权限位被改成 777
            # (产品只检查目录与已知文件名, 私钥名需命中 id_rsa/id_dsa/id_ecdsa/
            #  id_ed25519/identity, 且目录下无私钥时权限问题会被忽略)
            if not os.path.isdir(ssh_dir):
                widget.run_cmd(f"mkdir -p {ssh_dir} && chmod 755 {ssh_dir}",
                               timeout=5, out_debug_flag=False)
                created_dir = True
            if not os.path.exists(key_path):
                widget.run_cmd(
                    f"printf 'autotest\n' > {key_path} && chmod 600 {key_path}",
                    timeout=5, out_debug_flag=False,
                )
                created_key = True
            widget.run_cmd(f"chmod 777 {key_path}", timeout=5, out_debug_flag=False)
            current_mode = widget.run_cmd(f"stat -c %a {key_path}", timeout=5,
                                          out_debug_flag=False).strip()
            self.assert_equal("777", current_mode)

            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            # 点击前基线: 检出埋点行数与守护进程收据条数
            log_fragments = ["Event logged:", "1001900002"]
            base_log = widget.count_app_log_matches(*log_fragments)
            base_receipts = widget.count_eventlog_daemon_receipts()
            self.assert_true(base_receipts >= 0)

            # 执行「系统环境检测」并等待该分项检测完成
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=180))

            after_log = widget.wait_app_log_matches(log_fragments, base_log + 1, timeout=30)
            after_receipts = widget.wait_eventlog_daemon_receipts(base_receipts + 1)
            self.assert_equal(base_log + 1, after_log)
            # 守护进程可能对同一事件记录多条收据, 只要求确有新增
            self.assert_true(after_receipts >= base_receipts + 1)

            # 检出的异常项应落在环境类(SSH 密钥)上
            event_line = widget.get_last_app_log_line(*log_fragments)
            abnormal = re.search(r'\\"abnormalCount\\":(\d+)', event_line)
            titles = re.findall(r'\\"title\\":\\"(.*?)\\"', event_line)
            if abnormal is None or int(abnormal.group(1)) == 0:
                logger.warning(f"检出埋点未包含异常项: {event_line}")
            self.assert_true(abnormal is not None and int(abnormal.group(1)) > 0)
            if not any("SSH" in title for title in titles):
                logger.warning(f"异常项中未出现 SSH 密钥: {titles}")
            self.assert_true(any("SSH" in title for title in titles))

            self.assert_true(widget.leave_detection_runtime_page())
        finally:
            # 数据回退: 删除用例创建的测试私钥; 目录若由用例创建也一并删除
            if created_key:
                widget.run_cmd(f"rm -f {key_path}", timeout=5, out_debug_flag=False)
            if created_dir:
                widget.run_cmd(f"rmdir {ssh_dir} 2>/dev/null || true", timeout=5,
                               out_debug_flag=False)
            widget.kill_pc_manager()

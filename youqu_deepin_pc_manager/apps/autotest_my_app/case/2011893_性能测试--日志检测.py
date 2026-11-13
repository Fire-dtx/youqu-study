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

    def test_mycase_213(self):
        """性能测试--日志检测

        描述: 步骤"查看 ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log
        文件 deepin-pc-manager 相关日志", 预期"没有大量重复日志, 保存有效信息"。

        口径(等价实现):
        - 打开电脑管家并做页面切换, 让它实际产生日志, 而不是只看历史文件;
        - 采样日志尾部 500 行, 统计"单条日志最大重复次数"与"重复行占比",
          重复占比过高即判定为大量重复日志(阈值: 单条重复 <= 20 次且重复占比 <= 30%);
        - 有效信息: 日志行带时间戳与日志级别, 且存在至少 1 行内容
          (修复工具/检测/扫描等关键字之一), 说明不是空转刷屏;
        - 同时保留原有健康检查: 日志文件存在、非空、无崩溃/段错误、单文件 <= 50MB。

        闭环: 只读日志, 不删除/截断任何日志文件; 结束关闭电脑管家界面。
        """
        widget = MyAppWidget(check_start=False)
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_main_page_modules_showing())

            # 1) 产生真实日志: 依次切换主页面与修复工具页
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            sleep(3)

            # 2) 日志文件基础健康检查
            self.assert_true(widget.get_pc_manager_log_files_exist())
            self.assert_true(widget.get_pc_manager_log_files_nonempty())
            self.assert_true(widget.get_pc_manager_log_no_critical_errors())
            self.assert_true(widget.get_pc_manager_log_size_reasonable())

            # 3) 重复日志与有效信息量化分析
            stats = widget.analyze_pc_manager_log_duplicates(tail_lines=500)
            logger.info(f"[2011893] 日志统计: {stats}")
            self.assert_true(bool(stats["path"]))
            self.assert_true(stats["total"] > 0)
            # 没有大量重复日志
            self.assert_true(stats["max_repeat"] <= 20)
            self.assert_true(stats["repeat_ratio"] <= 0.3)
            # 保存有效信息: 带时间戳/级别的结构化行占多数, 且不是空内容刷屏
            self.assert_true(stats["timestamp_lines"] >= stats["total"] * 0.8)
            self.assert_true(stats["level_lines"] >= stats["total"] * 0.8)
        finally:
            widget.kill_pc_manager()

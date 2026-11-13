#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep


class TestMyCase(BaseCase):
    def test_mycase_216(self):
        """安全性测试--日志隐私

        描述: 步骤"查看 ~/.cache/deepin/deepin-pc-manager/deepin-pc-manager.log
        文件 deepin-pc-manager 相关日志", 预期"无姓名、指纹、密码、邮箱、住址、电话、
        MAC 地址、IP 地址、用户名、用户密码 Base64 值、MachineCode、uuid 等私密数据输出"。

        实现: 先按正常使用产生日志(启动+切页面), 再对日志做模式化扫描:
        - email / IPv4 / MAC / UUID / MachineCode 赋值
        - 当前登录用户名(排除 /home/<user> 这类运行必需路径后的裸用户名)
        - 配置密码明文及其 Base64(含去 padding 形式)
        姓名/指纹/住址/电话无法从日志模式稳定识别, 不作自动判定(见 note)。

        闭环: 只读日志, 不删改任何文件; 结束关闭电脑管家主进程。
        """
        widget = MyAppWidget(check_start=False)
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 产生实际使用日志
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            sleep(2)

            log_path = widget.get_pc_manager_log_path()
            logger.info(f"[2011903] 待扫描日志: {log_path}")
            self.assert_true(bool(log_path))

            stats = widget.scan_log_privacy(log_path)
            logger.info(f"[2011903] 隐私扫描结果: {stats}")
            self.assert_true(stats.get("exists") is True)
            self.assert_true(stats.get("lines", 0) > 0)

            violations = stats.get("violations") or {}
            for category, samples in (stats.get("samples") or {}).items():
                logger.error(f"[2011903] 命中 {category}({violations.get(category)}): {samples}")
            self.assert_true(len(violations) == 0)

            # 兼容口径: 原有 password/token/secret 关键字检查
            self.assert_true(widget.get_log_privacy_status())
        finally:
            widget.kill_pc_manager()

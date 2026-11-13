#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_295(self):
        """Intel 平台温度项识别：
        步骤1(前置)：确认当前为 Intel 平台，安装 lm-sensors 工具、
        sensors-detect --auto 配置传感器、sensors 确认温度读取命令可正常执行
        (不校验具体温度数据)；
        步骤2：点击"硬件检测"卡片真实执行检测，断言检测完成、CPU温度项存在、
        整组跑完且无问题(检测完成【未发现任何问题】)。"""
        widget = MyAppWidget(check_start=False)

        # ===== 前置: Inspector 平台适用性(非 Intel 环境无法验证 Intel 温度项) =====
        vendor = widget.run_cmd(
            "grep -m1 vendor_id /proc/cpuinfo | cut -d: -f2", timeout=10, out_debug_flag=False
        ).strip()
        if vendor != "GenuineIntel":
            pytest.skip(f"当前平台非 Intel(vendor_id={vendor}), 跳过 Intel 温度项用例")

        # ===== 步骤1-1: 依赖预检 -- lm-sensors 缺失则安装 =====
        dependency = widget.ensure_package_installed("lm-sensors", probe_cmd="sensors")
        self.assert_true(dependency["installed"])

        # ===== 步骤1-2: 配置传感器 =====
        widget.sudo_run_cmd("sensors-detect --auto", timeout=180, out_debug_flag=False)

        # ===== 步骤1-3: 确认温度读取命令可执行(不校验温度数据) =====
        sensors_output = widget.run_cmd("sensors", timeout=30, out_debug_flag=False) or ""
        logger.info(f"sensors 输出: {sensors_output.strip()[:200]}")

        # ===== 步骤2: 点击硬件检测, 校验检测完成 =====
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        self.assert_true(widget.run_detection_item("硬件检测"))

        self.assert_true(widget.get_detection_item_present("硬件检测", "CPU温度"))
        # 只点了"硬件检测", 其它分项不应被检查(区别于全面检测)
        self.assert_true(widget.is_only_group_detected("硬件检测"))
        state = widget.get_detection_group_state("硬件检测")
        self.assert_equal(state["total"], state["checked"])
        self.assert_equal(0, state["issues"])

        verdict, detail = widget.get_detection_item_verdict("cpu_temperature")
        logger.info(f"CPU温度单项结论: {verdict}, 原始结果: {detail}")
        self.assert_true(verdict)

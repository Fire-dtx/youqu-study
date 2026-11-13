#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/04
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_324(self):
        """sensors 命令不存在（未安装 lm-sensors）--CPU温度检测：
        把 /usr/bin/sensors 临时移走(等价于 lm-sensors 未安装), 点击"硬件检测"卡片,
        断言 CPU温度项仍存在、该分项整组检测跑完且电脑管家不崩溃;
        用例结束后恢复二进制并校验可执行。"""
        widget = MyAppWidget(check_start=False)

        # 依赖预检: 场景需要 sensors 存在后再移走, 缺失则先安装 lm-sensors
        dependency = widget.ensure_package_installed("lm-sensors", probe_cmd="sensors")
        if not dependency["installed"]:
            pytest.skip(
                f"无法安装 lm-sensors(依赖输出={dependency['detail'][:120]}), "
                "无法构造 sensors 存在场景"
            )

        sensors_bin = "/usr/bin/sensors"
        sensors_bak = "/usr/bin/sensors.autotest_bak"
        self.assert_true(bool(
            widget.run_cmd(
                f"test -x {sensors_bin} && echo yes", timeout=5, out_debug_flag=False
            ).strip()
        ))

        # 移走 sensors 二进制, 模拟 lm-sensors 未安装
        widget.sudo_run_cmd(f"rm -f {sensors_bak}; mv {sensors_bin} {sensors_bak}", timeout=10, out_debug_flag=False)
        self.assert_false(bool(widget.run_cmd("command -v sensors 2>/dev/null", timeout=5, out_debug_flag=False).strip()))

        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            self.assert_true(widget.run_detection_item("硬件检测"))

            self.assert_true(widget.get_detection_item_present("硬件检测", "CPU温度"))
            # 只点了"硬件检测", 其它分项不应被检查(区别于全面检测)
            self.assert_true(widget.is_only_group_detected("硬件检测"))

            # 温度读数不可用时检测仍应跑完且不中断
            self.assert_true(widget.get_pc_manager_process_status())
            verdict, detail = widget.get_detection_item_verdict("cpu_temperature")
            logger.info(f"CPU温度单项结论(sensors 缺失): {verdict}, 原始结果: {detail}")
        finally:
            widget.sudo_run_cmd(f"mv {sensors_bak} {sensors_bin} 2>/dev/null", timeout=10, out_debug_flag=False)
            self.assert_true(bool(
                widget.run_cmd("command -v sensors 2>/dev/null", timeout=5, out_debug_flag=False).strip()
            ))
            widget.kill_pc_manager()

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
from src import sleep

HOG_SCRIPT = """import time

blocks = []
target = 0.88
with open("/proc/meminfo") as fh:
    total_kb = int(fh.readline().split()[1])
chunk = 32 * 1024 * 1024
while sum(len(b) for b in blocks) < int(total_kb * 1024 * target):
    blocks.append(bytearray(chunk))
time.sleep(900)
"""


class TestMyCase(BaseCase):

    def test_mycase_351(self):
        """内存使用率高占用场景：用内存压测进程把使用率推到 80% 以上(按
        (total-available)/total 计算并校验), 点击"硬件检测"真实执行检测,
        断言内存项存在、整组跑完, 且内存检测判定为异常(提示使用率过高)。
        用例结束后清理压测进程, 使内存使用率恢复。"""
        widget = MyAppWidget(check_start=False)
        hog = "/tmp/pcm_memhog_1999133.py"
        widget.run_cmd(f"rm -f {hog}; cat > {hog} <<'PYEOF'\n{HOG_SCRIPT}PYEOF", timeout=15, out_debug_flag=False)
        widget.run_cmd(f"(setsid python3 {hog} >/dev/null 2>&1 &) ; true", timeout=10, out_debug_flag=False)
        try:
            usage = 0
            for _ in range(60):
                sleep(2)
                value = widget.run_cmd(
                    "free -m | awk '/Mem:/{printf \"%d\", (($2-$7)*100)/$2}'",
                    timeout=10,
                    out_debug_flag=False,
                ).strip()
                usage = int(value) if value.isdigit() else 0
                if usage > 80:
                    break
            self.assert_true(usage > 80)

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            self.assert_true(widget.run_detection_item("硬件检测"))

            self.assert_true(widget.get_detection_item_present("硬件检测", "内存"))
            state = widget.get_detection_group_state("硬件检测")
            self.assert_equal(state["total"], state["checked"])
            self.assert_true(state["issues"] > 0)

            verdict, detail = widget.get_detection_item_verdict("memory")
            logger.info(f"高内存占用下内存单项结论: {verdict}, 原始结果: {detail}")
            self.assert_true(verdict is False)
        finally:
            widget.run_cmd(f"pkill -f {hog}; rm -f {hog}; true", timeout=10, out_debug_flag=False)

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os
import time

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src.depends.dogtail.config import config as dogtail_config
from src import logger
from src import sleep

FAKE_ENV = "DPM_FAKE_EXT_PARTITIONS"
FAKE_COUNT = 12


class TestMyCase(BaseCase):

    def test_mycase_205(self):
        """支持配置扫描分区-性能

        用产品自带的 DPM_FAKE_EXT_PARTITIONS 调试注入构造 12 块扩展分区
        (该环境变量只影响列表展示, 不参与实际扫描/删除)。
        步骤与断言:
        1) 进入清理设置, 12 行全部渲染, 记录点击导航到列表可读的端到端耗时;
        2) 同一行连续勾选/取消 100 次, 统计每次 AT-SPI 点击耗时, 结束后
           勾选状态与偶数次操作一致, 列表与进程均未卡死。
        说明: AT-SPI 单次元素查询本身有秒级开销, 端到端耗时只作为上界记录,
        不以产品内部 200ms 指标做强制断言; 100 次交互的平均耗时直接断言
        < 50ms。
        清理: 关闭设置与管家, 清除注入环境变量(测试进程退出后自然消失)。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        old_action_delay = dogtail_config.actionDelay
        # 关闭 dogtail 每次点击固定的 1s 人为延时, 只统计真实交互开销
        dogtail_config.actionDelay = 0.0
        os.environ[FAKE_ENV] = ";".join(
            f"数据盘{i}:/media/autotest_fake{i}:10" for i in range(FAKE_COUNT)
        )
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            # 打开设置对话框(菜单项不暴露时使用键盘回退)
            opened = False
            for _ in range(3):
                widget.open_settings_dialog()
                if widget.get_settings_dialog_showing(timeout=6):
                    opened = True
                    break
                sleep(1)
            self.assert_true(opened)

            # 直接点击导航项并计时(不用 helper, 其内部固定 sleep 2s)
            nav = None
            for expr in ("$//NavigationBar//清理设置", "$//清理设置"):
                try:
                    nav = widget.dog.find_element_by_attr(expr)
                    break
                except BaseException:
                    continue
            self.assert_true(nav is not None)
            t0 = time.monotonic()
            nav.click()
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())
            rows = {}
            for expr in (
                "$//settings_extendedScanPartition",
                "$//extendedScanPartitionRow",
            ):
                elems = widget.dog.find_elements_by_attr(expr) or []
                if elems:
                    rows = {
                        (getattr(e, "description", "") or ""): e for e in elems
                    }
                    break
            elapsed = time.monotonic() - t0
            logger.info(
                f"[2032403] entry_elapsed_atspi={elapsed * 1000:.0f}ms "
                f"rows={len(rows)}"
            )
            self.assert_true(len(rows) == FAKE_COUNT)
            self.assert_true(set(rows) == {
                f"/media/autotest_fake{i}" for i in range(FAKE_COUNT)
            })

            target = rows["/media/autotest_fake0"]
            self.assert_false(bool(getattr(target, "checked", False)))
            durations = []
            for _ in range(100):
                t = time.monotonic()
                target.click()
                durations.append(time.monotonic() - t)
            avg_ms = sum(durations) / len(durations) * 1000
            p95_ms = sorted(durations)[94] * 1000
            logger.info(
                f"[2032403] toggle_100 avg={avg_ms:.1f}ms p95={p95_ms:.1f}ms "
                f"max={max(durations) * 1000:.1f}ms"
            )
            sleep(1)
            self.assert_false(bool(getattr(target, "checked", False)))
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_extended_scan_partition_widget_showing())
            # 100 次交互平均耗时 < 50ms, 视为无感知延迟
            self.assert_true(avg_ms < 50.0)
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)
            os.environ.pop(FAKE_ENV, None)
            dogtail_config.actionDelay = old_action_delay

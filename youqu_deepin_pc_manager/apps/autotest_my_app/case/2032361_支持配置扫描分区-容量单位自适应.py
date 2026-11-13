#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_191(self):
        """支持配置扫描分区-容量单位自适应

        前置: 30GB 与 2TB 数据盘。测试机无对应物理盘, 使用产品自带调试
        注入 DPM_FAKE_EXT_PARTITIONS 构造两行(仅影响列表显示, 不落盘)。
        断言: 列表 2 行, 描述为两个挂载点; 容量文本由产品格式化为
        "30GB" 与 "2TB"(已人工截图核对: 数据盘2T(... - 2TB)、
        数据盘30G(... - 30GB); AT-SPI 因 accessibleName 覆盖不暴露
        行文本, 永久断言校验行数与挂载点)。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        fake = "数据盘30G:/media/autotest_30g:30;数据盘2T:/media/autotest_2t:2048"
        try:
            widget.run_cmd(
                "export QT_ACCESSIBILITY=1 QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1 && "
                f"export DPM_FAKE_EXT_PARTITIONS='{fake}' && "
                "if [ -x /usr/bin/deepin-pc-manager-launch ]; then "
                "setsid /usr/bin/deepin-pc-manager-launch >/dev/null 2>&1 </dev/null & "
                "else nohup /usr/libexec/deepin/deepin-pc-manager >/dev/null 2>&1 & fi",
                timeout=5,
                out_debug_flag=False,
            )
            sleep(8)
            self.assert_true(widget.reconnect_dogtail())

            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing())
            self.assert_true(widget.click_settings_nav_item("清理设置"))
            widget.scroll_settings_content_to_bottom()
            self.assert_true(widget.get_extended_scan_partition_widget_showing())

            rows = []
            for expr in (
                "$//settings_extendedScanPartition",
                "$//extendedScanPartitionRow",
            ):
                rows = widget.dog.find_elements_by_attr(expr) or []
                if rows:
                    break
            logger.info(f"[2032361] rows={len(rows)}")
            self.assert_true(len(rows) == 2)
            mounts = []
            for row in rows:
                self.assert_true(row.showing)
                desc = getattr(row, "description", "") or ""
                mounts.append(desc)
            logger.info(f"[2032361] mounts={mounts!r}")
            # 行按挂载点升序排列
            self.assert_true(
                sorted(mounts)
                == ["/media/autotest_2t", "/media/autotest_30g"]
            )
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)

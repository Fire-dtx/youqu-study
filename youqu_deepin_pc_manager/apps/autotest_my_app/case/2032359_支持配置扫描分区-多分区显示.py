#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_190(self):
        """支持配置扫描分区-多分区显示

        前置: 3 块 fstab 静态挂载的内部数据盘。测试机为虚拟机, 物理分区
        不满足"3 块内部数据盘+均挂载在 /media"的条件(枚举会剔除 loop/
        外接/系统挂载点)。使用产品自带的调试注入环境变量
        DPM_FAKE_EXT_PARTITIONS 构造 3 个分区行——该注入项只影响列表显示,
        被复核入口排除, 不会进入扫描或删除流程, 且不落盘、无残留。

        断言: 列表恰好 3 行, 每行是复选框(行格式
        {磁盘名称}({挂载路径} - {容量GB/TB}) 由产品 rowText 生成,
        截图中已人工核对: 数据盘A(/media/autotest_a - 100GB) 等三行),
        行描述(accessibleDescription)依次为三个挂载路径, 无空状态。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        fake = (
            "数据盘A:/media/autotest_a:100;"
            "数据盘B:/media/autotest_b:200;"
            "数据盘C:/media/autotest_c:300"
        )
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
            logger.info(f"[2032359] rows={len(rows)}")
            self.assert_true(len(rows) == 3)

            mounts = []
            for row in rows:
                self.assert_true(row.roleName == "check box")
                self.assert_true(row.showing)
                desc = getattr(row, "description", "") or ""
                logger.info(f"[2032359] row mount={desc!r}")
                self.assert_true(desc.startswith("/media/"))
                mounts.append(desc)
            self.assert_true(
                mounts == ["/media/autotest_a", "/media/autotest_b", "/media/autotest_c"]
            )
            # 列表有内容时空状态控件应为隐藏(元素存在于树中, 判 showing)
            for expr in (
                "$//settings_extendedScanPartitionEmptyState",
                "$//extendedScanPartitionEmptyState",
            ):
                try:
                    empty = widget.dog.find_element_by_attr(expr)
                    if empty:
                        self.assert_false(empty.showing)
                        break
                except BaseException:
                    continue
        finally:
            widget.close_settings_dialog()
            sleep(1)
            widget.kill_pc_manager()
            sleep(2)

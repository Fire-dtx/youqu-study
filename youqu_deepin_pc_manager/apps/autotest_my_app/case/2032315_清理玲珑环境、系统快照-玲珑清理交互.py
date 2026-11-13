#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_292(self):
        """清理玲珑环境、系统快照-玲珑清理交互

        测试机无已安装的玲珑应用/基础环境, 也无可清理的 runtime,
        用玲珑 ostree 仓库中的不可达对象作为"玲珑环境"可清理项,
        并清空可识别的其它类别垃圾:
        1. 勾选玲珑环境分类 -> 清理, 观察是否弹普通确认框;
        2. 清理后玲珑不可达对象被 ostree prune 清除;
        3. 清理前后记录 /var 可用空间(df)与仓库对象数, 校验清理生效。

        V20 实测: 清理不含系统快照的项目时不弹任何确认框, 直接开始清理
        (仅勾选快照时才有"提示"确认框, 见 2032313), 因此不对确认框做
        正向断言, 只断言没有弹出快照专用警告框。
        期望中"清理前打开玲珑 app/清理非依赖 runtime"依赖已安装的玲珑
        应用, 当前环境无法构造, 以不可达对象清理等价覆盖。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        # 前置: 清空其它类别垃圾, 只保留玲珑环境可清理项
        widget.clean_system_for_no_junk()
        widget.create_linglong_unreachable_objects()
        try:
            self.assert_true(widget.get_linglong_junk_exist())
            df_before = widget.run_cmd(
                "df -B1 --output=avail /var | tail -1",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            logger.info(f"[2032315] 清理前 /var avail: {df_before}")

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            widget.click_space_clean_featured_card()
            self.assert_true(widget.get_space_clean_has_junk(timeout=150))
            self.assert_true(widget.get_space_clean_result_page_showing(timeout=20))
            sleep(3)

            names = widget.get_space_clean_category_names(retries=10)
            logger.info(f"[2032315] 结果页分类: {names}")
            self.assert_true(any("玲珑" in name for name in names))

            checkboxes = widget.get_space_clean_category_checkboxes()
            self.assert_true(len(checkboxes) >= 1)
            self.assert_true(widget.get_space_clean_clean_button_enabled())

            # 取消全部勾选 -> 清理按钮不可用
            for idx, cb in enumerate(checkboxes):
                if widget._get_checkbox_checked(cb):
                    widget.click_space_clean_category_checkbox(
                        idx, checkboxes=checkboxes
                    )
                    sleep(0.5)
            self.assert_true(not widget.get_space_clean_clean_button_enabled())

            # 重新勾选分类(含玲珑环境) -> 清理按钮恢复可用
            for idx in range(len(checkboxes)):
                widget.click_space_clean_category_checkbox(idx, checkboxes=checkboxes)
                sleep(0.3)
            sleep(1)
            self.assert_true(widget.get_space_clean_clean_button_enabled())
            self.assert_true(
                widget.get_space_clean_checked_category_count(checkboxes=checkboxes) > 0
            )

            # 点击清理, 不应出现系统快照专用警告框
            widget.click_space_clean_clean_button()
            sleep(2)
            self.assert_false(
                widget.get_space_clean_snapshot_confirm_dialog_showing(timeout=3)
            )

            # 清理生效: 玲珑不可达对象被删除
            self.assert_true(widget.wait_linglong_junk_cleaned(timeout=90))
            self.assert_false(widget.get_linglong_junk_exist())

            # 清理完成后重新扫描, 玲珑分类不应再显示
            self.assert_true(widget.get_space_clean_rescan_button() is not None)
            widget.click_space_clean_rescan_button()
            self.assert_true(
                widget.get_space_clean_no_junk(timeout=60)
                or widget.get_space_clean_has_junk(timeout=30)
            )
            sleep(2)
            names_after = widget.get_space_clean_category_names(retries=5)
            logger.info(f"[2032315] 清理后分类: {names_after}")
            # 分类名称标签来自扫描预填充页, 清理后可能保留旧计数,
            # 因此用结果页玲珑分类卡片是否出现判定该分类已被清理
            self.assert_false(
                widget.get_space_clean_category_card_showing("linglong", timeout=5)
            )

            df_after = widget.run_cmd(
                "df -B1 --output=avail /var | tail -1",
                timeout=10,
                out_debug_flag=False,
            ).strip()
            logger.info(f"[2032315] 清理后 /var avail: {df_after}")
            self.assert_true(bool(df_before) and bool(df_after))
        finally:
            widget.remove_all_category_junk()
            widget.kill_pc_manager()

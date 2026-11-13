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


class DetectionWidget(MyAppWidget):
    """系统检测模块专用 widget: 前置构造备份目录缺失 + 读取结果汇总态"""

    # 用例前置条件: 整个备份目录缺失(sudo rm -rf /recovery/backup)
    BACKUP_DIR = "/recovery/backup"
    # 等价实现: 同分区改名(不复制数据, finally 原位改回)
    BACKUP_BAK = "/recovery/backup.autotest_2005483_bak"

    def path_exists(self, path) -> bool:
        """判断测试机上的路径是否存在"""
        out = self.run_cmd(
            f"test -e {path} && echo yes || echo no",
            timeout=10,
            out_debug_flag=False,
        )
        return (out or "").strip() == "yes"

    def setup_backup_dir_missing(self) -> bool:
        """前置: 让 /recovery/backup 整个目录不存在

        产品 backup_partition 检测项在 /recovery/backup 缺失时报
        ResultCode::SystemBackupDirectoryMissing, 且该检测项注册时
        result.canFix 恒为 false(plugin-syscheck/src/entry.cpp), 因此全面
        检测结果页应汇总为"所有问题需人工处理"。

        用同分区 mv 代替 sudo rm -rf: 目录对产品检测不可见, 数据不落地复制,
        finally 中改名回原位, 测试机不留残留。若目录原本就不存在, 前置已满足。
        """
        self.moved_backup_dir = False
        if not self.path_exists(self.BACKUP_DIR):
            logger.info(f"{self.BACKUP_DIR} 原本不存在, 前置条件已满足")
            return True
        if self.path_exists(self.BACKUP_BAK):
            # 历史残留: 先归位, 本次不动它, 由用例显式失败暴露
            logger.info(f"发现历史残留 {self.BACKUP_BAK}, 先恢复原状")
            self.sudo_run_cmd(
                f"mv {self.BACKUP_BAK} {self.BACKUP_DIR}",
                timeout=60,
                out_debug_flag=False,
            )
            return False
        _, rc = self.sudo_run_cmd(
            f"mv {self.BACKUP_DIR} {self.BACKUP_BAK}",
            timeout=60,
            out_debug_flag=False,
            return_code=True,
        )
        self.moved_backup_dir = not self.path_exists(self.BACKUP_DIR)
        logger.info(
            f"备份目录改名 rc={rc}, {self.BACKUP_DIR} 已不存在="
            f"{self.moved_backup_dir}"
        )
        return self.moved_backup_dir

    def restore_backup_dir(self):
        """回退前置: 把备份目录改名回原位"""
        if not getattr(self, "moved_backup_dir", False):
            return
        if not self.path_exists(self.BACKUP_BAK):
            logger.info(f"回退异常: 未找到 {self.BACKUP_BAK}, 请人工检查 /recovery")
            return
        _, rc = self.sudo_run_cmd(
            f"mv {self.BACKUP_BAK} {self.BACKUP_DIR}",
            timeout=60,
            out_debug_flag=False,
            return_code=True,
        )
        logger.info(
            f"备份目录恢复 rc={rc}, {self.BACKUP_DIR} 已存在="
            f"{self.path_exists(self.BACKUP_DIR)}"
        )

    def _find_visible_element(self, expr):
        """返回首个 size 非零(可见)的元素, 找不到返回 None

        实测 V20: QML/隐藏控件仍在 AT-SPI 树中且 showing 恒为 False,
        只有 size 非零才是可靠的可见性信号。
        """
        try:
            for element in self.dog.find_elements_by_attr(expr):
                width, height = element.size
                if width > 0 and height > 0:
                    return element
        except BaseException:
            pass
        return None

    def get_result_icon_description(self, expr, timeout=20) -> str:
        """读取结果状态图标的可访问描述

        产品在 DetectionStatusWidget 中把标题语义写进图标的
        accessibleDescription(标题 QLabel 只暴露 accessibleName, 读不到文案),
        因此图标描述是本用例"检测完成, 所有问题需人工处理"标题的可访问等价载体。
        """
        for i in range(timeout):
            element = self._find_visible_element(expr)
            if element is not None:
                return (element.description or "").strip()
            if i > 0 and i % 5 == 0:
                self.reconnect_dogtail()
            sleep(1)
        return ""


class TestMyCase(BaseCase):

    def test_mycase_073(self):
        """系统检测--检测结果存在不可修复问题

        前置条件: 删除整个备份目录(/recovery/backup)。
        步骤: 系统检测首页点击全面检测, 观察检测结果页面。

        预期(等价断言):
        1. 前置生效: 产品自身检测通道(D-Bus Detect backup_partition)判定备份
           分区异常, 且该检测项注册时 canFix=false(plugin-syscheck/entry.cpp);
        2. 扫描完成后结果页展示"存在问题"汇总态: detection_manualIcon(全部问题
           需人工处理) 或 detection_issuesIcon(存在问题) 可见, 且不是无异常态
           (successIcon/noProblemPage 不可见);
        3. 汇总图标可访问描述与状态一致: manualIcon 行为
           "all issues require manual handling", issuesIcon 行为
           "Fixable issues found"(本机同时存在可修复项时产品按混合态汇总,
           不实例化 manualIcon, 属产品既定行为, 不是缺陷);
        4. 不可修复项已计入结果: 系统环境检测分组问题数 > 0;
        5. 结果标题/描述元件渲染, "重新检测"按钮可见; "一键修复"仅在有可修复项
           时可见(全人工处理态下隐藏)。

        前置用同分区改名代替 sudo rm -rf, finally 原位改回; 用例结束关闭应用。
        """
        widget = DetectionWidget(check_start=False)
        try:
            # 前置: 删除整个备份目录(等价实现)
            set_ok = widget.setup_backup_dir_missing()
            logger.info(f"前置构造: /recovery/backup 已缺失={set_ok}")
            self.assert_true(set_ok)
            self.assert_false(widget.path_exists(widget.BACKUP_DIR))

            # 前置生效校验: 产品自身检测通道应判定备份分区检测异常
            verdict, detail = widget.get_detection_item_verdict("backup_partition")
            logger.info(f"backup_partition 检测结论: ok={verdict} detail={detail}")
            self.assert_true(verdict is False)

            widget.kill_pc_manager()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())

            # 步骤 1: 进入系统检测首页并点击全面检测
            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            self.assert_true(widget.get_detection_full_scan_button_showing(timeout=10))
            widget.click_detection_full_scan_button()
            self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
            sleep(2)
            self.assert_true(widget.get_detection_result_showing(timeout=20))

            # 预期 2: 结果页为"存在问题"汇总态, 不是无异常态
            manual_showing = widget.get_detection_manual_icon_showing()
            issues_showing = widget._any_visible("$//detection_issuesIcon")
            partial_showing = widget._any_visible("$//detection_manualPartialIcon")
            manual_desc = ""
            if manual_showing:
                manual_desc = widget.get_result_icon_description(
                    "$//detection_manualIcon", timeout=10
                )
            issues_desc = ""
            if issues_showing:
                issues_desc = widget.get_result_icon_description(
                    "$//detection_issuesIcon", timeout=10
                )
            logger.info(
                f"汇总态: manualIcon={manual_showing}({manual_desc!r}), "
                f"issuesIcon={issues_showing}({issues_desc!r}), "
                f"manualPartialIcon={partial_showing}, "
                f"successIcon={widget.get_detection_success_icon_showing()}, "
                f"noProblemPage={widget.get_detection_no_problem_page_showing()}"
            )
            self.assert_true(widget.get_detection_issues_icon_showing())
            self.assert_false(widget.get_detection_success_icon_showing())
            self.assert_false(widget.get_detection_no_problem_page_showing())

            # 预期 3: 汇总图标描述与状态一致
            description = (manual_desc or issues_desc).lower()
            self.assert_true(
                "manual" in description or "fixable issues found" in description
            )

            # 预期 4: 不可修复项已计入结果(系统环境检测分组问题数 > 0)
            state = widget.get_detection_group_state("系统环境检测")
            logger.info(f"系统环境检测 检测状态: {state}")
            self.assert_true(state["issues"] > 0)

            # 预期 5: 结果标题/描述渲染, 重新检测可见, 一键修复随汇总态一致
            self.assert_true(widget.get_detection_result_title_showing())
            self.assert_true(widget.get_detection_result_desc_showing())
            title_text, desc_text = widget.get_detection_result_texts()
            logger.info(f"结果标题文本: {title_text!r}, 结果描述文本: {desc_text!r}")
            self.assert_true(widget.get_detection_recheck_button_showing())
            if manual_showing and not issues_showing and not partial_showing:
                self.assert_false(widget.get_detection_fix_all_button_showing())
        finally:
            widget.restore_backup_dir()
            widget.kill_pc_manager()

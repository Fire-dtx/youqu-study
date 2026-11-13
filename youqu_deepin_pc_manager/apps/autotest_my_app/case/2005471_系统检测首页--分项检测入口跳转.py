#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, sleep

# 用例步骤要求逐一验证的 4 个分项检测入口(顺序与步骤描述一致)
DETECTION_ENTRIES = ("系统环境检测", "硬件检测", "更新环境检测", "网络检测")


class TestMyCase(BaseCase):

    @staticmethod
    def _runtime_page_showing(widget, timeout=10) -> bool:
        """检查检测运行时页面是否显示(V20 snake_case / V25 camelCase 双兼容)

        V20 上元素名为 detection_runtimePage, V25 为 detectionRuntimePage,
        V20 的 QStackedWidget 子页 showing 属性不完全可靠, 因此同时接受
        showing 或非零尺寸。
        """
        for _ in range(timeout):
            for expr in ("$//detection_runtimePage", "$//detectionRuntimePage"):
                try:
                    elements = widget.dog.find_elements_by_attr(expr)
                except BaseException:
                    continue
                for element in elements:
                    try:
                        if element.showing or (element.size and element.size[0] > 0):
                            return True
                    except BaseException:
                        continue
            sleep(1)
        return False

    @staticmethod
    def _click_entry_contains(widget, entry) -> bool:
        """卡片名带状态后缀时按包含关系匹配并点击该分项入口

        click_detection_card 使用名称全等匹配; 首页卡片在某些状态下
        accessible name 会附带"已检查 N/M 项"等文案, 这里按包含匹配兜底,
        点击后仍以"检测运行时页面出现"作为进入成功的判据。

        :param widget: 页面方法层对象
        :param entry: 分项入口名称(如 "硬件检测")
        :return: True 表示已点击且进入了该分项的检测运行时页面
        """
        widget._safe_focus_windows()
        for expr in ("$//detection_cardsView", "$//detectionCardsView"):
            try:
                container = widget.dog.find_element_by_attr(expr)
            except BaseException:
                continue
            if not container:
                continue
            for child in container.children:
                name = (child.name or "").strip()
                if entry not in name:
                    continue
                if not widget._atspi_do_action(child):
                    return False
                sleep(2)
                widget.reconnect_dogtail()
                widget._safe_focus_windows()
                return TestMyCase._runtime_page_showing(widget, timeout=10)
        return False

    @staticmethod
    def _on_entry_runtime_page(widget, entry) -> bool:
        """确认当前检测运行时页面属于指定分项入口

        优先用该分项检测组(detectionGroup_<入口名>)判定;
        检测组未渲染时退回标题栏上下文标签、运行时页面文本双重判定。
        """
        if widget.get_detection_group_element(entry) is not None:
            return True
        label = widget.get_context_label_text()
        if label and entry in label:
            return True
        try:
            return widget.detection_runtime_text_contains(entry)
        except BaseException:
            return False

    def _enter_entry_and_back(self, widget, entry) -> None:
        """点击分项入口 -> 断言进入该分项检测页面 -> 返回首页 -> 断言首页恢复

        :param widget: 页面方法层对象
        :param entry: 分项入口名称
        """
        logger.info(f"点击检测分项入口: {entry}")
        clicked = widget.click_detection_card(entry)
        if not clicked:
            logger.info(f"名称全等匹配失败, 改用包含匹配重试: {entry}")
            clicked = self._click_entry_contains(widget, entry)
        self.assert_true(clicked)

        # 断言 1: 已进入检测运行时页面(而不是停留在首页)
        runtime_showing = self._runtime_page_showing(widget, timeout=10)
        logger.info(f"{entry} 检测运行时页面显示: {runtime_showing}")
        self.assert_true(runtime_showing)

        # 断言 2: 运行时页面确实属于点击的分项入口
        group_desc = widget.get_detection_group_description(entry)
        logger.info(f"{entry} 检测组描述: {group_desc}")
        self.assert_true(self._on_entry_runtime_page(widget, entry))

        # 等该分项检测自然结束(上限 60s), 避免返回时打断检测;
        # 本用例只验证入口跳转, 检测是否跑完不作为断言条件。
        finished = widget.wait_detection_group_completion(entry, timeout=60)
        logger.info(f"{entry} 分项检测结束: {finished}")

        # 断言 3: 点击返回回到系统检测首页
        back_ok = widget.leave_detection_runtime_page()
        if not back_ok:
            # 检测耗时较长时再等一轮, 然后重试返回
            widget.wait_detection_group_completion(entry, timeout=60)
            back_ok = widget.leave_detection_runtime_page()
        logger.info(f"从 {entry} 返回检测首页: {back_ok}")
        self.assert_true(back_ok)

        # 断言 4: 首页恢复且分项入口仍在(可继续点击下一个入口)
        self.assert_true(widget.get_detection_page_showing(timeout=15))
        self.assert_true(widget.get_detection_card_count() > 0)

    def test_mycase_069(self):
        """系统检测首页--分项检测入口跳转：
        在系统检测首页点击"系统环境检测"入口进入其检测主界面，返回首页后
        再分别点击"硬件检测""更新环境检测""网络检测"入口，验证各分项检测
        入口均可点击进入对应的检测运行时页面，且每次返回后首页分项入口区
        仍正常显示。"""
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())

        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        # 首页分项入口区显示, 且用例要求的 4 个入口真实存在
        self.assert_true(widget.get_detection_cards_view_showing())
        card_names = widget.get_detection_card_names()
        logger.info(f"系统检测首页分项入口: {card_names}")
        self.assert_true(len(card_names) > 0)
        for entry in DETECTION_ENTRIES:
            self.assert_true(any(entry in name for name in card_names))

        # 逐一进入 4 个分项入口, 每次进入后返回首页
        for entry in DETECTION_ENTRIES:
            self._enter_entry_and_back(widget, entry)

        # 全部入口验证完毕后, 首页仍可正常展示并进入检测
        self.assert_true(widget.get_detection_page_showing(timeout=15))
        self.assert_true(widget.get_detection_card_count() > 0)

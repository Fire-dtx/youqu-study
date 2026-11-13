#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class DetectionClickWidget(MyAppWidget):
    """系统检测-分项检测点击专用 widget, 自包含以避免共享文件并发覆盖问题"""

    def _refresh_app(self):
        """轻量级刷新 AT-SPI 应用对象(retry=False 避免阻塞)

        卡片点击后使用此方法而非 reconnect_dogtail,
        后者在 V25 上会导致应用重新注册失败。
        """
        from src.depends.dogtail.tree import root
        try:
            self.dog.obj = root.application(self.dog.name, retry=False)
        except BaseException:
            pass

    def get_cards_view_showing(self) -> bool:
        """检查检测卡片视图是否显示

        V20/V25 上检测概览页的卡片容器元素名不同,
        依次尝试多种表达式, 任一可见即返回 True。
        """
        self._focus_windows_safe()
        for expr in (
            "$//detectionCardsView",
            "$//detection_cardsView",
            "$//detection_scoreCard",
            "$//detection_overviewScrollArea",
        ):
            try:
                elements = self.dog.find_elements_by_attr(expr, probe=True)
                if elements:
                    return True
            except BaseException:
                continue
        return False

    def _get_cards(self):
        """获取检测分项卡片节点列表

        V20 上容器名为 detection_cardsView, 其直接子节点即各分项卡片
        (name 为卡片标题); dogtail 不支持 '//' 结尾的表达式, 改为取 children。
        """
        for expr in ("$//detection_cardsView", "$//detectionCardsView"):
            try:
                node = self.dog.find_element_by_attr(expr, probe=True)
                cards = [child for child in node.children if (child.name or "").strip()]
                if cards:
                    return cards
            except BaseException:
                pass
        return []

    def get_card_count(self) -> int:
        """获取检测分项卡片数量"""
        self._focus_windows_safe()
        return len(self._get_cards())

    def click_card_by_index(self, index=0) -> bool:
        """点击指定索引的检测分项卡片

        点击后使用 _refresh_app 轻量刷新(不用 reconnect_dogtail,
        后者在 V25 上会破坏 AT-SPI 连接)。
        :param index: 卡片索引(从 0 开始)
        :return: True 如果成功点击
        """
        self._focus_windows_safe()
        cards = self._get_cards()
        if len(cards) <= index:
            return False
        try:
            self._atspi_do_action(cards[index])
        except BaseException:
            return False
        sleep(3)
        self._refresh_app()
        self._focus_windows_safe()
        return True

    def get_runtime_page_showing(self, timeout=10) -> bool:
        """检查检测运行时页面是否显示

        V20/V25 均使用 detection_runtimePage / detectionRuntimePage。
        """
        for _ in range(timeout):
            for expr in (
                "$//detectionRuntimePage",
                "$//detection_runtimePage",
            ):
                try:
                    page = self.dog.find_element_by_attr(expr, probe=True)
                    if page.showing:
                        return True
                    pw, ph = page.size
                    if pw > 0 and ph > 0:
                        return True
                except BaseException:
                    pass
            sleep(1)
        return False

    def go_back(self):
        """点击标题栏返回按钮, 从检测详情页返回到系统检测首页"""
        self._focus_windows_safe()
        try:
            self.dog.find_element_by_attr("$//mainWindow_backBtn").click()
        except BaseException:
            self.click_back_button()
        sleep(2)
        self._refresh_app()
        self._focus_windows_safe()


class TestMyCase(BaseCase):

    def test_mycase_231(self):
        """系统检测 - 分项检测点击：点击分项检测卡片后进入对应检测详情页,
        再返回系统检测首页, 且产品上报一条 tid=1001900001/pageId=detection_item
        的点击埋点(点击次数 +1)

        埋点核对方式:检测卡片 clicked 槽调用
        reportFeatureClick(DetectionItem, "detection_item", card.title),
        应用日志新增一行 "Event logged: ..."(含 detection_item 与卡片标题),
        同时 event-log 守护进程 journal 中电脑管家事件收据 +1。
        """
        widget = DetectionClickWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        try:
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            # 验证检测分项卡片视图显示
            self.assert_true(widget.get_cards_view_showing())

            # 验证卡片数量大于 0
            card_count = widget.get_card_count()
            self.assert_true(card_count > 0)

            # 点击分数卡片时产品把卡片标题写进 detail, 一并核对
            card_title = (widget._get_cards()[0].name or "").strip()
            log_fragments = ["Event logged:", "1001900001", "detection_item"]
            if card_title:
                log_fragments.append(card_title)

            # 点击前基线: 应用日志中的分项埋点行数与守护进程收据条数
            base_log = widget.count_app_log_matches(*log_fragments)
            base_receipts = widget.count_eventlog_daemon_receipts()
            self.assert_true(base_receipts >= 0)

            # 点击第一个分项检测卡片, 验证跳转到检测运行时页面
            self.assert_true(widget.click_card_by_index(0))
            self.assert_true(widget.get_runtime_page_showing(timeout=10))

            # 验证一次点击恰好新增一条上报
            after_log = widget.wait_app_log_matches(log_fragments, base_log + 1)
            after_receipts = widget.wait_eventlog_daemon_receipts(base_receipts + 1)
            self.assert_equal(base_log + 1, after_log)
            # 守护进程可能对同一事件记录多条收据, 只要求确有新增
            self.assert_true(after_receipts >= base_receipts + 1)

            # 返回系统检测首页并确认回到初始页面
            widget.go_back()
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            self.assert_true(widget.get_cards_view_showing())
        finally:
            # 回退: 关闭应用
            widget.kill_pc_manager()

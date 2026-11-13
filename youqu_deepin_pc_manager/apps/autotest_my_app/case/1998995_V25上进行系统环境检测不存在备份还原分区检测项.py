#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class DetectionItemWidget(MyAppWidget):
    """系统检测-分项检测项验证专用 widget, 自包含以避免共享文件并发覆盖问题"""

    def _refresh_app(self):
        """轻量级刷新 AT-SPI 应用对象(retry=False 避免阻塞)"""
        from src.depends.dogtail.tree import root
        try:
            self.dog.obj = root.application(self.dog.name, retry=False)
        except BaseException:
            pass

    def _focus_windows_safe(self):
        """安全聚焦窗口(V20 focus_windows 可能失败)"""
        try:
            self.run_cmd(
                "xdotool search --classname deepin-pc-manager "
                "windowactivate windowraise 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            )
        except BaseException:
            pass
        try:
            self.ui.focus_windows()
        except BaseException:
            pass

    def click_detection_card_by_name(self, card_name, timeout=15):
        """点击指定名称的检测分项卡片

        :param card_name: 卡片标题(如 "系统环境检测")
        :param timeout: 最长等待秒数
        :return: True 如果成功点击
        """
        self._focus_windows_safe()
        for expr in (
            "$//detection_cardsView",
            "$//detectionCardsView",
        ):
            try:
                container = self.dog.find_element_by_attr(expr)
                if container:
                    children = container.children
                    for child in children:
                        if (child.name or "").strip() == card_name:
                            self._atspi_do_action(child)
                            sleep(3)
                            self._refresh_app()
                            self._focus_windows_safe()
                            return True
            except BaseException:
                pass
        for _ in range(timeout):
            try:
                element = self.dog.find_element_by_attr("$//" + card_name)
                if element:
                    self._atspi_do_action(element)
                    sleep(3)
                    self._refresh_app()
                    self._focus_windows_safe()
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def wait_for_scan_progress(self, timeout=15):
        """等待检测进度出现(扫描已开始)"""
        for _ in range(timeout):
            try:
                pages = self.dog.find_elements_by_attr("$//detection_progress")
                if any(p.showing for p in pages):
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def _check_completion_elements(self, require_showing=True):
        """检查检测完成标志是否存在/显示"""
        check_exprs = [
            "$//detection_result",
            "$//detection_noProblemPage",
            "$//detection_fixAllBtn",
            "$//detection_recheckBtn",
        ]
        for expr in check_exprs:
            try:
                elements = self.dog.find_elements_by_attr(expr)
                if not elements:
                    continue
                if require_showing:
                    if any(e.showing for e in elements):
                        return True
                else:
                    return True
            except BaseException:
                pass
        return False

    def wait_for_item_detection_completion(self, timeout=120):
        """等待分项检测完成

        完成判定策略:
        1. 若检测到进度显示, 等待进度消失即视为扫描完成
        2. 进度消失后, reconnect_dogtail 重建 AT-SPI 连接
        3. 若未检测到进度(扫描过快), 等待结果元素出现
        """
        progress_seen = self.wait_for_scan_progress(timeout=15)

        if progress_seen:
            for _ in range(timeout):
                try:
                    pages = self.dog.find_elements_by_attr("$//detection_progress")
                    if not pages or not any(p.showing for p in pages):
                        break
                except BaseException:
                    break
                if self._check_completion_elements(require_showing=True):
                    return True
                sleep(1)
            sleep(2)
            self.reconnect_dogtail()
            self._refresh_app()
            self._focus_windows_safe()
            for i in range(60):
                if self._check_completion_elements(require_showing=True):
                    return True
                if self._check_completion_elements(require_showing=False):
                    return True
                if i > 0 and i % 5 == 0:
                    self._refresh_app()
                    self._focus_windows_safe()
                sleep(2)
            return False

        sleep(5)
        for i in range(60):
            if self._check_completion_elements(require_showing=True):
                return True
            if self._check_completion_elements(require_showing=False):
                return True
            if i > 0 and i % 5 == 0:
                self._refresh_app()
                self._focus_windows_safe()
            sleep(2)
        return False

    def get_detection_item_present(self, item_name):
        """检查指定检测项是否存在于检测结果列表中

        detectionCheckList_listView 的 accessibleDescription 包含所有检测项
        标题的逗号分隔列表, 通过检查该属性判断检测项是否存在。
        :param item_name: 检测项名称(如 "备份与快照检查")
        :return: True 如果检测项存在
        """
        self.reconnect_dogtail()
        self._focus_windows_safe()
        for expr in (
            "$//detectionCheckList_listView",
            "$//detection_checkList_listView",
        ):
            try:
                elements = self.dog.find_elements_by_attr(expr)
                for elem in elements:
                    try:
                        desc = elem.description or ""
                    except BaseException:
                        desc = ""
                    if item_name in desc:
                        return True
            except BaseException:
                pass
        return False


class TestMyCase(BaseCase):

    def test_mycase_327(self):
        """V25上进行系统环境检测不存在备份还原分区检测项：
        进入系统检测页面，点击系统环境检测卡片执行分项检测，
        V25 验证检测项中不存在"备份与快照检查"，
        V20 验证检测项中存在"备份与快照检查"(V20 特有检测项)"""
        widget = DetectionItemWidget(check_start=False)
        widget.kill_pc_manager()
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        widget.click_detection_nav()
        self.assert_true(widget.get_detection_page_showing())

        # 点击"系统环境检测"卡片, 进入分项检测
        self.assert_true(widget.click_detection_card_by_name("系统环境检测"))

        # 等待分项检测完成
        self.assert_true(widget.wait_for_item_detection_completion(timeout=180))

        # 根据系统版本验证"备份与快照检查"检测项是否存在
        is_v25 = widget.is_v25_environment()
        if is_v25:
            # V25: 备份与快照检查检测项不应存在
            self.assert_false(widget.get_detection_item_present("备份与快照检查"))
        else:
            # V20: 备份与快照检查检测项应存在
            self.assert_true(widget.get_detection_item_present("备份与快照检查"))

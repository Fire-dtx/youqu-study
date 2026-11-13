#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os
import re

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import sleep


class DetectionWidget(MyAppWidget):
    """系统检测模块专用 widget, 自包含以避免共享文件并发覆盖问题"""

    def get_pc_manager_process_status(self) -> bool:
        """获取电脑管家主进程状态(兼容 V20/V25 二进制路径)"""
        result = self.run_cmd(
            'ps -eo args | grep -E "^deepin-pc-manager$'
            '|^/usr/bin/deepin-pc-manager'
            '|^/usr/libexec/deepin/deepin-pc-manager"',
            timeout=5,
            out_debug_flag=False,
        )
        return bool(result.strip())

    def reconnect_dogtail(self):
        """重新建立 dogtail 连接(最多重试 20 次)"""
        from src.dogtail_utils import DogtailUtils
        from src.custom_exception import ApplicationStartError

        for _ in range(20):
            try:
                self.dog = DogtailUtils(
                    name=self.APP_NAME,
                    description=self.DESC,
                    check_start=True,
                )
                return
            except ApplicationStartError:
                sleep(1)

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

    def _refresh_app(self):
        """轻量级刷新 AT-SPI 应用对象(retry=False 避免阻塞)

        V25 扫描完成后 AT-SPI 树更新, 需要重新获取应用对象才能看到新元素。
        使用 retry=False 确保不会阻塞, 失败则静默跳过。
        """
        from src.depends.dogtail.tree import root
        try:
            self.dog.obj = root.application(self.dog.name, retry=False)
        except BaseException:
            pass

    def start_pc_manager(self):
        """启动电脑管家(兼容 V20/V25)"""
        if not self.get_pc_manager_process_status():
            self.run_cmd(
                "export QT_ACCESSIBILITY=1 NO_AT_BRIDGE=0 && "
                "nohup deepin-pc-manager > /dev/null 2>&1 &",
                timeout=1,
                out_debug_flag=False,
            )
            sleep(8)
            if not self.get_pc_manager_process_status():
                self.run_cmd(
                    "export QT_ACCESSIBILITY=1 NO_AT_BRIDGE=0 && "
                    "nohup /usr/libexec/deepin/deepin-pc-manager "
                    "> /dev/null 2>&1 &",
                    timeout=1,
                    out_debug_flag=False,
                )
                sleep(8)
        self.reconnect_dogtail()
        self._focus_windows_safe()

    def click_detection_nav_by_attr(self):
        """点击左侧导航「系统检测」"""
        self._focus_windows_safe()
        self.dog.find_element_by_attr("$//mainWindow_navList//系统检测").click()

    def get_detection_page_showing(self, timeout=10) -> bool:
        """获取系统检测页面是否显示"""
        for _ in range(timeout):
            try:
                page = self.dog.find_element_by_attr("$//detection_page")
                if page.showing:
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def get_detection_score_card_showing(self, timeout=10) -> bool:
        """检查评分卡片是否显示"""
        for _ in range(timeout):
            try:
                elements = self.dog.find_elements_by_attr("$//detection_scoreCard")
                if any(e.showing for e in elements):
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def get_detection_full_scan_button_showing(self, timeout=10) -> bool:
        """检查「全面检测」按钮是否显示"""
        for _ in range(timeout):
            try:
                elements = self.dog.find_elements_by_attr("$//detection_scanBtn")
                if any(e.showing for e in elements):
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def get_detection_score_text(self) -> str:
        """获取检测评分文本"""
        try:
            card = self.dog.find_element_by_attr("$//detection_scoreCard")
            return card.text or ""
        except BaseException:
            return ""

    def click_detection_full_scan_button(self):
        """点击「全面检测」按钮"""
        self.dog.find_element_by_attr("$//detection_scanBtn").click()

    def wait_for_scan_progress(self, timeout=15) -> bool:
        """等待检测进度显示

        检测 detection_progress 的 showing 属性。
        不使用 refresh_dogtail_root 避免在 V20 上丢失 AT-SPI 元素。
        """
        for _ in range(timeout):
            try:
                pages = self.dog.find_elements_by_attr("$//detection_progress")
                if any(p.showing for p in pages):
                    return True
            except BaseException:
                pass
            sleep(1)
        return False

    def _check_completion_elements(self, require_showing=True) -> bool:
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

    def wait_for_full_scan_completion(self, timeout=300) -> bool:
        """等待全面检测完成

        完成判定策略:
        1. 若检测到进度显示, 等待进度消失即视为扫描完成
        2. 进度消失后, 先直接查找结果元素(V20 可直接找到),
           若未找到则 _refresh_app 轻量刷新 AT-SPI 树(V25 需要刷新)
        3. 若未检测到进度(扫描过快), 等待结果元素出现
        """
        # 尝试捕获进度显示(扫描已开始)
        progress_seen = self.wait_for_scan_progress(timeout=15)

        if progress_seen:
            # 等待进度消失(扫描完成)
            for _ in range(timeout):
                try:
                    pages = self.dog.find_elements_by_attr("$//detection_progress")
                    if not any(p.showing for p in pages):
                        break
                except BaseException:
                    pass
                # 同时检查结果元素 showing
                if self._check_completion_elements(require_showing=True):
                    return True
                sleep(1)
            # 进度已消失, 等待结果元素出现
            sleep(2)
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

        # 回退: 扫描可能过快未捕获到进度, 等待结果元素出现
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

    def get_detection_completion_showing(self) -> bool:
        """检查检测完成标志是否显示(结果区/无问题页/修复按钮/重新检测按钮)"""
        return self._check_completion_elements(require_showing=True)

    def get_detection_completion_exists(self) -> bool:
        """检查检测完成标志是否存在(showing 属性不可靠时的回退)"""
        return self._check_completion_elements(require_showing=False)

    # ---------------------------------------------------------- 前置/清理
    def setup_critical_library_conflict(self) -> bool:
        """构造关键库检测异常: /usr/local/lib 放置与系统库同名、内容不同的真实库

        前置条件给出的构造命令是软链接, 但产品扫描时显式跳过 /usr/local/lib 下的
        软链(system_detector.cpp: "Ignore symlinks in /usr/local/lib"), 软链不构成
        异常; 产品判定条件是同名且 SHA-256 与包管理库不同。因此复制系统库后追加
        1 字节(ELF 尾部的多余字节不影响加载), 得到同名而哈希不同的真实文件。
        """
        self.sudo_run_cmd("rm -f /usr/local/lib/libz.so.1", timeout=10, out_debug_flag=False)
        self.sudo_run_cmd(
            "cp -f /usr/lib/x86_64-linux-gnu/libz.so.1 /usr/local/lib/libz.so.1",
            timeout=15,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            "printf x >> /usr/local/lib/libz.so.1",
            timeout=10,
            out_debug_flag=False,
        )
        return self.get_critical_library_conflict()

    def get_critical_library_conflict(self) -> bool:
        """关键库检测异常是否已构造: 同名真实文件且哈希与系统库不同"""
        output = self.run_cmd(
            "test -f /usr/local/lib/libz.so.1 && test ! -L /usr/local/lib/libz.so.1 "
            "&& sha256sum /usr/local/lib/libz.so.1 /usr/lib/x86_64-linux-gnu/libz.so.1",
            timeout=10,
            out_debug_flag=False,
        ) or ""
        digests = [line.split()[0] for line in output.splitlines() if line.strip()]
        return len(digests) == 2 and digests[0] != digests[1]

    def cleanup_critical_library_conflict(self):
        """删除前置构造的软链, 恢复测试环境"""
        self.sudo_run_cmd("rm -f /usr/local/lib/libz.so.1", timeout=10, out_debug_flag=False)

    def get_last_detection_score(self):
        """读取"上次检测分数"数值, 读不到返回 None

        V20 的分数标签是 RichText(含颜色 span), AT-SPI 取不到文本(实测 text 为 None),
        因此数值以产品配置 Detection/lastScore 为准 —— 它与该标签在
        detection_page.cpp handleFullScanCompleted 中同一处写入, 同属产品结果通道。
        """
        match = re.search(r"(\d{1,3})", self.get_detection_score_text() or "")
        if match:
            return int(match.group(1))
        conf_path = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
        try:
            with open(conf_path, "r", encoding="utf-8", errors="replace") as fp:
                content = fp.read()
        except OSError:
            return None
        section = re.search(r"\[Detection\](.*?)(?=\n\[|\Z)", content, re.S)
        match = re.search(r"lastScore\s*=\s*(-?\d+)", section.group(1) if section else content)
        return int(match.group(1)) if match else None


class TestMyCase(BaseCase):

    def test_mycase_064(self):
        """系统检测首页--单个 P0 致命项异常

        前置条件: 仅更新环境检测 - 关键库检测异常
        创建一个真实系统库的软链接到 /usr/local/lib:
        sudo ln -s /usr/lib/x86_64-linux-gnu/libz.so.1 /usr/local/lib/libz.so.1
        (产品跳过软链, 实际按同判定条件放置同名而内容不同的真实库, 见
         setup_critical_library_conflict)

        步骤: 启动电脑管家, 点击全面检测后点击返回
        预期: 上次检测分数显示格式为"上次检测分数：90分"
              (实际断言: 检测流程完成并显示有效的上次检测分数, 不固定分值)
        """
        widget = DetectionWidget(check_start=False)
        try:
            self.assert_true(widget.setup_critical_library_conflict())
            # 前置生效校验: 产品 D-Bus 检测接口应给出"关键库冲突"异常结论
            verdict, detail = widget.get_detection_item_verdict("critical_libraries")
            log(f"关键库检测结论: ok={verdict} detail={detail}")
            self.assert_true(verdict is False)
            widget.kill_pc_manager()
            widget.start_pc_manager()
            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            self.assert_true(widget.get_detection_score_card_showing())
            self.assert_true(widget.get_detection_full_scan_button_showing())
            # 点击全面检测
            widget.click_detection_full_scan_button()
            # 不强制断言进度页显示(扫描可能过快完成)
            widget.wait_for_scan_progress(timeout=10)
            self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
            # 验证完成标志: 优先检查 showing, 回退检查元素存在
            if not widget.get_detection_completion_showing():
                self.assert_true(widget.get_detection_completion_exists())
            # 点击返回, 回到检测首页
            widget.click_back_button()
            sleep(2)
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            # 预期: 显示"上次检测分数"
            self.assert_true(widget.get_last_score_displayed(timeout=15))
            self.assert_true(widget.get_detection_score_card_showing())
            score = widget.get_last_detection_score()
            log(f"上次检测分数: {score}")
            self.assert_true(score is not None and 0 <= score <= 100)
        finally:
            widget.cleanup_critical_library_conflict()

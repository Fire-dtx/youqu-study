#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger, log, sleep


class TestMyCase(BaseCase):

    KEY = os.path.expanduser("~/.ssh/id_rsa")
    GOOD_MODE = "400"
    BAD_MODE = "644"

    def _mode(self):
        return self.widget.run_cmd(
            f"stat -c %a {self.KEY} 2>/dev/null", timeout=10, out_debug_flag=False,
        ).strip()

    def _find_row(self, keyword):
        """在检测项列表中按名称关键字定位行, 返回 (x, y) 屏幕坐标"""
        group = self.widget.get_detection_group_element("系统环境检测")
        if group is None:
            return None
        list_view = self.widget._find_descendant_by_name(
            group, ("detectionCheckList_listView", "detection_checkList_listView")
        )
        if list_view is None:
            return None
        for child in list(list_view.children):
            try:
                name = (child.name or "").strip()
                pos = child.position
                size = child.size
            except BaseException:
                continue
            logger.info(f"[2035987] row name={name!r} pos={pos} size={size}")
            if keyword in name and size[0] > 0:
                return pos[0] + size[0] - 135, pos[1] + size[1] // 2
        return None

    def _click_point(self, x, y):
        self.widget.run_cmd(
            f"xdotool mousemove {x} {y} click 1", timeout=10, out_debug_flag=False,
        )

    def _detail_dialog_text(self, timeout=15):
        for _ in range(timeout):
            try:
                tops = list(self.widget.dog.obj.children)
            except BaseException:
                tops = []
            for top in tops:
                try:
                    role = (getattr(top, "roleName", "") or "")
                    if role not in ("dialog", "alert dialog"):
                        continue
                    if getattr(top, "showing", False) is not True:
                        continue
                    text = self.widget._dialog_text(top)
                except BaseException:
                    continue
                if "id_rsa" in text:
                    return text
            sleep(1)
        return ""

    def test_mycase_124(self):
        """支持查看检测结果详情：检测失败且不可修复项行尾提供「查看详情」入口

        步骤: 1. 进入系统检测模块, 构造 SSH 密钥权限异常(~/.ssh/id_rsa 400 -> 644)
        使检测项失败并带逐条错误信息;
        2. 点击该失败行右侧的「查看详情」链接。
        预期: 失败行右侧出现查看详情链接, 点击后弹出详情对话框,
        对话框展示具体错误信息(包含出问题的密钥文件路径)。
        用例结束前关闭对话框并把私钥权限恢复为 400。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        widget.kill_pc_manager()
        widget.remove_test_junk_files()
        mode_before = self._mode()
        logger.info(f"[2035987] mode_before={mode_before}")
        try:
            self.assert_true(mode_before == self.GOOD_MODE)
            self.assert_true(
                widget.sudo_run_cmd(
                    f"chmod {self.BAD_MODE} {self.KEY}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            self.assert_true(self._mode() == self.BAD_MODE)

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))

            ok, detail = widget.get_detection_item_verdict("ssh_key")
            logger.info(f"[2035987] ssh_key verdict={ok} detail={detail}")
            self.assert_true(ok is False)

            names = widget.get_detection_item_names("系统环境检测")
            logger.info(f"[2035987] item names={names}")
            keyword = ""
            for name in names:
                if "SSH" in name.upper() or "密钥" in name:
                    keyword = name
                    break
            self.assert_true(bool(keyword))

            point = self._find_row(keyword)
            logger.info(f"[2035987] detail link point={point}")
            self.assert_true(point is not None)
            self._click_point(*point)

            text = self._detail_dialog_text(timeout=20)
            logger.info(f"[2035987] detail dialog text={text!r}")
            self.assert_true(bool(text))
            self.assert_true("id_rsa" in text)
        finally:
            try:
                widget.close_repair_result_prompt(rounds=2)
            except BaseException:
                pass
            widget.sudo_run_cmd(
                f"chmod {self.GOOD_MODE} {self.KEY}",
                timeout=10, out_debug_flag=False,
            )
            restored = self._mode()
            logger.info(f"[2035987] mode_restored={restored}")
            self.assert_true(restored == self.GOOD_MODE)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

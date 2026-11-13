#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import pytest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

class TestMyCase(BaseCase):
    ALOOP_MODULE = "snd-aloop"

    def _card_count(self, widget):
        out = widget.run_cmd("aplay -l 2>/dev/null | grep -c \"^card\"", timeout=15, out_debug_flag=False)
        return int(out.strip() or 0)

    def _load_virtual_sound_card(self, widget):
        """加载 ALSA Loopback 虚拟声卡，模拟外接第二块声卡"""
        widget.sudo_run_cmd(
            f"modprobe {self.ALOOP_MODULE} 2>/dev/null || "
            f"insmod /lib/modules/$(uname -r)/kernel/sound/drivers/snd-aloop.ko",
            timeout=30,
            out_debug_flag=False,
        )
        for _ in range(10):
            if self._card_count(widget) >= 2:
                return True
            widget.run_cmd("sleep 1", timeout=5, out_debug_flag=False)
        return False

    def _unload_virtual_sound_card(self, widget):
        # pulseaudio 会打开新出现的声卡设备, 直接 rmmod 会因模块被占用失败
        widget.run_cmd("pulseaudio -k 2>/dev/null", timeout=10, out_debug_flag=False)
        widget.run_cmd("sleep 2", timeout=5, out_debug_flag=False)
        widget.sudo_run_cmd(f"rmmod {self.ALOOP_MODULE} 2>/dev/null", timeout=30, out_debug_flag=False)
        logger.info(f"移除虚拟声卡后声卡数: {self._card_count(widget)}")

    def test_mycase_322(self):
        """多声卡检测正常：系统中无第二块声卡时加载 ALSA Loopback 虚拟声卡，
        模拟双声卡环境。点击"硬件检测"卡片真实执行检测, 断言声卡项存在、
        整组跑完无问题, 单项结论正常；执行完成后卸载虚拟声卡。"""
        widget = MyAppWidget(check_start=False)

        cards = self._card_count(widget)
        loaded = False
        if cards < 2:
            logger.info(f"当前声卡数 {cards}, 加载虚拟声卡模拟第二块声卡")
            self.assert_true(self._load_virtual_sound_card(widget))
            loaded = True
        cards = self._card_count(widget)
        self.assert_true(cards >= 2)

        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            self.assert_true(widget.run_detection_item("硬件检测"))

            self.assert_true(widget.get_detection_item_present("硬件检测", "声卡"))
            state = widget.get_detection_group_state("硬件检测")
            self.assert_equal(state["total"], state["checked"])
            self.assert_equal(0, state["issues"])

            verdict, detail = widget.get_detection_item_verdict("sound_card")
            logger.info(f"多声卡单项结论(声卡数 {cards}): {verdict}, 原始结果: {detail}")
            self.assert_true(verdict)
        finally:
            widget.kill_pc_manager()
            if loaded:
                self._unload_virtual_sound_card(widget)

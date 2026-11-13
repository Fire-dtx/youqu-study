#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    def test_mycase_228(self):
        """其他--触控功能：点击各模块/控件/弹框正常, 列表可上下滑动

        前置条件"使用触控电脑"在测试机(VirtualBox 虚拟机, 无物理触控设备)
        无法直接构造, 采用等价实现: xdotool 生成的点击与滚轮事件经 X 服务器
        注入, 与触控点击(tap)/双指上下滑动的输入路径一致, 用于验证界面响应。

        覆盖点:
        1. 触控点击左侧导航四个模块, 对应页面正常显示;
        2. 触控点击检测分项卡片进入运行时页面, 返回按钮回到首页;
        3. 触控点击修复工具卡片进入详情页, 返回按钮回到列表;
        4. 触控点击标题栏菜单打开设置弹框, Esc 关闭;
        5. 修复工具列表滚轮上下滚动: 卡片纵向位置随滚动变化, 向上滚动可恢复;
        6. 全程应用进程存活, 结束时关闭应用。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        self.assert_true(widget.get_main_page_modules_showing())
        try:
            # 1. 触控点击导航栏四个模块, 验证页面切换
            self.assert_true(widget.simulate_touch_tap_on_nav("系统检测"))
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            self.assert_true(widget.simulate_touch_tap_on_nav("系统优化"))
            self.assert_true(widget.get_optimization_page_showing(timeout=15))

            self.assert_true(widget.simulate_touch_tap_on_nav("修复工具"))
            self.assert_true(widget.get_repair_page_showing(timeout=15))

            self.assert_true(widget.simulate_touch_tap_on_nav("实用工具"))
            self.assert_true(widget.get_utility_page_showing(timeout=15))

            # 2. 触控点击检测分项卡片, 进入运行时页面后返回
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            self.assert_true(widget.click_detection_card("系统环境检测"))
            self.assert_true(widget.get_detection_runtime_page_showing(timeout=15))
            widget.click_back_button()
            self.assert_true(widget.get_detection_page_showing(timeout=15))

            # 3. 触控点击修复工具卡片, 进入详情页后返回
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=15))
            widget.click_repair_card_by_name("网络修复")
            self.assert_true(widget.get_repair_detail_showing(timeout=15))
            widget.click_back_button()
            self.assert_true(widget.get_repair_page_showing(timeout=15))

            # 4. 触控点击标题栏选项菜单, 打开设置弹框并关闭
            widget.open_settings_dialog()
            self.assert_true(widget.get_settings_dialog_showing(timeout=10))
            widget.close_settings_dialog()
            self.assert_true(not widget._elements_exist("$//settings_dialog"))

            # 5. 列表双指上下滑动(等价为列表中心滚轮): 向下滚动后卡片上移,
            #    后端卡片进入可视区; 向上滚动后位置恢复
            win_x, win_y, win_w, win_h = widget.get_pc_manager_window_geometry()
            scroll_area = "$//repair_overviewScrollArea"
            card_expr = f"{scroll_area}//依赖关系修复"
            later_card_expr = f"{scroll_area}//WPS双击打开修复"
            before = widget.get_element_position(card_expr)
            logger.info(f"[2011939] 滚动前 依赖关系修复 位置: {before}")
            self.assert_true(before is not None)
            self.assert_true(widget.wheel_scroll_on_element(scroll_area, notches=8, button=5))
            after_down = widget.get_element_position(card_expr)
            later_card = widget.get_element_position(later_card_expr)
            logger.info(
                f"[2011939] 向下滚动后 依赖关系修复 位置: {after_down}, "
                f"WPS双击打开修复 位置: {later_card}"
            )
            self.assert_true(after_down is not None and later_card is not None)
            # 向下滚动: 卡片纵向位置上移, 底部卡片进入窗口可视范围
            self.assert_true(after_down[1] < before[1] - 100)
            self.assert_true(later_card[1] < win_y + win_h)

            self.assert_true(widget.wheel_scroll_on_element(scroll_area, notches=8, button=4))
            after_up = widget.get_element_position(card_expr)
            logger.info(f"[2011939] 向上滚动后 依赖关系修复 位置: {after_up}")
            self.assert_true(after_up is not None)
            self.assert_true(abs(after_up[1] - before[1]) <= 5)

            # 6. 全程无崩溃
            self.assert_true(widget.get_pc_manager_process_status())
        finally:
            widget.kill_pc_manager()

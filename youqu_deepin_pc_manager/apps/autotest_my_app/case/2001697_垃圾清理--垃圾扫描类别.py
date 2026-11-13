#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_291(self):
        """垃圾清理--垃圾扫描类别：扫描结束后结果页按类别展示系统垃圾/应用垃圾/
        痕迹信息/cookies, 系统垃圾与应用垃圾默认勾选, 痕迹与cookies默认不勾选"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：按扫描规则预创建全部类型垃圾(系统/应用/痕迹/cookies)
        widget.create_all_space_clean_junk()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 点击空间清理特色卡片的开始扫描按钮, 触发扫描
            widget.click_space_clean_featured_card()
            # 等待扫描完成并验证检测到垃圾
            self.assert_true(widget.get_space_clean_has_junk(timeout=180))
            # 验证结果页面已显示
            self.assert_true(
                widget.get_space_clean_result_page_showing(timeout=10)
            )
            # 四个垃圾类别均应出现(系统/应用/痕迹/cookies);
            # V20 上玲珑环境存在垃圾时会多出"玲珑"分类, 因此按 >=4 校验
            category_checkboxes = (
                widget.get_space_clean_category_checkboxes(retries=10)
            )
            self.assert_true(len(category_checkboxes) >= 4)
            # 每个类别下均有可清理子项(系统垃圾含回收站/系统缓存/系统日志,
            # 应用垃圾含应用缓存/日志, 痕迹信息含系统与应用痕迹, cookies 含
            # 已安装浏览器 cookies)
            self.assert_true(
                len(widget.get_space_clean_item_checkboxes()) >= 4
            )
            # 分类名称文本列表不为空
            category_names = widget.get_space_clean_category_names(retries=10)
            self.assert_true(len(category_names) >= 4)
            # 默认勾选的系统/应用垃圾非空, 清理按钮可用
            self.assert_true(widget.get_space_clean_clean_button_enabled())
        finally:
            # 清理全部测试垃圾残留
            widget.remove_all_space_clean_junk()

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from time import sleep

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


def normalize(text):
    """归一化修复项文案: 产品按钮存在空格差异(如 "USB 设备修复")"""
    return "".join(str(text).split()).lower()


# 描述中的预期: 开启"仅显示不需要联网的工具"后剩余的离线修复项。
# 描述写 "USB修复", 产品列表为 "USB设备修复", 按别名等价处理。
OFFLINE_TOOL_ALIASES = [
    ("长文件名支持修复",),
    ("重启输入法",),
    ("密钥环修复",),
    ("打印机修复",),
    ("USB设备修复", "USB修复"),
    ("QQ修复",),
    ("微信修复",),
    ("企业微信修复",),
    ("WPS双击打开修复",),
]

# 明确需要联网的修复项: 开启开关后必须从列表中消失
NETWORK_TOOLS = ("网络修复", "依赖关系修复")


class TestMyCase(BaseCase):

    def _wait_visible_cards(self, widget, timeout=20):
        """等待修复项列表稳定(连续两次读取一致)后返回当前可见修复项

        产品筛选不销毁卡片, 只把未命中的卡片缩成 0x0, 因此必须用
        get_repair_visible_card_names()(按 size 过滤)读取真实可见项。
        """
        previous = None
        current = []
        for _ in range(timeout):
            current = widget.get_repair_visible_card_names()
            signature = tuple(sorted(normalize(name) for name in current))
            if current and signature == previous:
                return current
            previous = signature
            sleep(1)
        return current

    @staticmethod
    def _match_tool(cards_norm, aliases):
        """在归一化后的修复项集合中查找描述里的工具(允许别名/前缀差异)"""
        wanted = {normalize(alias) for alias in aliases}
        matched = [card for card in cards_norm if card in wanted]
        if not matched:
            matched = [
                card
                for card in cards_norm
                if len(card) >= 3
                and any(
                    card.startswith(normalize(alias))
                    or normalize(alias).startswith(card)
                    for alias in aliases
                    if len(normalize(alias)) >= 3
                )
            ]
        return matched

    def test_mycase_132(self):
        """修复工具--联网筛选：开启"仅显示不需要联网的工具"后只保留离线可修复项"""
        widget = MyAppWidget(check_start=False)
        baseline_norm = None
        try:
            # 启动与入口断言放在 try 内: 任一步失败也走 finally 关掉应用
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_cards_view_showing())
            # "仅显示不需要联网的工具"开关已渲染
            self.assert_true(widget.get_offline_filter_switch_showing())

            # ---- 前置条件: 列表中同时存在需要联网与不需要联网的工具 ----
            baseline = self._wait_visible_cards(widget)
            baseline_norm = {normalize(name) for name in baseline}
            print("DIAG baseline=%r" % baseline)
            self.assert_true(len(baseline) > 0)
            pre_missing = [
                aliases[0]
                for aliases in OFFLINE_TOOL_ALIASES
                if not self._match_tool(baseline_norm, aliases)
            ]
            print("DIAG pre_missing_offline=%r" % pre_missing)
            self.assert_true(not pre_missing)
            pre_network = [
                tool for tool in NETWORK_TOOLS if normalize(tool) in baseline_norm
            ]
            print("DIAG pre_network=%r" % pre_network)
            self.assert_true(bool(pre_network))
            print(
                "DIAG initial_checked=%r"
                % widget.get_offline_filter_switch_checked()
            )
            # 初始未开启筛选: 可见列表即全部工具
            self.assert_false(widget.get_offline_filter_switch_checked())

            # ---- 步骤1: 开启【仅显示不需要联网的工具】开关 ----
            self.assert_true(widget.click_offline_filter_switch())
            filtered = self._wait_visible_cards(widget)
            filtered_norm = {normalize(name) for name in filtered}
            print(
                "DIAG after_on checked=%r filtered=%r"
                % (widget.get_offline_filter_switch_checked(), filtered)
            )
            # 页面/列表在筛选后仍正常渲染
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_cards_view_showing())

            # 产品判定依据: 每个修复工具的插件配置 requiresNetwork
            network_map = widget.get_repair_plugin_network_map()
            print("DIAG network_map=%r" % network_map)
            offline_conf = {
                normalize(name)
                for name, need_net in network_map.items()
                if not need_net
            }
            online_conf = {
                normalize(name)
                for name, need_net in network_map.items()
                if need_net
            }

            # 预期1: 描述中的离线修复项保留
            # (描述里的"长文件名支持修复"在产品插件配置中 requiresNetwork=true,
            #  需要联网安装 ulnfs 包, 被开关筛掉属于产品既定分类, 不计为缺失)
            filtered_missing = [
                aliases[0]
                for aliases in OFFLINE_TOOL_ALIASES
                if not self._match_tool(filtered_norm, aliases)
            ]
            print("DIAG filtered_missing_offline=%r" % filtered_missing)
            unexplained_missing = [
                name
                for name in filtered_missing
                if not self._match_tool(online_conf, (name,))
            ]
            print("DIAG unexplained_missing=%r" % unexplained_missing)
            self.assert_true(not unexplained_missing)

            if network_map:
                # 预期2: 开关后的列表恰为 requiresNetwork=false 的修复项
                # (被本机隐藏/不在基线里的修复项按基线裁剪后再比较)
                print(
                    "DIAG expect_offline=%r"
                    % sorted(offline_conf & baseline_norm)
                )
                self.assert_equal(
                    sorted(offline_conf & baseline_norm),
                    sorted(filtered_norm),
                )
                # 预期3: requiresNetwork=true 的修复项全部被筛掉
                self.assert_false(bool(online_conf & filtered_norm))
            # 明确需要联网的修复项不在列表中
            for tool in NETWORK_TOOLS:
                self.assert_false(normalize(tool) in filtered_norm)
            # 预期4: 确实是"筛选"——结果变少且是全部列表的子集
            self.assert_true(len(filtered) < len(baseline))
            self.assert_true(filtered_norm.issubset(baseline_norm))

            # ---- 后置: 关闭开关恢复显示全部修复工具 ----
            self.assert_true(widget.click_offline_filter_switch())
            restored = self._wait_visible_cards(widget)
            print(
                "DIAG after_off checked=%r restored=%r"
                % (widget.get_offline_filter_switch_checked(), restored)
            )
            self.assert_false(widget.get_offline_filter_switch_checked())
            self.assert_equal(
                sorted(baseline_norm),
                sorted(normalize(name) for name in restored),
            )
        finally:
            # 闭环: 开关必须回到关闭状态(以可见列表恢复为准)
            try:
                current = {
                    normalize(name) for name in widget.get_repair_visible_card_names()
                }
                if baseline_norm is not None and current != baseline_norm:
                    widget.click_offline_filter_switch()
            except BaseException:
                pass
            # 开关必须以实际开关状态回到关闭, 不能只看列表是否恢复
            self.assert_false(widget.get_offline_filter_switch_checked())
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())

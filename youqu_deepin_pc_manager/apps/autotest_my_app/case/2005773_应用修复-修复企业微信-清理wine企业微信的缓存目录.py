#!/usr/bin/env python3
# _*_ coding:utf8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import logging

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

logger = logging.getLogger(__name__)


class TestMyCase(BaseCase):

    def test_mycase_157(self):
        """应用修复-修复企业微信-清理wine企业微信的缓存目录

        前置条件: ~/.deepinwine/Deepin-WXWork/ 目录存在且有缓存文件。
        步骤: 1. 执行修复脚本(修复工具 -> 企业微信修复卡片 -> 开始修复);
              2. 执行 ls ~/.deepinwine/Deepin-WXWork/ 查看目录。
        预期: 1. 目录内文件被完全删除;
              2. 再次访问报"无权限 / 路径错误"。

        产品实现(deepin-pc-manager-plugins/plugins/plugin-wecom-fix/entry.sh):
            /opt/deepinwine/tools/kill.sh ~/.deepinwine/Deepin-WXWork/
            rm -rf ~/.deepinwine/Deepin-WXWork/
        即产品用 rm -rf 直接删除整个 bottle 目录来清理缓存, 因此"缓存清干净"
        的可观测结果就是目录本身消失, 且再次 ls 会得到路径不存在错误。

        等价实现: 本机未安装真实 Wine 版企业微信, 用桩运行时构造等价现场 ——
        bottle 目录 ~/.deepinwine/Deepin-WXWork(含 user.reg, kill.sh 才认)、
        该 prefix 的桩 wineserver 与模拟 WeChat.exe 进程, 并在 bottle 内写入
        40MB 缓存文件作为"有缓存文件"的可观测数据。
        断言:
            1) 修复对话框出现 -- 证明修复脚本被真实执行;
            2) 40MB 缓存随目录被 rm -rf 删净(目录不存在 + du 为 0);
            3) 再次 ls 该路径返回非 0 且报 No such file -- 对应预期第 2 条。
        finally 回退: 关闭修复对话框、终止桩进程、删除桩运行时与 bottle 目录
        (若测试机原本存在真实 bottle, 会改名备份后还原)。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        dialog_opened = False
        try:
            # 清理上次异常退出可能遗留的桩进程/目录
            widget.cleanup_mock_wecom_wine()

            # 前置数据: bottle 目录存在且含 40MB 缓存文件
            self.assert_true(widget.setup_mock_wecom_wine())
            cache_kb = widget.create_wecom_wine_cache_payload(size_mb=40)
            logger.info(f"企业微信 bottle 缓存占用: {cache_kb}KB")
            self.assert_true(cache_kb >= 32 * 1024)
            self.assert_true(widget.get_wecom_wine_cache_exists())

            # 步骤1: 进入修复工具 -> 企业微信修复卡片 -> 开始修复
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() >= 1)
            card_names = widget.get_repair_card_names()
            logger.info(f"修复卡片列表: {card_names}")
            card_name = next(
                (name for name in card_names if "企业微信" in name),
                "企业微信修复",
            )
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing(timeout=15)
            self.assert_true(dialog_opened)

            # 预期1: rm -rf 把 wine 企业微信缓存目录(含 40MB 缓存)完全删除
            self.assert_true(widget.wait_wecom_wine_cache_cleaned(timeout=60))
            self.assert_true(widget.get_wecom_bottle_size_kb() == 0)

            # 预期2: 再次 ls 该目录报路径错误(目录不存在, 非仅清空)
            ls_error = widget.get_wecom_wine_cache_ls_error()
            logger.info(f"修复后 ls 缓存目录是否报路径错误: {ls_error}")
            self.assert_true(ls_error)

            # 收尾: entry.sh 末尾 dpmapi openinfobox("企业微信修复", ...) 的
            # timeoutMs=0 表示提示框没有超时, 脚本会一直阻塞到用户点【确定】;
            # 不点掉它, 提示框留在桌面并让修复窗口关不掉, 污染后续用例
            state = widget.finish_repair_flow("企业微信修复")
            logger.info(f"企业微信修复收尾状态: {state}")
            self.assert_false(state["window_left"])
        finally:
            if dialog_opened:
                # entry.sh 末尾 dpmapi openinfobox("企业微信修复", ...) 的
                # timeoutMs=0 表示提示框没有超时: 不点掉会留在桌面并让脚本一直阻塞
                widget.finish_repair_flow("企业微信修复")
            # 回退构造数据: 桩进程 + 桩运行时 + bottle 目录
            widget.cleanup_mock_wecom_wine()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

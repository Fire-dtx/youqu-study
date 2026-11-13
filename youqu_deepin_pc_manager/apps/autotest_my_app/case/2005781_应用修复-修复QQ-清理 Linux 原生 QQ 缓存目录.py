#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import logging

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

logger = logging.getLogger(__name__)


class TestMyCase(BaseCase):

    def test_mycase_161(self):
        """应用修复-修复QQ-清理 Linux 原生 QQ 缓存目录

        前置条件: ~/.config/QQ/Cache 存在且有缓存文件。
        步骤: 修复工具 -> QQ修复卡片 -> 开始修复, 产品真实执行
              deepin-pc-manager-plugins/plugins/plugin-qq-fix/entry.sh,
              其中 `rm -rf <home>/.config/QQ/Cache` 清理 Linux 原生 QQ 缓存。
        预期: ~/.config/QQ/Cache 下的文件被完全删除(目录消失/为空)。

        等价实现: 测试机未安装 Linux 原生 QQ, 用桩现场在
        ~/.config/QQ/Cache 下构造 avatar/filecache/temp 子目录与 8MB 缓存块,
        让产品脚本的 rm -rf 有真实清理对象; 用例前 backup_qq_state 把测试机
        真实的 ~/.config/QQ、~/.deepinwine/Deepin-QQ 整体移走, finally 中
        restore_qq_state 原样还原, 不破坏真实用户数据。
        断言链:
            a) 修复页面/QQ修复卡片/详情页可达;
            b) 开始修复后修复对话框弹出        —— 脚本被真实执行;
            c) 输出日志出现"清理完成"          —— 脚本执行到末尾(log_info);
            d) 缓存目录整体消失、文件数 0、占用 0 —— 预期"缓存文件被完全删除"。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        # 备份测试机真实 QQ 现场(产品脚本会删除 ~/.config/QQ/Cache)
        widget.backup_qq_state()
        dialog_opened = False
        try:
            # 清理上次异常退出可能遗留的构造缓存
            widget.cleanup_qq_cache()
            # 前置数据: ~/.config/QQ/Cache 存在且有缓存文件
            cache_kb = widget.create_mock_qq_cache_payload(size_mb=8)
            logger.info(f"QQ 缓存构造占用: {cache_kb}KB")
            self.assert_true(cache_kb >= 6 * 1024)
            self.assert_true(widget.get_qq_cache_file_count() >= 4)
            self.assert_true(widget.get_qq_cache_exists())

            # 步骤: 修复工具 -> QQ修复卡片 -> 开始修复
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() >= 1)
            card_names = widget.get_repair_card_names()
            logger.info(f"修复卡片列表: {card_names}")
            card_name = next((name for name in card_names if "QQ" in name), "QQ修复")
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing(timeout=15)
            self.assert_true(dialog_opened)

            # a+b: 脚本真实执行并跑到 log_info "清理完成"
            self.assert_true(widget.get_repair_output_contains("清理完成", timeout=60))
            # c: 预期 ~/.config/QQ/Cache 下的文件被完全删除
            self.assert_true(widget.wait_qq_cache_cleaned(timeout=60))
            self.assert_true(widget.get_qq_cache_file_count() == 0)
            self.assert_true(widget.get_qq_cache_size_kb() == 0)

            # 收尾: entry.sh 末尾 dpmapi openinfobox("QQ修复", ...) 的 timeoutMs=0
            # 表示提示框没有超时, 脚本会一直阻塞到用户点【确定】; 不点掉它,
            # 提示框留在桌面并让修复窗口关不掉, 污染后续用例
            state = widget.finish_repair_flow("QQ修复")
            logger.info(f"QQ修复收尾状态: {state}")
            self.assert_false(state["window_left"])
        finally:
            if dialog_opened:
                # entry.sh 末尾 dpmapi openinfobox("QQ修复", ...) 的 timeoutMs=0
                # 表示提示框没有超时: 不点掉会留在桌面并让脚本一直阻塞。
                # 提示框(有标题/无标题)与修复窗口都由该 helper 一并处理
                widget.finish_repair_flow("QQ修复")
                try:
                    widget.close_repair_dialog()
                except BaseException:
                    pass
            # 回退构造数据并还原用例前备份的真实 QQ 现场
            widget.cleanup_qq_cache()
            widget.restore_qq_state()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

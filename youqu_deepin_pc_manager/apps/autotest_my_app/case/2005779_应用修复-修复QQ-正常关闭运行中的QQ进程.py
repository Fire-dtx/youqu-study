#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import logging

from src import sleep

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

logger = logging.getLogger(__name__)


class TestMyCase(BaseCase):

    def test_mycase_160(self):
        """应用修复-修复QQ-正常关闭运行中的QQ进程

        前置条件: QQ 正在运行。
        步骤: 执行修复脚本(修复工具 -> QQ修复卡片 -> 开始修复)。
        预期: ~/.config/QQ/Cache 目录被完全删除。

        产品实现(deepin-pc-manager-plugins/plugins/plugin-qq-fix/entry.sh):
            pkill -x "qq"                       # 结束 Linux 原生 QQ 进程
            [ -x /opt/deepinwine/tools/kill.sh ] && kill.sh <各用户 bottle>
            rm -rf <home>/.deepinwine/Deepin-QQ/  <home>/.config/QQ/Cache
            log_info "清理完成"
            dpmapi openinfobox "QQ修复" "QQ缓存清理完成，修复完成"

        本机未安装 QQ(无 linuxqq 包、无 ~/.deepinwine/Deepin-QQ), 用桩现场等价:
        1) 把 sleep 复制成 /tmp/qq 运行, 进程名精确匹配 pkill -x qq,
           代表"QQ 正在运行"的前置条件;
        2) 在 ~/.config/QQ/Cache 下写入 8MB 缓存(含子目录), 让 rm -rf 真实生效。
        断言链:
            a) 修复对话框出现            —— 修复脚本被真实执行;
            b) 输出日志出现"清理完成"     —— 脚本执行到末尾(log_info);
            c) 缓存目录整体消失(文件数 0、占用 0) —— 预期"缓存目录被完全删除";
            d) qq 进程被终止             —— pkill -x qq 真实生效。
        用例描述的 "~/.config/QQ/Cache-QQ" 与产线脚本实际目标
        "~/.config/QQ/Cache" 不一致, 以产品脚本为准(见 note)。
        finally 回退: 关闭修复对话框/提示框、结束模拟进程、删 /tmp/qq 与构造缓存,
        并还原用例前备份的 ~/.config/QQ、~/.deepinwine/Deepin-QQ。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        # 备份测试机真实 QQ 现场(产品脚本会删除这两个目录)
        widget.backup_qq_state()
        dialog_opened = False
        try:
            # 清理上次异常退出可能遗留的进程/缓存
            widget.kill_qq_process()
            widget.cleanup_qq_cache()
            # 前置数据: 运行中的 QQ 进程 + QQ 缓存目录
            widget.start_mock_qq_process()
            self.assert_true(widget.get_qq_process_status())
            logger.info(f"模拟 QQ 进程 pid: {widget.get_mock_qq_process_pid()}")
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
            card_name = next(
                (name for name in card_names if "QQ" in name),
                "QQ修复",
            )
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing(timeout=15)
            self.assert_true(dialog_opened)

            # a+b: 脚本真实执行并跑到 log_info "清理完成"
            self.assert_true(widget.get_repair_output_contains("清理完成", timeout=60))
            # c: 预期 ~/.config/QQ/Cache 被完全删除
            self.assert_true(widget.wait_qq_cache_cleaned(timeout=60))
            self.assert_true(widget.get_qq_cache_file_count() == 0)
            self.assert_true(widget.get_qq_cache_size_kb() == 0)
            # d: 运行中的 QQ 进程被 pkill -x qq 终止
            self.assert_true(widget.wait_qq_process_killed(timeout=60))
            # 修复完成提示框(dpmapi openinfobox)若弹出, 应可正常确认关闭
            # (V20 上提示框由主进程创建, 关闭后脚本才退出; 未弹出也不影响上述断言)
            notify_shown = False
            for _ in range(15):
                if widget.get_repair_notify_dialog_state().get("has_ok"):
                    notify_shown = True
                    break
                sleep(1)
            logger.info(f"QQ 修复完成提示框是否弹出: {notify_shown}")
            if notify_shown:
                self.assert_true(widget.click_repair_notify_ok(timeout=20))

            # 收尾: QQ 插件用的是 dpmapi openinfobox("QQ修复", ...), 其
            # timeoutMs=0 表示提示框没有超时、脚本阻塞在弹窗上; 上面只处理了
            # 主进程无标题提示框, 有标题的这条必须用 finish_repair_flow 点掉,
            # 否则提示框留在桌面且修复窗口关不掉, 污染后续用例
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
            # 回退构造数据: 模拟进程、临时二进制、构造缓存, 并还原真实现场
            widget.kill_qq_process()
            widget.cleanup_qq_cache()
            widget.restore_qq_state()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

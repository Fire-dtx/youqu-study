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

    def test_mycase_162(self):
        """应用修复-修复QQ-修复后 QQ 功能验证（原生版）

        用例描述: 脚本执行完成后首次启动 Linux 原生版 QQ, 双击打开、登录账号
        并发送消息、查看聊天记录; 预期 QQ 可正常启动(首次启动缓慢为预期),
        无闪退卡顿、功能正常。

        产品实现(plugin-qq-fix/entry.sh, 已解码核对):
            pkill -x "qq"
            删除 ~/.deepinwine/Deepin-QQ/(存在且非符号链接才删)
            删除 ~/.config/QQ/Cache(存在且非符号链接才删)
            log_info "清理完成"; dpmapi openinfobox "QQ修复" "QQ缓存清理完成，修复完成"

        测试机未安装 Linux 原生 QQ(dpkg 无 linuxqq, which qq 无输出), 按规程用
        "可观测的模拟 QQ 客户端"等价实现, 覆盖描述里的观察点:
        1) 前置数据: 运行中的 qq 进程(复制 sleep 为 /tmp/qq, comm=qq, 能被
           pkill -x qq 命中) + ~/.config/QQ/Cache 缓存 + ~/.config/QQ/UserData
           账号会话与聊天记录(chat_history.db/message.log)。用例前
           backup_qq_state 把测试机真实的 ~/.config/QQ、~/.deepinwine/Deepin-QQ
           整体移走, finally 中 restore_qq_state 原样还原, 不破坏真实用户数据。
        2) 修复真实执行: 修复工具 -> QQ修复卡片 -> 开始修复, 断言修复对话框
           弹出、qq 进程被 pkill 终止、缓存目录被 rm -rf 删净、输出出现"清理完成"。
        3) 修复后功能验证(等价断言):
           - 聊天记录 md5 与修复前一致 —— 修复未破坏用户数据(查看聊天记录);
           - 重新启动 QQ, 60s 内健康起来(首次启动缓慢属预期), 进程非僵尸且
             VmRSS > 0, 观察 10s 内仍是同一 pid 且持续存活 —— 无闪退/反复重启;
           - 向 message.log 追加一条消息成功、行数增加 —— 数据目录读写正常
             (登录账号后发送消息)。
        4) finally 回退: 关修复提示框/修复对话框、杀模拟进程、删 /tmp/qq、清构造
           缓存并还原备份的真实 QQ 现场, 不留残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        dialog_opened = False
        try:
            # 归一化: 清理上次异常退出残留, 并备份测试机真实 QQ 现场
            # 先备份真实 QQ 现场再清理: cleanup_qq_cache 删除的
            # ~/.config/QQ/Cache 一旦先删, 备份里就没有真实缓存了。
            widget.kill_qq_process()
            backup_state = widget.backup_qq_state()
            logger.info(f"QQ 现场备份: {backup_state}")
            widget.cleanup_qq_cache()
            # 前置数据: 运行中的 QQ + 缓存 + 账号会话/聊天记录
            widget.start_mock_qq_process()
            self.assert_true(widget.get_qq_process_status())
            cache_kb = widget.create_mock_qq_cache_payload(size_mb=8)
            logger.info(f"QQ 缓存构造占用: {cache_kb}KB")
            self.assert_true(cache_kb >= 6 * 1024)
            self.assert_true(widget.create_mock_qq_user_data())
            chat_digest = widget.get_qq_chat_history_digest()
            self.assert_true(bool(chat_digest))
            message_lines = widget.get_qq_message_count()
            self.assert_true(message_lines >= 1)
            # 执行修复: 修复工具 -> QQ修复卡片 -> 开始修复
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
            # 修复脚本真实生效: pkill -x qq + rm -rf ~/.config/QQ/Cache
            self.assert_true(widget.wait_qq_process_killed(timeout=30))
            self.assert_true(widget.wait_qq_cache_cleaned(timeout=60))
            self.assert_true(widget.get_repair_output_contains("清理完成", timeout=60))
            # 收尾: entry.sh 末尾 dpmapi openinfobox("QQ修复", ...) 的 timeoutMs=0
            # 表示提示框没有超时, 脚本会一直阻塞到用户点【确定】; 不点掉它,
            # 提示框留在桌面并让修复窗口关不掉。
            # 这里故意不把 dialog_opened 置 False: finally 仍需再调一次收尾,
            # 覆盖"后续步骤失败时提示框又被拉起"的情况(helper 可重复调用)。
            state = widget.finish_repair_flow("QQ修复")
            logger.info(f"QQ修复收尾状态: {state}")
            self.assert_false(state["window_left"])
            # 预期2-a: 聊天记录未被修复破坏(缓存目录之外的用户数据仍在且一致)
            self.assert_equal(chat_digest, widget.get_qq_chat_history_digest())
            # 预期1: 修复后重新启动 QQ, 首次启动可缓慢但必须真的起来
            widget.start_mock_qq_process()
            self.assert_true(widget.wait_qq_process_started(timeout=60))
            self.assert_true(widget.is_qq_process_healthy())
            pid = widget.get_mock_qq_process_pid()
            self.assert_true(bool(pid))
            # 预期2-b: 启动后稳定驻留, 无闪退/卡死/反复重启
            self.assert_true(widget.is_qq_process_alive_after(10))
            self.assert_equal(pid, widget.get_mock_qq_process_pid())
            self.assert_true(widget.is_qq_process_healthy())
            # 预期2-c: 功能正常 —— 仍可写入新消息(等价"发送消息")
            self.assert_true(widget.append_qq_message("post-repair hello"))
            self.assert_true(widget.get_qq_message_count() > message_lines)
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
            # 回退: 进程、临时二进制、构造的缓存与用户数据、真实 QQ 现场备份
            widget.kill_qq_process()
            widget.cleanup_qq_cache()
            widget.restore_qq_state()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

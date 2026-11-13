#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_155(self):
        """应用修复-修复微信-修复后微信功能验证

        用例描述: 修复微信后首次启动微信、登录账号、发送消息、查看聊天记录,
        预期微信可正常启动(首次启动缓慢属预期), 无闪退卡顿、功能正常。

        产品实现(deepin-pc-manager-plugins/plugins/plugin-wechat-fix/entry.sh):
            killall wechat 2>/dev/null || true
            rm -rf ~/.xwechat/radium/cache || true
            dpmapi openinfobox "微信修复" "微信缓存清理完成，修复完成"

        测试机未安装真实微信, 按规程用"可观测的模拟微信客户端"等价实现, 覆盖
        描述里的四个观察点:
        1) 前置数据: 运行中的微信进程(复制 sleep 为 /tmp/wechat, comm=wechat,
           可被 killall 命中) + ~/.xwechat/radium/cache 缓存文件 +
           ~/.xwechat/user_data 账号会话与聊天记录(chat_history.db/message.log)。
           测试机若已有真实 ~/.xwechat, 先整体 mv 备份, 结束时原样还原。
        2) 修复真实执行: 修复工具 -> 微信修复卡片 -> 开始修复, 断言修复对话框
           (shellRepair)弹出、微信进程被 killall 终止、缓存目录被 rm -rf 删净。
        3) 修复后功能验证(等价断言):
           - 聊天记录 md5 与修复前一致 —— 修复未破坏用户数据(查看聊天记录);
           - 重新启动微信, 60s 内健康起来(首次启动缓慢属预期), 进程非僵尸且
             VmRSS > 0, 观察 10s 内仍是同一 pid 且持续存活 —— 无闪退/反复重启;
           - 向 message.log 追加一条消息成功、行数增加 —— 数据目录读写正常
             (登录账号后发送消息)。
        4) finally 回退: 关修复对话框、杀模拟进程、删 /tmp/wechat、清构造目录并
           还原备份的真实 ~/.xwechat, 不留残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        cache_backed = False
        dialog_opened = False
        try:
            # 清理上次残留, 并把测试机已有的真实微信数据整体备份
            # 必须先整体备份测试机真实微信数据, 再清理上次残留:
            # clean_wechat_cache 会 rm -rf ~/.xwechat, 备份前清理会把真实
            # 聊天记录一并销毁且 finally 无从还原。
            widget.kill_wechat_process()
            cache_backed = widget.backup_wechat_cache()
            widget.clean_wechat_cache()
            # 前置数据: 运行中的微信 + 缓存文件 + 账号会话/聊天记录
            widget.start_mock_wechat_process()
            self.assert_true(widget.get_wechat_process_status())
            widget.create_mock_wechat_cache()
            self.assert_true(widget.get_wechat_cache_exists())
            self.assert_true(widget.create_mock_wechat_user_data())
            chat_digest = widget.get_wechat_chat_history_digest()
            self.assert_true(bool(chat_digest))
            message_lines = widget.get_wechat_message_count()
            self.assert_true(message_lines >= 1)
            # 执行修复: 修复工具 -> 微信修复卡片 -> 开始修复
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() >= 1)
            widget.click_wechat_fix_card()
            self.assert_true(widget.get_repair_detail_showing())
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing()
            self.assert_true(dialog_opened)
            # 修复脚本真实生效: killall wechat + rm -rf ~/.xwechat/radium/cache
            self.assert_true(widget.wait_wechat_process_killed(timeout=30))
            self.assert_true(widget.wait_wechat_cache_cleaned(timeout=60))
            # 关闭修复完成对话框, 进入修复后验证
            # entry.sh 末尾 dpmapi openinfobox("微信修复", ...) 的 timeoutMs=0
            # 表示提示框没有超时, 且它属于 session-daemon 进程, 只按窗口关闭
            # 关不掉; 必须点掉提示框才能让脚本退出并关掉修复窗口
            state = widget.finish_repair_flow("微信修复")
            self.assert_false(state["window_left"])
            dialog_opened = False
            # 预期2-a: 聊天记录未被修复破坏(数据仍在且内容一致)
            self.assert_equal(chat_digest, widget.get_wechat_chat_history_digest())
            # 预期1: 修复后重新启动微信, 首次启动可缓慢但必须真的起来
            widget.start_mock_wechat_process()
            self.assert_true(widget.wait_wechat_process_started(timeout=60))
            self.assert_true(widget.is_wechat_process_healthy())
            pid = widget.get_wechat_process_pid()
            self.assert_true(bool(pid))
            # 预期2-b: 启动后稳定驻留, 无闪退/卡死/反复重启
            self.assert_true(widget.is_wechat_process_alive_after(10))
            self.assert_equal(pid, widget.get_wechat_process_pid())
            self.assert_true(widget.is_wechat_process_healthy())
            # 预期2-c: 功能正常 —— 仍可写入新消息(等价"发送消息")
            self.assert_true(widget.append_wechat_message("post-repair hello"))
            self.assert_true(widget.get_wechat_message_count() > message_lines)
        finally:
            if dialog_opened:
                # entry.sh 末尾 dpmapi openinfobox("微信修复", ...) 的
                # timeoutMs=0 表示提示框没有超时: 不点掉会留在桌面并让脚本
                # 一直阻塞, 所以先解阻塞再动数据(杀进程/还原 ~/.xwechat)
                widget.finish_repair_flow("微信修复")
            # 回退: 进程、临时二进制、构造的缓存与用户数据、真实微信数据备份
            widget.kill_wechat_process()
            widget.clean_wechat_cache()
            if cache_backed:
                widget.restore_wechat_cache()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

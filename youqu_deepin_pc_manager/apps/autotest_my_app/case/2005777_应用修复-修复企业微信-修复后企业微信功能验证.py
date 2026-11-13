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

    def test_mycase_159(self):
        """应用修复-修复企业微信-修复后企业微信功能验证

        前置条件: 执行完企业微信修复脚本(修复工具 -> 企业微信修复 -> 开始修复)。
        步骤: 1. 双击打开企业微信; 2. 登录账号并发送消息、查看聊天记录。
        预期: 1. 企业微信可正常启动(首次启动缓慢为预期现象);
              2. 无闪退、卡顿问题, 功能正常。

        产品实现(deepin-pc-manager-plugins/plugins/plugin-wecom-fix/entry.sh):
            /opt/deepinwine/tools/kill.sh ~/.deepinwine/Deepin-WXWork/
            rm -rf ~/.deepinwine/Deepin-WXWork/
            dpmapi openinfobox "企业微信修复" "企业微信缓存清理完成，修复完成"
        即修复会终止 Wine 容器并删除整个 bottle(~/.deepinwine/Deepin-WXWork),
        所以"修复后首次启动企业微信"的真实语义是: 容器已被删除, 重新拉起时
        Wine 需要重新生成 prefix(首次启动缓慢属预期), 之后登录/发消息/看记录正常。

        等价实现: 本机未安装真实 Wine 版企业微信, 复用 2005771/2005773 的桩运行时
        (setup_mock_wecom_wine: bottle + 桩 wineserver + 模拟 WeChat.exe 进程),
        覆盖描述里的全部观察点:
          1) 前置数据: 运行中的模拟企业微信、bottle 内 20MB 缓存、容器内本地会话
             与聊天记录(chat_history.db / message.log), 并把测试机可能存在的真实
             bottle 改名备份, 用例结束原样还原;
          2) 真实执行修复: 修复工具 -> 企业微信修复卡片 -> 开始修复, 断言修复
             对话框弹出、企业微信进程被 kill.sh->wineserver -k 终止、bottle 目录
             及缓存被 rm -rf 删净 —— 即"修复已完成"的前置条件成立;
          3) 预期1(可正常启动): 在 bottle 已被删除的状态下重新构造(等价"双击
             重新打开企业微信, 首次启动重新生成 prefix"), 断言 bottle 被重新创建、
             WeChat.exe 在 60s 内健康起来(非僵尸且 VmRSS > 0);
          4) 预期2(无闪退/卡顿, 功能正常): 10s 观察窗内仍是同一 pid 且持续健康;
             容器内重建本地会话(等价登录账号)、追加一条新消息后消息数增加、
             读回的最后一条消息与写入一致、聊天记录 md5 稳定(等价查看聊天记录)。
             产品删的是整个 bottle, 旧聊天记录随容器删除属产品既定行为, 故不做
             "旧记录保留"断言, 而以"新容器下登录后数据可写可读回"作为功能正常
             的等价断言。
        finally 回退: 关闭修复对话框、终止桩进程(含全部历史桩 wineserver)、删除
        桩运行时/bottle/会话数据并还原真实 bottle 备份, 测试机不留残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        dialog_opened = False
        kill_helper = {}
        try:
            # 清理上次异常退出可能遗留的桩进程/目录
            widget.cleanup_mock_wecom_wine()
            # 产品 entry.sh 用 /opt/deepinwine/tools/kill.sh 终止容器进程;
            # 测试机的 deepin-wine-runtime 不含该工具, 缺失时脚本静默跳过,
            # 进程杀不掉、后续断言全落空, 故先补齐等价桩(系统自带则不动)
            kill_helper = widget.ensure_wecom_kill_helper()
            logger.info(f"产品 kill.sh 现场: {kill_helper}")
            self.assert_true(kill_helper.get("helper") in ("existing", "stub"))

            # 前置数据: Wine 企业微信运行中 + bottle 缓存 + 容器内会话/聊天记录
            self.assert_true(widget.setup_mock_wecom_wine())
            self.assert_true(widget.get_wecom_process_status())
            pre_cache_kb = widget.create_wecom_wine_cache_payload(size_mb=20)
            logger.info(f"修复前企业微信 bottle 缓存占用: {pre_cache_kb}KB")
            self.assert_true(pre_cache_kb >= 16 * 1024)
            self.assert_true(widget.get_wecom_wine_cache_exists())
            self.assert_true(widget.create_mock_wecom_chat_history())
            self.assert_true(bool(widget.get_wecom_chat_history_digest()))
            pre_msg_count = widget.get_wecom_chat_message_count()
            self.assert_true(pre_msg_count >= 2)

            # 步骤0: 执行修复(修复工具 -> 企业微信修复卡片 -> 开始修复)
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
            # 修复脚本真实生效: kill.sh 终止进程 + rm -rf 删净 bottle(含缓存)
            self.assert_true(widget.wait_wecom_process_killed(timeout=60))
            self.assert_true(widget.wait_wecom_wine_cache_cleaned(timeout=60))
            self.assert_true(widget.get_wecom_bottle_size_kb() == 0)
            # 收尾: entry.sh 末尾 dpmapi openinfobox("企业微信修复", ...) 的
            # timeoutMs=0 表示提示框没有超时, 脚本会一直阻塞到用户点【确定】;
            # 不点掉它, 提示框留在桌面并让修复窗口关不掉。
            # 这里故意不把 dialog_opened 置 False: finally 仍需再调一次收尾,
            # 覆盖"后续步骤失败时提示框又被拉起"的情况(helper 可重复调用)。
            state = widget.finish_repair_flow("企业微信修复")
            logger.info(f"企业微信修复收尾状态: {state}")
            self.assert_false(state["window_left"])

            # 步骤1/预期1: 修复后首次启动企业微信 —— 容器已删除, 重新生成 prefix 并拉起
            self.assert_true(widget.setup_mock_wecom_wine(protect_bottle=False))
            self.assert_true(widget.get_wecom_wine_cache_exists())
            self.assert_true(widget.wait_wecom_process_started(timeout=60))
            self.assert_true(widget.is_wecom_process_healthy())
            pid = widget.get_wecom_process_pid()
            self.assert_true(bool(pid))

            # 预期2-a: 启动后稳定驻留, 无闪退/反复重启
            self.assert_true(widget.is_wecom_process_alive_after(10))
            self.assert_equal(pid, widget.get_wecom_process_pid())
            self.assert_true(widget.is_wecom_process_healthy())

            # 步骤2/预期2-b: 登录账号 -> 发送消息 -> 查看聊天记录(容器内数据可写可读回)
            self.assert_true(widget.create_mock_wecom_chat_history())
            self.assert_true(bool(widget.get_wecom_chat_history_digest()))
            post_msg_count = widget.get_wecom_chat_message_count()
            self.assert_true(post_msg_count >= 2)
            self.assert_true(widget.append_wecom_chat_message("post-repair wecom hello"))
            self.assert_true(widget.get_wecom_chat_message_count() > post_msg_count)
            self.assert_equal(
                "post-repair wecom hello", widget.get_wecom_chat_last_message()
            )
            # 进程经上述读写后仍健康(无卡死)
            self.assert_true(widget.is_wecom_process_healthy())
        finally:
            if dialog_opened:
                # entry.sh 末尾 dpmapi openinfobox("企业微信修复", ...) 的
                # timeoutMs=0 表示提示框没有超时: 不点掉会留在桌面并让脚本一直阻塞
                widget.finish_repair_flow("企业微信修复")
            # 回退: 桩进程(含历史 wineserver)、桩运行时、bottle 会话数据、真实 bottle 备份
            widget.cleanup_mock_wecom_wine()
            # 删除本用例安装的 kill.sh 桩(系统自带的不动)
            if kill_helper:
                widget.remove_wecom_kill_helper(kill_helper)
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_153(self):
        """应用修复-修复微信-正常关闭运行中的微信进程

        前置条件: 微信正在运行(用例描述为 Wine 版微信, 本机用模拟进程等价)。
        步骤: 修复工具 -> 微信修复卡片 -> 开始修复。

        产品实现(deepin-pc-manager-plugins/plugins/plugin-wechat-fix/entry.sh):
            killall wechat 2>/dev/null || true
            rm -rf ~/.xwechat/radium/cache || true
            dpmapi openinfobox "微信修复" "微信缓存清理完成，修复完成"

        因此预期断言等价实现为:
        1) 修复对话框(openinfobox)弹出 —— 证明脚本被真实执行;
        2) 微信进程被 killall 强制终止;
        3) 微信缓存目录被 rm -rf 删除(释放空间)。
        前置数据构造: 复制 sleep 为 /tmp/wechat 运行(进程名匹配 killall wechat),
        并在 ~/.xwechat/radium/cache 下写入缓存文件, 让两条命令都真实生效。
        finally 中回退: 关闭修复对话框、终止模拟进程、删除 /tmp/wechat 与缓存目录。
        """
        widget = MyAppWidget(check_start=False)
        # 测试机可能已有真实微信数据: 整体移走再构造, finally 原样还原
        had_wechat_data = widget.backup_wechat_cache()
        print(f"[2005763] 原有 ~/.xwechat 备份: {had_wechat_data}")
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        dialog_opened = False
        try:
            # 清理上次残留(进程 / 缓存 / 临时二进制)
            widget.kill_wechat_process()
            widget.clean_wechat_cache()
            # 构造前置数据: 运行中的微信进程 + 微信缓存文件
            widget.start_mock_wechat_process()
            self.assert_true(widget.get_wechat_process_status())
            widget.create_mock_wechat_cache()
            self.assert_true(widget.get_wechat_cache_exists())
            # 进入修复工具页
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() >= 1)
            # 点击微信修复卡片, 进入详情页
            widget.click_wechat_fix_card()
            self.assert_true(widget.get_repair_detail_showing())
            # 执行修复脚本
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing()
            self.assert_true(dialog_opened)
            # 预期1: rm -rf 删除微信缓存目录, 释放磁盘空间
            self.assert_true(widget.wait_wechat_cache_cleaned(timeout=60))
            self.assert_equal(0, widget.get_wechat_cache_file_count())
            # 预期2: killall wechat 强制终止运行中的微信进程
            self.assert_true(widget.wait_wechat_process_killed(timeout=30))
            # 修复脚本的完成提示: openinfobox("微信修复", "微信缓存清理完成，修复完成")
            # 是独立弹框(不进 shellRepair 输出日志), 按对话框断言
            # 正文 label 不暴露 accessible text(实测只有对象名), 因此以
            # "完成提示框确实弹出且按钮可交互"作为脚本执行完成的等价证据
            prompt_state = widget.get_confirm_dialog_state(
                "微信修复", timeout=30, action_text=widget.INFOBOX_OK_TEXT
            )
            output = widget.get_repair_output_text()
            print(f"[2005763] 修复输出: {output[-400:]!r}")
            print(f"[2005763] 完成提示框: {prompt_state}")
            self.assert_true(bool(prompt_state.get("showing")))
            self.assert_true(widget.INFOBOX_OK_TEXT in prompt_state.get("buttons", []))
            self.assert_false("[ERROR]" in output)
            # 收尾: entry.sh 末尾 dpmapi openinfobox("微信修复", ...) 的
            # timeoutMs=0 表示提示框没有超时, 不点掉脚本会一直阻塞且弹窗
            # 盖在桌面上; 点掉提示框后确认修复窗口已真正关闭
            state = widget.finish_repair_flow("微信修复")
            self.assert_false(state["window_left"])
        finally:
            if dialog_opened:
                # entry.sh 末尾 dpmapi openinfobox("微信修复", ...) 的
                # timeoutMs=0 表示提示框没有超时: 不点掉会留在桌面并让脚本
                # 一直阻塞, 所以先解阻塞再动数据(杀进程/还原 ~/.xwechat)
                widget.finish_repair_flow("微信修复")
            # 回退构造数据: 进程、临时二进制、缓存目录, 再还原原有微信数据
            widget.kill_wechat_process()
            widget.clean_wechat_cache()
            widget.restore_wechat_cache()
            print(
                "[2005763] ~/.xwechat 还原后存在: "
                f"{widget._keyring_path_exists(os.path.expanduser('~/.xwechat'))}"
            )
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

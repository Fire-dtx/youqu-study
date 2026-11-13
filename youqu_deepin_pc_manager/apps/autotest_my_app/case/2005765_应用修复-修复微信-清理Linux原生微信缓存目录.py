#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_033(self):
        """应用修复-修复微信-清理 Linux 原生微信缓存目录

        产品实现(deepin-pc-manager-plugins/plugins/plugin-wechat-fix/entry.sh):

            killall wechat 2>/dev/null || true
            echo "清理linux微信缓存"
            rm -rf ~/.xwechat/radium/cache || true
            dpmapi openinfobox "微信修复" "微信缓存清理完成，修复完成"

        前置条件: ~/.xwechat/radium/cache 存在且有缓存文件。测试机上若原本
        已有该目录(真实微信数据), 先整体备份到 ~/.autotest_wechat_backup,
        再构造带缓存文件的模拟目录, 用例结束原样还原, 不留残留、不毁数据。

        步骤: 修复工具 -> 微信修复卡片 -> 详情页 -> 开始修复, 然后查看
        ~/.xwechat/radium/cache。

        预期等价断言:
        1) 修复对话框(shellRepair 输出框)弹出 —— 证明 entry.sh 被真实执行;
        2) ~/.xwechat/radium/cache 被 rm -rf 完全删除 —— 目录不存在
           (test -e 为假)且目录内文件计数为 0。

        finally 回退: 关闭修复对话框、终止模拟微信进程、删除构造的缓存目录,
        并恢复备份的原始 ~/.xwechat。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        cache_backed = False
        dialog_opened = False
        try:
            # 清理上次残留, 再备份测试机已有的真实微信数据
            # 必须先整体备份测试机真实微信数据, 再清理上次残留:
            # clean_wechat_cache 会 rm -rf ~/.xwechat, 备份前清理会把真实
            # 聊天记录一并销毁且 finally 无从还原。
            widget.kill_wechat_process()
            cache_backed = widget.backup_wechat_cache()
            widget.clean_wechat_cache()
            # 构造前置数据: ~/.xwechat/radium/cache 及缓存文件(含子目录,
            # 用于校验 rm -rf 的递归删除语义)
            widget.create_mock_wechat_cache()
            widget.run_cmd(
                f"mkdir -p {widget.WECHAT_CACHE_DIR}/sub/dir && "
                f"echo nested > {widget.WECHAT_CACHE_DIR}/sub/dir/nested.tmp",
                timeout=10,
                out_debug_flag=False,
            )
            self.assert_true(widget.get_wechat_cache_exists())
            self.assert_true(widget.get_wechat_cache_file_count() >= 2)
            # 进入修复工具页, 校验列表已加载
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() >= 1)
            # 点击微信修复卡片进入详情页
            widget.click_wechat_fix_card()
            self.assert_true(widget.get_repair_detail_showing())
            # 点击开始修复, 真实执行 entry.sh
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing()
            self.assert_true(dialog_opened)
            # 预期: 修复脚本 rm -rf 把缓存目录完全删除
            self.assert_true(widget.wait_wechat_cache_cleaned(timeout=60))
            self.assert_false(widget.get_wechat_cache_exists())
            self.assert_equal(0, widget.get_wechat_cache_file_count())
            # rm -rf 只针对 cache 目录: 其父级 radium 应仍在
            parent_exists = widget.run_cmd(
                f"test -d {os.path.dirname(widget.WECHAT_CACHE_DIR)} "
                "&& echo exists "
                "|| echo missing",
                timeout=5,
                out_debug_flag=False,
            )
            print(f"[2005765] ~/.xwechat/radium 保留: {parent_exists.strip()!r}")
            self.assert_true("exists" in parent_exists)
            output = widget.get_repair_output_text()
            prompt_state = widget.get_confirm_dialog_state(
                "微信修复", timeout=30, action_text=widget.INFOBOX_OK_TEXT
            )
            print(f"[2005765] 修复输出: {output[-300:]!r}")
            print(f"[2005765] 完成提示框: {prompt_state}")
            self.assert_false("[ERROR]" in output)
            self.assert_true(bool(prompt_state.get("showing")))
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
            widget.kill_wechat_process()
            widget.clean_wechat_cache()
            if cache_backed:
                widget.restore_wechat_cache()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

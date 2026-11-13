#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_154(self):
        """应用修复-修复微信-磁盘空间不足执行脚本

        用例描述: 前置"UOS 系统正常运行, 磁盘空间不足 100MB"; 步骤"执行修复
        脚本, 观察缓存删除步骤执行结果"; 预期"rm -rf 命令可正常删除缓存释放
        空间 / 无磁盘空间不足导致的脚本崩溃"。

        产品实现(plugin-wechat-fix/entry.sh, executionMode=user):
            killall wechat 2>/dev/null || true
            echo "清理linux微信缓存"
            rm -rf ~/.xwechat/radium/cache || true
            dpmapi openinfobox "微信修复" "微信缓存清理完成，修复完成"

        前置构造(等价实现): 测试机根分区仅约 1GB 可用且整轮用例共用, 不能把
        根分区真塞到 100MB 以下(会让后续用例集体 ENOSPC)。因此挂一块 100MB
        tmpfs 并写入 70MB 占位文件(可用约 30MB), 再把 ~/.xwechat 软链到该盘
        内目录 —— entry.sh 的 rm -rf 真实作用在"可用空间不足 100MB"的文件
        系统上, 删除后 df 可用空间上升可量化。tmpfs 不可用时退化为普通缓存
        目录(仍验证缓存被真实删除), 不因环境不允许挂载而失败。

        预期等价断言:
        1) 前置成立: 删除目标所在盘可用空间 < 100MB(仅 tmpfs 模式);
        2) 修复对话框(shellRepair 输出框)弹出 —— entry.sh 被真实执行;
        3) ~/.xwechat/radium/cache 被 rm -rf 删除(目录不存在, 文件计数为 0);
        4) 删除后该盘可用空间上升(释放空间, 仅 tmpfs 模式);
        5) 输出日志若可读, 不含 ENOSPC/No space left 等磁盘不足崩溃特征。

        finally 回退: 关闭修复对话框、删除软链、卸载 tmpfs 并删除挂载点、
        清理缓存目录, 最后还原备份的真实 ~/.xwechat。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        cache_backed = False
        dialog_opened = False
        low_space = {"mode": "none", "mount": "", "free_mb": -1}
        try:
            # 清理上次残留, 再备份测试机已有的真实微信数据
            # 必须先整体备份测试机真实微信数据, 再清理上次残留:
            # clean_wechat_cache 会 rm -rf ~/.xwechat, 备份前清理会把真实
            # 聊天记录一并销毁且 finally 无从还原。
            widget.kill_wechat_process()
            cache_backed = widget.backup_wechat_cache()
            widget.clean_wechat_cache()
            # 构造前置: "磁盘空间不足 100MB"的盘 + 微信缓存目录
            low_space = widget.setup_low_space_wechat_cache()
            self.assert_true(low_space.get("mode") in ("tmpfs", "fallback"))
            if low_space["mode"] == "tmpfs":
                # 前置真正成立: 删除目标所在盘可用空间不足 100MB
                self.assert_true(low_space["free_mb"] < 100)
            self.assert_true(widget.get_wechat_cache_exists())
            self.assert_true(widget.get_wechat_cache_file_count() >= 1)
            free_before = low_space["free_mb"]
            # 进入修复工具页
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() >= 1)
            # 微信修复卡片 -> 详情页
            widget.click_wechat_fix_card()
            self.assert_true(widget.get_repair_detail_showing())
            # 执行修复脚本
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing()
            self.assert_true(dialog_opened)
            # 预期: rm -rf 正常删除缓存目录(低磁盘空间下无 ENOSPC 崩溃)
            self.assert_true(widget.wait_wechat_cache_cleaned(timeout=60))
            self.assert_false(widget.get_wechat_cache_exists())
            self.assert_equal(0, widget.get_wechat_cache_file_count())
            # 预期: 删除缓存释放了空间
            if low_space["mode"] == "tmpfs":
                free_after = widget.get_mount_free_space_mb(low_space["mount"])
                self.assert_true(free_after >= free_before + 1)
            # 预期: 修复输出无磁盘空间不足导致的报错特征
            output_text = widget.get_repair_output_text() or ""
            for marker in ("No space left", "ENOSPC", "Disk quota exceeded", "Traceback"):
                self.assert_false(marker in output_text)
            # 收尾: entry.sh 末尾 dpmapi openinfobox("微信修复", ...) 的
            # timeoutMs=0 表示提示框没有超时, 不点掉脚本会一直阻塞且弹窗
            # 盖在桌面上; 点掉提示框后确认修复窗口已真正关闭
            state = widget.finish_repair_flow("微信修复")
            self.assert_false(state["window_left"])
        finally:
            if dialog_opened:
                # entry.sh 末尾 dpmapi openinfobox("微信修复", ...) 的
                # timeoutMs=0 表示提示框没有超时: 不点掉会留在桌面并让脚本
                # 一直阻塞, 所以先解阻塞再动数据(杀进程/卸 tmpfs/还原数据)
                widget.finish_repair_flow("微信修复")
            widget.kill_wechat_process()
            widget.cleanup_low_space_wechat_cache(low_space)
            widget.clean_wechat_cache()
            if cache_backed:
                widget.restore_wechat_cache()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

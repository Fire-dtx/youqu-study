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

    def test_mycase_034(self):
        """应用修复-修复QQ-磁盘空间不足执行脚本

        用例描述: 前置"UOS 系统正常运行, 磁盘空间不足 100MB"; 步骤"执行修复
        脚本, 观察缓存删除步骤执行结果"; 预期"rm -rf 命令可正常删除缓存释放
        空间 / 无磁盘空间不足导致的脚本崩溃"。

        产品实现(plugin-qq-fix/entry.sh, executionMode=user):
            pkill -x qq
            [ -x /opt/deepinwine/tools/kill.sh ] && kill.sh <home>/.deepinwine/Deepin-QQ
            for user_home in /home/*:
                [ -d "$cache_dir" ] && [ ! -L "$cache_dir" ] && rm -rf "$cache_dir"
            log_info "清理完成"
            dpmapi openinfobox "QQ修复" "QQ缓存清理完成，修复完成"
            (cache_dir = <home>/.config/QQ/Cache, wine_dir = <home>/.deepinwine/Deepin-QQ)

        前置构造(等价实现): 测试机整轮用例共用同一块盘(根分区约 1GB 可用), 不能
        把根分区真塞到 100MB 以下(会让后续用例集体 ENOSPC)。因此挂一块 100MB
        tmpfs 并 bind 到 ~/.config/QQ(真实 QQ 数据先由 backup_qq_state 整体
        移走), 盘内写 40MB 占位文件使可用空间约 40MB, 再在盘内构造 20MB 的
        QQ 缓存目录 —— 产品脚本的 rm -rf 因此真实作用在"可用空间不足 100MB"的
        文件系统上, 删除后 df 可用空间上升可量化。
        注意: 产品脚本对 cache_dir 有 `[ ! -L ]` 符号链接防护, 故不用软链
        方式(会被脚本跳过造成假通过), 而用 bind 挂载让 Cache 成为低空间盘上
        的真实目录。挂载不可用时退化为普通缓存目录(仍验证缓存被真实删净),
        不因环境不允许挂载而失败。

        预期等价断言:
        1) 前置成立: 删除目标所在盘可用空间 < 100MB(仅 tmpfs 模式);
        2) 修复对话框(shellRepair 输出框)弹出 —— entry.sh 被真实执行;
        3) 输出日志出现"清理完成" —— 脚本执行到末尾, 低空间下未中途崩溃;
        4) ~/.config/QQ/Cache 被 rm -rf 删净(目录不存在, 文件数/占用为 0);
        5) 删除后该盘可用空间上升(释放空间, 仅 tmpfs 模式);
        6) 输出日志不含 ENOSPC/No space left 等磁盘不足崩溃特征。

        finally 回退: 关闭修复对话框/信息提示框、卸载 bind 与 tmpfs、删除
        挂载点、清理构造缓存, 最后 restore_qq_state 原样还原真实 QQ 现场。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        # 备份测试机真实 QQ 现场(产品脚本会删除 ~/.config/QQ/Cache 与
        # ~/.deepinwine/Deepin-QQ), 用例结束原样还原
        widget.backup_qq_state()
        dialog_opened = False
        low_space = {}
        try:
            # 清理上次异常退出可能遗留的构造缓存/挂载
            widget.cleanup_qq_cache()

            # 前置数据: "磁盘空间不足 100MB"的盘 + 盘内 QQ 缓存
            low_space = widget.setup_low_space_qq_cache()
            self.assert_true(low_space.get("mode") in ("tmpfs", "fallback"))
            if low_space["mode"] == "tmpfs":
                # 前置真正成立: 删除目标所在盘可用空间不足 100MB
                self.assert_true(low_space["free_mb"] < 100)
            self.assert_true(widget.get_qq_cache_exists())
            self.assert_true(widget.get_qq_cache_file_count() >= 4)
            cache_kb = widget.get_qq_cache_size_kb()
            logger.info(f"QQ 缓存构造占用: {cache_kb}KB, 盘可用: "
                        f"{low_space['free_mb']}MB({low_space['mode']})")
            self.assert_true(cache_kb >= 15 * 1024)
            free_before = low_space["free_mb"]

            # 步骤: 修复工具 -> QQ修复卡片 -> 详情页
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() >= 1)
            card_names = widget.get_repair_card_names()
            logger.info(f"修复卡片列表: {card_names}")
            card_name = next((name for name in card_names if "QQ" in name), "QQ修复")
            widget.click_repair_card_by_name(card_name)
            self.assert_true(widget.get_repair_detail_showing())

            # 步骤: 执行修复脚本(磁盘空间不足场景)
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing(timeout=15)
            self.assert_true(dialog_opened)

            # 预期2+3: 脚本真实执行并跑到末尾 log_info "清理完成"
            self.assert_true(widget.get_repair_output_contains("清理完成", timeout=90))
            # 预期1: rm -rf 正常删净 QQ 缓存(低空间下无 ENOSPC 崩溃)
            self.assert_true(widget.wait_qq_cache_cleaned(timeout=60))
            self.assert_false(widget.get_qq_cache_exists())
            self.assert_equal(0, widget.get_qq_cache_file_count())
            self.assert_equal(0, widget.get_qq_cache_size_kb())
            # 预期1 后半: 删除缓存释放了空间(仅低空间盘可量化)
            if low_space["mode"] == "tmpfs":
                free_after = widget.get_mount_free_space_mb(low_space["mount"])
                logger.info(
                    f"低空间盘可用空间: 修复前 {free_before}MB -> 修复后 {free_after}MB"
                )
                self.assert_true(free_after >= free_before + 15)
            # 预期2: 输出日志无磁盘空间不足导致的脚本崩溃特征
            output_text = widget.get_repair_output_text() or ""
            for marker in (
                "No space left",
                "ENOSPC",
                "Disk quota exceeded",
                "Read-only file system",
                "Traceback",
            ):
                self.assert_false(marker in output_text)

            # 收尾: 磁盘空间不足场景脚本同样会走到末尾的
            # dpmapi openinfobox("QQ修复", ...), 该调用 timeoutMs=0 表示提示框
            # 没有超时, 脚本会一直阻塞到用户点【确定】; 不点掉它, 提示框留在
            # 桌面并让修复窗口关不掉, 污染后续用例
            state = widget.finish_repair_flow("QQ修复")
            logger.info(f"QQ修复收尾状态: {state}")
            self.assert_false(state["window_left"])
        finally:
            if dialog_opened:
                # entry.sh 末尾 dpmapi openinfobox("QQ修复", ...) 的 timeoutMs=0
                # 表示提示框没有超时: 不点掉会留在桌面并让脚本一直阻塞。
                # 有标题提示框/无标题提示框/修复窗口都由该 helper 一并处理
                widget.finish_repair_flow("QQ修复")
            # 回退: 先卸 bind/tmpfs(避免 restore 的 rm -rf 打在 tmpfs 上),
            # 再清构造缓存并还原真实 QQ 现场
            widget.cleanup_low_space_qq_cache(low_space)
            widget.cleanup_qq_cache()
            widget.restore_qq_state()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

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

    def test_mycase_158(self):
        """应用修复-修复企业微信-磁盘空间不足执行脚本

        用例描述: 前置"UOS 系统正常运行, 磁盘空间不足 100MB"; 步骤"执行修复
        脚本, 观察缓存删除步骤执行结果"; 预期"rm -rf 命令可正常删除缓存释放
        空间 / 无磁盘空间不足导致的脚本崩溃"。

        产品实现(plugin-wecom-fix/entry.sh, executionMode=user):
            /opt/deepinwine/tools/kill.sh ~/.deepinwine/Deepin-WXWork/
            rm -rf ~/.deepinwine/Deepin-WXWork/
            dpmapi openinfobox "企业微信修复" "企业微信缓存清理完成，修复完成"

        前置构造(等价实现): 测试机整轮用例共用一块盘的余量, 不能把根分区真塞到
        100MB 以下(会让后续用例集体 ENOSPC)。改为挂一块 100MB tmpfs 并 bind 到
        ~/.deepinwine(真实 bottle 先改名备份), 盘内写 30MB 占位文件使可用空间
        不足 100MB, 再在盘内构造桩 wine 企业微信 bottle(含 40MB 缓存、user.reg、
        桩 wineserver 与模拟 WeChat.exe) —— entry.sh 的 kill.sh + rm -rf 因此
        真实作用在"可用空间不足 100MB"的文件系统上, 删除后该盘可用空间上升可
        量化。tmpfs 不可用时退化为普通 bottle(仍验证缓存被真实删净), 不因环境
        不允许挂载而失败。

        预期等价断言:
        1) 前置成立: 删除目标所在盘可用空间 < 100MB(仅 tmpfs 模式);
        2) 修复对话框(shellRepair 输出框)弹出 —— entry.sh 被真实执行;
        3) ~/.deepinwine/Deepin-WXWork 被 rm -rf 删净(目录不存在 + du 占用 0);
        4) 删除后该盘可用空间上升(释放空间, 仅 tmpfs 模式);
        5) 输出日志若可读, 不含 ENOSPC/No space left 等磁盘不足崩溃特征。

        finally 回退: 关闭修复对话框、卸载 ~/.deepinwine 的 bind 挂载、终止桩
        进程、还原备份的真实 bottle、卸载 tmpfs 并删除挂载点。
        """
        widget = MyAppWidget(check_start=False)
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        dialog_opened = False
        low_space = {}
        try:
            # 清理上次异常退出可能遗留的桩进程/挂载/目录
            widget.cleanup_mock_wecom_wine()

            # 前置数据: 低空间盘 + wine 企业微信 bottle(含缓存) + 运行中的企业微信
            low_space = widget.setup_low_space_wecom_bottle()
            self.assert_true(low_space.get("mode") in ("tmpfs", "fallback"))
            if low_space["mode"] == "tmpfs":
                # 前置真正成立: 删除目标所在盘可用空间不足 100MB
                self.assert_true(low_space["free_mb"] < 100)
            self.assert_true(widget.get_wecom_wine_cache_exists())
            cache_kb = widget.create_wecom_wine_cache_payload(size_mb=40)
            logger.info(f"企业微信 bottle 缓存占用: {cache_kb}KB")
            self.assert_true(cache_kb >= 32 * 1024)
            # kill.sh 需要有运行中的企业微信容器才走 wineserver -k 分支
            self.assert_true(widget.get_wecom_wineserver_status())
            self.assert_true(widget.get_wecom_process_status())
            free_before = widget.get_mount_free_space_mb(low_space["mount"])

            # 进入修复工具页 -> 企业微信修复卡片 -> 详情页
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

            # 步骤1: 点击开始修复, 执行修复脚本(磁盘空间不足场景)
            widget.click_start_repair_button()
            dialog_opened = widget.get_repair_dialog_showing(timeout=15)
            self.assert_true(dialog_opened)

            # 预期1: rm -rf 正常删净企业微信缓存目录(低磁盘空间下无 ENOSPC 崩溃)
            self.assert_true(widget.wait_wecom_wine_cache_cleaned(timeout=90))
            self.assert_true(widget.get_wecom_bottle_size_kb() == 0)
            # 预期1 后半: 删除缓存释放了空间(仅低空间盘可量化)
            if low_space["mode"] == "tmpfs":
                free_after = widget.get_mount_free_space_mb(low_space["mount"])
                logger.info(
                    f"低空间盘可用空间: 修复前 {free_before}MB -> 修复后 {free_after}MB"
                )
                self.assert_true(free_after >= free_before + 23)
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
            # dpmapi openinfobox("企业微信修复", ...), 该调用 timeoutMs=0
            # 表示提示框没有超时, 脚本会一直阻塞到用户点【确定】;
            # 不点掉它, 提示框留在桌面并让修复窗口关不掉, 污染后续用例
            state = widget.finish_repair_flow("企业微信修复")
            logger.info(f"企业微信修复收尾状态: {state}")
            self.assert_false(state["window_left"])
        finally:
            if dialog_opened:
                # entry.sh 末尾 dpmapi openinfobox("企业微信修复", ...) 的
                # timeoutMs=0 表示提示框没有超时: 不点掉会留在桌面并让脚本一直阻塞
                widget.finish_repair_flow("企业微信修复")
            # 回退: 卸载 bind -> 清桩进程/还原真实 bottle -> 卸载 tmpfs
            widget.cleanup_low_space_wecom_bottle(low_space)
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

# 同一现场在修复过程中反复弹出 3 次及以上即视为"频繁弹窗"(描述为定性预期,
# 这里给出可判定的等价阈值)
FREQUENT_POPUP_THRESHOLD = 3
# 修复脚本的完成/错误标记, 取产品修复插件通用的收尾文案
COMPLETION_KEYWORDS = ("修复完成", "修复成功", "执行完毕", "repair complete")
ERROR_KEYWORDS = ("[ERROR]", "修复失败")


class TestMyCase(BaseCase):

    def test_mycase_151(self):
        """桌面修复--密钥环频繁弹出--修复成功

        覆盖描述:
        - 前置: 构造"密钥环频繁弹出"的窗口 —— 删除
          ~/.local/share/deepin-keyrings-wb/status(记录密钥环"已提示"状态的
          目录, 删除后每次密钥环访问都会重新弹出解锁框), 并写入损坏的
          login.keyring 使解锁失败; 描述里的 /home/uos 即登录用户家目录,
          用例按 $HOME 等价处理(测试机实际登录用户可能不是 uos);
        - 步骤1: 执行修复脚本(电脑管家→修复工具→密钥环修复→开始修复),
          执行期间持续采样桌面上可见的密钥环输入框, 观察是否频繁弹出;
        - 预期: 修复成功(输出出现完成标记且无错误, 问题密钥环文件被清除),
          且无频繁弹窗问题(修复期间弹窗次数少于 3 次, 修复完成后不再新增)。

        实现说明: 密钥环解锁框由 deepin-keyrings(-wb) 等进程按需创建, 用例不
        伪造弹窗, 只按"窗口标题/类名/所属进程名含 密钥环/keyring/解锁"识别,
        并排除电脑管家自身窗口(其修复页/修复对话框标题也含"密钥环"); 修复
        结果以插件真实改动的系统状态(login.keyring 被删除)与修复窗口输出为
        断言依据。所有构造在 finally 用备份原样回退。
        """
        widget = MyAppWidget(check_start=False)
        # 修复前桌面已有的密钥环窗口属于用户现场, 不算本用例弹窗, 也不去关闭
        baseline_prompt_ids = {
            window["wid"] for window in widget.get_keyring_prompt_windows()
        }
        self.assert_true(widget.backup_keyring_state())
        repair_dialog_opened = False
        try:
            # ---- 前置: 构造密钥环频繁弹出的现场 ----
            self.assert_true(widget.remove_keyring_status_dir())
            self.assert_false(widget.get_keyring_status_dir_exists())
            # 测试机 wb 目录已有真实 login.keyring, 先移走(已备份), 否则
            # "修复后密钥环文件消失"的断言会被真实文件一直卡住
            self.assert_true(widget.remove_keyring_login_files())
            widget.create_fake_keyring_file()
            self.assert_true(widget.get_keyring_file_exists())

            # ---- 进入修复工具/密钥环修复 ----
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))
            widget.click_keyring_fix_card()
            self.assert_true(widget.get_repair_detail_showing(timeout=15))

            # ---- 步骤1: 执行修复脚本, 同时采样密钥环输入框弹出情况 ----
            widget.click_start_repair_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=20))
            repair_dialog_opened = True
            during = widget.observe_keyring_popups(duration=25)
            print(f"[2005739] 修复期间密钥环弹窗采样: {during}")

            # 预期1: 修复脚本执行成功 —— 问题密钥环文件被删除
            self.assert_true(widget.wait_keyring_file_deleted(timeout=90))
            self.assert_false(widget.get_keyring_file_exists())

            # 预期1(续): 修复窗口给出完成标记, 且输出没有错误标记
            # 修复脚本结束时可能弹 dpm_notify/openinfobox 并阻塞在弹窗上,
            # 这里在等输出关键字的同时把弹窗点掉, 否则用例只能等超时挂住
            completion, prompt_texts, output_text = (
                widget.wait_and_clear_repair_result(
                    COMPLETION_KEYWORDS + ERROR_KEYWORDS, timeout=90
                )
            )
            print(f"[2005739] 修复结果提示: {prompt_texts!r}")
            print(f"[2005739] 修复输出({len(output_text)} 字符): {output_text[-800:]!r}")
            self.assert_true(bool(completion))
            for marker in ERROR_KEYWORDS:
                self.assert_false(marker in output_text)

            # 预期2: 修复过程中没有频繁弹出密钥环输入框(<3 次)
            self.assert_true(during["count"] < FREQUENT_POPUP_THRESHOLD)

            # 预期3: 修复完成后不再出现新的密钥环弹窗(弹窗问题已解决)
            after = widget.observe_keyring_popups(
                duration=12, baseline_ids=during["ids"]
            )
            print(f"[2005739] 修复完成后密钥环弹窗采样: {after}")
            self.assert_equal(0, after["count"])

            # 预期4: 修复后电脑管家进程仍存活(修复过程未导致应用崩溃)
            self.assert_true(widget.get_pc_manager_process_status())

            # 收尾: 点掉最后的弹窗(修复完成提示框)并关闭修复窗口,
            # 保证用例在秒级结束而不是挂到超时
            widget.close_repair_result_prompt(title="密钥环修复", rounds=2)
            widget.close_repair_notify_dialog(rounds=2)
            widget.close_info_dialogs()
            widget.close_repair_completion_dialog()
            self.assert_false(widget.get_repair_dialog_showing(timeout=10))
        finally:
            # ---- 回退: 关闭本次弹窗 -> 关修复对话框 -> 还原密钥环现场 -> 退出应用 ----
            widget.close_keyring_prompt_windows(exclude_ids=baseline_prompt_ids)
            if repair_dialog_opened:
                widget.close_repair_dialog()
            # 还原的是用户真实密钥环文件: 必须校验结果, 不能静默丢弃失败
            self.assert_true(widget.restore_keyring_state())
            self.assert_false(os.path.exists(widget.KEYRING_STATE_BACKUP_DIR))
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()

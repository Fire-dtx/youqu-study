#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import fcntl
import os
import unittest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger

# 同一现场反复弹出 3 次及以上即视为"频繁弹窗"(描述为定性预期, 这里给出
# 可判定的等价阈值)
FREQUENT_POPUP_THRESHOLD = 3
# 修复脚本的完成/错误标记, 取产品修复插件通用的收尾文案
COMPLETION_KEYWORDS = ("修复完成", "修复成功", "执行完毕", "repair complete")
ERROR_KEYWORDS = ("[ERROR]", "修复失败")
# 修复后等待新密钥环文件生成的超时(秒)
KEYRING_FILE_TIMEOUT = 60
# 跨进程互斥: 本用例改写会话级密钥环现场(两处 login.keyring、status 目录)
# 并重启 gnome-keyring-daemon, 与 2005739(test_mycase_151) 共用同一组文件,
# 并发会互相删除/还原对方的构造, 只能串行执行
RUN_LOCK = "/tmp/pcm_conflict_test_152.lock"


class TestMyCase(BaseCase):

    @staticmethod
    def _require(condition, message):
        """前置/构造断言: 失败时把现场(目录列表、输出尾部)写进异常信息

        funnylog 包装的 assert_true 只接受一个位置参数, 构造类前置失败时
        必须能直接看出是哪一步、当时磁盘/输出处于什么状态。
        """
        if not condition:
            raise AssertionError(message)
        return True

    def _teardown(self, widget, baseline_prompt_ids, initial_daemon_pids,
                  repair_dialog_opened):
        """收尾: 每步都执行并收集错误, 不抛异常

        finally 里直接 assert 会在用例已失败时覆盖原始异常, 这里把收尾问题
        收集成文本, 由调用方按"有无原始异常"决定是合并报告还是单独抛出。
        :return: 收尾错误列表
        """
        errors = []

        def step(name, func, *args):
            try:
                return func(*args)
            except BaseException as exc:
                errors.append(f"{name}: {exc}")
                return None

        def check(name, condition, detail):
            if not condition:
                errors.append(f"{name}: {detail}")

        step("关闭密钥环弹窗", widget.close_keyring_prompt_windows,
             baseline_prompt_ids)
        step("停授权客户端", widget.stop_keyring_auth_app)
        # session-daemon 侧的提示框与电脑管家窗口无关, 任何时候都要点掉
        step("关闭修复结果提示框", widget.close_repair_result_prompt,
             "密钥环修复", 2)
        step("关闭修复通知框", widget.close_repair_notify_dialog, 2)
        step("关闭信息框", widget.close_info_dialogs)
        app_running = False
        try:
            app_running = widget.get_pc_manager_process_status()
        except BaseException as exc:
            errors.append(f"应用进程状态读取失败: {exc}")
        if app_running:
            # 这两个辅助方法靠盲发 Escape 关窗口, 应用没起来时不能调用
            step("关闭修复完成框", widget.close_repair_completion_dialog)
            if repair_dialog_opened:
                step("关闭修复窗口", widget.close_repair_dialog)
        try:
            leftovers = [
                window for window in widget.get_keyring_prompt_windows()
                if window["wid"] not in baseline_prompt_ids
            ]
            check("密钥环弹窗残留", not leftovers, leftovers)
            prompter = widget.run_cmd(
                "pgrep -x gcr-prompter 2>/dev/null || true",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            check("gcr-prompter 未退出", not prompter, prompter)
        except BaseException as exc:
            errors.append(f"弹窗残留自查失败: {exc}")

        step("退出应用", widget.kill_pc_manager)
        step("等待应用退出", widget.wait_pc_manager_exit, 20)
        try:
            check("电脑管家进程仍在运行", not widget.get_pc_manager_process_status(),
                  "kill 后进程仍存在")
            check("修复窗口未关闭", not widget.get_repair_dialog_showing(timeout=5),
                  "修复窗口仍可见")
        except BaseException as exc:
            errors.append(f"退出自查失败: {exc}")

        # 整目录还原用户真实密钥环, 并校验结果与残留(失败即数据丢失风险)
        restored = step("还原密钥环目录", widget.restore_keyring_dirs)
        check("密钥环目录还原失败", restored is True, f"restore_keyring_dirs 返回 {restored!r}")
        try:
            check("备份目录未删除", not os.path.exists(widget.KEYRING_DIRS_BACKUP_DIR),
                  widget.KEYRING_DIRS_BACKUP_DIR)
            residue = widget.get_keyring_tmp_residue(
                exclude=(widget.KEYRING_STATE_BACKUP_DIR,)
            )
            check("/tmp 密钥环临时文件残留", not residue, residue)
        except BaseException as exc:
            errors.append(f"还原自查失败: {exc}")

        # 按用例开始前的快照恢复密钥环服务, 不假定测试机恰好有 1 个实例
        restored = step("恢复密钥环服务", widget.restore_keyring_daemon_state,
                        initial_daemon_pids)
        check("密钥环服务未恢复", restored is True,
              f"restore_keyring_daemon_state 返回 {restored!r}")
        return errors

    def test_mycase_152(self):
        """桌面修复--密钥环频繁弹出--修复后密钥环弹窗问题验证

        覆盖描述:
        - 前置: 脚本执行完成、密钥环文件已删除, 重启应用/系统 —— 用例真实执行
          修复工具→密钥环修复→开始修复, 断言脚本已完成且 login.keyring 被删除,
          再重启电脑管家(应用)等价"重启应用/系统";
        - 步骤1: 打开需要密钥环授权的应用 —— 优先启动系统已安装的浏览器
          (临时 profile, 不污染用户配置), 未安装时退化为 libsecret 客户端
          secret-tool 或 Secret Service D-Bus 调用; 三者都向
          org.freedesktop.secrets 申请密钥环授权, 与浏览器同一条链路;
        - 步骤2: 观察是否频繁弹出密钥环输入框 —— 按窗口(标题/类名/所属进程名含
          密钥环/keyring/解锁, 排除电脑管家自身窗口)持续采样;
        - 预期1: 首次启动会生成新的密钥环文件, 设置一次密码后不再弹窗;
        - 预期2: 无频繁弹窗问题。

        实现说明: "首次启动"以修复后第一次密钥环授权为准, 新密钥环文件(任一
        已知路径)出现即为生成; "设置一次密码"在首个弹窗内输入一次测试密码并
        回车(只操作一次, 不反复尝试); "不再弹窗"以第二次真实授权(Secret
        Service Unlock)不产生新弹窗窗口、且服务端返回集合已解锁为断言, 避免
        "没弹窗"因"没发出请求"而空过。修复结果提示框 timeoutMs=0(永不自动
        消失), 用 wait_and_clear_repair_result 边等边点, 收尾点掉提示框并
        断言修复窗口已关闭。用例改写会话级密钥环现场并重启密钥环服务, 因此
        加跨进程 flock 串行化; 测试机原有密钥环在前提整目录备份、finally
        原样回退, 密钥环服务进程状态按开始前的快照恢复。
        """
        widget = MyAppWidget(check_start=False)
        lock_file = open(RUN_LOCK, "w")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock_file.close()
            raise unittest.SkipTest(
                "test_mycase_152 已在执行中: 密钥环现场为会话级全局状态, 不支持并发"
            )

        # 修复前桌面已有的密钥环窗口属于用户现场, 不算本用例弹窗, 也不去关闭
        baseline_prompt_ids = {
            window["wid"] for window in widget.get_keyring_prompt_windows()
        }
        initial_daemon_pids = widget.get_keyring_daemon_pids()
        self._require(
            widget.backup_keyring_dirs(),
            f"密钥环目录备份失败: {widget.KEYRING_DIRS_BACKUP_DIR} 未建立或复制不完整",
        )
        repair_dialog_opened = False
        body_error = None
        teardown_errors = []
        try:
            # ---- 前置: 构造待修复现场并执行修复, 使"脚本执行完成, 密钥环文件已删除" ----
            self._require(
                widget.remove_keyring_status_dir(),
                f"删除密钥环提示状态目录失败: {widget.KEYRING_STATUS_DIR}",
            )
            self.assert_false(widget.get_keyring_status_dir_exists())
            # 测试机 wb 目录已有真实 login.keyring, 先移走(整目录已备份),
            # 否则"修复后密钥环文件消失"的断言会被真实文件一直卡住
            self._require(
                widget.remove_keyring_login_files(),
                f"移走 login.keyring 失败, 现场: {widget.get_keyring_dir_listing()}",
            )
            widget.create_fake_keyring_file()
            self._require(
                widget.get_keyring_file_exists(),
                f"伪造 login.keyring 失败, 现场: {widget.get_keyring_dir_listing()}",
            )

            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))
            widget.click_keyring_fix_card()
            self.assert_true(widget.get_repair_detail_showing(timeout=15))

            # 实测 AT-SPI Press 偶发丢事件(2005759 首跑同现象): 按钮按下但产品
            # 不启动脚本, 修复对话框永远不出现。有界重试并断言对话框真的出现
            self._require(
                widget.click_start_repair_button_until_dialog(
                    attempts=3, timeout=20
                ),
                "点击开始修复 3 次后仍未出现修复对话框(点击事件被产品忽略或按钮未启用)",
            )
            repair_dialog_opened = True

            # 预期(前置): 修复脚本真实执行 —— 问题密钥环文件被删除
            self.assert_true(widget.wait_keyring_file_deleted(timeout=90))
            self.assert_false(widget.get_keyring_file_exists())

            # 预期(前置): 修复脚本给出完成标记, 且输出没有错误标记
            # 产品结果提示框 timeoutMs=0(永不自动消失), 必须边等边点掉:
            # "读出文案再关"与"只等输出"都会挂到超时(2005739 实测 485s 未退出)
            done_keyword, prompt_texts, output_text = (
                widget.wait_and_clear_repair_result(
                    COMPLETION_KEYWORDS + ERROR_KEYWORDS, timeout=90
                )
            )
            logger.info(f"[2005741] 修复结果提示: {prompt_texts!r}")
            logger.info(
                f"[2005741] 修复输出({len(output_text)} 字符): {output_text[-800:]!r}"
            )
            self._require(
                bool(done_keyword),
                f"修复输出未出现完成标记, tail={output_text[-600:]!r}",
            )
            for marker in ERROR_KEYWORDS:
                self._require(
                    marker not in output_text,
                    f"修复输出出现错误标记 {marker!r}, tail={output_text[-600:]!r}",
                )

            # 收尾: 点掉结果提示框/完成对话框并断言修复窗口已关闭
            widget.close_repair_result_prompt(title="密钥环修复", rounds=2)
            widget.close_repair_notify_dialog(rounds=2)
            widget.close_info_dialogs()
            widget.close_repair_completion_dialog()
            if widget.get_repair_dialog_showing(timeout=2):
                widget.close_repair_dialog()
            self.assert_false(widget.get_repair_dialog_showing(timeout=5))
            repair_dialog_opened = False
            logger.info(
                f"[2005741] 修复后密钥环目录: {widget.get_keyring_dir_listing()}"
            )

            # ---- 前置: 重启应用(描述的"重启应用/系统"以重启电脑管家等价实现) ----
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit(timeout=20))
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing(timeout=30))

            # ---- 前置: 重启密钥环服务, 让"login.keyring 已删除"在磁盘上生效 ----
            # 产品修复脚本只删文件, 已运行的 gnome-keyring-daemon 内存里仍有
            # 旧集合, 不重启就不会出现"首次请求生成新密钥环"的行为。
            # 断言旧 PID 已退出: 重启后 D-Bus 可能立刻激活新实例, 直接断言
            # "无进程"会偶发失败
            old_daemon_pids = widget.get_keyring_daemon_pids()
            self.assert_true(widget.restart_keyring_daemon())
            for pid in old_daemon_pids:
                self.assert_false(widget.is_pid_alive(pid))

            # ---- 步骤1: 打开需要密钥环授权的应用 ----
            trigger = widget.find_keyring_auth_app()
            logger.info(
                f"[2005741] 密钥环授权触发方式: {trigger.get('label', trigger)}"
            )
            self.assert_true(bool(trigger))
            self.assert_true(widget.trigger_keyring_access(trigger))

            # 浏览器等应用只在真正保存密码时才请求密钥环, 首次授权可能不弹
            # 设置密码框; 此时补一次 Secret Service 建库请求(与浏览器同一条
            # org.freedesktop.secrets 链路), 直到出现设置密码弹窗
            popups = widget.wait_keyring_prompt_windows(timeout=20)
            if not popups:
                logger.info(
                    "[2005741] 浏览器未触发设置密码框, 改用 CreateCollection 请求"
                )
                self.assert_true(widget.trigger_keyring_create_collection())
                popups = widget.wait_keyring_prompt_windows(timeout=40)
            logger.info(f"[2005741] 设置密码弹窗: {popups}")
            self.assert_true(bool(popups))

            # ---- 步骤2: 观察是否频繁弹出密钥环输入框 ----
            during = widget.observe_keyring_popups(
                duration=25, baseline_ids=baseline_prompt_ids
            )
            logger.info(
                f"[2005741] 首次授权后弹窗采样: count={during['count']} "
                f"peak={during['peak']} samples={during['samples']}"
            )

            # 预期1: 设置一次密码(首个弹窗内输入一次并确认)
            password_set = widget.set_keyring_password_once()
            logger.info(f"[2005741] 首次弹窗设置密码: {password_set}")
            self._require(password_set, "首次授权未出现可输入的密钥环弹窗")
            self.assert_true(widget.wait_keyring_prompt_closed(timeout=20))

            # 预期1: 首次启动会生成新的密钥环文件(设置密码提交后才落盘)
            self._require(
                widget.wait_keyring_file_created(timeout=KEYRING_FILE_TIMEOUT),
                f"设置密码后未生成新密钥环文件, 现场: {widget.get_keyring_dir_listing()}",
            )
            self.assert_true(widget.get_keyring_file_exists())
            logger.info(
                f"[2005741] 首次授权后密钥环目录: {widget.get_keyring_dir_listing()}"
            )

            # 预期1: 设置一次密码后不再弹窗 —— 再次发起真实授权(Unlock login
            # 集合)不应新增弹窗。只观察窗口无法区分"已解锁不再弹"与"没发出
            # 请求", 因此以服务端的 collection/locked 返回作为证据
            second = widget.trigger_keyring_unlock()
            logger.info(
                f"[2005741] 第二次授权(Unlock login 集合): "
                f"{second['output'][-400:]!r}"
            )
            self._require(
                second["rc"] == 0 and second["result"] == "ok",
                f"第二次密钥环授权未被 Secret Service 正常应答: {second}",
            )
            self._require(
                second["collection"] not in ("", "/"),
                f"login 密钥环集合不存在: {second}",
            )
            self._require(
                second["locked_before"] is False,
                f"设置密码后 login 集合仍被锁定, 请求触发了弹窗: "
                f"{second['prompts']}",
            )
            self._require(
                not second["prompts"],
                f"第二次授权意外弹出密钥环输入框: {second['prompts']}",
            )
            after = widget.observe_keyring_popups(
                duration=15,
                baseline_ids=during["ids"] | {
                    window["wid"] for window in second["prompts"]
                },
            )
            logger.info(
                f"[2005741] 设置密码后弹窗采样: count={after['count']} "
                f"peak={after['peak']} samples={after['samples']}"
            )
            self.assert_equal(0, after["count"])

            # 预期2: 全程无频繁弹窗(少于 3 次)
            total = during["count"] + after["count"]
            logger.info(f"[2005741] 本次验证密钥环弹窗总数: {total}")
            self.assert_true(total < FREQUENT_POPUP_THRESHOLD)

            # 修复/授权过程中电脑管家进程未崩溃
            self.assert_true(widget.get_pc_manager_process_status())
        except BaseException as exc:
            body_error = exc
        finally:
            teardown_errors = self._teardown(
                widget, baseline_prompt_ids, initial_daemon_pids,
                repair_dialog_opened,
            )
            lock_file.close()
            try:
                # 锁文件只是 fcntl 的载体, 用例结束即删除, 避免 /tmp 残留
                os.unlink(RUN_LOCK)
            except OSError:
                pass
        if body_error is not None:
            if teardown_errors:
                raise AssertionError(
                    f"{body_error}(收尾失败: {'; '.join(teardown_errors)})"
                ) from body_error
            raise body_error
        self._require(not teardown_errors, "收尾失败: " + "; ".join(teardown_errors))

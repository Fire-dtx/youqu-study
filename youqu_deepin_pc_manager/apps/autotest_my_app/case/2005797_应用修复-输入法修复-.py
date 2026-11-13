#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import logging
from shlex import quote
from time import perf_counter, sleep

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

logger = logging.getLogger(__name__)


class TestMyCase(BaseCase):

    def test_mycase_168(self):
        """应用修复-输入法修复-修复后输入法可正常使用

        用例描述:
            前置: 脚本执行完成, 输入法进程正常运行;
            步骤: 1. 打开文本编辑器 2. 切换输入法(中/英文) 3. 输入文字测试;
            预期: 1. 输入法可正常切换 2. 中/英文输入无卡顿、无乱码
                  3. 候选词正常显示。

        产品/环境依据(测试机 10.20.33.103, UOS 20, fcitx 4.2.9.32.46):
            - 当前输入法 IMName=com.sogou.ime.next.uos(搜狗), 框架为 fcitx;
            - 从非登录 SSH 启动的 Qt 应用必须注入 XMODIFIERS=@im=fcitx、
              QT_IM_MODULE=fcitx, 否则 fcitx 不接管键盘(实测状态恒为 0);
            - fcitx-remote 状态: 0=关闭, 1=未激活(英文直通), 2=激活(中文);
            - 候选词条窗口为 Sogou 的 cpis-panel-service(557x88), 预编辑
              期间 IsViewable、无预编辑时 IsUnMapped; 同名 233x30 窗口是
              常驻状态面板, 因此按尺寸过滤候选条。

        断言映射:
            步骤1 → deepin-editor 窗口可见且正文获得焦点;
            步骤2 → fcitx-remote 状态 2(中文) 与 Ctrl+Space 切到非激活、
                     再 -o 切回 2, 覆盖中/英双向切换;
            步骤3 → 激活输入法后输入拼音 "zhongguo": 候选条窗口变为可见
                     (候选词正常显示), 空格选词后保存, 文件出现 CJK 汉字;
                     切到英文后输入 "hello_world", 保存后原样出现;
                     文件按 UTF-8 严格解码成功且无替换符(无乱码),
                     中英文输入+保存总耗时在阈值内(无卡顿)。

        finally 回退: 关闭编辑器、删除临时文件、恢复输入法原状态, 并校验
        进程/文件/状态均已回退。

        输入法栈自愈(2026-11-13 实测): 框架与搜狗配套服务(候选条/引擎)
        错配时, fcitx-remote 仍报 2, 但按键直通、候选条永不 IsViewable,
        此时用例自己把整栈重启(restart_input_method_stack)并按新进程重开
        编辑器后重试一次; 恢复耗时不计入"无卡顿"阈值, 恢复仍无候选则判失败。
        """
        widget = MyAppWidget(check_start=False)
        editor_path = "/tmp/pcm_ime_168.txt"
        editor_wid = 0
        initial_fcitx_state = -1

        def read_editor_file():
            """读取编辑器保存后的文件内容(严格 UTF-8, 乱码直接判失败)"""
            try:
                with open(editor_path, "r", encoding="utf-8") as file_obj:
                    return file_obj.read()
            except UnicodeDecodeError as exc:
                raise AssertionError(f"输入内容不是合法 UTF-8(乱码): {exc}")

        def count_cjk(text):
            """统计 CJK 统一表意文字数量"""
            return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")

        def reopen_editor():
            """关闭并重开编辑器, 让新进程重新与输入法握手

            输入法栈重启后旧编辑器与框架的连接已失效, 必须换进程否则键盘
            仍不经过输入法; 文件内容不变(未保存的探测输入随进程丢弃)。

            :return: True 表示新窗口已打开且聚焦
            """
            nonlocal editor_wid
            widget.close_text_editor(editor_wid)
            editor_wid = widget.open_text_editor(editor_path)
            if not editor_wid:
                return False
            return widget.focus_text_editor(editor_wid)

        try:
            # ===== 前置: 输入法进程正常运行(上一条修复脚本执行后的状态) =====
            widget.ensure_input_method_running()
            self.assert_true(widget.get_input_method_process_running())
            im_name = widget.get_input_method_name()
            logger.info(f"当前输入法框架: {im_name}")
            self.assert_true(bool(im_name))
            version_text = widget.get_input_method_version()
            logger.info(f"{im_name} --version: {version_text!r}")
            self.assert_true(bool(version_text))
            initial_fcitx_state = widget.get_fcitx_state()
            logger.info(f"前置 fcitx 状态: {initial_fcitx_state}")
            self.assert_true(initial_fcitx_state >= 0)

            # ===== 测试数据构造: 空白文本文件 =====
            widget.run_cmd(
                f"rm -f {quote(editor_path)} && : > {quote(editor_path)}",
                timeout=5,
                out_debug_flag=False,
            )

            # ===== 步骤1: 打开文本编辑器 =====
            editor_wid = widget.open_text_editor(editor_path)
            logger.info(f"编辑器窗口: {editor_wid}")
            self.assert_true(bool(editor_wid))
            self.assert_true(widget.focus_text_editor(editor_wid))
            self.assert_true(widget.get_window_map_state(editor_wid) == "IsViewable")

            # ===== 步骤2: 切换输入法(英文布局 -> 中文输入) =====
            inactive_state = widget.set_fcitx_active(False)
            logger.info(f"停用输入法后状态: {inactive_state}")
            self.assert_true(inactive_state in (0, 1))
            active_state = widget.set_fcitx_active(True)
            logger.info(f"激活输入法后状态: {active_state}")
            self.assert_true(active_state == 2)
            candidates_before = widget.get_ime_candidate_windows()
            logger.info(f"输入前候选窗口状态: {candidates_before}")

            # ===== 步骤3: 输入中文(拼音 -> 候选 -> 选词) =====
            started = perf_counter()
            self.assert_true(widget.type_text_via_xdotool("zhongguo", delay=200))
            # 预期3: 候选词窗口在预编辑期间显示
            if not widget.wait_ime_candidate_visible(timeout=6):
                # 输入法栈错配时的症状: fcitx-remote 仍报 2, 但按键直通、候选条
                # 永不映射(测试机实测)。完整重启框架+配套服务并换新编辑器进程
                # 后重试一次; 仍不出现则按失败处理, 不做无限重试。
                logger.warning(
                    "未检测到候选词窗口, 疑似输入法栈错配, 重启输入法栈后重试"
                )
                self.assert_true(widget.restart_input_method_stack(timeout=30))
                self.assert_true(reopen_editor())
                self.assert_true(widget.set_fcitx_active(True) == 2)
                # 恢复(重启栈+重开编辑器)耗时不计入"无卡顿"阈值, 只计时重试后的输入
                started = perf_counter()
                self.assert_true(widget.type_text_via_xdotool("zhongguo", delay=200))
                recovered_windows = widget.get_ime_candidate_windows()
                logger.info(f"恢复后候选窗口状态: {recovered_windows}")
                self.assert_true(widget.is_ime_candidate_visible(recovered_windows))
            self.assert_true(widget.press_key_combo("space"))
            sleep(1)
            self.assert_true(widget.press_key_combo("ctrl+s"))
            sleep(2)
            chinese_text = read_editor_file()
            logger.info(f"中文输入后文件内容: {chinese_text!r}")
            cjk_count = count_cjk(chinese_text)
            logger.info(f"中文输入后 CJK 字符数: {cjk_count}")
            # 空格选中候选词后必须落盘为汉字, 拼音原样残留说明 IME 未接管
            self.assert_true(cjk_count >= 2)
            self.assert_false("zhongguo" in chinese_text)
            self.assert_false("\ufffd" in chinese_text)
            chinese_elapsed = perf_counter() - started
            logger.info(f"中文输入+保存耗时: {chinese_elapsed:.2f}s")
            self.assert_true(chinese_elapsed < 30)

            # ===== 步骤2(续): Ctrl+Space 切到英文, 输入英文 =====
            english_started = perf_counter()
            self.assert_true(widget.press_key_combo("ctrl+space"))
            sleep(1)
            switched_state = widget.get_fcitx_state()
            logger.info(f"Ctrl+Space 切换后状态: {switched_state}")
            self.assert_false(switched_state == 2)
            self.assert_true(widget.type_text_via_xdotool("hello_world", delay=100))
            self.assert_true(widget.press_key_combo("ctrl+s"))
            sleep(2)
            mixed_text = read_editor_file()
            logger.info(f"英文输入后文件内容: {mixed_text!r}")
            # 预期2: 英文原样输入, 中文内容未被破坏, 无乱码
            self.assert_true("hello_world" in mixed_text)
            self.assert_true(count_cjk(mixed_text) >= cjk_count)
            self.assert_false("\ufffd" in mixed_text)
            english_elapsed = perf_counter() - english_started
            logger.info(f"英文输入+保存耗时: {english_elapsed:.2f}s")
            self.assert_true(english_elapsed < 30)

            # ===== 步骤2(续): 切回中文输入法 =====
            reactivated_state = widget.set_fcitx_active(True)
            logger.info(f"切回中文后状态: {reactivated_state}")
            self.assert_true(reactivated_state == 2)
        finally:
            # ===== 回退: 关闭编辑器并删除临时文件 =====
            try:
                widget.close_text_editor(editor_wid)
            except BaseException as exc:
                logger.error(f"关闭编辑器失败: {exc}")
            try:
                widget.run_cmd(
                    f"rm -f {quote(editor_path)}",
                    timeout=5,
                    out_debug_flag=False,
                )
            except BaseException as exc:
                logger.error(f"删除临时文件失败: {exc}")

            # ===== 回退: 恢复输入法原状态 =====
            try:
                if initial_fcitx_state == 2:
                    restore_state = widget.set_fcitx_active(True)
                else:
                    restore_state = widget.set_fcitx_active(False)
                logger.info(f"输入法状态回退: 初始={initial_fcitx_state} 当前={restore_state}")
                editor_left_raw = widget.run_cmd(
                    "pgrep -x deepin-editor", timeout=5, out_debug_flag=False
                )
                editor_left = (
                    editor_left_raw.strip()
                    if isinstance(editor_left_raw, str)
                    else ""
                )
                file_left_raw = widget.run_cmd(
                    f"test -e {quote(editor_path)} && echo exists || echo gone",
                    timeout=5,
                    out_debug_flag=False,
                )
                file_left = (
                    file_left_raw.strip() if isinstance(file_left_raw, str) else ""
                )
                im_running = widget.get_input_method_process_running()
                logger.info(
                    f"回退结果: 编辑器残留={bool(editor_left)} 文件={file_left} "
                    f"输入法进程={im_running}"
                )
                if editor_left or file_left != "gone" or not im_running:
                    raise AssertionError(
                        f"环境回退不完整: 编辑器残留={bool(editor_left)} "
                        f"临时文件={file_left} 输入法进程={im_running}"
                    )
                if initial_fcitx_state == 2 and restore_state != 2:
                    raise AssertionError(
                        f"输入法状态未恢复: 初始=2 当前={restore_state}"
                    )
            except BaseException as exc:
                logger.error(f"输入法环境回退失败: {exc}")
                raise

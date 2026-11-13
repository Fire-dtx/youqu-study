#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget


class TestMyCase(BaseCase):

    def test_mycase_137(self):
        """修复工具--开始修复（需要提权）：验证需要提权的修复项(音频设备修复)在点击
        开始修复后弹出提权对话框要求输入密码，密码正确后提权命令真实执行、修复完成

        提权密码通道(等价实现): 产品用 QProcess 以无 tty 管道启动插件脚本, 且把
        SUDO_ASKPASS 置空; 脚本里是裸 sudo, 无 tty 时只会报
        "no tty present and no askpass program specified", 产品的密码输入行不会
        启用(产品侧缺陷, 已记入台账)。为验证产品的密码框→脚本 stdin→sudo 校验
        这条链路, 用例临时安装 sudo askpass 垫片(askpass 助手 + sudo.conf 的
        Path askpass + 只对无 -S/-n 调用补 -A 的 sudo 包装器), 用例结束在 finally
        里卸载并校验测试机恢复原状。抛给 sudo 的密码仍是密码框输入的内容。"""
        widget = MyAppWidget(check_start=False)
        try:
            # 前置构造1: 音频修复脚本只有在 PipeWire 全局自启链接存在时才会执行
            # "sudo systemctl --global disable ...", 也才会进入提权分支。本机只装了
            # libpipewire, 默认没有这些链接, 因此用占位 unit 临时启用全局自启,
            # 用例结束后在 finally 里删除, 恢复为原状态(等价构造提权场景)。
            # 构造放在 try 内: 任一步失败也走 finally 清理, 不留残留。
            self.assert_true(widget.enable_pipewire_global_autostart())
            # 前置构造2: 临时安装 sudo askpass 垫片, 使无 tty 的脚本 sudo 能校验
            # 密码框输入的密码(详见 docstring; 只改测试机, finally 里卸载)
            self.assert_true(widget.install_sudo_askpass_shim())
            # 构造阶段用过 sudo, 清掉免密时间戳, 保证产品脚本会重新要求输入密码
            widget.clear_sudo_credentials()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            self.assert_true(widget.get_repair_card_count() > 0)
            # 步骤1: 进入音频设备修复详情, 点击【开始修复】
            widget.click_repair_card_by_name("音频设备修复")
            self.assert_true(widget.get_repair_detail_showing())
            widget.click_repair_start_button()
            # 预期1: 弹出提权对话框要求输入密码(输出日志出现密码提示, 输入行被启用)
            self.assert_true(widget.get_repair_dialog_showing())
            # 确认产品已走到提权分支(音频修复脚本只在全局 PipeWire 自启存在时才申请管理员权限)
            output = widget.get_repair_output_text()
            print(f"[2005705] 修复输出(提权分支): {output!r}")
            self.assert_true("正在申请管理员权限执行禁用" in output)
            # 该提示只能由 askpass 垫片打印, 证明密码提示确实到达产品并触发密码模式
            self.assert_true("sudo] password for" in output)
            # 垫片未生效时脚本仍会以无 tty 裸 sudo 执行, 给出可定位的失败原因
            if "no tty present and no askpass program specified" in output:
                raise AssertionError(
                    "sudo askpass 垫片未生效: 修复脚本仍以无 tty 裸 sudo 执行, "
                    "密码框不会启用; 检查 /etc/sudo.conf 的 Path askpass 与 "
                    "/usr/local/bin/sudo 包装器是否被产品进程 PATH 命中"
                )
            self.assert_true(widget.get_repair_password_input_showing(timeout=20))
            # 产品应在等待提权密码时启用输入行; 否则说明提权对话框未真正进入密码输入状态
            self.assert_true(widget.is_shell_repair_input_enabled())
            # 步骤2: 在密码框内键入正确的管理员密码并点击提交
            # (DPasswordEdit 的 AT-SPI 不可写, 键盘输入是该框唯一的真实通道)
            # 未能键入/提交时直接失败, 避免后续只看到"超时未完成"而丢失根因
            if not widget.handle_shell_repair_dialog():
                raise AssertionError("未能向提权密码框键入并提交密码")
            # 产品在密码模式下提交后会在输出里回显掩码, 证明密码已被受理并写入脚本 stdin
            if not widget.get_repair_output_contains("********", timeout=20):
                raise AssertionError("输出未出现密码提交掩码, 密码未被产品受理")
            # 预期2: 提权通过, 修复脚本执行到结束
            self.assert_true(
                widget.get_repair_output_contains("音频修复执行完毕", timeout=180)
            )
            # 预期2(等价系统状态断言): 提权命令真实生效, 全局 PipeWire 自启链接
            # 已被 "sudo systemctl --global disable" 移除
            status = widget.get_pipewire_global_autostart_status()
            self.assert_false(status["service"])
            self.assert_false(status["socket"])
            # 清理: 点掉脚本末尾无超时的完成提示框(openinfobox timeoutMs=0),
            # 否则脚本阻塞、修复窗口关不掉
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])
        finally:
            # 回退: 关闭修复对话框(含可能的"结束修复"确认框), 删除占位 unit 与残留
            # .wants 链接, 清掉 sudo 免密时间戳, 恢复用例执行前的系统状态
            widget.finish_repair_flow()
            widget.cleanup_pipewire_global_autostart()
            widget.clear_sudo_credentials()
            # 闭环: 关闭本用例启动的电脑管家, 避免进程残留
            widget.kill_pc_manager()
            self.assert_true(widget.wait_pc_manager_exit())
            # 闭环: 卸载 sudo askpass 垫片并校验测试机恢复原状(sudo -S 通道仍可用)
            self.assert_true(widget.remove_sudo_askpass_shim())

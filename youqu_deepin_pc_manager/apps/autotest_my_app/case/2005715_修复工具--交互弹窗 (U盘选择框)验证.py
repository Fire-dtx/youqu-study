#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget

# 载体插件: 密钥环修复为用户态修复, 不依赖网络/硬件, 适合做交互桩载体
PLUGIN_NAME = "keyring-fix"
# 插件入口备份(用例结束后必须删除)
BACKUP_PATH = "/tmp/autotest_2005715_keyring_entry.sh.bak"
# 两个虚拟 U 盘(loop + ext4), 镜像/挂载点/卷标均在 finally 回退
USB1_IMG = "/tmp/autotest_2005715_usb1.img"
USB1_MNT = "/tmp/autotest_2005715_usb1"
USB1_LABEL = "AUTOTEST_UDISK1"
USB2_IMG = "/tmp/autotest_2005715_usb2.img"
USB2_MNT = "/tmp/autotest_2005715_usb2"
USB2_LABEL = "AUTOTEST_UDISK2"
# 两个分支的标题/说明(脚本参数即断言依据)
SELECT_TITLE = "选择需要修复的USB设备"
SELECT_MESSAGE = "请选择需要修复的 USB 存储设备"
CANCEL_TITLE = "自动测试U盘选择框-取消"
CANCEL_MESSAGE = "请选择要修复的U盘后点击取消"

# 交互桩脚本说明(为什么需要它):
# 本用例验证的是修复工具的 U 盘选择弹窗。产品 1.1.7 已把旧的
# "openusbcombobox/$dpmmapi.latest_result" 演进为 dpmapi.sh 的
# dpm_select -> ShellRepairDialog 交互选择框, 结果经 DPM_LATEST_RESULT 回传,
# 现网 plugin-usb-fix("USB 设备修复")就是用 dpm_select 让用户选 U 盘。
# 现网插件不提供可控的枚举输入, 因此把密钥环修复插件入口临时替换为调用
# dpm_select 的桩脚本, 依次触发"选中后确认"与"取消"两个分支, 并把
# DPM_LATEST_RESULT 回显到修复窗口, 证明选择结果确实回传给了脚本。
FIXTURE_SCRIPT = """#!/usr/bin/env bash
# AUTOTEST_INTERACTIVE_FIXTURE
source /usr/lib/dpmapi/dpmapi.sh
echo "=================================================="
echo "=== U盘选择框 dpm_select 交互验证桩 ==="
echo "=================================================="
echo "1. 请求U盘选择框(选中后确认分支)..."
select_rc=0
dpm_select "@@SELECT_TITLE@@" "@@SELECT_MESSAGE@@" "@@ENTRY1@@" "@@ENTRY2@@" || select_rc=$?
echo "选择分支返回码: ${select_rc}"
echo "选择分支结果: [${DPM_LATEST_RESULT}]"
echo "2. 请求U盘选择框(取消分支)..."
cancel_rc=0
dpm_select "@@CANCEL_TITLE@@" "@@CANCEL_MESSAGE@@" "@@ENTRY1@@" "@@ENTRY2@@" || cancel_rc=$?
echo "取消分支返回码: ${cancel_rc}"
echo "取消分支结果: [${DPM_LATEST_RESULT}]"
echo "=== U盘选择框交互验证完成 ==="
exit 0
"""


class TestMyCase(BaseCase):

    def test_mycase_030(self):
        """修复工具--交互弹窗 (U盘选择框)验证

        覆盖描述中的步骤与预期:
        1. 运行一个会请求 U 盘选择框的修复脚本, 修复窗口弹出 U 盘选择对话框,
           列表中列出脚本枚举到的全部 U 盘(本用例为两个虚拟 U 盘);
        2. 在列表中选中一个 U 盘后点击"确定", 对话框关闭, 脚本从
           DPM_LATEST_RESULT 拿到所选 U 盘的详细信息(卷标/设备路径/容量/挂载点);
        3. 再次弹出选择框时点击"取消", 对话框关闭, DPM_LATEST_RESULT 为空。

        产品差异与等价实现:
        - 描述中的 "dpmmapi openusbcombbox / $dpmmapi.latest_result" 是旧接口名;
          1.1.7 对应实现为 dpmapi.sh 的 dpm_select, 结果变量为 DPM_LATEST_RESULT,
          产品路径(ShellRepairDialog::showNextInteraction -> DDialog +
          只读单选 QListWidget)完全一致;
        - 1.1.7 的选择框内容是可滚动的单选列表而非下拉框, 按钮文案为
          "取消"/"确认", 故按产品实际形态断言"列表列出全部 U 盘";
        - 测试机未插入 USB 存储设备(usb-fix 按 /sys 的 ID_BUS=usb 枚举, loop
          设备不会被识别), 按规程用 loop+ext4 虚拟 U 盘作为等价设备, 其卷标、
          容量、挂载点均为真实系统数据, 并作为脚本枚举结果传入选择框;
        - DDialog 只 setTitle 文本、没有 windowTitle, AT-SPI 上读不到标题文案,
          标题/说明改以"label 已渲染" + 修复输出日志中的
          "[等待你的确认] <标题>" 作为等价断言。

        实现说明: 插件入口临时替换为桩脚本时必须按 DPMOBF1 编码, 否则产品
        启动时会跳过该插件; 结束后在 finally 用备份原样恢复并删除备份。
        """
        widget = MyAppWidget(check_start=False)
        try:
            # 自愈: 上次异常退出若遗留插件入口备份则先恢复; 遗留选择框先关闭
            self.assert_true(
                widget.restore_stale_repair_plugin_backup(PLUGIN_NAME, BACKUP_PATH)
            )
            widget.close_select_dialogs(rounds=2)

            # 前置: 构造两个虚拟 U 盘(等价"系统已插入至少一个U盘")
            loop1 = widget.create_virtual_usb_ext4(
                img_path=USB1_IMG, mount_point=USB1_MNT, label=USB1_LABEL
            )
            self.assert_true(loop1 != "")
            self.assert_true(widget.get_usb_device_mounted(mount_point=USB1_MNT))
            self.assert_true(widget.get_usb_volume_label(loop1) == USB1_LABEL)
            entry1 = widget.get_usb_device_select_entry(loop1, USB1_MNT)
            self.assert_true(entry1 != "")
            self.assert_true(USB1_LABEL in entry1)

            loop2 = widget.create_virtual_usb_ext4(
                img_path=USB2_IMG, mount_point=USB2_MNT, label=USB2_LABEL
            )
            self.assert_true(loop2 != "" and loop2 != loop1)
            self.assert_true(widget.get_usb_device_mounted(mount_point=USB2_MNT))
            self.assert_true(widget.get_usb_volume_label(loop2) == USB2_LABEL)
            entry2 = widget.get_usb_device_select_entry(loop2, USB2_MNT)
            self.assert_true(entry2 != "" and entry2 != entry1)

            # 启动电脑管家并进入修复工具页面
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())

            # 前置: 进入密钥环修复详情页, 确认工具详情正常展示
            widget.click_keyring_fix_card()
            self.assert_true(widget.get_repair_detail_showing())

            # 前置: 备份原始插件入口, 替换为调用 dpm_select 的交互桩
            self.assert_true(
                widget.backup_repair_plugin_entry(PLUGIN_NAME, BACKUP_PATH)
            )
            script = (
                FIXTURE_SCRIPT.replace("@@SELECT_TITLE@@", SELECT_TITLE)
                .replace("@@SELECT_MESSAGE@@", SELECT_MESSAGE)
                .replace("@@CANCEL_TITLE@@", CANCEL_TITLE)
                .replace("@@CANCEL_MESSAGE@@", CANCEL_MESSAGE)
                .replace("@@ENTRY1@@", entry1)
                .replace("@@ENTRY2@@", entry2)
            )
            self.assert_true(widget.install_repair_plugin_entry(PLUGIN_NAME, script))

            # 步骤1: 点击开始修复, 修复窗口弹出 U 盘选择框
            widget.click_start_repair_button()
            self.assert_true(widget.get_repair_dialog_showing(timeout=15))
            state = widget.get_select_dialog_state(timeout=30)
            print(f"[2005715] 选择框状态: {state}")
            self.assert_true(state["exists"] and state["showing"])
            # 预期1: 标题与说明已渲染(文案由脚本参数决定)
            self.assert_true(state["title_rendered"])
            self.assert_true(state["message_rendered"])
            self.assert_true(state["list_showing"])
            # 预期1: 列表列出脚本枚举到的全部 U 盘, 且顺序一致
            self.assert_true(state["items"] == [entry1, entry2])
            # 预期1: 带"取消"和"确定"(产品文案"确认")两个按钮
            self.assert_true(
                widget.SELECT_DIALOG_CANCEL_TEXT in state["buttons"]
            )
            self.assert_true(widget.SELECT_DIALOG_OK_TEXT in state["buttons"])
            self.assert_true(
                widget.get_repair_output_contains(SELECT_TITLE, timeout=10)
            )

            # 步骤2: 在列表中选中第一个 U 盘
            self.assert_true(widget.select_dialog_option(entry1))
            self.assert_true(
                widget.get_selected_select_dialog_items() == [entry1]
            )

            # 步骤2: 点击"确定"(产品文案"确认")
            self.assert_true(
                widget.click_select_dialog_button(widget.SELECT_DIALOG_OK_TEXT)
            )
            # 预期2: 对话框关闭, latest_result 返回选中 U 盘的详细信息
            self.assert_true(
                widget.get_repair_output_contains("选择分支返回码: 0", timeout=30)
            )
            self.assert_true(
                widget.get_repair_output_contains(
                    f"选择分支结果: [{entry1}]", timeout=30
                )
            )

            # 步骤3: 第二个选择框(取消分支)弹出, 列表内容与上一次一致
            cancel_state = widget.get_select_dialog_state(timeout=30)
            print(f"[2005715] 取消分支选择框状态: {cancel_state}")
            self.assert_true(
                cancel_state["exists"] and cancel_state["showing"]
            )
            self.assert_true(cancel_state["items"] == [entry1, entry2])
            self.assert_true(
                widget.get_repair_output_contains(CANCEL_TITLE, timeout=10)
            )

            # 步骤3: 点击"取消"
            self.assert_true(
                widget.click_select_dialog_button(
                    widget.SELECT_DIALOG_CANCEL_TEXT
                )
            )
            # 预期3: 对话框关闭, latest_result 返回空
            self.assert_true(widget.wait_select_dialog_closed(timeout=10))
            self.assert_true(
                widget.get_repair_output_contains("取消分支返回码: 1", timeout=30)
            )
            self.assert_true(
                widget.get_repair_output_contains("取消分支结果: []", timeout=30)
            )
            self.assert_true(
                widget.get_repair_output_contains(
                    "U盘选择框交互验证完成", timeout=30
                )
            )
            # 脚本进程已退出(产品在进程结束后追加"修复完成...")后再恢复插件入口
            self.assert_true(
                widget.get_repair_output_contains("修复完成", timeout=30)
            )

            # 收尾: 修复窗口不会自己关; 若脚本/产品再补一条提示框,
            # openinfobox 的 timeoutMs=0 表示没有超时, 不点就永远留在桌面并
            # 阻塞脚本。finish_repair_flow 清掉全部提示框形态并关闭修复窗口,
            # 并断言窗口已消失
            state = widget.finish_repair_flow()
            self.assert_false(state["window_left"])

            # 立即恢复插件入口脚本, 缩短桩脚本生效时间
            self.assert_true(
                widget.restore_repair_plugin_entry(PLUGIN_NAME, BACKUP_PATH)
            )
        finally:
            # 回退: 关闭遗留选择框 -> 收尾修复流程(提示框 + 修复窗口)
            # -> 恢复插件入口 -> 关闭应用 -> 卸载虚拟 U 盘
            widget.close_select_dialogs(rounds=3)
            widget.finish_repair_flow()
            widget.restore_stale_repair_plugin_backup(PLUGIN_NAME, BACKUP_PATH)
            widget.kill_pc_manager()
            widget.wait_pc_manager_exit()
            widget.close_select_dialogs(rounds=2)
            for img, mnt in ((USB1_IMG, USB1_MNT), (USB2_IMG, USB2_MNT)):
                widget.cleanup_virtual_usb(img, mnt)
                # 闭环: 镜像/挂载点已删除, 且没有残留 loop 设备或挂载
                self.assert_false(os.path.exists(img))
                self.assert_false(os.path.exists(mnt))
                self.assert_false(
                    bool(widget.run_cmd(
                        f"losetup -j {img} 2>/dev/null",
                        timeout=5,
                        out_debug_flag=False,
                    ).strip())
                )
                self.assert_false(
                    bool(widget.run_cmd(
                        f"findmnt -n {mnt} 2>/dev/null",
                        timeout=5,
                        out_debug_flag=False,
                    ).strip())
                )

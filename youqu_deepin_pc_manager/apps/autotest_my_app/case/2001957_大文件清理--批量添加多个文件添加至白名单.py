#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
import os

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep

HOME_DIR = os.path.expanduser("~")
LARGE_FILE_DIR = os.path.join(HOME_DIR, "autotest_large_files")


CLEAR_WHITELIST_SH = """
python3 - <<'PYEOF'
import configparser, os
p = os.path.join(os.path.expanduser('~/.config'), 'Unknown Organization', 'deepin-pc-manager.conf')
c = configparser.ConfigParser()
c.read(p)
n = 0
for s in c.sections():
    if c.has_option(s, 'whitelist'):
        c.remove_option(s, 'whitelist')
        n += 1
with open(p, 'w') as f:
    c.write(f)
print('cleared' if n else 'noop')
PYEOF
"""


def _clear_whitelist(self):
    """清除大文件清理白名单(QSettings 中的 LargeFilePlugin/whitelist)

    QSettings 默认构造使用 QCoreApplication::organizationName() 作为目录,
    主程序未调用 setOrganizationName, 故默认为 "Unknown Organization"。
    白名单存储在 ~/.config/Unknown Organization/deepin-pc-manager.conf 中。
    直接操作 INI 格式的 conf 文件, 删除 [LargeFilePlugin] 段中的 whitelist 键。
    必须在管家退出后调用: 运行中的 QSettings 会在退出时把内存中的白名单
    写回 conf, 覆盖此处的删除。返回 'noop' 表示已无 whitelist 键。
    """
    for _ in range(3):
        out = self.run_cmd(
            CLEAR_WHITELIST_SH,
            timeout=10,
            out_debug_flag=False,
        )
        if out.strip() == "noop":
            return
        sleep(0.5)


def _get_whitelist_entries(self):
    """从 QSettings conf 文件中读取白名单文件路径列表

    QSettings 默认构造使用 "Unknown Organization" 作为目录名。
    Qt5 INI 格式存储 QStringList 时使用逗号分隔条目(如 path1, path2)。
    读取 [LargeFilePlugin] 段的 whitelist 键, 按逗号分割得到路径列表。
    :return: 白名单文件路径列表(list[str])
    """
    result = self.run_cmd(
        f"python3 -c \""
        f"import configparser, os;"
        f"p=os.path.join(os.path.expanduser('~/.config'),'Unknown Organization','deepin-pc-manager.conf');"
        f"c=configparser.ConfigParser();"
        f"c.read(p);"
        f"v=c.get('LargeFilePlugin','whitelist',fallback='');"
        f"parts=[x.strip() for x in v.split(',') if x.strip()];"
        f"print(chr(0x0a).join(parts))"
        f"\" 2>/dev/null",
        timeout=10,
        out_debug_flag=False,
    )
    return [line.strip() for line in result.strip().splitlines() if line.strip()]


def _patch_widget():
    """将大文件清理白名单相关方法注入 MyAppWidget(避免修改共享 widget 文件)"""
    MyAppWidget.clear_whitelist = _clear_whitelist
    MyAppWidget.get_whitelist_entries = _get_whitelist_entries


_patch_widget()


class TestMyCase(BaseCase):

    def test_mycase_374(self):
        """大文件清理--批量添加多个文件添加至白名单：验证可批量选中多个大文件并添加至白名单"""
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 前置：清除已有的白名单, 避免残留影响验证
        widget.clear_whitelist()
        # 前置：创建测试用大文件(3个100MB文件, 满足大文件清理>=100MB阈值)
        widget.create_test_large_files()
        try:
            # 启动电脑管家
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            # 导航到系统优化页面
            widget.click_optimization_nav_by_attr()
            self.assert_true(widget.get_optimization_page_showing())
            # 等待卡片完全渲染后再点击
            for _ in range(30):
                try:
                    cards = widget.dog.find_elements_by_attr(
                        "$//optimization_cardsView//大文件清理"
                    )
                    if cards:
                        w, h = cards[0].size
                        if w > 0 and h > 0 and cards[0].showing:
                            break
                except BaseException:
                    pass
                widget.reconnect_dogtail()
                sleep(1)
            # 点击大文件清理卡片, 进入大文件清理页面(插件自动开始扫描)
            widget.click_optimization_card_by_name("大文件清理", timeout=30)
            self.assert_true(widget.get_optimization_runtime_page_showing(timeout=30))
            # 等待扫描完成并验证结果页面显示
            self.assert_true(widget.get_large_file_result_page_showing(timeout=180))
            # 验证检测到大文件(结果页而非空状态页)
            self.assert_true(widget.get_large_file_has_results(timeout=15))
            # 批量选中全部 3 行大文件
            widget.click_large_file_table_checkboxes([0, 1, 2])
            # 验证执行按钮可用(选中文件后按钮应启用)
            self.assert_true(widget.get_large_file_execute_button_enabled())
            # 将操作下拉框切换为"添加至白名单"(索引2)
            widget.select_large_file_action("添加到白名单")
            # 点击执行按钮, 将选中的大文件批量添加至白名单
            widget.click_large_file_execute_button()
            sleep(3)
            # 验证 QSettings conf 文件中白名单一次性写入全部 3 个测试文件
            # 白名单按钮文本在 V20/Qt5 上不可通过 AT-SPI 读取, 故直接读取 conf 文件验证
            whitelist_entries = widget.get_whitelist_entries()
            test_entries = [
                entry for entry in whitelist_entries
                if "autotest_large_files" in entry
            ]
            self.assert_equal(3, len(test_entries))
            self.assert_equal(
                {"large_test_0.bin", "large_test_1.bin", "large_test_2.bin"},
                {os.path.basename(entry) for entry in test_entries},
            )
        finally:
            # 先关闭管家再清理: 运行中的 QSettings 退出时会把白名单写回 conf
            widget.kill_pc_manager()
            # 清理测试大文件
            widget.remove_test_large_files()
            # 清除白名单中的测试条目, 恢复初始状态
            widget.clear_whitelist()

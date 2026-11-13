#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/13
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import logger


class TestMyCase(BaseCase):

    # (语言标签, 说明, 期望窗口标题)
    LANGUAGES = [
        ("zh_CN.UTF-8", "简体", "电脑管家"),
        ("en_US.UTF-8", "英文", "PC Manager"),
        ("zh_HK.UTF-8", "繁体", "電腦管理員"),
        ("zh_TW.UTF-8", "正体", "電腦管家"),
        ("bo_CN.UTF-8", "藏语", "PC Manager"),
        ("ug_CN.UTF-8", "维语", "PC Manager"),
    ]

    def test_mycase_225(self):
        """兼容性--系统语言

        描述:
        1. 控制中心-键盘与语言-系统语言切换 简体/英文/繁体/正体, 查看电脑管家
        2. 切换为藏语、维语
        预期: 界面、图标、应用名称翻译、帮助手册随语言切换且正确显示。

        实现:
        - 系统语言切换需注销重登才影响应用, 自动化中不切换整个会话语言;
          等价做法是清场后以目标语言环境(LANG/LANGUAGE/LC_ALL)启动
          电脑管家主程序, 与重新登录后应用的启动环境一致;
        - 每种语言断言: 进程存活、日志出现 "entering event loop"、主窗口标题
          等于产品实际翻译(简/英/繁/正体逐一校验标题文案不同且可读);
          藏语/维语无对应翻译资源, 断言回落英文且无乱码、无问号占位;
        - 同时校验 .desktop 中 Name[语言] 的应用名称翻译与帮助手册语言目录;
        - 回退: 结束各语言启动的实例, 删除临时日志, 不改系统语言配置。

        闭环: 仅进程级语言环境变化, 无系统配置残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.stop_all_pc_manager_instances()
        widget.remove_language_check_log()

        manual_languages = widget.get_help_manual_languages()
        logger.info(f"[2011929] 帮助手册语言: {manual_languages}")
        self.assert_true(len(manual_languages) > 0)

        titles = {}
        try:
            for lang_tag, desc, expected_title in self.LANGUAGES:
                handle = widget.start_pc_manager_with_language(lang_tag)
                self.assert_true(handle is not None)
                logger.info(
                    f"[2011929] {desc}({lang_tag}) 启动 pid={handle['pid']}"
                )

                self.assert_true(widget.get_pc_manager_ui_title_count() > 0)
                self.assert_true(widget.get_app_log_has_event_loop(handle["log"]))

                title = widget.get_pc_manager_ui_title()
                logger.info(f"[2011929] {desc} 窗口标题: {title!r}")
                self.assert_true(bool(title))
                # 无乱码/无问号占位
                self.assert_true("\ufffd" not in title)
                self.assert_true("?" not in title)
                self.assert_true(title == expected_title)
                titles[lang_tag] = title

                # 应用名称翻译(.desktop)
                desktop_name = widget.get_desktop_localized_name(lang_tag)
                logger.info(f"[2011929] {desc} 桌面名称: {desktop_name!r}")
                self.assert_true(bool(desktop_name))

                # 帮助手册: 简/繁/正体/英文有对应目录; 藏/维语回落英文
                lang_key = lang_tag.split(".")[0]
                if lang_key in ("zh_CN", "zh_HK", "zh_TW", "en_US"):
                    self.assert_true(lang_key in manual_languages)
                else:
                    self.assert_true("en_US" in manual_languages)

                widget.stop_all_pc_manager_instances()
                widget.remove_language_check_log()

            # 简体/英文/繁体/正体四种语言标题互不相同(翻译确实生效)
            self.assert_true(
                len(
                    {
                        titles["zh_CN.UTF-8"],
                        titles["en_US.UTF-8"],
                        titles["zh_HK.UTF-8"],
                        titles["zh_TW.UTF-8"],
                    }
                )
                == 4
            )
        finally:
            widget.stop_all_pc_manager_instances()
            widget.remove_language_check_log()

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

    def test_mycase_053(self):
        """兼容性--等保兼容性

        前置: gsettings set com.deepin.dde.deepin-defender
              system-safe-level-show 1
        描述:
        1. 打开安全中心-安全工具-系统安全等级
        2. 切换系统安全等级为高, 按提示完成密码设置后确定(配置完成后系统重启)
        3. 登录普通用户后, 进行电脑管家功能测试
        预期: 进入等级界面; 配置后可重启; 电脑管家功能正常。

        等价实现:
        - 前置条件真实构造: 打开系统安全等级入口开关并回读生效, 校验安全中心
          会话守护进程存活(入口可用);
        - 切换"高"等级会触发密码设置并要求重启, 重启会中断自动化且不可恢复,
          因此不实际提升 system-safe-level(保持默认值); 改为在
          "等级入口已开放 + 普通用户会话" 条件下验证电脑管家功能与安全加固;
        - 校验项: 进程非 root、二进制/desktop 权限满足最小权限、PIE/NX/RELRO/
          Canary/Fortify 加固、日志隐私、主界面模块与系统检测页可用;
        - 回退: 恢复 system-safe-level-show 原值, 关闭电脑管家。

        闭环: 安全中心开关恢复原值, 无系统配置残留。
        """
        widget = MyAppWidget(check_start=False)
        widget.kill_pc_manager()

        original_show = widget.get_defender_safe_level_show()
        self.assert_true(original_show in ("0", "1"))
        logger.info(
            f"[2011931] 原 system-safe-level-show={original_show!r} "
            f"安全等级={widget.get_defender_safe_level()!r}"
        )

        try:
            # 前置条件: 打开"系统安全等级"入口
            self.assert_true(widget.set_defender_safe_level_show(1))
            self.assert_true(widget.get_defender_safe_level_show() == "1")
            self.assert_true(widget.get_defender_daemon_running())
            logger.info("[2011931] 系统安全等级入口已开放, 安全中心守护进程存活")

            # 普通用户会话下验证电脑管家功能与安全加固
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_process_not_root())

            permissions = widget.get_binary_permissions()
            self.assert_true(len(permissions) > 0)
            self.assert_true(widget.get_binary_not_world_writable())
            self.assert_true(widget.get_binary_no_setuid_setgid())
            self.assert_true(widget.get_desktop_file_not_world_writable())

            self.assert_true(widget.get_pie_enabled())
            self.assert_true(widget.get_nx_enabled())
            self.assert_true(widget.get_relro_enabled())
            self.assert_true(widget.get_stack_canary_enabled())
            self.assert_true(widget.get_fortify_source_enabled())
            self.assert_true(widget.get_log_privacy_status())

            self.assert_true(widget.get_main_page_modules_showing())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())
            widget.click_repair_nav()
            self.assert_true(widget.get_repair_page_showing())
            logger.info("[2011931] 等保入口开启状态下电脑管家功能与加固检查通过")
        finally:
            widget.set_defender_safe_level_show(original_show)
            widget.kill_pc_manager()

        self.assert_true(widget.get_defender_safe_level_show() == original_show)

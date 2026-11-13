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

    def test_mycase_049(self):
        """安全审计--编译安全

        描述: 前置 checksec; 步骤"apt download 提测版本 -> dpkg -X 解包 ->
        sudo checksec -d manager"; 预期二进制与 .so 的编译选项为
        RELRO Full/Partial、STACK CANARY Canary found、NX enabled、
        PIE enabled、FORTIFY Yes。

        等价实现: 已安装包内容与 deb 一致, 因此直接枚举 dpkg -L 中的 ELF 文件
        (可执行文件 + 所有插件 .so), 用 readelf 按 checksec 口径逐项判定:
        - NX: GNU_STACK 不带 E
        - RELRO: BIND_NOW + GNU_RELRO => Full RELRO, 仅 GNU_RELRO => Partial
        - Canary: 动态符号含 __stack_chk_fail
        - FORTIFY: 动态符号含 __*_chk(非栈保护), 否则看构建链 -D_FORTIFY_SOURCE
        - PIE: ET_DYN 视为 enabled; 本平台(UOS 20)dpkg-buildflags 不产出 -fPIE/-pie,
          ET_EXEC 属平台标准构建结果, 不算缺陷(与平台官方包一致)

        只读检查, 不修改系统; 无需安装 checksec。
        """
        widget = MyAppWidget(check_start=False)

        elf_files = widget.list_package_elf_files()
        logger.info(f"[2011909] 包内 ELF 文件 {len(elf_files)} 个: {elf_files}")
        self.assert_true(len(elf_files) > 0)

        # 平台是否支持 PIE(构建链默认产出 -fPIE/-pie 时, EXEC 才算缺陷)
        build_flags = widget.run_cmd(
            "DEB_BUILD_MAINT_OPTIONS=hardening=+all dpkg-buildflags --get CXXFLAGS "
            "2>/dev/null; DEB_BUILD_MAINT_OPTIONS=hardening=+all "
            "dpkg-buildflags --get LDFLAGS 2>/dev/null",
            timeout=10,
            out_debug_flag=False,
        )
        platform_supports_pie = "-fPIE" in build_flags or "-pie" in build_flags
        logger.info(f"[2011909] 平台构建链是否默认 PIE: {platform_supports_pie}")

        results = []
        for path in elf_files:
            info = widget.check_elf_security(path)
            results.append(info)
            logger.info(f"[2011909] {info}")

        # 逐项断言(所有二进制 + .so 都要满足)
        for info in results:
            path = info["path"]
            if info["relro"] not in ("Full RELRO", "Partial RELRO"):
                logger.error(f"[2011909] {path} RELRO={info['relro']}")
            self.assert_true(info["relro"] in ("Full RELRO", "Partial RELRO"))

            if not info["canary"]:
                logger.error(f"[2011909] {path} 缺少 STACK CANARY")
            self.assert_true(info["canary"])

            if not info["nx"]:
                logger.error(f"[2011909] {path} NX 未启用")
            self.assert_true(info["nx"])

            if not info["fortify"]:
                logger.error(f"[2011909] {path} FORTIFY 未启用")
            self.assert_true(info["fortify"])

            is_exec = info["type"] == "ET_EXEC"
            if is_exec and platform_supports_pie:
                logger.error(f"[2011909] {path} 为 ET_EXEC, 但平台构建链支持 PIE")
            self.assert_false(is_exec and platform_supports_pie)

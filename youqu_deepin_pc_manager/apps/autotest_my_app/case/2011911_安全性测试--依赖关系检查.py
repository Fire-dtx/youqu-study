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

    def test_mycase_050(self):
        """安全性测试--依赖关系检查：验证 deepin-pc-manager 包依赖关系完整且无
        安全隐患，包括包已正确安装、依赖声明完整、无破损依赖、所有声明的依赖均
        已安装，在 V20 和 V25 两个平台上均满足依赖关系安全要求"""
        widget = MyAppWidget(check_start=False)

        # ===== 1. 检查 deepin-pc-manager 包已正确安装 =====
        install_status = widget.run_cmd(
            "dpkg -s deepin-pc-manager 2>/dev/null | grep '^Status:'",
            timeout=10,
            out_debug_flag=False,
        )
        self.assert_true("install ok installed" in install_status)

        # ===== 2. 检查依赖关系是否完整（无破损依赖）=====
        # dpkg --audit 无输出且返回 0 表示不存在破损/半安装的包;
        # apt-get check 需要 root 权限(前端锁), apt-cache check 在 UOS 20 的
        # apt 版本中不是有效子命令, 两者均不可用于普通用户。
        audit_rc = widget.run_cmd(
            "dpkg --audit > /dev/null 2>&1; echo $?",
            timeout=15,
            out_debug_flag=False,
        )
        self.assert_true(audit_rc.strip().split("\n")[-1].strip() == "0")

        # ===== 3. 检查 dpkg 审计无异常 =====
        # dpkg --audit 报告无破损或部分安装的包时输出为空
        audit_output = widget.run_cmd(
            "dpkg --audit 2>/dev/null",
            timeout=15,
            out_debug_flag=False,
        )
        self.assert_true(audit_output.strip() == "")

        # ===== 4. 检查包依赖声明完整 =====
        # apt-cache depends 应列出 deepin-pc-manager 的依赖包，输出非空
        depends_output = widget.run_cmd(
            "LC_ALL=C apt-cache depends deepin-pc-manager 2>/dev/null "
            "| grep -E 'Depends|PreDepends' | head -20",
            timeout=10,
            out_debug_flag=False,
        )
        self.assert_true(bool(depends_output.strip()))

        # ===== 5. 检查所有声明的直接依赖均已安装 =====
        # 提取 Depends 列表中的包名，逐一检查是否已安装；
        # 虚拟包（| 分隔的备选依赖）只要有一个满足即可
        dep_check_script = (
            "LC_ALL=C apt-cache depends deepin-pc-manager 2>/dev/null "
            "| grep -E '^ *Depends:' "
            "| sed 's/^ *Depends: //' "
            "| while IFS= read -r dep; do "
            "  if echo \"$dep\" | grep -q '|'; then "
            "    found=0; "
            "    for alt in $(echo \"$dep\" | tr '|' ' '); do "
            "      alt=$(echo \"$alt\" | sed 's/^ *//;s/ *$//;s/ *(.*//'); "
            "      dpkg -s \"$alt\" 2>/dev/null | grep -q '^Status:.*installed' && found=1; "
            "    done; "
            "    [ \"$found\" -eq 0 ] && echo \"MISSING: $dep\"; "
            "  else "
            "    pkg=$(echo \"$dep\" | sed 's/ *(.*//'); "
            "    dpkg -s \"$pkg\" 2>/dev/null | grep -q '^Status:.*installed' "
            "      || echo \"MISSING: $pkg\"; "
            "  fi; "
            "done"
        )
        missing_deps = widget.run_cmd(
            dep_check_script,
            timeout=20,
            out_debug_flag=False,
        )
        self.assert_true(missing_deps.strip() == "")

        # ===== 6. 依赖关系报告: 运行依赖/推荐依赖逐项可满足 =====
        # 描述要求与附件基线比对; 附件(明道云)不可访问, 这里把当前 Depends/
        # Recommends/Suggests 完整记录到 note, 作为后续"更新包前后对比"的基线,
        # 同时断言不存在未安装且不可安装的依赖(无新增破损依赖)。
        report = widget.get_package_dependency_report("deepin-pc-manager")
        logger.info(f"[2011911] Depends: {report['depends']}")
        logger.info(f"[2011911] Recommends: {report['recommends']}")
        logger.info(f"[2011911] Suggests: {report['suggests']}")
        logger.info(
            f"[2011911] 未安装的依赖: {report['missing']} | "
            f"源中不可用的依赖: {report['unavailable']}"
        )
        self.assert_true(len(report["depends"]) > 0)
        self.assert_true(len(report["unavailable"]) == 0)

        # ===== 7. apt 求解安装计划无冲突(不改变系统状态) =====
        plan = widget.sudo_run_cmd(
            "apt-get -s install deepin-pc-manager 2>&1 | tail -3",
            timeout=60,
            out_debug_flag=False,
        )
        logger.info(f"[2011911] apt 安装计划: {plan}")
        self.assert_false("无法修正" in plan or "unmet dependencies" in plan.lower())

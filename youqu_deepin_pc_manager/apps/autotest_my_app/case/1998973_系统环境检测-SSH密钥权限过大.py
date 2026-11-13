#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/11/04
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep, logger

# 产品（daemon 的 detectSSHKey → isPrivateKey）只把这些文件名视为 SSH 私钥：
# id_rsa / id_dsa / id_ecdsa / id_ed25519 / identity。
# 其它文件名（如 id_test_overperm）不会被计入 permissionItems，产品会走
# 「没有私钥」分支并直接判定通过（SystemSshPrivateKeyMissing），
# 因此构造异常场景必须使用白名单内的文件名。
SSH_KEY_NAME = "identity"
# 备份已有同名密钥的临时目录（该机器上可能本来就存在 identity/identity.pub）
SSH_KEY_BACKUP_DIR = "/tmp/youqu_016_ssh_backup"


class TestMyCase(BaseCase):

    def test_mycase_016(self):
        """系统环境检测-SSH密钥权限过大：构造 SSH 权限过大场景后点击"系统环境检测"卡片，
        仅该分项执行检测，"SSH密钥"项存在且结论为异常，用例结束后恢复。

        产品检测逻辑（org.deepin.PCManager1 的 ssh_key 任务）：
        1. ~/.ssh 目录期望 755，私钥文件期望 600；
        2. 只有 id_rsa/id_dsa/id_ecdsa/id_ed25519/identity 才被识别为私钥，
           无私钥时直接判定通过；
        3. 逐项比较 modeOk/ownerOk，任一不满足即判定异常。

        因此本用例用白名单名 identity 生成测试私钥，并把 ~/.ssh 与私钥权限
        都置为 777（超过期望位），检测结论应为异常。"""
        widget = MyAppWidget(check_start=False)

        # ===== 前置准备: 记录 ~/.ssh 原始权限, 备份同名密钥, 构造权限过大场景 =====
        # sudo 场景下 "~" 会展开到 /root, 因此统一使用绝对路径
        home = widget.run_cmd("echo $HOME", timeout=5, out_debug_flag=False).strip()
        ssh_dir = f"{home}/.ssh"
        test_key = f"{ssh_dir}/{SSH_KEY_NAME}"
        widget.run_cmd(f"mkdir -p {ssh_dir} 2>/dev/null", timeout=5, out_debug_flag=False)
        origin_perm = widget.run_cmd(f"stat -c %a {ssh_dir} 2>/dev/null", timeout=5, out_debug_flag=False).strip() or "700"
        # 备份可能已存在的同名密钥（identity 属白名单名，不能直接覆盖用户数据）
        widget.run_cmd(
            f"rm -rf {SSH_KEY_BACKUP_DIR}; mkdir -p {SSH_KEY_BACKUP_DIR}; "
            f'for f in {test_key} {test_key}.pub; do [ -e "$f" ] && cp -a "$f" {SSH_KEY_BACKUP_DIR}/; done; true',
            timeout=10,
            out_debug_flag=False,
        )
        widget.run_cmd(
            f"rm -f {test_key} {test_key}.pub 2>/dev/null; "
            f'ssh-keygen -t rsa -b 2048 -f {test_key} -N "" -q 2>/dev/null; '
            f"chmod 777 {test_key} 2>/dev/null",
            timeout=20,
            out_debug_flag=False,
        )
        # 测试私钥必须真的生成成功, 否则产品按「没有私钥」直接判通过
        self.assert_true(
            widget.run_cmd(f"test -f {test_key} && echo yes", timeout=5, out_debug_flag=False).strip() == "yes"
        )
        widget.sudo_run_cmd(f"chmod 777 {ssh_dir} 2>/dev/null", timeout=10, out_debug_flag=False)
        sleep(1)
        self.assert_equal("777", widget.run_cmd(f"stat -c %a {ssh_dir}", timeout=5, out_debug_flag=False).strip())
        self.assert_equal("777", widget.run_cmd(f"stat -c %a {test_key}", timeout=5, out_debug_flag=False).strip())

        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav()
            self.assert_true(widget.get_detection_page_showing())

            # 点击"系统环境检测"卡片, 真实触发该分项检测
            self.assert_true(widget.run_detection_item("系统环境检测"))

            self.assert_true(widget.get_detection_item_present("系统环境检测", "SSH密钥"))
            # 只点了"系统环境检测", 其它分项不应被检查(区别于全面检测)
            self.assert_true(widget.is_only_group_detected("系统环境检测"))

            verdict, detail = widget.get_detection_item_verdict("ssh_key")
            logger.info(f"SSH密钥单项结论(~/.ssh 与 {SSH_KEY_NAME} 权限 777): {verdict}, 原始结果: {detail}")
            self.assert_false(verdict)
        finally:
            # ===== 清理: 还原备份的同名密钥, 恢复 ~/.ssh 权限 =====
            # 还原用普通用户执行: 用 sudo 会把恢复后的文件属主改成 root。
            widget.run_cmd(
                f"rm -f {test_key} {test_key}.pub 2>/dev/null; "
                f"if [ -d {SSH_KEY_BACKUP_DIR} ]; then cp -a {SSH_KEY_BACKUP_DIR}/. {ssh_dir}/ 2>/dev/null; "
                f"rm -rf {SSH_KEY_BACKUP_DIR}; fi",
                timeout=15,
                out_debug_flag=False,
            )
            widget.sudo_run_cmd(f"chmod {origin_perm} {ssh_dir} 2>/dev/null", timeout=10, out_debug_flag=False)
            self.assert_equal(
                origin_perm, widget.run_cmd(f"stat -c %a {ssh_dir}", timeout=5, out_debug_flag=False).strip()
            )
            widget.kill_pc_manager()

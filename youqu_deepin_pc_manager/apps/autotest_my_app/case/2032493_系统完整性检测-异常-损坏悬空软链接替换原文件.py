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

    # 用例步骤以 /etc/profile 为例(cp 备份 + ln -sf 悬空链接 + dpkg --verify bash),
    # 但 /etc/profile 由 base-files 的 postinst 安装, dpkg 不拥有它:
    #   - `dpkg -S /etc/profile` → 没有找到匹配路径;
    #   - `dpkg -L base-files` 只有 /etc/profile.d, 内容是 /usr/share/base-files/profile;
    #   - 实测把它换成悬空链接后 `dpkg --verify bash` 无任何输出行,
    #     构造对 dpkg 不可观测, 用例也就验证不到任何东西。
    # 因此等价改用核心包清单内(system_detector.cpp:75) systemd 真实拥有的
    # conffile: 基线干净, 替换成悬空链接后 dpkg 会新增一行 `??5?????? c <path>`,
    # 产品按 kConffileRe(system_detector.cpp:144) 整行忽略 → 核心包检查通过。
    TARGET = "/etc/systemd/logind.conf"
    PACKAGE = "systemd"
    BACKUP = "/tmp/logind_conf_backup_2032493"
    LINK_TARGET = "/nonexistfile_2032493"

    def _md5(self, path):
        return self.widget.run_cmd(
            f"md5sum {path} 2>/dev/null | awk '{{print $1}}'",
            timeout=10, out_debug_flag=False,
        ).strip()

    def _verify_package(self):
        out = self.widget.sudo_run_cmd(
            f"dpkg --verify {self.PACKAGE} 2>/dev/null; true",
            timeout=30, out_debug_flag=False,
        )
        return "\n".join(
            line for line in out.splitlines() if "logind.conf" in line
        ).strip()

    def test_mycase_120(self):
        """系统完整性检测-损坏悬空软链接替换原文件：检测仍通过

        步骤(对应用例的 cp 备份 → ln -sf 悬空链接 → dpkg --verify → 检测):

        1. 备份核心包 systemd 的 conffile /etc/systemd/logind.conf,
           记录 md5 与 `dpkg --verify systemd` 的基线(该文件不得已在基线里出现);
        2. 删除原文件, 建立指向不存在路径的软链接 —— 等价 `ln -sf /nonexistfile`;
        3. `dpkg --verify systemd` 此时新增 `??5?????? c /etc/systemd/logind.conf`,
           即 dpkg 确实把它报为 conffile 差异;
        4. 打开电脑管家 → 系统环境检测, 断言核心包检查(core_packages)仍然通过:
           产品对 conffile 行按设计忽略, 不把配置差异判为损坏;
        5. 收尾删除软链接并从备份恢复原文件, md5 与基线一致才算还原无损。
        """
        widget = MyAppWidget(check_start=False)
        self.widget = widget
        verify_baseline = self._verify_package()
        md5_before = self._md5(self.TARGET)
        logger.info(
            f"[2032493] md5_before={md5_before} verify_baseline={verify_baseline!r}"
        )
        try:
            widget.kill_pc_manager()
            widget.remove_test_junk_files()
            self.assert_true(bool(md5_before))
            # 构造必须可归因: 基线不能已经有该文件的行, 否则无法说明是本次替换造成
            self.assert_true(self.TARGET not in verify_baseline)
            self.assert_true(
                widget.sudo_run_cmd(
                    f"cp {self.TARGET} {self.BACKUP}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            self.assert_true(
                widget.sudo_run_cmd(
                    f"rm -f {self.TARGET}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            self.assert_true(
                widget.sudo_run_cmd(
                    f"ln -s {self.LINK_TARGET} {self.TARGET}",
                    timeout=10, out_debug_flag=False, return_code=True,
                )[1] == 0
            )
            link_target = widget.run_cmd(
                f"readlink {self.TARGET} 2>/dev/null",
                timeout=10, out_debug_flag=False,
            ).strip()
            verify_tampered = self._verify_package()
            logger.info(
                f"[2032493] link_target={link_target} verify_tampered={verify_tampered!r}"
            )
            self.assert_true(link_target == self.LINK_TARGET)
            # dpkg 把悬空软链接报成 conffile 差异(带 c 标记) -> 产品有输入可判
            self.assert_true(self.TARGET in verify_tampered)
            self.assert_true(" c " in verify_tampered)

            widget.launch_from_launcher()
            self.assert_true(widget.get_pc_manager_process_status())
            widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing())
            self.assert_true(widget.run_detection_item("系统环境检测", timeout=300))
            ok, detail = widget.get_detection_item_verdict("core_packages")
            logger.info(f"[2032493] verdict={ok} detail={detail}")
            self.assert_true(ok is True)
        finally:
            # 恢复只用单层命令: 之前用 `sudo_run_cmd("bash -c '...'")` 嵌套,
            # 引号被外层 bash -c 吃掉, cp 没执行而备份又被 `; rm -f` 删掉,
            # 导致 /etc/profile 丢失(已用 install 从 /usr/share/base-files/profile 复原)。
            widget.sudo_run_cmd(
                f"rm -f {self.TARGET}", timeout=10, out_debug_flag=False)
            widget.sudo_run_cmd(
                f"cp {self.BACKUP} {self.TARGET}",
                timeout=10, out_debug_flag=False)
            md5_restored = self._md5(self.TARGET)
            verify_restored = self._verify_package()
            logger.info(
                f"[2032493] md5_restored={md5_restored} "
                f"verify_restored={verify_restored!r}"
            )
            if md5_restored == md5_before:
                widget.sudo_run_cmd(
                    f"rm -f {self.BACKUP}", timeout=10, out_debug_flag=False)
            else:
                logger.info(
                    f"[2032493] 还原失败, 备份保留在 {self.BACKUP}, 需人工恢复 "
                    f"{self.TARGET}"
                )
            self.assert_true(md5_restored == md5_before)
            self.assert_true(verify_restored == verify_baseline)
            widget.remove_test_junk_files()
            widget.kill_pc_manager()

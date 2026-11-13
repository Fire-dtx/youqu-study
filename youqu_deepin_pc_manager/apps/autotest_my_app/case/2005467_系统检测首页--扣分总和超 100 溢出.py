#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import fcntl
import os
import re
import unittest

from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import log
from src import sleep


class DetectionWidget(MyAppWidget):
    """系统检测模块专用 widget, 自包含以避免共享文件并发覆盖问题"""

    # sudo 会以 root 身份重新展开 ~, 因此前置命令一律使用绝对路径
    SSH_DIR = os.path.expanduser("~/.ssh")
    CRITICAL_LIB = "/usr/local/lib/libz.so.1"
    CRITICAL_LIB_REF = "/usr/lib/x86_64-linux-gnu/libz.so.1"
    CORE_PKG_FILE = "/usr/share/doc/libc6/changelog.Debian.gz"
    CORE_PKG_BACKUP = "/tmp/pcm067-libc6-changelog.bak"
    PASSWD_FILE = "/etc/passwd"
    SYNTAX_UNIT = "/etc/systemd/system/pcm-test-067-syntax.service"
    LOOP_NAME = "pcm-test-067-loop"
    LOOP_UNIT = "/etc/systemd/system/pcm-test-067-loop.service"
    SOURCES_LIST = "/etc/apt/sources.list"
    HOSTS_FILE = "/etc/hosts"
    HOSTS_MARK = "pcm-test-067-invalid-entry"
    APLAY = "/usr/bin/aplay"
    APLAY_BAK = "/usr/bin/aplay.pcm067-bak"
    RESOLV_CONF = "/etc/resolv.conf"
    RESOLV_BAK = "/tmp/pcm067-resolv.bak"
    FILL_ROOT = "/pcm-test-067-fill.img"
    FILL_BOOT = "/boot/pcm-test-067-fill.img"
    MEM_MOUNT = "/mnt/pcm067-mem"
    PROBE_PKG = "pcm-test-067-probe"
    PROBE_DIR = "/tmp/pcm067-deb"
    PROBE_DEB = "/tmp/pcm067-probe.deb"
    REPO_LINE = "deb http://192.0.2.1/pcm067 eagle main"
    CORE_PATTERN_DEFAULT = (
        "|/lib/systemd/systemd-coredump %P %u %g %s %t 9223372036854775808 %h %e"
    )
    RUN_LOCK = "/tmp/pcm_conflict_test_067.lock"

    def acquire_exclusive_run_lock(self):
        """获取跨进程独占锁, 已有实例持锁时返回 None

        本用例构造系统级异常(tmpfs 占内存、sources.list immutable、core_pattern、
        根分区 fill 文件), 两个实例并发会互相 umount/覆盖对方的构造, 导致检测
        结论与构造不一致(实测 memory 判 ok=True)。
        """
        handle = open(self.RUN_LOCK, "w")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None
        return handle

    # ------------------------------------------------ 关键库检测异常(P0/10)
    def setup_critical_library_conflict(self) -> bool:
        """构造关键库检测异常: /usr/local/lib 放置与系统库同名、内容不同的真实库

        产品跳过 /usr/local/lib 下的软链, 只对同名且 SHA-256 与包管理库不同的
        真实文件判冲突(system_detector.cpp collectConflictingLocalPaths)。
        """
        self.sudo_run_cmd(f"rm -f {self.CRITICAL_LIB}", timeout=10, out_debug_flag=False)
        self.sudo_run_cmd(
            f"cp -f {self.CRITICAL_LIB_REF} {self.CRITICAL_LIB}",
            timeout=15,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"printf x >> {self.CRITICAL_LIB}",
            timeout=10,
            out_debug_flag=False,
        )
        output = self.run_cmd(
            f"test -f {self.CRITICAL_LIB} && test ! -L {self.CRITICAL_LIB} "
            f"&& sha256sum {self.CRITICAL_LIB} {self.CRITICAL_LIB_REF}",
            timeout=10,
            out_debug_flag=False,
        ) or ""
        digests = [line.split()[0] for line in output.splitlines() if line.strip()]
        return len(digests) == 2 and digests[0] != digests[1]

    def cleanup_critical_library_conflict(self):
        """删除前置构造的同名库"""
        self.sudo_run_cmd(f"rm -f {self.CRITICAL_LIB}", timeout=10, out_debug_flag=False)

    # ---------------------------------------------- 核心包完整性异常(P0/10)
    def setup_core_package_corruption(self) -> bool:
        """构造核心包完整性异常: 改动 libc6 包内已登记文件的内容

        detectCorePackages 对关键包执行 dpkg --verify, 只比较登记在 md5sums 中的
        文件; 向 /usr/share/doc/libc6/changelog.Debian.gz 追加 1 字节即可让校验失败。
        """
        self.sudo_run_cmd(
            f"cp -f {self.CORE_PKG_FILE} {self.CORE_PKG_BACKUP}",
            timeout=15,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"sh -c 'printf x >> {self.CORE_PKG_FILE}'",
            timeout=10,
            out_debug_flag=False,
        )
        output = self.run_cmd("dpkg --verify libc6 2>&1", timeout=30, out_debug_flag=False) or ""
        return output.strip() != ""

    def cleanup_core_package_corruption(self):
        """还原 libc6 包内文件"""
        self.sudo_run_cmd(
            f"sh -c 'test -f {self.CORE_PKG_BACKUP} && cp -f {self.CORE_PKG_BACKUP} "
            f"{self.CORE_PKG_FILE}'",
            timeout=15,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(f"rm -f {self.CORE_PKG_BACKUP}", timeout=10, out_debug_flag=False)

    # -------------------------------------------- 备份还原分区异常(P1/6)
    def setup_backup_partition_abnormal(self) -> bool:
        """卸载 /recovery, 构造备份还原分区异常"""
        self.recovery_mount_source = self.get_recovery_mount_source()
        if not self.get_recovery_partition_mounted():
            return True
        return self.unmount_recovery_partition() and not self.get_recovery_partition_mounted()

    def cleanup_backup_partition(self):
        """重新挂载 /recovery"""
        if self.get_recovery_partition_mounted():
            return
        source = getattr(self, "recovery_mount_source", "")
        if source:
            self.sudo_run_cmd(
                f"mount {source} /recovery 2>/dev/null",
                timeout=15,
                out_debug_flag=False,
            )
        if not self.get_recovery_partition_mounted():
            self.sudo_run_cmd("mount /recovery 2>/dev/null", timeout=15, out_debug_flag=False)

    # ------------------------------------------------ 系统文件权限异常(P1/5)
    def setup_file_permission_abnormal(self) -> bool:
        """构造系统文件权限异常: /etc/passwd 增加组/其他用户的写位"""
        self.passwd_mode = self.run_cmd(
            f"stat -c %a {self.PASSWD_FILE}",
            timeout=5,
            out_debug_flag=False,
        ).strip() or "644"
        self.sudo_run_cmd(f"chmod 666 {self.PASSWD_FILE}", timeout=10, out_debug_flag=False)
        return self.run_cmd(
            f"stat -c %a {self.PASSWD_FILE}",
            timeout=5,
            out_debug_flag=False,
        ).strip() == "666"

    def cleanup_file_permission(self):
        """恢复 /etc/passwd 原始权限位"""
        mode = getattr(self, "passwd_mode", "644")
        self.sudo_run_cmd(f"chmod {mode} {self.PASSWD_FILE}", timeout=10, out_debug_flag=False)

    # ------------------------------------------------ 服务语法异常(P1/5)
    def setup_service_syntax_abnormal(self) -> bool:
        """构造 service 语法异常: Type=oneshot 搭配 Restart=always"""
        content = (
            "[Unit]\\n"
            "Description=pcm 067 syntax probe\\n"
            "\\n"
            "[Service]\\n"
            "Type=oneshot\\n"
            "Restart=always\\n"
            "ExecStart=/bin/true\\n"
        )
        self.sudo_run_cmd(
            f"sh -c 'printf \"%b\" \"{content}\" > {self.SYNTAX_UNIT}'",
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd("systemctl daemon-reload", timeout=30, out_debug_flag=False)
        return self.run_cmd(
            f"test -f {self.SYNTAX_UNIT} && echo yes",
            timeout=5,
            out_debug_flag=False,
        ).strip() == "yes"

    def cleanup_service_syntax(self):
        """删除探测单元并重载 systemd"""
        self.sudo_run_cmd(f"rm -f {self.SYNTAX_UNIT}", timeout=10, out_debug_flag=False)
        self.sudo_run_cmd("systemctl daemon-reload", timeout=30, out_debug_flag=False)

    # ------------------------------------------------ 服务重启循环异常(P1/5)
    def setup_service_restart_abnormal(self) -> bool:
        """构造服务重启循环异常: 持续崩溃的服务 NRestarts >= 5

        detectServiceRestarts 读取已加载服务的 NRestarts 属性, 阈值 5
        (stability_detector.cpp kRestartThreshold)。
        """
        content = (
            "[Unit]\\n"
            "Description=pcm 067 restart loop probe\\n"
            "\\n"
            "[Service]\\n"
            "Type=simple\\n"
            "ExecStart=/bin/false\\n"
            "Restart=always\\n"
            "RestartSec=1\\n"
        )
        self.sudo_run_cmd(
            f"sh -c 'printf \"%b\" \"{content}\" > {self.LOOP_UNIT}'",
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd("systemctl daemon-reload", timeout=30, out_debug_flag=False)
        self.sudo_run_cmd(
            f"systemctl start {self.LOOP_NAME}",
            timeout=30,
            out_debug_flag=False,
        )
        sleep(8)
        restarts = self.run_cmd(
            f"systemctl show {self.LOOP_NAME} -p NRestarts --value",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        return restarts.isdigit() and int(restarts) >= 5

    def cleanup_service_restart(self):
        """停止并删除重启循环探测单元"""
        self.sudo_run_cmd(
            f"systemctl stop {self.LOOP_NAME} 2>/dev/null",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(f"rm -f {self.LOOP_UNIT}", timeout=10, out_debug_flag=False)
        self.sudo_run_cmd("systemctl daemon-reload", timeout=30, out_debug_flag=False)

    # ------------------------------------------------ 频繁崩溃异常(P1/5)
    def setup_coredump_abnormal(self) -> bool:
        """构造频繁崩溃检测异常: 把 core_pattern 改为非 systemd-coredump

        高负载时 sudo 子进程偶发未落盘(写入被中断), 因此写入后校验并重试。
        """
        self.core_pattern = self.run_cmd(
            "cat /proc/sys/kernel/core_pattern",
            timeout=5,
            out_debug_flag=False,
        ).strip()
        current = self.core_pattern
        for _ in range(3):
            self.sudo_run_cmd(
                "sh -c \"printf '%s\\n' '/tmp/pcm067-core.%p' "
                "> /proc/sys/kernel/core_pattern\"",
                timeout=30,
                out_debug_flag=False,
            )
            current = self.run_cmd(
                "cat /proc/sys/kernel/core_pattern",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            if current and current != self.core_pattern:
                return True
            sleep(1)
        raise AssertionError(
            f"coredump 构造失败: 备份={self.core_pattern!r} 当前={current!r}"
        )

    def cleanup_coredump(self):
        """恢复 core_pattern 原始值(不接受测试残留值)"""
        pattern = getattr(self, "core_pattern", "")
        if not pattern or "pcm067" in pattern:
            pattern = self.CORE_PATTERN_DEFAULT
        self.sudo_run_cmd(
            f"sh -c \"printf '%s\\n' '{pattern}' > /proc/sys/kernel/core_pattern\"",
            timeout=30,
            out_debug_flag=False,
        )

    # ------------------------------------------------ 仓库地址异常(P1/5)
    def setup_repository_url_abnormal(self) -> bool:
        """构造仓库地址异常: sources.list 追加不可达地址

        不可达地址让 lastore 的 update_source job 失败, detectRepositoryURL
        判为异常。该构造会在断言后立即清理, 避免 180s 的 job 超时拖慢全面检测。
        """
        # 幂等: 先解锁(可能被其它用例/上轮残留设成 immutable), 再清残留
        self.sudo_run_cmd(
            f"chattr -i {self.SOURCES_LIST}",
            timeout=30,
            out_debug_flag=False,
        )
        self.cleanup_repository_url()
        self.sudo_run_cmd(
            f"sh -c \"printf '%s\\n' '{self.REPO_LINE}' >> {self.SOURCES_LIST}\"",
            timeout=10,
            out_debug_flag=False,
        )
        count = self.run_cmd(
            f"grep -c '192.0.2.1/pcm067' {self.SOURCES_LIST}",
            timeout=5,
            out_debug_flag=False,
        ).strip()
        if not (count.isdigit() and int(count) >= 1):
            tail = self.run_cmd(
                f"tail -2 {self.SOURCES_LIST}; lsattr {self.SOURCES_LIST}",
                timeout=5,
                out_debug_flag=False,
            )
            raise AssertionError(f"repository_url 构造失败: grep={count!r} tail={tail!r}")
        return True

    def cleanup_repository_url(self):
        """删除前置追加的不可达源(先解锁, 否则 sed -i 静默失败)"""
        self.sudo_run_cmd(
            f"chattr -i {self.SOURCES_LIST}",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"sed -i '/pcm067/d' {self.SOURCES_LIST}",
            timeout=10,
            out_debug_flag=False,
        )

    # ------------------------------------------------ 仓库权限异常(P1/5)
    def setup_repository_permission_abnormal(self) -> bool:
        """构造仓库权限异常: 给 /etc/apt/sources.list 加 immutable 属性"""
        self.sudo_run_cmd(
            f"chattr +i {self.SOURCES_LIST}",
            timeout=30,
            out_debug_flag=False,
        )
        for _ in range(3):
            attrs = self.run_cmd(
                f"lsattr {self.SOURCES_LIST} 2>/dev/null",
                timeout=5,
                out_debug_flag=False,
            ).strip()
            if attrs and "i" in attrs.split()[0]:
                return True
            sleep(1)
        raise AssertionError(f"repository_permission 构造失败: lsattr={attrs!r}")

    def cleanup_repository_permission(self):
        """清除 sources.list 的 immutable 属性"""
        self.sudo_run_cmd(
            f"chattr -i {self.SOURCES_LIST}",
            timeout=10,
            out_debug_flag=False,
        )

    # ------------------------------------------------ ssh 密钥异常(P2/2)
    def get_ssh_dir_owner(self) -> str:
        """读取 ~/.ssh 的属主用户名"""
        return self.run_cmd(
            f"stat -c %U {self.SSH_DIR} 2>/dev/null",
            timeout=5,
            out_debug_flag=False,
        ).strip()

    def has_ssh_private_key(self) -> bool:
        """~/.ssh 下是否存在产品识别的私钥文件"""
        output = self.run_cmd(
            f"ls {self.SSH_DIR} 2>/dev/null "
            "| grep -xE 'id_rsa|id_dsa|id_ecdsa|id_ed25519|identity'",
            timeout=5,
            out_debug_flag=False,
        )
        return (output or "").strip() != ""

    def setup_ssh_key_permission_abnormal(self) -> bool:
        """构造 ssh 密钥检测异常: sudo chown root:root ~/.ssh

        产品仅在 ~/.ssh 存在私钥时才汇总权限结论, 缺少时先生成临时私钥。
        """
        self.created_ssh_key = False
        if not self.has_ssh_private_key():
            self.run_cmd(
                f"ssh-keygen -t ed25519 -N '' -f {self.SSH_DIR}/id_ed25519 -q",
                timeout=30,
                out_debug_flag=False,
            )
            self.created_ssh_key = True
        self.sudo_run_cmd(
            f"chown root:root {self.SSH_DIR}",
            timeout=10,
            out_debug_flag=False,
        )
        return self.get_ssh_dir_owner() == "root"

    def cleanup_ssh_key_permission(self):
        """恢复 ~/.ssh 属主, 并删除前置构造的临时私钥"""
        user = self.run_cmd("id -un", timeout=5, out_debug_flag=False).strip()
        group = self.run_cmd("id -gn", timeout=5, out_debug_flag=False).strip()
        self.sudo_run_cmd(
            f"chown {user}:{group} {self.SSH_DIR}",
            timeout=10,
            out_debug_flag=False,
        )
        if getattr(self, "created_ssh_key", False):
            self.run_cmd(
                f"rm -f {self.SSH_DIR}/id_ed25519 {self.SSH_DIR}/id_ed25519.pub",
                timeout=10,
                out_debug_flag=False,
            )

    # ------------------------------------------------ 时间配置异常(P2/2)
    def setup_time_config_abnormal(self) -> bool:
        """构造时间配置异常: 停止 systemd-timesyncd(保持 enabled)"""
        self.sudo_run_cmd(
            "systemctl stop systemd-timesyncd",
            timeout=30,
            out_debug_flag=False,
        )
        return self.run_cmd(
            "systemctl is-active systemd-timesyncd",
            timeout=10,
            out_debug_flag=False,
        ).strip() != "active"

    def cleanup_time_config(self):
        """重新启动 systemd-timesyncd"""
        self.sudo_run_cmd(
            "systemctl start systemd-timesyncd",
            timeout=30,
            out_debug_flag=False,
        )

    # ------------------------------------------------ hosts 文件异常(P2/2)
    def setup_hosts_file_abnormal(self) -> bool:
        """构造 hosts 文件异常: 追加一行无 IP 的非法条目"""
        self.sudo_run_cmd(
            f"sh -c \"printf '%s\\n' '{self.HOSTS_MARK}' >> {self.HOSTS_FILE}\"",
            timeout=10,
            out_debug_flag=False,
        )
        return self.run_cmd(
            f"grep -c '^{self.HOSTS_MARK}$' {self.HOSTS_FILE}",
            timeout=5,
            out_debug_flag=False,
        ).strip() == "1"

    def cleanup_hosts_file(self):
        """删除前置追加的 hosts 条目"""
        self.sudo_run_cmd(
            f"sed -i '/^{self.HOSTS_MARK}$/d' {self.HOSTS_FILE}",
            timeout=10,
            out_debug_flag=False,
        )

    # ------------------------------------------------ 声卡异常(P1/5)
    def setup_sound_card_abnormal(self) -> bool:
        """构造声卡检测异常: 临时移走 aplay

        detectSoundCard 依赖 `aplay -l`; 命令缺失时返回 ServiceUnavailable
        ("aplay.not.installed") 即异常。用例结束移回。
        """
        self.sudo_run_cmd(
            f"sh -c 'test -e {self.APLAY} && mv -f {self.APLAY} {self.APLAY_BAK}'",
            timeout=10,
            out_debug_flag=False,
        )
        return self.run_cmd(
            f"test ! -e {self.APLAY} && test -e {self.APLAY_BAK} && echo yes",
            timeout=5,
            out_debug_flag=False,
        ).strip() == "yes"

    def cleanup_sound_card(self):
        """移回 aplay"""
        self.sudo_run_cmd(
            f"sh -c 'test -e {self.APLAY_BAK} && mv -f {self.APLAY_BAK} {self.APLAY}'",
            timeout=10,
            out_debug_flag=False,
        )

    # ------------------------------------------------ DNS 异常(P1/5, net_svc 组)
    def setup_dns_abnormal(self) -> bool:
        """构造 DNS 异常: resolv.conf 只保留不可达的 nameserver

        detectDNS 以真实解析为准, 全部 nameserver 解析失败且首选服务器不可 ping
        时判 NetworkDnsUnreachable。192.0.2.1 属 TEST-NET-1, 保证不可达。
        """
        self.sudo_run_cmd(
            f"cp -f {self.RESOLV_CONF} {self.RESOLV_BAK}",
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"sh -c \"printf 'nameserver 192.0.2.1\\n' > {self.RESOLV_CONF}\"",
            timeout=10,
            out_debug_flag=False,
        )
        return self.run_cmd(
            f"grep -c '^nameserver 192.0.2.1$' {self.RESOLV_CONF}",
            timeout=5,
            out_debug_flag=False,
        ).strip() == "1"

    def cleanup_dns(self):
        """恢复 resolv.conf"""
        self.sudo_run_cmd(
            f"sh -c 'test -f {self.RESOLV_BAK} && cp -f {self.RESOLV_BAK} "
            f"{self.RESOLV_CONF}'",
            timeout=10,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(f"rm -f {self.RESOLV_BAK}", timeout=10, out_debug_flag=False)

    # ------------------------------------------------ 本地环境异常(P1/5, repo 组)
    def setup_local_environment_abnormal(self) -> bool:
        """构造本地环境异常: 安装一个 postinst 失败的自制包

        detectLocalEnvironment 以 `dpkg --audit` 输出是否为空判定; postinst 以
        非 0 退出会让包停留在 half-configured, audit 即输出未配置包。
        用例结束 purge 该探针包。
        """
        self.sudo_run_cmd(
            f"rm -rf {self.PROBE_DIR} {self.PROBE_DEB}",
            timeout=10,
            out_debug_flag=False,
        )
        self.run_cmd(f"mkdir -p {self.PROBE_DIR}/DEBIAN", timeout=10, out_debug_flag=False)
        self.run_cmd(
            "sh -c \"printf 'Package: %s\\nVersion: 1.0\\nSection: misc\\n"
            "Priority: optional\\nArchitecture: all\\nMaintainer: test@test\\n"
            "Description: pcm 067 probe\\n' > %s/DEBIAN/control\""
            % (self.PROBE_PKG, self.PROBE_DIR),
            timeout=10,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"sh -c \"printf '#!/bin/sh\\nexit 1\\n' > {self.PROBE_DIR}/DEBIAN/postinst\"",
            timeout=10,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"chmod 755 {self.PROBE_DIR}/DEBIAN/postinst",
            timeout=10,
            out_debug_flag=False,
        )
        self.run_cmd(
            f"dpkg-deb -b {self.PROBE_DIR} {self.PROBE_DEB}",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(f"dpkg -i {self.PROBE_DEB}", timeout=60, out_debug_flag=False)
        audit = self.run_cmd("dpkg --audit", timeout=30, out_debug_flag=False) or ""
        return audit.strip() != ""

    def cleanup_local_environment(self):
        """清除 half-configured 探针包"""
        self.sudo_run_cmd(
            f"dpkg --purge --force-all {self.PROBE_PKG}",
            timeout=60,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"rm -rf {self.PROBE_DIR} {self.PROBE_DEB}",
            timeout=10,
            out_debug_flag=False,
        )

    # ------------------------------------------------ 磁盘空间异常(P1/5)
    def setup_disk_space_abnormal(self) -> bool:
        """构造磁盘空间异常: 用 fallocate 把 / 使用率抬到约 91%(阈值 90)"""
        info = (self.run_cmd(
            "df -k --output=size,used,avail / | tail -1",
            timeout=10,
            out_debug_flag=False,
        ) or "").split()
        if len(info) < 3:
            return False
        total_kb, used_kb = int(info[0]), int(info[1])
        need_kb = int(total_kb * 0.91) - used_kb
        if need_kb <= 0:
            return True
        self.sudo_run_cmd(
            f"fallocate -l {need_kb}K {self.FILL_ROOT}",
            timeout=120,
            out_debug_flag=False,
        )
        usage = self._partition_usage("/")
        log(f"构造后 / 使用率: {usage}%")
        return usage > 90

    def cleanup_disk_space(self):
        """删除根分区填充文件"""
        self.sudo_run_cmd(f"rm -f {self.FILL_ROOT}", timeout=30, out_debug_flag=False)

    # ------------------------------------------------ 引导分区空间异常(P1/5)
    def setup_boot_partition_abnormal(self) -> bool:
        """构造 /boot 空间不足: 填到剩余小于 160MB(V20 阈值)"""
        info = (self.run_cmd(
            "df -k --output=avail /boot | tail -1",
            timeout=10,
            out_debug_flag=False,
        ) or "").split()
        if not info:
            return False
        avail_kb = int(info[0])
        need_kb = avail_kb - 100 * 1024  # 预留 100MB, 低于 160MB 阈值
        if need_kb <= 0:
            return True
        self.sudo_run_cmd(
            f"fallocate -l {need_kb}K {self.FILL_BOOT}",
            timeout=120,
            out_debug_flag=False,
        )
        avail_now = self.run_cmd(
            "df -k --output=avail /boot | tail -1",
            timeout=10,
            out_debug_flag=False,
        ).strip()
        log(f"构造后 /boot 剩余: {avail_now}KB")
        return avail_now.isdigit() and int(avail_now) < 160 * 1024

    def cleanup_boot_partition(self):
        """删除 /boot 填充文件"""
        self.sudo_run_cmd(f"rm -f {self.FILL_BOOT}", timeout=30, out_debug_flag=False)

    # ------------------------------------------------ 内存占用异常(P2/2)
    def setup_memory_abnormal(self) -> bool:
        """构造内存占用异常: tmpfs 写入至使用率超过 80%

        detectMemory 以 MemAvailable 计算使用率, 超过 80% 判异常;
        写入量按 MemTotal 与当前 MemAvailable 动态计算(tmpfs 页直接占内存)。
        """
        fields = self._meminfo()
        total_mb = fields.get("MemTotal", 0) // 1024
        avail_mb = fields.get("MemAvailable", 0) // 1024
        if total_mb <= 0 or avail_mb <= 0:
            return False
        alloc_mb = avail_mb - int(total_mb * 0.10)
        if alloc_mb <= 0:
            return True
        log(f"内存占用构造: 总量 {total_mb}MB, 可用 {avail_mb}MB, 写入 {alloc_mb}MB")
        self.sudo_run_cmd(
            f"umount -l {self.MEM_MOUNT} 2>/dev/null; mkdir -p {self.MEM_MOUNT}",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"mount -t tmpfs -o size={alloc_mb + 256}M tmpfs {self.MEM_MOUNT}",
            timeout=30,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"dd if=/dev/zero of={self.MEM_MOUNT}/fill bs=1M "
            f"count={alloc_mb} status=none",
            timeout=300,
            out_debug_flag=False,
        )
        for _ in range(60):
            usage = self._memory_usage()
            if usage > 80:
                log(f"构造后内存使用率: {usage}%")
                return True
            sleep(1)
        log(f"内存使用率未达标: {self._memory_usage()}%")
        return False

    def cleanup_memory(self):
        """释放内存占用 tmpfs"""
        self.sudo_run_cmd(
            f"rm -f {self.MEM_MOUNT}/fill",
            timeout=60,
            out_debug_flag=False,
        )
        self.sudo_run_cmd(
            f"umount -l {self.MEM_MOUNT} 2>/dev/null; rmdir {self.MEM_MOUNT} 2>/dev/null",
            timeout=60,
            out_debug_flag=False,
        )

    # ------------------------------------------------ 环境读取
    def _partition_usage(self, mount_point: str) -> int:
        """读取挂载点使用率(百分比)"""
        output = (self.run_cmd(
            f"df -k --output=pcent {mount_point} | tail -1",
            timeout=10,
            out_debug_flag=False,
        ) or "").replace("%", "").strip()
        return int(output) if output.isdigit() else -1

    def _meminfo(self) -> dict:
        """解析 /proc/meminfo 前 3 行(MemTotal/MemFree/MemAvailable), 单位 KB

        内存被占满时 fork 子进程会因换页极慢甚至超时, 因此直接读文件。
        """
        fields = {}
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as fp:
                lines = [next(fp) for _ in range(3)]
        except (OSError, StopIteration):
            return fields
        for line in lines:
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                fields[parts[0].rstrip(":")] = int(parts[1])
        return fields

    def _memory_usage(self) -> int:
        """按 MemAvailable 计算内存使用率(百分比)"""
        fields = self._meminfo()
        total = fields.get("MemTotal", 0)
        avail = fields.get("MemAvailable", 0)
        if total <= 0:
            return -1
        return 100 - (avail * 100 // total)

    # ------------------------------------------------ 检测流程
    def wait_for_scan_progress(self, timeout=15) -> bool:
        """等待检测进度出现(扫描已开始)

        实测(deepin-pc-manager V20): detection_progress 的 showing 恒为 False,
        元素存在性也无区分度(QML 隐藏页元素常驻 AT-SPI 树); 只有 size 非零
        才表示当前处于扫描运行态。
        """
        for _ in range(timeout):
            if self._any_visible("$//detection_progress"):
                return True
            sleep(1)
        return False

    def wait_for_scan_started(self, timeout=20) -> bool:
        """等待全面检测进入运行态

        检测可能在 1 秒内完成, 此时直接由结果态判定"已执行"。
        两者皆无说明点击未触发检测, 用例必须失败而不是空等。
        """
        result_exprs = (
            "$//detection_resultTitle",
            "$//detection_resultDesc",
            "$//detection_issuesIcon",
            "$//detection_noProblemPage",
        )
        for _ in range(timeout):
            if self._any_visible("$//detection_progress"):
                return True
            if self._any_visible(*result_exprs):
                return True
            sleep(1)
        return False

    def get_last_detection_score(self):
        """读取"上次检测分数"数值, 读不到返回 None

        V20 的分数标签是 RichText, AT-SPI 取不到文本; 数值以产品配置
        Detection/lastScore 为准, 它与标签在同一处写入(detection_page.cpp)。
        """
        match = re.search(r"(\d{1,3})", self.get_detection_score_text() or "")
        if match:
            return int(match.group(1))
        conf_path = os.path.expanduser("~/.config/deepin-pc-manager/deepin-pc-manager.conf")
        try:
            with open(conf_path, "r", encoding="utf-8", errors="replace") as fp:
                content = fp.read()
        except OSError:
            return None
        section = re.search(r"\[Detection\](.*?)(?=\n\[|\Z)", content, re.S)
        match = re.search(r"lastScore\s*=\s*(-?\d+)", section.group(1) if section else content)
        return int(match.group(1)) if match else None


class TestMyCase(BaseCase):

    def test_mycase_067(self):
        """系统检测首页--扣分总和超 100 溢出

        前置条件: 所有 P0/P1/P2 项全部异常
        构造的异常(检测项/优先级/扣分):
          critical_libraries P0 10 -- /usr/local/lib 同名库哈希不同
          core_packages      P0 10 -- libc6 包内文件被改动
          backup_partition   P1  6 -- 卸载 /recovery
          file_permissions   P1  5 -- /etc/passwd 增加组/其他写位
          service_syntax     P1  5 -- Type=oneshot 搭配 Restart=always
          service_restarts   P1  5 -- 崩溃循环 unit, NRestarts >= 5
          coredump           P1  5 -- core_pattern 非 systemd-coredump
          repository_permission P1 5 -- sources.list 加 immutable
          disk_space         P1  5 -- fallocate 把 / 使用率抬到 90% 以上
          boot_partition_space P1 5 -- /boot 剩余小于 160MB
          sound_card         P1  5 -- 移走 aplay
          dns                P1  5 -- resolv.conf 只留不可达 nameserver(net_svc 组)
          local_environment  P1  5 -- half-configured 探针包(repo 组)
          ssh_key            P2  2 -- chown root:root ~/.ssh
          time_config        P2  2 -- 停止 systemd-timesyncd
          hosts_file         P2  2 -- /etc/hosts 非法条目
          memory             P2  2 -- tmpfs 写入使内存使用率超 80%
          repository_url     P1  5 -- 追加不可达源(断言后立即清理, 避免 job 超时)
        构造但结论不可前置校验(只记录结论, 不作前置断言):
          repository_url    -- 结论依赖 lastore update_source job(可达 180s),
                               60s 内 D-Bus 取不到结果
          local_environment -- V20 会话守护进程以普通用户运行, dpkg --audit
                               因权限不足只输出到 stderr, 产品恒判正常
        仍无法构造(无硬件/需断网): disk_health、battery_health、cpu_temperature、
        network_hardware、network_settings、dhcp_service、ip_conflict、fd_usage,
        这些项只记录结论, 不作前置断言。

        步骤: 启动电脑管家, 点击全面检测后点击返回
        预期: 上次检测分数显示, 评分不溢出(0-100, 不为负数)
        """
        widget = DetectionWidget(check_start=False)
        run_lock = widget.acquire_exclusive_run_lock()
        if run_lock is None:
            raise unittest.SkipTest(
                "test_mycase_067 已在执行中: 检测类用例共享系统级构造, 不支持并发"
            )
        # 用例一开始就启动电脑管家: 前置构造依赖系统与 D-Bus 状态, 不依赖界面,
        # 但界面需全程存在, 便于观察与后续 UI 断言(与同目录用例保持一致)。
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        try:
            setups = (
                ("repository_url", widget.setup_repository_url_abnormal),
                ("repository_permission", widget.setup_repository_permission_abnormal),
                ("critical_libraries", widget.setup_critical_library_conflict),
                ("core_packages", widget.setup_core_package_corruption),
                ("file_permissions", widget.setup_file_permission_abnormal),
                ("service_syntax", widget.setup_service_syntax_abnormal),
                ("service_restarts", widget.setup_service_restart_abnormal),
                ("coredump", widget.setup_coredump_abnormal),
                ("ssh_key", widget.setup_ssh_key_permission_abnormal),
                ("time_config", widget.setup_time_config_abnormal),
                ("hosts_file", widget.setup_hosts_file_abnormal),
                ("sound_card", widget.setup_sound_card_abnormal),
                ("dns", widget.setup_dns_abnormal),
                ("local_environment", widget.setup_local_environment_abnormal),
                ("disk_space", widget.setup_disk_space_abnormal),
                ("boot_partition_space", widget.setup_boot_partition_abnormal),
                ("backup_partition", widget.setup_backup_partition_abnormal),
                ("memory", widget.setup_memory_abnormal),
            )
            for detection_id, setup in setups:
                if not setup():
                    log(f"{detection_id} 前置构造失败")
                    raise AssertionError(f"{detection_id} 前置构造失败")
            # 前置生效校验: 除以下两项外, 已构造的检测项都应给出异常结论
            #   repository_url: 结论依赖 lastore update_source job(可达 180s),
            #                   60s 内取不到 D-Bus 结果; 构造保留, 仅记录结论
            #   local_environment: V20 会话守护进程以普通用户运行,
            #                   dpkg --audit 因权限不足只报 stderr, 产品恒判正常
            unverifiable = {"repository_url", "local_environment"}
            failed_checks = []
            for detection_id, _ in setups:
                if detection_id in unverifiable:
                    continue
                verdict, detail = widget.get_detection_item_verdict(detection_id)
                log(f"{detection_id} 检测结论: ok={verdict} detail={detail}")
                if verdict is not False:
                    failed_checks.append(f"{detection_id}(ok={verdict})")
            if failed_checks:
                raise AssertionError("未判异常: " + ", ".join(failed_checks))
            # 不可达源会让 lastore 的 update_source job 跑满 180s, 断言后立即清理;
            # 此时 sources.list 处于 immutable 状态, 需先解锁, 删行后再恢复
            widget.cleanup_repository_permission()
            widget.cleanup_repository_url()
            widget.setup_repository_permission_abnormal()
            # 其它项仅记录结论(需断网/无硬件/不可构造)
            for detection_id in (
                "repository_url", "local_environment",
                "disk_health", "battery_health", "cpu_temperature",
                "network_hardware", "network_settings", "dhcp_service",
                "ip_conflict", "fd_usage", "network_connectivity", "system_version",
            ):
                verdict, detail = widget.get_detection_item_verdict(detection_id)
                log(f"{detection_id} 参考结论: ok={verdict} detail={detail}")
            widget.kill_pc_manager()
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            if not widget.get_detection_page_showing(timeout=5):
                widget.click_detection_nav_by_attr()
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            self.assert_true(widget.get_detection_score_card_showing())
            self.assert_true(widget.get_detection_full_scan_button_showing())
            # 执行全面检测
            widget.click_detection_full_scan_button()
            # assert_true 不接受消息参数, 检测未执行时断言即为失败依据
            self.assert_true(widget.wait_for_scan_started(timeout=20))
            self.assert_true(widget.wait_for_full_scan_completion(timeout=300))
            widget.click_back_button()
            sleep(2)
            self.assert_true(widget.get_detection_page_showing(timeout=15))
            self.assert_true(widget.get_last_score_displayed(timeout=15))
            # 预期: 评分不溢出(0-100, 不为负数)
            score = widget.get_last_detection_score()
            log(f"上次检测分数: {score}")
            self.assert_true(score is not None and 0 <= score <= 100)
        finally:
            widget.kill_pc_manager()
            widget.cleanup_memory()
            widget.cleanup_disk_space()
            widget.cleanup_boot_partition()
            widget.cleanup_local_environment()
            widget.cleanup_dns()
            widget.cleanup_sound_card()
            widget.cleanup_service_restart()
            widget.cleanup_hosts_file()
            widget.cleanup_time_config()
            widget.cleanup_ssh_key_permission()
            widget.cleanup_coredump()
            widget.cleanup_service_syntax()
            widget.cleanup_file_permission()
            widget.cleanup_backup_partition()
            widget.cleanup_core_package_corruption()
            widget.cleanup_critical_library_conflict()
            widget.cleanup_repository_permission()
            widget.cleanup_repository_url()

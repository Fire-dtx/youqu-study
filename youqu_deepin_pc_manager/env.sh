#!/bin/bash
# SPDX-FileCopyrightText: 2023 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
export PIPENV_VERBOSITY=-1
ROOT_DIR=$(dirname $(realpath "${BASH_SOURCE[0]}"))
tag=$(echo "$(cat ${ROOT_DIR}/CURRENT | grep "tag = ")" | cut -d "=" -f2 | python3 -c "s=input();print(s.strip())")
config_pwd=$(cat ${ROOT_DIR}/setting/globalconfig.ini | grep -v "CLIENT_PASSWORD" | grep "PASSWORD = ")
PASSWORD=$(echo "${config_pwd}" | cut -d "=" -f2 | python3 -c "s=input();print(s.strip())")
IP=$(hostname -I)
DEV=false
while getopts ":p:D" opt
do
    case $opt in
        p)
            PASSWORD=$OPTARG
            ;;
        D)
            DEV=true
            ;;
        ?)
            echo -e " 参数说明:\
            \n\t-p password 指定密码, 如: bash env.sh -p xxx
            \n\t-D 开发环境部署, 如: bash env.sh -D
            "
            exit 1
            ;;
    esac
done

debian_platform=false
yq=apt
if command -v apt &> /dev/null; then
    debian_platform=true
    yq=apt
else
    yq=yum
fi

DISPLAY_SERVER=$(cat ${HOME}/.xsession-errors | grep XDG_SESSION_TYPE | head -n 1 | cut -d "=" -f2)
if [ "${DISPLAY_SERVER}" = "" ]; then
    ps -ef | grep -v grep | grep kwin_x11
    [ $? = 0 ] && DISPLAY_SERVER=x11 || DISPLAY_SERVER=wayland
fi
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
whitelist="/usr/share/deepin-elf-verify/whitelist"
pypi_mirror="https://pypi.tuna.tsinghua.edu.cn/simple"

# sudo 免交互：脚本常在 nohup/无 tty 下执行，sudo 时间戳过期后（默认 15 分钟）
# 后续 sudo 会因 "no tty present" 失败；统一改为从 PASSWORD 取密码。
sudo() { printf '%s\n' "${PASSWORD}" | command sudo -S -p '' "$@"; }
export -f sudo 2>/dev/null || true

echo "${PASSWORD}" | command sudo -S su > /dev/null 2>&1

# ---------------------------------------------------------------- apt 源配置
_sudo_pass() { printf '%s\n' "${PASSWORD}" | sudo -S "$@"; }

# 源配置逻辑统一由公共模块提供（env.sh 与 deploy_pc_manager.sh 共用），
# 保证部署脚本在装包前就能用上与系统版本匹配的源。
APT_SRC_SUDO_CMD="_sudo_pass"
source "${ROOT_DIR}/src/utils/apt_sources.sh"

# ---------------------------------------------------------------- 版本源配置
# 按系统发行版写入 /etc/apt/sources.list 的实现在 src/utils/apt_sources.sh
# （V20=eagle，V25=snipe）。写入前备份，但**退出不还原**：测试机需要保持
# 与系统版本匹配的源，否则「系统版本检测」等用例会因 lastore 源任务失败
# 而判定异常。原始配置保留在 /var/backups/youqu-apt-sources/*.orig 与
# *.youqu.bak，可人工回滚。

# 由 deploy_pc_manager.sh 调用时, 备份由外层脚本负责; 此处仍按系统
# 版本写入对应软件源(部署期间 apt 需要正确的 V20/V25 源), 外层同样不恢复。
if [ "${PCM_APT_SOURCES_ISOLATED:-0}" = "1" ]; then
    echo -e "apt源\t外层部署脚本已写入版本源(不做还原)"
    ensure_apt_sources_active || true
    apply_release_apt_sources
else
    ensure_apt_sources_active || true
    apply_release_apt_sources
    isolate_v25_sources
fi

if [ ! -f "$HOME/.Xauthority" ]; then
        touch $HOME/.Xauthority
fi

if [ "${DEV}" = "true" ]; then
    source ./src/utils/env_dev.sh
else
    source ./src/utils/env_vir.sh
fi

bash ${ROOT_DIR}/src/utils/env_polkit.sh -p "${PASSWORD}" || echo -e "polkit\t预授权未生效(见上方输出), 检测/修复类用例可能因鉴权被拒而失败"

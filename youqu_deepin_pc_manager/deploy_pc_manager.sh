#!/bin/bash
# SPDX-FileCopyrightText: 2024 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
#
# deepin-pc-manager 一键部署脚本（供 youqu_deepin_pc_manager 测试工程使用）
#
# 流程：
#   1. 安装编译依赖（V20: Qt5/DTK5；V25: Qt6/DTK6 自动识别）
#      V20 测试机上的 Qt5/DTK5 运行时为 +sign 版本、仓库 dev 包版本不匹配，
#      apt 无法直接安装；脚本改为解包 dev 包（头文件/CMake 配置）到 /usr，
#      不注册 dpkg 依赖，避免降级系统运行时。
#   2. 拉取 deepin-pc-manager 源码（Gerrit，运行时交互输入用户名/密码）
#   3. dpkg-buildpackage 打包
#   4. 安装 deb 并校验可执行文件
#   5. 配置测试环境（polkit 策略权限、youqu 虚拟环境）
#
# 用法：
#   bash deploy_pc_manager.sh [-r URL] [-b 分支] [-t 标签] [-c 提交] [-d 源码目录]
#                             [-u 用户名] [-p sudo密码] [-j 并行数] [-kne]
#
#   默认仓库：https://gerrit.uniontech.com/deepin-pc-manager
#   默认分支：develop/refactor（构建该分支最新提交）
#   默认源码目录：$HOME/deepin-pc-manager-src
#
# 说明：
#   - 不要以 root 运行；sudo 密码默认读取 setting/globalconfig.ini 的 PASSWORD。
#   - Gerrit 用户名/密码在脚本运行时交互输入，密码不回显；凭据写入权限 600
#     的临时 credential 文件，退出即删除，不写入 remote URL/仓库配置。
#   - 自动化场景可预先导出 PCM_GIT_USER / PCM_GIT_PASSWORD / PCM_SUDO_PASSWORD。

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GERRIT_URL="${PCM_GERRIT_URL:-https://gerrit.uniontech.com/deepin-pc-manager}"
BRANCH="develop/refactor"
TAG=""
# 默认跟踪 develop/refactor 最新提交；-c 可固定提交，-t 可指定标签。
COMMIT="${PCM_COMMIT:-}"
SRC_DIR="${HOME}/deepin-pc-manager-src"
GIT_USER="${PCM_GIT_USER:-}"
GIT_PASS="${PCM_GIT_PASSWORD:-}"
SUDO_PASS="${PCM_SUDO_PASSWORD:-}"
JOBS="$(nproc 2>/dev/null || echo 2)"
NO_GIT=0
SKIP_ENV=0
FORCE_ENV=0
APT_UPDATE=1
APP_FROM_APT=0
PYPI_MIRROR="${PCM_PYPI_MIRROR:-https://pypi.tuna.tsinghua.edu.cn/simple}"

info() { printf '\033[32m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[deploy]\033[0m %s\n' "$*"; }
err()  { printf '\033[31m[deploy]\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

usage() {
    cat <<'EOF'
用法: bash deploy_pc_manager.sh [选项]

  -r <url>     Gerrit 仓库地址（默认 https://gerrit.uniontech.com/deepin-pc-manager）
  -b <branch>  分支（默认 develop/refactor；指定后构建该分支最新提交）
  -t <tag>     标签（指定后忽略提交/分支）
  -c <commit>  固定提交（默认构建 develop/refactor 最新提交）
  -d <dir>     源码目录（默认 $HOME/deepin-pc-manager-src）
  -u <user>    Gerrit 用户名（默认运行时交互输入）
  -p <pass>    sudo 密码（默认读取 setting/globalconfig.ini 的 PASSWORD）
  -j <n>       并行编译数（默认 CPU 核数）
  -k           跳过源码拉取，使用 -d 指定的现有源码
  -n           跳过 youqu 测试环境（env.sh）部署
  -e           强制重新执行 env.sh（默认 .venv 存在则跳过）
  -U           跳过 apt-get update
  -A           直接从系统仓库安装 deepin-pc-manager（固定 1.0.10，不推荐）
  -h           显示本帮助

V20 测试机会自动解包 Qt5/DTK5 开发包（qtbase5-dev、libdtkcore-dev 等）到
/usr，绕开 +sign 运行时与仓库 dev 包的版本约束；g++ 元包按 8.3 版本降级安装。
源码构建失败时不再回退系统仓库（仓库版本 1.0.10，低于源码版本）。

运行时交互输入的 Gerrit 密码不回显；凭据写入权限 600 的临时 credential 文件，
退出即删除，不写入 git remote。
自动化可用环境变量 PCM_GIT_USER / PCM_GIT_PASSWORD / PCM_SUDO_PASSWORD。
EOF
    exit 0
}

while getopts ":r:b:t:c:d:u:p:j:knehUA" opt; do
    case "${opt}" in
        r) GERRIT_URL="${OPTARG}" ;;
        b) BRANCH="${OPTARG}"; COMMIT="" ;;
        t) TAG="${OPTARG}"; COMMIT="" ;;
        c) COMMIT="${OPTARG}" ;;
        d) SRC_DIR="${OPTARG}" ;;
        u) GIT_USER="${OPTARG}" ;;
        p) SUDO_PASS="${OPTARG}" ;;
        j) JOBS="${OPTARG}" ;;
        k) NO_GIT=1 ;;
        n) SKIP_ENV=1 ;;
        e) FORCE_ENV=1 ;;
        U) APT_UPDATE=0 ;;
        A) APP_FROM_APT=1 ;;
        h) usage ;;
        ?) err "未知参数: -${OPTARG}"; usage ;;
    esac
done

[ "$(id -u)" -eq 0 ] && die "不要以 root 用户执行本脚本"

# ---------------------------------------------------------------- sudo
init_sudo() {
    if [ -z "${SUDO_PASS}" ]; then
        SUDO_PASS="$(grep -E '^PASSWORD[[:space:]]*=' "${ROOT_DIR}/setting/globalconfig.ini" 2>/dev/null \
            | grep -v CLIENT_PASSWORD | tail -n1 | cut -d '=' -f2 | tr -d '[:space:]')"
    fi
    if [ -z "${SUDO_PASS}" ]; then
        [ -t 0 ] || die "需要 sudo 密码，请用 -p 指定"
        read -r -s -p "请输入 sudo 密码: " SUDO_PASS
        echo
    fi
    printf '%s\n' "${SUDO_PASS}" | sudo -S -v >/dev/null 2>&1 || die "sudo 密码校验失败"
    info "sudo 权限就绪"
}

sudo_run() { printf '%s\n' "${SUDO_PASS}" | sudo -S "$@"; }

# ---------------------------------------------------------------- apt 源配置
# 源写入与隔离逻辑由 src/utils/apt_sources.sh 提供（env.sh 共用同一实现）。
# 构建期先写入与本机版本匹配的源（V20=eagle / V25=snipe），再隔离
# sources.list.d 中不匹配的 V25 源。写入后的源**保持生效**、退出不还原：
# 测试机需要正确的源才能通过「系统版本检测」等用例；原始配置已备份到
# /var/backups/youqu-apt-sources/*.orig 与 *.youqu.bak，可人工回滚。
APT_SRC_SUDO_CMD=sudo_run
source "${ROOT_DIR}/src/utils/apt_sources.sh"

# ---------------------------------------------------------------- git 认证
SCRIPT_TMP=""
GIT_CRED_ARGS=()
cleanup() {
    [ -n "${SCRIPT_TMP}" ] && rm -f "${SCRIPT_TMP}"
    unset PCM_GIT_PASSWORD GIT_ASKPASS 2>/dev/null || true
    # 不调用 restore_apt_sources：按系统版本写入的源保持生效，
    # 否则部署完测试机仍是错误源（V25 源装在 V20 上），
    # 系统版本检测等用例必然不通过。备份保留，可人工回滚。
}
trap cleanup EXIT INT TERM

_urlencode() {
    python3 -c 'import sys, urllib.parse; sys.stdout.write(urllib.parse.quote(sys.argv[1], safe=""))' "$1" 2>/dev/null \
        || printf '%s' "$1"
}

init_git_auth() {
    # Gerrit 允许匿名只读拉取：无凭据且非交互时按匿名方式继续
    if [ -z "${GIT_USER}" ] && [ -z "${GIT_PASS}" ] && [ ! -t 0 ]; then
        info "未提供 Gerrit 凭据，按匿名方式拉取源码"
        export GIT_TERMINAL_PROMPT=0
        return 0
    fi
    if [ -z "${GIT_USER}" ]; then
        [ -t 0 ] || die "需要 Gerrit 用户名，请用 -u 指定"
        read -r -p "Gerrit 用户名: " GIT_USER
    fi
    if [ -z "${GIT_PASS}" ]; then
        [ -t 0 ] || die "需要 Gerrit 密码，请导出 PCM_GIT_PASSWORD"
        read -r -s -p "Gerrit 密码: " GIT_PASS
        echo
    fi
    [ -n "${GIT_USER}" ] && [ -n "${GIT_PASS}" ] || die "用户名/密码不能为空"

    # Git 2.20(测试机) 在 401 后重试时对 ASKPASS 提供的用户名处理异常，
    # 表现为 remote: Unauthorized；改用 credential store 文件（600，退出删除）。
    local host
    host="$(printf '%s' "${GERRIT_URL}" | sed -E 's#^[a-zA-Z]+://([^/]+).*#\1#')"
    SCRIPT_TMP="$(mktemp /tmp/pcm_cred.XXXXXX)"
    chmod 600 "${SCRIPT_TMP}"
    printf 'https://%s:%s@%s\n' "$(_urlencode "${GIT_USER}")" "$(_urlencode "${GIT_PASS}")" "${host}" >"${SCRIPT_TMP}"
    GIT_CRED_ARGS=(-c "credential.helper=store --file=${SCRIPT_TMP}")
    export PCM_GIT_USER="${GIT_USER}" PCM_GIT_PASSWORD="${GIT_PASS}"
    export GIT_TERMINAL_PROMPT=0
    info "已配置 Gerrit 认证（临时凭据文件 600，退出即删）"
}

# ---------------------------------------------------------------- 依赖
APT_LOG="/tmp/deploy_pcm_apt.log"
apt_install() {
    local spec="$1" name="${1%%=*}"
    if dpkg -s "${name}" >/dev/null 2>&1; then
        info "依赖已安装: ${name}"
        return 0
    fi
    info "安装依赖: ${spec}"
    if sudo_run env DEBIAN_FRONTEND=noninteractive apt-get install -y "${spec}" >"${APT_LOG}" 2>&1; then
        return 0
    fi
    err "安装失败: ${spec}"
    tail -n 6 "${APT_LOG}"
    return 1
}

# ---------------------------------------------------------------- V20 开发文件
# UOS 20 测试机上的 Qt5/DTK5 运行时是 +sign 版本（如 libqt5core5a 5.11.3.81），
# 仓库里的 dev 包（5.11.3.42/DTK5.6.x）依赖精确同版本运行时，apt 会拒绝安装。
# 这里把 dev 包（头文件 + CMake 配置 + .so 链接）直接解包到 /usr，不注册 dpkg
# 依赖，避免把系统 Qt/DTK 降级；补丁级 ABI 兼容，可正常链接现有运行时。
DEV_WORK="/tmp/deploy_pcm_dev"

unpack_dev_pkg() {
    local pkg="$1"
    local dir="${DEV_WORK}/${pkg}" deb
    mkdir -p "${dir}"
    info "解包开发包: ${pkg}"
    if ! ( cd "${dir}" && apt-get download "${pkg}" >/dev/null 2>&1 ); then
        err "下载开发包失败: ${pkg}"
        return 1
    fi
    deb="$(ls -t "${dir}"/"${pkg}"_*.deb 2>/dev/null | head -n1)"
    [ -n "${deb}" ] || { err "未找到开发包文件: ${pkg}"; return 1; }
    # dpkg-deb -x 把文件属主记为执行用户；非 root 解包后 cp -a 到 /usr 会
    # 原样保留该属主, 把系统目录写成普通用户所有。改为以 root 解包。
    # (--root-owner-group 只对打包生效, 不能用于解包。)
    if ! sudo_run dpkg-deb -x "${deb}" "${dir}/root"; then
        err "解包失败: ${pkg}"
        return 1
    fi
    if ! sudo_run cp -a "${dir}/root/usr/." /usr/; then
        err "部署开发文件失败: ${pkg}"
        return 1
    fi
    return 0
}

# dev 包 CMake 配置引用的 soname 与系统实际库不一致时补兼容链接（不替换运行时库）
fix_dev_soname_links() {
    local lib_dir="/usr/lib/x86_64-linux-gnu"
    local name ref base major real
    while read -r name; do
        ref="${lib_dir}/${name}"
        [ -e "${ref}" ] && continue
        base="${name%%.so.*}"
        major="${name#*.so.}"; major="${major%%.*}"
        real="$(ls "${lib_dir}/${base}.so.${major}".* 2>/dev/null | head -n1)"
        [ -n "${real}" ] || continue
        sudo_run ln -sf "${real}" "${ref}"
        info "兼容链接: ${name} -> $(basename "${real}")"
    done < <(grep -rhoE 'lib[A-Za-z0-9_+.-]+\.so\.[0-9]+(\.[0-9]+)+' "${lib_dir}/cmake" 2>/dev/null | sort -u)
    return 0
}

v20_dev_ready() {
    [ -f /usr/lib/x86_64-linux-gnu/cmake/Qt5/Qt5Config.cmake ] || return 1
    [ -x /usr/lib/qt5/bin/moc ] && [ -x /usr/lib/qt5/bin/lrelease ] || return 1
    [ -f /usr/include/GL/gl.h ] || return 1
    return 0
}

ensure_gxx() {
    if g++ --version >/dev/null 2>&1; then
        info "g++ 已可用: $(g++ --version | head -n1)"
        return 0
    fi
    info "安装 g++（eagle 8.3）"
    if sudo_run env DEBIAN_FRONTEND=noninteractive apt-get install -y --allow-downgrades g++ >"${APT_LOG}" 2>&1; then
        info "g++ 就绪: $(g++ --version | head -n1)"
        return 0
    fi
    warn "g++ 元包安装失败，改为安装 g++-8 并注册命令"
    apt_install g++-8 || return 1
    sudo_run ln -sf /usr/bin/g++-8 /usr/bin/g++
    command -v g++ >/dev/null 2>&1 || { err "g++ 不可用"; return 1; }
    info "g++ 就绪: $(g++ --version | head -n1)"
}

install_v20_dev_packages() {
    if v20_dev_ready; then
        info "Qt5/DTK5 开发文件已就绪，跳过解包"
    else
        local p
        for p in qtbase5-dev qtbase5-dev-tools qt5-qmake qt5-qmake-bin \
                 qttools5-dev-tools libqt5svg5-dev \
                 libdtkcore-dev libdtkgui-dev libdtkwidget-dev libpolkit-qt5-1-dev \
                 mesa-common-dev libegl1-mesa-dev libgles2-mesa-dev; do
            unpack_dev_pkg "${p}" || return 1
        done
    fi
    fix_dev_soname_links
    [ -x /usr/lib/qt5/bin/moc ] || { err "moc 不可用"; return 1; }
    [ -x /usr/lib/qt5/bin/lrelease ] || { err "lrelease 不可用"; return 1; }
    info "Qt5/DTK5 开发文件就绪（$(/usr/lib/qt5/bin/moc -v 2>&1 | head -n1)）"
    return 0
}

detect_profile() {
    if [ -d /usr/lib/x86_64-linux-gnu/cmake/Qt6 ]; then
        echo "v25"
        return 0
    fi
    if [ -d /usr/lib/x86_64-linux-gnu/cmake/Qt5 ]; then
        echo "v20"
        return 0
    fi
    # 开发包尚未安装时，按运行时库判断（qtbase5-dev 装完才会出现 cmake/Qt5）
    if dpkg -s libqt6core6 >/dev/null 2>&1; then
        echo "v25"
        return 0
    fi
    if dpkg -s libqt5core5a >/dev/null 2>&1; then
        echo "v20"
        return 0
    fi
    if grep -qiE 'VERSION_ID="?20|eagle' /etc/os-release 2>/dev/null; then
        echo "v20"
        return 0
    fi
    die "未检测到 Qt5/Qt6 环境，无法确定构建配置"
}

install_dependencies() {
    local profile="$1"
    local p zlib
    local common=(git debhelper cmake pkg-config)

    if [ "${profile}" = "v20" ]; then
        for p in "${common[@]}"; do
            apt_install "${p}" || { err "编译依赖安装失败: ${p}"; return 1; }
        done
        ensure_gxx || return 1
        zlib="$(dpkg-query -W -f='${Version}' zlib1g 2>/dev/null)"
        apt_install "zlib1g-dev=${zlib}" || { unpack_dev_pkg zlib1g-dev || return 1; }
        install_v20_dev_packages || return 1
    else
        local pkgs=(git debhelper cmake g++ pkg-config zlib1g-dev \
                    qt6-base-dev qt6-l10n-tools libqt6svg6-dev \
                    libdtk6core-dev libdtk6widget-dev libpolkit-qt6-1-dev libostree-dev)
        for p in "${pkgs[@]}"; do
            apt_install "${p}" || { err "编译依赖安装失败: ${p}"; return 1; }
        done
    fi
    info "编译依赖就绪（${profile}）"
}

# ---------------------------------------------------------------- 源码
prepare_source() {
    if [ "${NO_GIT}" = "1" ]; then
        [ -f "${SRC_DIR}/debian/rules" ] || die "源码目录无效（缺少 debian/rules）: ${SRC_DIR}"
        info "按参数跳过源码拉取，使用现有目录: ${SRC_DIR}"
        return 0
    fi

    if [ -d "${SRC_DIR}/.git" ]; then
        info "更新源码: ${SRC_DIR}"
        if ! git -C "${SRC_DIR}" "${GIT_CRED_ARGS[@]}" fetch --prune origin; then
            err "git fetch 失败（检查用户名/密码/网络）"
            return 1
        fi
    else
        mkdir -p "$(dirname "${SRC_DIR}")"
        info "克隆源码: ${GERRIT_URL}（分支 ${BRANCH}）"
        if ! git "${GIT_CRED_ARGS[@]}" clone -b "${BRANCH}" "${GERRIT_URL}" "${SRC_DIR}"; then
            err "git clone 失败（检查用户名/密码/网络）"
            return 1
        fi
    fi

    if [ -n "${TAG}" ]; then
        git -C "${SRC_DIR}" checkout -f "${TAG}" >/dev/null 2>&1 \
            || git -C "${SRC_DIR}" checkout -f "origin/${TAG}" \
            || { err "切换标签失败: ${TAG}"; return 1; }
    elif [ -n "${COMMIT}" ]; then
        git -C "${SRC_DIR}" checkout -f "${COMMIT}" >/dev/null 2>&1 \
            || { err "切换提交失败: ${COMMIT}"; return 1; }
    else
        git -C "${SRC_DIR}" checkout -f "${BRANCH}" || { err "切换分支失败: ${BRANCH}"; return 1; }
        git -C "${SRC_DIR}" reset --hard "origin/${BRANCH}" || { err "同步分支失败: ${BRANCH}"; return 1; }
    fi
    git -C "${SRC_DIR}" remote set-url origin "${GERRIT_URL}"
    info "源码版本: $(git -C "${SRC_DIR}" log -1 --format='%h %s' 2>/dev/null)"
    info "源码包版本: $(sed -n '1s/.*(\([^)]*\)).*/\1/p' "${SRC_DIR}/debian/changelog" 2>/dev/null)"
    return 0
}

# ---------------------------------------------------------------- 构建/安装
# 仅 -A 显式指定时使用：系统仓库版本为 1.0.10，低于源码版本，不用于常规部署。
install_app_from_repo() {
    info "从系统仓库安装 deepin-pc-manager"
    if ! sudo_run env DEBIAN_FRONTEND=noninteractive apt-get install -y deepin-pc-manager >"${APT_LOG}" 2>&1; then
        err "apt 安装失败"
        tail -n 20 "${APT_LOG}" >&2
        die "安装 deepin-pc-manager 失败"
    fi
    info "已安装: $(dpkg-query -W -f='${Package} ${Version}' deepin-pc-manager 2>/dev/null)"
}

BUILD_LOG=""
build_package() {
    local profile="$1"
    [ -f "${SRC_DIR}/debian/rules" ] || die "源码目录无效（缺少 debian/rules）: ${SRC_DIR}"
    chmod +x "${SRC_DIR}/debian/rules" 2>/dev/null || true
    rm -rf "${SRC_DIR}"/obj-* 2>/dev/null || true

    # 多版本打包：构建平台按 V20/V25 切换 debian/control。
    if [ "${profile}" = "v20" ] && [ -f "${SRC_DIR}/debian/control.1" ]; then
        cp -f "${SRC_DIR}/debian/control.1" "${SRC_DIR}/debian/control"
        info "使用 V20 打包配置: debian/control.1"
    elif [ "${profile}" = "v25" ] && git -C "${SRC_DIR}" rev-parse --git-dir >/dev/null 2>&1; then
        git -C "${SRC_DIR}" checkout -- debian/control 2>/dev/null || true
    fi
    [ "${profile}" = "v20" ] && export QT_SELECT=qt5

    BUILD_LOG="$(dirname "${SRC_DIR}")/deploy_build.log"
    export DEB_BUILD_OPTIONS="parallel=${JOBS} nocheck"
    info "开始构建（并行 ${JOBS}，日志 ${BUILD_LOG}）"
    if ! ( cd "${SRC_DIR}" && dpkg-buildpackage -us -uc -b -d >"${BUILD_LOG}" 2>&1 ); then
        err "构建失败，日志尾部："
        tail -n 30 "${BUILD_LOG}" >&2
        return 1
    fi
    info "构建完成"
}

install_package() {
    local arch deb
    arch="$(dpkg --print-architecture)"
    deb="$(ls -t "$(dirname "${SRC_DIR}")"/deepin-pc-manager_*_"${arch}".deb 2>/dev/null | head -n1)"
    if [ -z "${deb}" ]; then
        err "未找到构建产物: $(dirname "${SRC_DIR}")/deepin-pc-manager_*_${arch}.deb"
        return 1
    fi

    info "安装: ${deb}"
    if sudo_run dpkg -i "${deb}" >/tmp/deploy_pcm_install.log 2>&1; then
        info "安装成功"
    else
        warn "dpkg 安装提示依赖缺失，尝试修复"
        sudo_run env DEBIAN_FRONTEND=noninteractive apt-get install -f -y >>/tmp/deploy_pcm_install.log 2>&1 || true
        if ! sudo_run dpkg -i "${deb}" >>/tmp/deploy_pcm_install.log 2>&1; then
            tail -n 20 /tmp/deploy_pcm_install.log >&2
            err "安装失败"
            return 1
        fi
        info "安装成功（依赖已修复）"
    fi
    return 0
}

configure_test_env() {
    local polkit="/usr/share/polkit-1/actions/org.deepin.PCManager1.policy"
    if [ -f "${polkit}" ]; then
        sudo_run chmod 644 "${polkit}"
        info "polkit 策略权限已设为 644"
    else
        warn "未找到 polkit 策略文件: ${polkit}"
    fi
    # action 由被测应用安装后才注册，因此预授权与 pkcheck 校验必须在安装之后执行
    if [ -f "${ROOT_DIR}/src/utils/env_polkit.sh" ]; then
        bash "${ROOT_DIR}/src/utils/env_polkit.sh" -p "${SUDO_PASS}" \
            || warn "polkit 预授权未生效（检测/修复类用例可能因鉴权被拒而失败）"
    fi

    if [ ! -x /usr/libexec/deepin/deepin-pc-manager ] && [ ! -x /usr/bin/deepin-pc-manager ]; then
        die "未找到 deepin-pc-manager 可执行文件（/usr/libexec/deepin 或 /usr/bin）"
    fi
    [ -e /usr/bin/dpmapi ] || warn "未找到 dpmapi（插件开发包相关功能可能不可用）"
    info "被测应用安装校验通过"

    # 用例依赖的外部命令：arping（IP 冲突检测用例的构造/校验手段）
    apt_install iputils-arping || warn "iputils-arping 安装失败，IP 冲突检测用例将无法通过"
}

ensure_venv_python() {
    # 需求: 部署后可以直接 `python3 manage.py run -a apps/autotest_my_app`。
    # 不把框架依赖装进系统 site-packages：numpy/Pillow/cryptography 等 .so 与 apt 的
    # python3-numpy/python3-pil 同名，电脑管家「关键库检测」会持续报本地库冲突
    # (用例 1999059 的 3012 结论)。改为把 .venv/bin 前置到用户 PATH：裸 python3
    # 即虚拟环境解释器，系统解释器与 apt 包保持原样。
    local venv_py="${ROOT_DIR}/.venv/bin/python3"
    local marker="# youqu venv python (managed by deploy_pc_manager.sh)"
    local f
    if [ ! -x "${venv_py}" ]; then
        err "未找到虚拟环境解释器: ${venv_py}"
        return 1
    fi
    if ! "${venv_py}" -c "import funnylog, pytest, allure_pytest, pytest_rerunfailures" >/dev/null 2>&1; then
        err "虚拟环境缺少测试框架依赖（可用 -e 重建 .venv）"
        return 1
    fi
    for f in "${HOME}/.bashrc" "${HOME}/.profile"; do
        [ -f "${f}" ] || continue
        grep -qF "${marker}" "${f}" 2>/dev/null && continue
        {
            printf '\n%s\n' "${marker}"
            printf 'case ":$PATH:" in\n    *":%s/.venv/bin:"*) ;;\n    *) export PATH="%s/.venv/bin:$PATH" ;;\nesac\n' \
                "${ROOT_DIR}" "${ROOT_DIR}"
        } >> "${f}"
        info "已在 ${f} 前置 .venv/bin 到 PATH"
    done
    export PATH="${ROOT_DIR}/.venv/bin:${PATH}"
    hash -r 2>/dev/null || true
    if [ "$(command -v python3)" = "${venv_py}" ]; then
        info "python3 已解析到虚拟环境: $(python3 -V 2>&1)，框架依赖校验通过"
    else
        warn "当前 shell 的 python3 未解析到虚拟环境（非登录 shell 请用 bash -lc 或 .venv/bin/python）"
    fi
    return 0
}

deploy_youqu_env() {
    if [ "${SKIP_ENV}" = "1" ]; then
        info "按参数跳过 youqu 测试环境部署"
        return 0
    fi
    if [ "${FORCE_ENV}" = "0" ] && [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
        info "youqu 虚拟环境已存在，校验虚拟环境依赖与 python3 解析（需要重建请加 -e）"
        ensure_venv_python || die "虚拟环境 python3 校验失败"
        return 0
    fi
    info "执行 youqu 测试环境部署（env.sh）"
    ( cd "${ROOT_DIR}" && PCM_APT_SOURCES_ISOLATED=1 bash env.sh -p "${SUDO_PASS}" ) || die "env.sh 执行失败"
    ensure_venv_python || die "虚拟环境 python3 校验失败"
}

verify_installed_version() {
    local expected installed
    expected="$(sed -n '1s/.*(\([^)]*\)).*/\1/p' "${SRC_DIR}/debian/changelog" 2>/dev/null)"
    installed="$(dpkg-query -W -f='${Version}' deepin-pc-manager 2>/dev/null)"
    [ -n "${expected}" ] || { warn "无法从源码读取版本号"; return 0; }
    if [ "${installed}" = "${expected}" ]; then
        info "版本校验通过: ${installed}"
        return 0
    fi
    err "版本不一致: 已安装 ${installed}，源码为 ${expected}"
    return 1
}

summary() {
    local app_bin="" p commit expected
    for p in /usr/bin/deepin-pc-manager /usr/libexec/deepin/deepin-pc-manager; do
        if [ -x "${p}" ]; then
            app_bin="${p}"
            break
        fi
    done
    echo
    info "================ 部署完成 ================"
    dpkg-query -W -f='  应用: ${Package} ${Version}\n' deepin-pc-manager 2>/dev/null
    echo "  可执行文件: ${app_bin:-未找到}"
    echo "  服务:       deepin-pc-manager-daemon (system) / deepin-pc-manager-session-daemon (user)"
    if [ "${APP_FROM_APT}" = "1" ]; then
        echo "  安装方式:   系统仓库 (apt)"
    else
        expected="$(sed -n '1s/.*(\([^)]*\)).*/\1/p' "${SRC_DIR}/debian/changelog" 2>/dev/null)"
        commit="$(git -C "${SRC_DIR}" log -1 --format='%h' 2>/dev/null)"
        echo "  安装方式:   源码构建"
        echo "  源码目录:   ${SRC_DIR}"
        echo "  源码提交:   ${commit}（${expected}）"
        echo "  构建日志:   ${BUILD_LOG}"
    fi
    echo "  运行用例:   cd ${ROOT_DIR} && python3 manage.py run -a apps/autotest_my_app"
    echo "  解释器:     ${ROOT_DIR}/.venv/bin/python3（已前置到 ~/.profile、~/.bashrc 的 PATH）"
    echo "=========================================="
}

main() {
    command -v apt-get >/dev/null 2>&1 || die "仅支持 apt 系发行版"
    init_sudo
    ensure_apt_sources_active || die "apt 源不可用（sources 配置中没有启用的 deb 条目）"
    # 装包前先写入与本机版本匹配的源，否则 apt-get update / build-dep 可能
    # 依赖错误版本（V20 机器混入 V25 源会把 libc6/systemd/sshd 一起升级）。
    # 写入源后 apply 内部会执行 apt-get update；-U 表示跳过该刷新。
    if [ "${APT_UPDATE}" != "1" ]; then
        export PCM_APT_SKIP_UPDATE=1
        info "跳过 apt-get update（-U）"
    fi
    apply_release_apt_sources
    isolate_v25_sources

    if [ "${NO_GIT}" = "0" ] && [ "${APP_FROM_APT}" = "0" ]; then
        init_git_auth
    fi

    if [ "${APP_FROM_APT}" = "1" ]; then
        install_app_from_repo
    else
        local profile
        profile="$(detect_profile)"
        [ -n "${profile}" ] || die "无法确定构建配置（V20/V25）"
        info "构建配置: ${profile}"
        install_dependencies "${profile}" || die "编译依赖安装失败（详见 ${APT_LOG}）"
        prepare_source || die "源码拉取失败（检查 Gerrit 凭据/网络）"
        build_package "${profile}" || die "源码构建失败（详见 ${BUILD_LOG}）"
        install_package || die "源码包安装失败（详见 /tmp/deploy_pcm_install.log）"
        verify_installed_version || die "安装版本与源码不一致"
    fi
    configure_test_env
    deploy_youqu_env
    summary
}

main "$@"

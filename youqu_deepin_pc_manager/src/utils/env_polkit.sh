#!/bin/bash
# SPDX-FileCopyrightText: 2026 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
# 配置 PCManager 无人值守 UI 自动化测试所需的 polkit 授权。
# 放开 org.deepin.PCManager1.doAction（系统检测/全面检查入口）与
# org.deepin.PCManager1.run-repair-tool（root 模式修复工具入口）。
#
# 为什么要放开 run-repair-tool：修复工具以 executionMode=root 的插件经系统
# 守护进程执行，守护进程在启动脚本前调用 polkit checkAuthorization 鉴权
# （policy 中 allow_active=auth_admin）。UI 自动化无法回答 dde-polkit-agent
# 弹出的系统认证窗口，表现是修复对话框只显示
# "Preparing to execute repair tool via daemon: xxx" 后无限等待。
# 因此测试机预授权给当前测试用户；产品侧的鉴权逻辑本身不在本工程覆盖范围。

PASSWORD=""
while getopts ":p:" opt
do
    case $opt in
        p)
            PASSWORD=$OPTARG
            ;;
        ?)
            echo -e " 参数说明:\
            \n\t-p password 指定 sudo 密码, 如: bash env_polkit.sh -p xxx"
            exit 1
            ;;
    esac
done

if [ -z "${PASSWORD}" ]; then
    # 未通过 -p 传入时读取项目配置, 不在代码里写死密码
    _PCM_CONF="${PCM_CONF:-$(cd "$(dirname "$0")/../.." && pwd)/setting/globalconfig.ini}"
    PASSWORD="$(grep -E '^PASSWORD[[:space:]]*=' "${_PCM_CONF}" 2>/dev/null \
        | grep -v CLIENT_PASSWORD | tail -n1 | cut -d '=' -f2 | tr -d '[:space:]')"
fi
if [ -z "${PASSWORD}" ]; then
    echo "未指定 sudo 密码(-p)且配置中无 PASSWORD: ${_PCM_CONF:-setting/globalconfig.ini}"
    exit 1
fi

if [ "$(id -u)" = "0" ]; then
    echo "请勿以 root 用户执行"
    exit 1
fi

sudo_exec() {
    echo "${PASSWORD}" | sudo -S "$@"
}

if ! sudo_exec true > /dev/null 2>&1; then
    echo -e "sudo\t密码错误或无权限"
    exit 1
fi

POLKIT_LA_DIR="/etc/polkit-1/localauthority/50-local.d"
POLKIT_RULES_DIR="/etc/polkit-1/rules.d"
USER_NAME=$(id -un)
ACTIONS="org.deepin.PCManager1.doAction org.deepin.PCManager1.run-repair-tool"

# 后端按目录存在性判定，不按 OS 版本号：
#   eagle(polkit 0.105) 只有 localauthority，且 50-local.d 默认不存在；
#   V25(polkit 123) 只有 rules.d(JS) 与 localauthority.conf.d。
POLKIT_BACKEND=none
if sudo_exec test -d /etc/polkit-1/localauthority > /dev/null 2>&1; then
    POLKIT_BACKEND=pkla
elif sudo_exec test -d "${POLKIT_RULES_DIR}" > /dev/null 2>&1; then
    POLKIT_BACKEND=rules_js
fi

restart_polkit(){
    if sudo_exec systemctl restart polkit > /dev/null 2>&1; then
        return 0
    fi
    sudo_exec systemctl restart polkitd > /dev/null 2>&1
}

# 以当前进程身份查询授权结果，与用例实际调用路径一致。
# 注意 pkcheck 的 -u 是 --allow-user-interaction，不是"指定用户"，
# 早期实现误加 -u 导致 pkcheck 直接报参数错误，被误判为"未授权"。
verify_polkit(){
    if ! command -v pkcheck > /dev/null 2>&1; then
        echo -e "polkit\t配置成功 √ (未安装 pkcheck, 跳过校验)"
        return 0
    fi
    local ok=true action out
    for action in ${ACTIONS}; do
        out=$(pkcheck --action-id "${action}" --process $$ 2>&1)
        if [ $? = 0 ]; then
            continue
        fi
        if printf '%s' "${out}" | grep -q "is not registered"; then
            # 应用未安装时 action 未注册，属正常：应用装完再跑一次本脚本即可
            echo -e "polkit\t${action} 尚未注册(被测应用未安装), 应用安装后需重新执行本脚本"
            continue
        fi
        ok=false
        echo -e "polkit\t${action} 未授权: ${out}"
    done
    if [ "${ok}" = "true" ]; then
        echo -e "polkit\t配置成功 √"
        return 0
    fi
    echo -e "polkit\t配置已写入, 但 pkcheck 验证未通过"
    return 1
}

write_and_verify(){
    local content="$1" target="$2" tmp_file
    tmp_file=$(mktemp) || return 1
    printf '%s\n' "${content}" > "${tmp_file}"
    if sudo_exec test -f "${target}" && sudo_exec cmp -s "${tmp_file}" "${target}" > /dev/null 2>&1; then
        sudo_exec chmod 644 "${target}" > /dev/null 2>&1 || true
        rm -f "${tmp_file}"
        echo -e "polkit\t(${POLKIT_BACKEND}) 已配置"
        # 规则内容没变也要重启：polkitd 可能先于规则文件启动，旧进程不会重载
        restart_polkit || echo -e "polkit\t重启 polkit 失败, 请手动重启"
        verify_polkit
        return $?
    fi
    if ! sudo_exec cp "${tmp_file}" "${target}" > /dev/null 2>&1 \
        || ! sudo_exec chmod 644 "${target}" > /dev/null 2>&1 \
        || ! sudo_exec cmp -s "${tmp_file}" "${target}" > /dev/null 2>&1; then
        echo -e "polkit\t写入 ${target} 失败, 请检查 sudo 权限"
        rm -f "${tmp_file}"
        return 1
    fi
    rm -f "${tmp_file}"
    restart_polkit || echo -e "polkit\t重启 polkit 失败, 请手动重启"
    verify_polkit
}

case "${POLKIT_BACKEND}" in
    pkla)
        # eagle 上 50-local.d 默认不存在，pkla 后端只按该目录里的 *.pkla 生效
        sudo_exec mkdir -p "${POLKIT_LA_DIR}" > /dev/null 2>&1
        write_and_verify "[PCManager test authorization]
Identity=unix-user:${USER_NAME}
Action=org.deepin.PCManager1.doAction;org.deepin.PCManager1.run-repair-tool
ResultAny=yes
ResultInactive=yes
ResultActive=yes" "${POLKIT_LA_DIR}/49-pcmanager-test.pkla"
        exit $?
        ;;
    rules_js)
        write_and_verify "// PCManager 无人值守 UI 测试预授权：允许测试用户直接发起检测/修复。
// 仅用于测试机，产品侧鉴权逻辑不在本工程覆盖范围。
polkit.addRule(function(action, subject) {
    if (subject.user === \"${USER_NAME}\" &&
        [\"org.deepin.PCManager1.doAction\",
         \"org.deepin.PCManager1.run-repair-tool\"].indexOf(action.id) >= 0) {
        return polkit.Result.YES;
    }
});" "${POLKIT_RULES_DIR}/49-pcmanager-test.rules"
        exit $?
        ;;
    *)
        echo -e "polkit\t系统没有可用的 polkit 配置目录(${POLKIT_LA_DIR} 与 ${POLKIT_RULES_DIR} 均不存在)"
        exit 1
        ;;
esac

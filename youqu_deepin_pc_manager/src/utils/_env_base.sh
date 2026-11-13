#!/bin/bash
# SPDX-FileCopyrightText: 2023 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only

ctrl_c_handler(){
    echo "正在退出……"
    exit 1
}

trap ctrl_c_handler INT

check_status(){
    if [ $? = 0 ]; then
        echo -e "$1\t安装成功 √"
    else
        echo -e "$1\t安装失败 ×"
        cat /tmp/env.log
    fi
}

# 环境能力探测：安装方式按"能力"决定，禁止按 OS 大版本号(20/25)分支。
# 同一台机器可能混源(如 V20 混入 V25 源)、也可能既非 eagle 也非 V25。
# MAJOR_VERSION 仅用于日志标注，不得参与安装逻辑判断。
detect_env_capabilities(){
    if [ -z "${MAJOR_VERSION:-}" ]; then
        MAJOR_VERSION=$(sed -n 's/^MajorVersion=//p' /etc/os-version 2>/dev/null | head -n 1)
        if [ -z "${MAJOR_VERSION}" ]; then
            MAJOR_VERSION=$(sed -n 's/^VERSION_ID="\?\([0-9][0-9]*\).*/\1/p' /etc/os-release 2>/dev/null | head -n 1)
        fi
        export MAJOR_VERSION
    fi

    if [ -z "${PIP_FLAGS+x}" ]; then
        local pip_major
        pip_major=$(python3 -m pip --version 2>/dev/null | awk '{print $2}' | cut -d. -f1)
        # PEP 668: 只有 pip>=23.0.1 认识 --break-system-packages；
        # 更早的 pip（如 eagle 的 20.3.4）没有该约束，传参会直接报错。
        if [ "${pip_major:-0}" -ge 23 ] 2>/dev/null; then
            PIP_FLAGS="--break-system-packages"
        else
            PIP_FLAGS=""
        fi
        export PIP_FLAGS
    fi

    if [ -z "${POLKIT_BACKEND:-}" ]; then
        # pkla(older polkit) 与 rules.d(JS) 互斥：eagle 只有 localauthority，
        # V25(polkit 123) 只有 rules.d 与 localauthority.conf.d。
        # 注意 50-local.d 在 eagle 上默认不存在，需按上级目录判定再创建。
        if [ -d /etc/polkit-1/localauthority ]; then
            POLKIT_BACKEND=pkla
        elif [ -d /etc/polkit-1/rules.d ]; then
            POLKIT_BACKEND=rules_js
        else
            POLKIT_BACKEND=none
        fi
        export POLKIT_BACKEND
    fi
}

# 以 root 执行。env.sh 会把 sudo 重定义成自动喂密码的函数，
# 此处优先复用；独立执行时退回显式喂密码/免密。
sudo_pc(){
    if declare -F sudo > /dev/null 2>&1; then
        sudo "$@" > /dev/null 2>&1
    elif [ -n "${PASSWORD:-}" ]; then
        echo "${PASSWORD}" | command sudo -S "$@" > /dev/null 2>&1
    else
        command sudo -n "$@" > /dev/null 2>&1
    fi
}

# V25 的 /usr 是 immutable overlay，默认只读挂载；Debian 系 pip 又用
# /usr/lib/python3.X/EXTERNALLY-MANAGED 拒绝写入系统 site-packages。
# 测试机需要把依赖同步进系统解释器，所以：先解除只读再删除标记；
# 删不掉时退回 --break-system-packages（PIP_FLAGS 已由能力探测给出）。
enable_system_pip_write(){
    local marker rc=0
    for marker in /usr/lib/python3.*/EXTERNALLY-MANAGED; do
        [ -e "${marker}" ] || continue
        sudo_pc rm -f "${marker}"
        if [ -e "${marker}" ]; then
            # overlay 挂载点 remount 必须带源名，否则报 "bad option"
            sudo_pc mount -o remount,rw usr-overlay /usr
            if [ -e "${marker}" ]; then
                sudo_pc mount -o remount,rw /usr
            fi
            sudo_pc rm -f "${marker}"
        fi
        if [ -e "${marker}" ]; then
            echo -e "pip标记\t${marker} 未能移除, 依赖安装改用 --break-system-packages"
            rc=1
        else
            echo -e "pip标记\t已移除 ${marker}"
        fi
    done
    return ${rc}
}

# sudo 包装函数通过 stdin 回显密码，`echo content | sudo tee` 会让 tee 只读到
# 密码行、文件内容为空。改为先写临时文件，再用 install 落盘。
install_script_with_sudo(){
    local content="$1" target="$2" tmp rc
    tmp=$(mktemp) || return 1
    printf '%s\n' "${content}" > "${tmp}"
    sudo install -m 755 "${tmp}" "${target}" > /dev/null 2>&1
    rc=$?
    rm -f "${tmp}"
    return ${rc}
}

# 让用户 shell 里的裸 python3 解析到项目虚拟环境（部署后可直接 `python3 manage.py run`）。
# 不把框架依赖装进系统 site-packages：numpy/Pillow/cryptography 等 .so 与 apt 的
# python3-numpy/python3-pil 同名，电脑管家「关键库检测」会持续报本地库冲突（3012）。
ensure_venv_on_path(){
    local venv_bin="${ROOT_DIR}/.venv/bin"
    local marker="# youqu venv python (managed by env.sh)"
    local f
    [ -x "${venv_bin}/python3" ] || return 1
    for f in "${HOME}/.bashrc" "${HOME}/.profile"; do
        [ -f "${f}" ] || continue
        grep -qF "${marker}" "${f}" 2>/dev/null && continue
        {
            printf '\n%s\n' "${marker}"
            printf 'case ":$PATH:" in\n    *":%s:"*) ;;\n    *) export PATH="%s:$PATH" ;;\nesac\n' \
                "${venv_bin}" "${venv_bin}"
        } >> "${f}"
    done
    case ":${PATH}:" in
        *":${venv_bin}:"*) ;;
        *) export PATH="${venv_bin}:${PATH}" ;;
    esac
    hash -r 2>/dev/null || true
    return 0
}

wayland_env(){
    deb_array=(g++ build-essential cmake qt5-default qt5-qmake libqt5gui5 libqt5core5a wl-clipboard)
    for deb in ${deb_array[*]}
    do
        sudo apt install -y ${deb} > /tmp/env.log 2>&1
        check_status ${deb}
        apt policy ${deb} > /tmp/_yqdebversion.txt 2>&1
        cat /tmp/_yqdebversion.txt | grep "已安装"
    done

    # 根据 libkf5waylandclient5 的版本决定安装 libkf5wayland-dev 的版本;
    libkf5waylandclient5_version=$(apt policy libkf5waylandclient5 | grep "已安装" | python3 -c "s=input();print(s.split('：')[1])")
    sudo apt install -y libkf5wayland-dev=${libkf5waylandclient5_version} > /tmp/env.log 2>&1
    wayland_info="libkf5wayland-dev 可能存在依赖报错，解决方法：\n
    方案一. 添加镜像对应的 ppa 仓库源，重新执行；\n
    方案二. sudo aptitude install libkf5wayland-dev,先输 n,再输 y,再输 y \n
    ***方案二可能引入兼容性问题，慎用，在下非常非常非常不推荐。***"
    echo -e ${wayland_info} >> /tmp/env.log 2>&1
    check_status libkf5wayland-dev

    # 编译工具
    cd ${ROOT_DIR}/src/depends/wayland_autotool/
    mkdir -p build && cd build
    cmake .. > /dev/null 2>&1
    make -j4 > /dev/null 2>&1
    sudo make install > /dev/null 2>&1
    [ $? = 0 ] && tool_status="成功 √" || tool_status="失败 ×"
    echo -e "wayland_autotool 安装${tool_status}"
    # 添加wayland下有用的环境变量，其实框架执行的时候底层也会自动判断并添加，这里咱们先打个提前量；
    cat $HOME/.bashrc | grep 'export GDMSESSION=Wayland' > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "export QT_WAYLAND_SHELL_INTEGRATION=kwayland-shell" >> $HOME/.bashrc
        echo "export XDG_SESSION_DESKTOP=Wayland" >> $HOME/.bashrc
        echo "export XDG_SESSION_TYPE=wayland" >> $HOME/.bashrc
        echo "export WAYLAND_DISPLAY=wayland-0" >> $HOME/.bashrc
        echo "export GDMSESSION=Wayland" >> $HOME/.bashrc
        echo 'export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"' >> $HOME/.bashrc
    fi
    wayland_cmd_path="/usr/local/bin/wayland_autotool"
    result=`sudo cat ${whitelist} | grep ${wayland_cmd_path}`
    if [ -z "$result" ]; then
        sudo sed -i '$a\'"${wayland_cmd_path}"'' ${whitelist} || echo "白名单${whitelist}写入失败"
        sudo systemctl restart deepin-elf-verify.service || true
    fi

    nohup wayland_autotool > /dev/null 2>&1 &
}

system_env(){
    echo "${PASSWORD}" | sudo -S su  > /dev/null 2>&1
    sudo sed -i "s/#PubkeyAuthentication yes/PubkeyAuthentication yes/g" /etc/ssh/sshd_config > /dev/null 2>&1
    sudo sed -i "s/#   StrictHostKeyChecking ask/   StrictHostKeyChecking no/g" /etc/ssh/ssh_config  > /dev/null 2>&1
    cat $HOME/.bashrc | grep 'export DISPLAY=":0"' > /dev/null 2>&1
    if [ $? -ne 0 ]; then
         echo 'export PIPENV_VERBOSITY=-1' >> $HOME/.bashrc
         echo 'export DISPLAY=":0"' >> $HOME/.bashrc
         echo 'export QT_QPA_PLATFORM=' >> $HOME/.bashrc
         echo 'export QT_ACCESSIBILITY=1' >> $HOME/.bashrc
         echo 'export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1' >> $HOME/.bashrc
    fi
    source $HOME/.bashrc
    install_script_with_sudo "cd ${ROOT_DIR}/src/depends/sniff/;python3 sniff" /usr/bin/sniff
    [ -s /usr/bin/sniff ] || echo -e "sniff\t写入失败 ×"

    gsettings set org.gnome.desktop.interface toolkit-accessibility true  > /dev/null 2>&1
    sudo systemctl enable ssh  > /dev/null 2>&1
    sudo systemctl start ssh  > /dev/null 2>&1
}

init_pip(){
    sudo python3 -m pip config set global.index-url ${pypi_mirror} > /tmp/env.log 2>&1
    sudo python3 -m pip install -U pip > /tmp/env.log 2>&1
    sudo python3 -m pip cache purge > /tmp/env.log 2>&1
    sudo python3 -m pip config set global.timeout 10000 > /tmp/env.log 2>&1
}

install_py_deb(){
    # 系统已安装同名 deb 时无需解包复制：pipenv 虚拟环境使用 --site-packages 创建，
    # 可以直接复用系统 dist-packages，避免 apt download 解析不到已安装版本而失败。
    if dpkg -s "${1}" > /dev/null 2>&1; then
        echo -e "${1}\t系统已安装，跳过解包"
        return 0
    fi
    rm -rf ${1}*
    ${yq} download ${1} > /tmp/env.log 2>&1
    if [ $? != 0 ]; then
        cat /tmp/env.log
        exit 120
    fi
    dpkg -x ${1}*.deb ${1}
    cp -r ./${1}/usr/lib/python3/dist-packages/* ${2}/lib/python${PYTHON_VERSION}/site-packages/
    rm -rf ${1}*
}

#!/bin/bash
# SPDX-FileCopyrightText: 2023 UnionTech Software Technology Co., Ltd.
# SPDX-License-Identifier: GPL-2.0-only
source ${ROOT_DIR}/src/utils/_env_base.sh
detect_env_capabilities
enable_system_pip_write

export PIPENV_VENV_IN_PROJECT=true
export PIPENV_PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
export PIPENV_QUIET=true
export PIPENV_DEFAULT_PYTHON_VERSION=3

echo "
 ██╗   ██╗  ██████╗      ███████╗ ███╗   ██╗ ██╗   ██╗
 ╚██╗ ██╔╝ ██╔═══██╗     ██╔════╝ ████╗  ██║ ██║   ██║
  ╚████╔╝  ██║   ██║     █████╗   ██╔██╗ ██║ ██║   ██║
   ╚██╔╝   ██║▄▄ ██║     ██╔══╝   ██║╚██╗██║ ╚██╗ ██╔╝
    ██║    ╚██████╔╝     ███████╗ ██║ ╚████║  ╚████╔╝
    ╚═╝     ╚══▀▀═╝      ╚══════╝ ╚═╝  ╚═══╝   ╚═══╝
    ${tag} -> ${IP}
"

env(){
    if [ "${debian_platform}" = "true" ]; then
        sudo apt update
    fi

    deb_array=(
        python3-pip
        python3-tk
        scrot
        openjdk-11-jdk-headless
        gir1.2-atspi-2.0
        libatk-adaptor
        at-spi2-core
        python3-opencv
    )
    cd ${ROOT_DIR}/src/utils
    BASICENV=$(python3 sub_env_cut.py)
    if [ "${BASICENV}" = "BASICENV" ]; then
        ENV_CUT_FLAG="cut"
        deb_array=(
            python3-pip
            openjdk-11-jdk-headless
        )
    fi

    if [ "${debian_platform}" = "false" ]; then
        deb_array[${#deb_array[@]}]=java-11-openjdk-headless
        deb_array[${#deb_array[@]}]=python3-tkinter
        deb_array[${#deb_array[@]}]=xdotool
        deb_array[${#deb_array[@]}]=opencv
    fi

    for deb in ${deb_array[*]}
    do
        sudo ${yq} install -y ${deb} > /tmp/env.log 2>&1
        check_status ${deb}
    done

    if [ "${DISPLAY_SERVER}" = "wayland" ]; then
        wayland_env
    fi
}
env

init_pip

sudo python3 -m pip install ${PIP_FLAGS} --ignore-installed pipenv -i https://repo.huaweicloud.com/repository/pypi/simple > /tmp/env.log 2>&1
if [ $? != 0 ]; then
    # 兜底：部分发行版 pip 不认 --break-system-packages 或不允许 --ignore-installed，
    # 退回最保守的参数重试一次。
    sudo python3 -m pip install pipenv -i https://repo.huaweicloud.com/repository/pypi/simple >> /tmp/env.log 2>&1
fi
echo -e "pipenv\t安装完成"
# pipenv 由 sudo pip 安装到 /usr/local/bin，而通过非交互 ssh / systemd / 精简
# PATH 调用本脚本时 PATH 可能不含该目录，裸调 pipenv 会报「未找到命令」，
# 表现为最后的「AT环境创建失败」。这里解析出可执行文件绝对路径并补进 PATH。
resolve_pipenv() {
    local c
    if c=$(command -v pipenv 2>/dev/null); then
        printf '%s' "${c}"
        return 0
    fi
    for c in /usr/local/bin/pipenv /usr/bin/pipenv "${HOME}/.local/bin/pipenv"; do
        if [ -x "${c}" ]; then
            printf '%s' "${c}"
            return 0
        fi
    done
    return 1
}
PIPENV_BIN=$(resolve_pipenv) || PIPENV_BIN=""
if [ -z "${PIPENV_BIN}" ]; then
    echo -e "pipenv\t未找到可执行文件, 重试安装"
    sudo python3 -m pip install pipenv -i https://repo.huaweicloud.com/repository/pypi/simple >> /tmp/env.log 2>&1
    PIPENV_BIN=$(resolve_pipenv) || PIPENV_BIN=""
fi
if [ -z "${PIPENV_BIN}" ]; then
    echo -e "pipenv\t安装失败 ×"
    cat /tmp/env.log
    exit 120
fi
export PATH="$(dirname "${PIPENV_BIN}"):${PATH}"
echo -e "pipenv\t可用: ${PIPENV_BIN}"

cd ${ROOT_DIR}/
# Pipfile 中 [requires] 固定写死 3.12，而部署机系统 python3 可能是 3.7/3.10，
# 版本不匹配会让 pipenv 拒绝创建虚拟环境；按实际解释器版本改写。
if [ -f ${ROOT_DIR}/Pipfile ]; then
    sed -i "s/^python_version = .*/python_version = \"${PYTHON_VERSION}\"/" ${ROOT_DIR}/Pipfile
fi
create_venv() {
    "${PIPENV_BIN}" --python "${PYTHON_VERSION}" --site-packages > /tmp/env.log 2>&1
}
if ! create_venv; then
    echo -e "AT环境创建失败, 诊断输出:"
    cat /tmp/env.log
    # 残留的 .venv 与当前解释器不匹配时 pipenv 会直接拒绝创建，清理后重试一次
    if [ -d "${ROOT_DIR}/.venv" ]; then
        echo -e "清理残留虚拟环境后重试: ${ROOT_DIR}/.venv"
        "${PIPENV_BIN}" --rm > /dev/null 2>&1 || rm -rf "${ROOT_DIR}/.venv"
        if ! create_venv; then
            echo -e "AT环境创建失败"
            cat /tmp/env.log
            exit 121
        fi
    else
        exit 121
    fi
fi
python_virtualenv_path=$("${PIPENV_BIN}" --venv)
whitelist_path=`echo "${python_virtualenv_path}" | sed "s;${HOME};;g"`
if [ -f "${whitelist}" ]; then
    result=`sudo cat ${whitelist} | grep ${whitelist_path}`
    if [ -z "$result" ]; then
        sudo sed -i '$a\'"${whitelist_path}"'' ${whitelist}
        sudo sed -i '$a\'"${python_virtualenv_path}"'' ${whitelist}
        sudo systemctl restart deepin-elf-verify.service || true
    fi
fi

py_debs=(
    python3-gi
    python3-pyatspi
    python3-dbus
    python3-cairo
    python3-pil
    python3-ptyprocess
    python3-pexpect
    python3-numpy
    python3-opencv
)
for pd in ${py_debs[*]}
do
    install_py_deb ${pd} ${python_virtualenv_path}
done

# python3 manage.py run 使用系统 python3 执行，AT-SPI/gi 等模块必须在系统
# dist-packages 中就位；已安装的 deb 跳过，缺失的从当前源补装。
sys_py_debs=(python3-gi python3-pyatspi python3-dbus python3-cairo python3-pil
             python3-ptyprocess python3-pexpect python3-numpy python3-opencv
             python3-gi-cairo)
missing_py_debs=""
for pd in ${sys_py_debs[*]}
do
    dpkg-query -W -f='${Status}' ${pd} 2>/dev/null | grep -q "install ok installed" \
        || missing_py_debs="${missing_py_debs} ${pd}"
done
if [ -n "${missing_py_debs}" ]; then
    sudo ${yq} install -y ${missing_py_debs} > /tmp/env.log 2>&1
    check_status "系统python依赖${missing_py_debs}"
fi

cd ${ROOT_DIR}/src/utils/
sub_py_debs=$(python3 sub_deb.py)
for spd in ${sub_py_debs[*]}
do
    install_py_deb ${spd} ${python_virtualenv_path}
done

pip_array=(
    pyscreeze==0.1.28
    PyAutoGUI==0.9.53
    # setuptools>=81 移除了 pkg_resources，pytest 6.2.5 与
    # pytest-rerunfailures 10.2 依赖它，导入即报 ModuleNotFoundError。
    "setuptools<81"
    pytest==6.2.5
    pytest-rerunfailures==10.2
    pytest-timeout==2.1.0
    allure-pytest==2.9.45
    funnylog
    pdocr-rpc
    image-center
    allure-custom
)

if [ "${ENV_CUT_FLAG}" = "cut" ]; then
    pip_array=(
        "setuptools<81"
        pytest==6.2.5
        pytest-rerunfailures==10.2
        pytest-timeout==2.1.0
        allure-pytest==2.9.45
        allure-custom
        funnylog
    )
fi

for p in ${pip_array[*]}
do
    "${PIPENV_BIN}" run pip install ${p} -i ${pypi_mirror} > /tmp/env.log 2>&1
    check_status ${p}
    "${PIPENV_BIN}" run pip list | grep -v grep | grep ${p}
done
echo "${PASSWORD}" | sudo -S su > /dev/null 2>&1
cd ${ROOT_DIR}/src/utils/
requirements=$(python3 sub_depends.py)
if [ "${requirements}" != "" ]; then
    echo -e "\n应用库依赖:\n${requirements}\n"
    for requirement in ${requirements[*]}
    do
        echo -e "${flag_feel}安装应用库依赖: ${requirement}"
        "${PIPENV_BIN}" run pip install -r ${requirement} -i ${pypi_mirror}
    done
fi

cd ${ROOT_DIR}/src/utils/
webui=$(python3 sub_webui.py)
if [ "${webui}" != "" ]; then
    "${PIPENV_BIN}" run pip install playwright -i ${pypi_mirror}
    "${PIPENV_BIN}" run playwright install chromium
fi

cd ${ROOT_DIR}/src/utils/
remote=$(python3 sub_remote.py)
if [ "${remote}" != "" ]; then
    "${PIPENV_BIN}" run pip install zerorpc -i ${pypi_mirror}
fi

"${PIPENV_BIN}" run pip install -U auto_uos --default-timeout=5 --retries 1 \
    --extra-index-url ${pypi_mirror} -i http://10.20.54.182:8081 --trusted-host=10.20.54.182 \
> /tmp/env.log 2>&1
if [ $? = 0 ]; then
    pip_show=$("${PIPENV_BIN}" run pip show auto_uos | grep Location)
    public_location=$(echo "${pip_show}" | cut -d ":" -f2 | python3 -c "s=input();print(s.strip())")
    sudo rm -rf ${ROOT_DIR}/public
    sudo cp -r ${public_location}/auto_uos ${ROOT_DIR}/public
    sudo chmod -R 777 ${ROOT_DIR}/public
    echo -e "auto_uos\t安装成功 √ (public/ 已部署)"
else
    echo -e "auto_uos\t跳过 (内网私有包不可达, 不影响框架运行)"
fi

cd ${ROOT_DIR}
# 需求：部署后可直接用 `python3 manage.py run`。
# 不把框架依赖装进系统 site-packages：numpy/Pillow/cryptography 等 .so 与 apt 的
# python3-numpy/python3-pil 等同名，电脑管家「关键库检测」会持续报本地库冲突
# (用例 1999059 的 3012 结论)。改为把 .venv/bin 前置到用户 PATH，裸 python3
# 即虚拟环境解释器，系统解释器与 apt 包保持原样。
ensure_venv_on_path
if "${PIPENV_BIN}" run python -c "import pytest, allure_pytest, pytest_rerunfailures, funnylog" > /dev/null 2>&1; then
    echo -e "虚拟环境依赖\t可用 √ (python3 → ${python_virtualenv_path}/bin/python3)"
else
    echo -e "虚拟环境依赖\t不可用 × (请检查上面的依赖安装输出)"
fi
rm -rf Pipfile
echo "${python_virtualenv_path}"
system_env

install_script_with_sudo "${PIPENV_BIN} run python \"\$@\"" /usr/bin/youqu
install_script_with_sudo "${PIPENV_BIN} shell" /usr/bin/youqu-shell
install_script_with_sudo "${PIPENV_BIN} --rm" /usr/bin/youqu-rm
for f in /usr/bin/youqu /usr/bin/youqu-shell /usr/bin/youqu-rm; do
    [ -s "${f}" ] || echo -e "${f}\t写入失败 ×"
done

cd ${ROOT_DIR};youqu manage.py -h

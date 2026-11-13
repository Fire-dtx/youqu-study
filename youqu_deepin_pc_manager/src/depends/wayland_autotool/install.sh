# SPDX-FileCopyrightText: 2023 UnionTech Software Technology Co., Ltd.

# SPDX-License-Identifier: GPL-2.0-only
# pylint: disable=C0114
# sudo 密码统一取项目配置 setting/globalconfig.ini（可用 PCM_SUDO_PASSWORD/PCM_CONF 覆盖）
if [ -z "${PCM_SUDO_PASSWORD}" ]; then
  _PCM_CONF="${PCM_CONF:-$(cd "$(dirname "$0")/../../.." && pwd)/setting/globalconfig.ini}"
  PCM_SUDO_PASSWORD="$(grep -E '^PASSWORD[[:space:]]*=' "${_PCM_CONF}" 2>/dev/null \
    | grep -v CLIENT_PASSWORD | tail -n1 | cut -d '=' -f2 | tr -d '[:space:]')"
fi
[ -n "${PCM_SUDO_PASSWORD}" ] || {
  echo "PCM_SUDO_PASSWORD 未设置, 且 ${_PCM_CONF} 中无 PASSWORD" >&2
  exit 1
}
# 预授权 sudo 时间戳, 后续 sudo 调用无需再次喂密码
printf '%s\n' "${PCM_SUDO_PASSWORD}" | sudo -S -v
sudo apt update
sudo apt install -y g++ build-essential cmake qt5-default qt5-qmake libkf5wayland-dev libqt5gui5 libqt5core5a
mkdir -p build && cd build && cmake .. && make -j4 && sudo make install

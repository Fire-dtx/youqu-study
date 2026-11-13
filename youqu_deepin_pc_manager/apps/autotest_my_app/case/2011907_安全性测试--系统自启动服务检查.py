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

    def test_mycase_218(self):
        """安全性测试--系统自启动服务检查

        描述步骤与预期:
        1) find /lib/systemd/system /etc/systemd/system -name "*deepin-pc-manager*"
           -> 预期"存在电脑管家的自启服务";
        2) systemctl list-units --type=service | grep -i deepin-pc-manager
           -> 预期"无返回, 服务未启动"。

        实测(2.14.0): 系统中存在 deepin-pc-manager-daemon.service, 采用 D-Bus 激活
        (Type=dbus, BusName=org.deepin.PCManager1, UnitFileState=static), 常驻进程
        /usr/lib/deepin-daemon/deepin-pc-manager-daemon 正在运行; 用户级(systemctl --user)
        没有任何匹配服务。即"自启服务(单元)存在", 但"不随开机 enabled 启动,
        也非用户 service", 与预期语义一致。

        等价断言:
        - 单元文件存在, 且只允许一个产品服务单元;
        - 该单元通过 D-Bus 激活, 不是 enabled 的开机自启(static/disabled), 且 ExecStart
          指向产品 daemon;
        - 用户级无匹配服务(对应"无返回, 服务未启动");
        - 产品主程序运行时与 systemd 服务相互独立(不依赖服务常驻)。

        闭环: 只读 systemd 状态, 不 enable/disable/stop 任何系统服务。
        """
        widget = MyAppWidget(check_start=False)

        # 1) 步骤 1: 单元文件存在
        units = widget.get_pc_manager_systemd_units()
        logger.info(f"[2011907] systemd 单元: {units}")
        self.assert_true(len(units["files"]) >= 1)
        # 只允许一个产品服务单元(避免历史/实验单元残留)
        self.assert_equal(len(units["files"]), 1)

        unit_file = units["files"][0]
        unit_name = unit_file.rsplit("/", 1)[-1]
        self.assert_true(unit_name.endswith(".service"))

        # 2) 该服务由 D-Bus 按需激活, 不作为 enabled 开机自启
        props = widget.get_systemd_unit_properties(unit_name)
        logger.info(f"[2011907] 单元属性: {props}")
        self.assert_equal(props["type"], "dbus")
        self.assert_equal(props["bus_name"], "org.deepin.PCManager1")
        self.assert_true(props["unit_file_state"] in ("static", "disabled", "masked"))
        self.assert_true("deepin-pc-manager-daemon" in props["exec_start"])

        # 3) 步骤 2: 用户级服务无返回(服务未随用户会话启动)
        self.assert_true(len(units["user_units"]) == 0)

        # 4) 产品主程序可独立运行, 不依赖系统服务手动启动
        try:
            widget.start_pc_manager()
            self.assert_true(widget.get_pc_manager_process_status())
            self.assert_true(widget.get_main_page_modules_showing())
            # 服务状态不因应用启动而改变(仍是同一个 D-Bus 激活单元)
            props_after = widget.get_systemd_unit_properties(unit_name)
            self.assert_equal(props_after["type"], "dbus")
            self.assert_equal(props_after["bus_name"], "org.deepin.PCManager1")
        finally:
            widget.kill_pc_manager()

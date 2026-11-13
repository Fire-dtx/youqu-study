#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/23
"""
from apps.autotest_my_app.case import BaseCase
from apps.autotest_my_app.widget import MyAppWidget
from src import sleep


class TestMyCase(BaseCase):

    def test_mycase_371(self):
        """大文件清理--扫描过程中点击返回按钮：验证返回按钮只退出插件视图,
        不取消 daemon 侧正在进行的大文件扫描任务

        源码依据(plugin-large-file):
        - LargeFilePlugin::stop() 仅调用 widget_->stopLoad();
        - stopLoad() 只置 loadStarted_=false 并切回扫描外视图;
        - 插件从未调用 org.deepin.PCManager1.StopLargeFileScan,
          取消入口只挂在 daemon 接口上。
        任务状态取自 daemon 的 Task 对象属性, 取消路径会写入 status="cancelled"。
        """
        widget = MyAppWidget(check_start=False)
        # 前置：确保电脑管家已关闭
        widget.kill_pc_manager()
        # 制造足量文件, 保证"点击返回"必然落在扫描进行中的窗口内
        widget.create_scan_slow_fixture()
        # 启动电脑管家
        widget.start_pc_manager()
        self.assert_true(widget.get_pc_manager_process_status())
        # 经会话总线启动扫描, 并等待任务进入 running
        task_path, detail = widget.start_large_file_scan_via_dbus()
        self.assert_true(task_path or detail)
        running = False
        for _ in range(15):
            if widget.get_large_file_scan_task_state(task_path)["status"] == "running":
                running = True
                break
            sleep(1)
        self.assert_true(running)
        # 导航到系统优化页面
        widget.click_optimization_nav_by_attr()
        self.assert_true(widget.get_optimization_page_showing())
        # 点击"大文件清理"卡片, 进入扫描视图(复用已启动的任务)
        widget.click_optimization_card_by_name("大文件清理")
        self.assert_true(widget.get_optimization_runtime_page_showing())
        # 返回前确保扫描仍在进行: 已扫完则重新触发一次扫描, 拿到新的进行窗口
        pre_back = widget.get_large_file_scan_task_state(task_path)
        if pre_back["status"] != "running":
            task_path, detail = widget.start_large_file_scan_via_dbus()
            self.assert_true(task_path or detail)
            for _ in range(20):
                pre_back = widget.get_large_file_scan_task_state(task_path)
                if pre_back["status"] == "running":
                    break
                sleep(0.2)
        self.assert_equal("running", pre_back["status"])
        # 在扫描过程中点击返回按钮: 点击后立即读状态, 不等页面切换
        widget.click_back_button(wait=0)
        after = widget.get_large_file_scan_task_state(task_path)
        self.assert_equal("running", after["status"])
        # 等页面切回系统优化页面
        sleep(2)
        self.assert_true(widget.get_optimization_page_showing())
        # 断言1：返回后扫描未被取消, 任务继续跑到成功
        final = {}
        for _ in range(80):
            final = widget.get_large_file_scan_task_state(task_path)
            if final["status"].startswith("success") or final["status"] == "cancelled":
                break
            sleep(0.2)
        self.assert_not_equal("cancelled", final["status"])
        self.assert_false(final["status"].startswith("failure"))
        self.assert_true(final["status"].startswith("success"))
        # 断言2：重新进入页面后扫描任务仍然可用(存在且未被取消), 页面正常回到扫描视图
        widget.click_optimization_card_by_name("大文件清理")
        self.assert_true(widget.get_optimization_runtime_page_showing())
        again = {}
        for _ in range(10):
            again = widget.get_large_file_scan_task_state(task_path)
            if again["status"]:
                break
            sleep(0.5)
        self.assert_not_equal("", again["status"])
        self.assert_not_equal("cancelled", again["status"])
        # 清理：取消扫描、删除夹具并关闭电脑管家
        widget.stop_large_file_scan_via_dbus()
        widget.remove_scan_slow_fixture()
        widget.kill_pc_manager()

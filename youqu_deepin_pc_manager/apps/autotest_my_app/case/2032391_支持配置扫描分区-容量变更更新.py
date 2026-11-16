#!/usr/bin/env python3
# _*_ coding:utf-8 _*_
"""
:Author:ut000635
:Date  :2026/10/12
"""
import pytest

from apps.autotest_my_app.case import BaseCase


class TestMyCase(BaseCase):

    def test_mycase_201(self):
        """支持配置扫描分区-容量变更更新

        覆盖描述:
        - 前置: sda4/sda2 挂 /media/autotest_a|b; 用 device-mapper 在
          /dev/sda6 上建 5GB 线性卷并挂 /media/autotest_c, 设置页显示 3 行;
        - 步骤: 将 dm 卷扩容到 8GB(suspend/reload/resume), 重开设置页;
        - 预期: C 行容量字段由 5GB 更新为 8GB, A/B 行不变。

        跳过原因(2026-11-16, 实测后改为 Skip, 不触碰任何分区):
        本用例的构造必须有一块**可牺牲的内置、非 removable 分区**做
        dm-linear 底层, 本机三条路都不成立:
        1. 原实现直接在 /dev/sda6 上建 dm-linear 并 mkfs —— mkfs 写的是底层
           设备前 5GiB, 覆盖了 sda6 原 25GiB ext4 的超级块/块组描述符,
           该盘从此只剩 5GiB 可用; 随后 043(需要 5GiB 大文件) 直接 ENOSPC。
           这块盘同时是 190/191/192/041/043 的构造用测试数据盘, 不能每次
           被清空重建;
        2. 改用 /data 稀疏镜像 + loop + dm 实测不可行: setup 与 5GiB 容量都
           正常, 但产品按 ADR 0007 过滤 loop 后端设备, 扫描分区列表只出现
           2 行(autotest_a/autotest_b), autotest_c 不出现;
        3. /dev/sdb1 是外接 U 盘, 产品按"外接设备剔除"黑名单过滤。
        补齐第二块可牺牲内置分区后, 恢复 dm-linear 构造即可去掉本 skip;
        届时仍需保证 mkfs 只落在该专用分区上。
        """
        pytest.skip(
            "缺可牺牲的内置非 removable 分区: 产品过滤 loop 后端设备"
            "(ADR 0007)与外接盘, 本机唯一候选 /dev/sda6 是测试数据盘, "
            "在其上 mkfs 会破坏 190/191/192/041/043 的构造前提"
        )

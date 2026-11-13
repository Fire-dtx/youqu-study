#!/usr/bin/env python3
# _*_ coding:utf-8 _*_

# SPDX-FileCopyrightText: 2023 UnionTech Software Technology Co., Ltd.

# SPDX-License-Identifier: GPL-2.0-only
# pylint: disable=C0114,C0103
import os
import re
import sys
import time
import difflib
from collections import defaultdict
from typing import Union

from setting.globalconfig import GlobalConfig
from src import logger
from src.cmdctl import CmdCtl
from src.custom_exception import ElementNotFound
from src.custom_exception import ApplicationStartError

try:
    from src.depends.dogtail.tree import SearchError
    from src.depends.dogtail.tree import root
    from src.depends.dogtail.tree import predicate
    from src.depends.dogtail.tree import config
    from src.depends.dogtail.tree import Node

    config.childrenLimit = 1000
    # config.logDebugToStdOut = False
    config.logDebugToFile = False
    config.searchCutoffCount = 2
    GlobalConfig.NO_DOGTAIL = False
except ModuleNotFoundError:
    GlobalConfig.NO_DOGTAIL = True

from src.mouse_key import MouseKey


# ===== 控件查找日志与统计 =====
# 日志统一在 find_elements_by_attr 输出, 覆盖所有调用点(用例直接调用与
# widget 封装)。格式固定为单行 key=value, 便于 grep/awk 汇总:
#   [控件查找] 结果=真实未命中 hit=0 probe=0 expr=$//repair_runtimePage//开始修复 count=0
#              cost=0.41s caller=... 目标name='开始修复' 同名控件=无 匿名控件=48(未设name/objectName)
#              已命名控件=187 匿名类型=[filler]44|[push button]2 匿名文本=[label]'磁盘工具' 遍历节点=331
#   以上字段(含匿名控件文本)全部输出在同一条 WARNING 内, 不拆多行;
#   grep 锚点: "[控件查找]" 全部, "结果=真实未命中" 只看真实问题, "匿名文本=" 只看未设 name 的控件文本。
#   [控件查找] 结果=直接命中 hit=1 probe=0 expr=$//repair_startBtn name='开始修复' ...
#   [控件查找] 结果=候选未命中(回退探测) hit=0 probe=1 expr=$//detectionFullScanPage ...
#   [控件查找] 结果=候选命中(回退命中) hit=1 probe=1 expr=$//detection_fullScanPage ...
# probe=0 是直接查找(未命中=用例要的控件不存在); probe=1 是多候选回退的探测
# (V20/V25 双写, 未命中属预期)。候选探测默认不输出, UI_LOOKUP_VERBOSE=1 时
# 输出全部; 默认每个 (表达式, 结果) 只输出一次, 避免轮询等待刷屏。
_LOOKUP_STATS = defaultdict(
    lambda: {"hit": 0, "miss": 0, "probe_hit": 0, "probe_miss": 0}
)
_LOOKUP_LOGGED = set()
_CURRENT_CASE = None
_CASE_MISS = defaultdict(set)


def _lookup_verbose():
    return os.environ.get("UI_LOOKUP_VERBOSE", "").lower() in ("1", "true", "yes")


def _lookup_caller(skip=1):
    """获取控件查找的调用点(文件:行号:函数)"""
    try:
        frame = sys._getframe(skip + 1)
        return (
            f"{os.path.basename(frame.f_code.co_filename)}:"
            f"{frame.f_lineno}:{frame.f_code.co_name}"
        )
    except BaseException:
        return "?"


def set_current_case(case_name):
    """由 pytest 钩子设置当前用例, 用于按用例统计未命中表达式"""
    global _CURRENT_CASE
    _CURRENT_CASE = case_name


def _node_text(node, max_len=30):
    """读取控件文本(Text 接口 -> description), 供匿名控件识别用"""
    text = ""
    try:
        text = str(node.text or "").strip()
    except BaseException:
        text = ""
    if not text:
        try:
            text = str(getattr(node, "description", "") or "").strip()
        except BaseException:
            text = ""
    # 压平换行/制表, 去掉日志分隔符 |, 保证整条诊断始终是单行 key=value
    text = re.sub(r"\s+", " ", text).replace("|", "/")
    return text[:max_len]


def _lookup_tree_diag(obj, expr, limit_nodes=3000):
    """未命中时统计 AT-SPI 树: 目标 name 是否存在、匿名控件(未设 name)数量与文本"""
    target = re.split(r"(?<!\\)/", expr.rstrip("/"))[-1].replace(r"\/", "/")
    if not target or target == "*":
        return ""
    stack = list(obj) if isinstance(obj, list) else [obj]
    names, anonymous, seen = set(), 0, 0
    anon_texts, anon_sampled = [], 0
    anon_roles = defaultdict(int)
    while stack and seen < limit_nodes:
        node = stack.pop()
        seen += 1
        try:
            name = (node.name or "").strip()
        except BaseException:
            name = ""
        if name:
            names.add(name)
        else:
            anonymous += 1
            try:
                anon_roles[node.roleName] += 1
            except BaseException:
                anon_roles["?"] += 1
            # 匿名控件太多, 只采样前 30 个并保留最多 8 条非空文本, 避免日志刷屏
            if anon_sampled < 100 and len(anon_texts) < 8:
                anon_sampled += 1
                text = _node_text(node)
                if text:
                    try:
                        role = node.roleName
                    except BaseException:
                        role = "?"
                    anon_texts.append(f"[{role}]'{text}'")
        try:
            stack.extend(node.children)
        except BaseException:
            continue
    same = "有" if target in names else "无"
    near = [
        n
        for n in difflib.get_close_matches(target, names, n=6, cutoff=0.6)
        if n != target
    ][:5]
    detail = (
        f"目标name={target!r} 同名控件={same} "
        f"匿名控件={anonymous}(未设name/objectName) 已命名控件={len(names)} "
    )
    if anon_roles:
        top_roles = sorted(anon_roles.items(), key=lambda i: -i[1])[:5]
        detail += "匿名类型=" + "|".join(f"[{r}]{c}" for r, c in top_roles) + " "
    if anon_texts:
        detail += "匿名文本=" + "|".join(anon_texts) + " "
    detail += f"遍历节点={seen}"
    if near:
        detail += " 相近name=" + "|".join(repr(n) for n in near)
    return detail


def _lookup_log(expr, elements, cost, probe, caller, obj=None):
    hit = bool(elements)
    stat = _LOOKUP_STATS[expr]
    key = ("probe_" if probe else "") + ("hit" if hit else "miss")
    stat[key] += 1
    # 只有直接查找的未命中才算"找不到控件"; 多候选回退(V20/V25 双写)
    # 的未命中是预期行为, 单独统计, 避免汇总误报。
    if not hit and not probe and _CURRENT_CASE:
        _CASE_MISS[_CURRENT_CASE].add(expr)

    verbose = _lookup_verbose()
    # 候选回退(probe)默认不输出, 否则 V20/V25 双写会产生大量预期内的未命中;
    # UI_LOOKUP_VERBOSE=1 时输出全部, 每行带 probe=1 与直接查找区分。
    if probe and not verbose:
        return
    log_key = (expr, hit)
    if not verbose and log_key in _LOOKUP_LOGGED:
        return
    _LOOKUP_LOGGED.add(log_key)

    probe_tag = 1 if probe else 0
    # 中文结果字段放在行首: 一眼区分"这条路真的找不到控件"与"多候选回退中
    # 的预期未命中", 不必再解读 hit/probe 数字。
    if hit:
        result = "候选命中(回退命中)" if probe else "直接命中"
    else:
        result = "候选未命中(回退探测)" if probe else "真实未命中"
    if hit:
        element = elements[0]
        try:
            name = element.name
            role = element.roleName
            size = element.size
        except BaseException:
            name, role, size = "?", "?", "?"
        logger.info(
            f"[控件查找] 结果={result} hit=1 probe={probe_tag} expr={expr} "
            f"count={len(elements)} name={name!r} role={role!r} size={size} "
            f"cost={cost:.2f}s caller={caller}"
        )
    else:
        # 直接未命中: 扫描一次 AT-SPI 树, 说明"树里到底有没有这个 name"、
        # 有多少匿名控件(未设 name/objectName), 以及可能的近似名称。
        # 候选回退(probe)不做该扫描, 未命中属预期, 且避免重复开销。
        diag = ""
        if obj is not None and not probe and expr.startswith("$"):
            try:
                diag = _lookup_tree_diag(obj, expr)
            except BaseException:
                diag = ""
        suffix = f" {diag}" if diag else ""
        logger.warning(
            f"[控件查找] 结果={result} hit=0 probe={probe_tag} expr={expr} count=0 "
            f"cost={cost:.2f}s caller={caller}{suffix}"
        )


def log_lookup_summary():
    """会话结束输出控件查找汇总(表达式维度 + 用例维度)"""
    miss_exprs = [(expr, s) for expr, s in _LOOKUP_STATS.items() if s["miss"]]
    miss_cases = {case: exprs for case, exprs in _CASE_MISS.items() if exprs}
    probe_miss = sum(s["probe_miss"] for s in _LOOKUP_STATS.values())
    logger.info(
        f"[控件查找汇总] 表达式={len(_LOOKUP_STATS)} "
        f"直接未命中表达式={len(miss_exprs)} 直接未命中用例={len(miss_cases)} "
        f"回退探测未命中次数={probe_miss}"
    )
    for expr, stat in sorted(miss_exprs, key=lambda i: (-i[1]["miss"], i[0])):
        logger.info(
            f"[控件查找汇总] expr={expr} 结果=真实未命中 hit={stat['hit']} "
            f"miss={stat['miss']} probe_hit={stat['probe_hit']} "
            f"probe_miss={stat['probe_miss']}"
        )
    for case, exprs in sorted(miss_cases.items()):
        logger.info(
            f"[控件查找汇总] case={case} miss={len(exprs)} "
            f"exprs={','.join(sorted(exprs))}"
        )


class DogtailUtils(MouseKey):
    """
    通过属性进行元素定位和操作。
    """

    # pylint: disable=too-many-arguments,too-many-locals,too-many-public-methods
    __author__ = "Mikigo <huangmingqiang@uniontech.com>, Litao <litaoa@uniontech.com>"

    def __init__(self, name=None, description=None, number=-1, check_start=True, key: dict = None):
        if GlobalConfig.NO_DOGTAIL:
            raise EnvironmentError("Dogtail 及其相关依赖存在问题,调用相关方法失败~")
        config.logDebugToStdOut = False
        self.name = name
        self.description = description
        try:
            if name:
                self.obj = root.application(self.name, self.description)
            else:
                self.obj = root
            if number > 0:
                self.obj = self.obj.findChildren(predicate.GenericPredicate(**key))[number]

        except SearchError:
            if check_start:
                search_app = CmdCtl.run_cmd(f"ps -ef | grep {self.name}")
                logger.error(search_app)
                raise ApplicationStartError(self.name) from SearchError

    def app_element(self, *args, **kwargs) -> Node:
        """
         获取app元素的对象
        :return: 元素的对象
        """
        try:
            element = self.obj.child(*args, **kwargs, retry=False)
            logger.debug(f"{args, kwargs} 获取元素对象 <{element}>")
            return element
        except SearchError:
            raise ElementNotFound(*args, **kwargs) from SearchError

    def get_element_children_text(self, element):
        element = self.app_element(element)
        all_children = element.children
        text = []
        for i in range(len(all_children)):
            text.append(all_children[i].name)
        return text

    def left_upper_corner_position(self, element) -> tuple:
        """
         获取元素左上角的坐标
        :param element: 元素名称
        :return: 元素左上角坐标
        """
        position = self.app_element(element).position
        logger.debug(f"获取元素 {element}元素左上角坐标 {position}")
        return position

    def element_size(self, *args, **kwargs) -> tuple:
        """
         获取元素的大小
        :return: 元素大小
        """
        size = self.app_element(*args, **kwargs).size
        logger.debug(f"元素{args, kwargs} 的大小 {size}")
        return size

    def right_upper_corner_position(self, element) -> tuple:
        """
         获取元素右上角的坐标
        :param element: 元素名称
        :return: 元素右上角坐标
        """
        _x = self.left_upper_corner_position(element)[0] + self.element_size(element)[0]
        _y = self.left_upper_corner_position(element)[1]
        logger.debug(f"获取元素 {element}, 右上角坐标 ({_x, _y})")
        return int(_x), int(_y)

    def element_center(self, element) -> tuple:
        """
         获取元素的中心位置
        :param element:
        :return: 元素中心坐标
        """
        _x, _y, _w, _h = self.app_element(element).extents
        _x = _x + _w / 2
        _y = _y + _h / 2
        logger.debug(f"获取元素中心坐标 ({_x, _y})")
        return _x, _y

    def element_click(self, element, button=1):
        """
         元素点击
        :param element: 应用的元素
        :param button: 1>left,2>middle,3>right
        :return: None
        """
        logger.debug(
            f"""{"左键" if button == 1 else f"{'右键' if button == 3 else '鼠标中健'}"} 点击元素 {element}"""
        )
        mouse_click = (
            self.click if button == 1 else self.right_click if button == 3 else self.middle_click
        )
        mouse_click(*self.element_center(element))

    def element_double_click(self, element):
        """
         元素双击
        :return: None
        """
        logger.debug(f"双击元素 {element}")
        self.double_click(*self.element_center(element))

    def element_point(self, element):
        """
         鼠标移动到元素上（位置是在元素的中心）
        :param element: 应用的元素
        :return: None
        """
        logger.debug(f"鼠标移至元素 {element} 中心")
        self.move_to(*self.element_center(element))

    @staticmethod
    def __evalx(expr, element, recursive):
        """evalx"""
        node = re.match(".*?[^\\\\]/", expr)
        if node:
            name = node.group().replace("\\/", "/")[:-1]
        else:
            return False
        if name == "*":
            element = element.children
        else:
            element = element.findChildren(predicate.GenericPredicate(name), recursive=recursive)
        return node, element

    def __trace(self, element, result, expr):
        if expr.startswith("//"):
            name = expr[2:]
            node, element = self.__evalx(name, element, recursive=True)
        elif expr.startswith("/"):
            name = expr[1:]
            node, element = self.__evalx(name, element, recursive=False)
        else:
            return False
        try:
            next_node = name[node.end() - 1:]
            if next_node != "/":
                for i in element:
                    self.__trace(i, result, next_node)
            else:
                result += element
        except SearchError:
            raise ElementNotFound(expr) from SearchError
        return result

    def find_elements_by_attr(self, expr, probe=False, _caller=None) -> Union[list, bool]:
        """
         通过层级获取元素
        :param expr: 元素定位 $/xx.xxx//xxx,  $根节点  /当前子节点， //递归查找子节点
        :param probe: True 表示多候选回退中的探测, 默认不输出日志
                      (UI_LOOKUP_VERBOSE=1 时输出)
        :return: 元素对象
        """
        caller = _caller or _lookup_caller(skip=1)
        start = time.perf_counter()
        raw_expr = expr
        result = []
        # 所有分支(命中/未命中/异常)统一走 finally 记一条日志, 诊断也在此触发
        try:
            if expr == "$":
                result = self.obj if isinstance(self.obj, list) else [self.obj]
                return result
            if not expr.startswith("$"):
                return False
            if not expr.endswith("/") or expr.endswith(r"\/"):
                expr = expr + "/"
            result = self.__trace(self.obj, [], expr[1:])
            return result
        finally:
            _lookup_log(
                raw_expr, result, time.perf_counter() - start, probe, caller, self.obj
            )

    def find_element_by_attr(self, expr, index=0, probe=False) -> Node:
        """
         查找界面元素
        :param expr: 匹配格式 元素定位 $/xxx//xxx,  $根节点  /当前子节点， //递归查找子节点
        :param index: 匹配结果索引
        :param probe: True 表示多候选回退中的探测, 默认不输出日志
        :return: 元素对象
        """
        elements = self.find_elements_by_attr(
            expr, probe=probe, _caller=_lookup_caller(skip=1)
        )
        if not elements:
            raise ElementNotFound(expr)
        try:
            return elements[index]
        except IndexError:
            raise ElementNotFound(f"{expr}, index:{index}") from IndexError

    def find_element_by_attr_and_click(self, expr, index=0):
        self.find_element_by_attr(expr, index).click()

    def find_element_by_attr_and_right_click(self, expr, index=0):
        self.find_element_by_attr(expr, index).click(3)

    def find_elements_to_the_end(self, ele_name):
        """
         递归查找应用界面的元素(适用于查找多个同名称元素)
        :param ele_name: 需要查找的元素名称
        :return: 查找到的元素对象的列表
        """
        eles = []
        root_ele = self.obj

        def recur_inter(node=None):
            if not node:
                node = root_ele
            children = node.children
            if children:
                for i in children:
                    if i.combovalue == ele_name:
                        eles.append(i)
                    recur_inter(i)

        recur_inter()
        return eles

# -*- coding: utf-8 -*-
"""全局「窗口尺寸 / 响应式布局」中枢（0.4.11 新增）。

为什么需要它
------------
0.4.10 及以前：

* 全项目只有 tetris / snake / dino 三个对局页监听 ``page.on_resize``，而且
  是直接给 ``page.on_resize`` 赋值 —— 后挂的页面会把先挂的回调覆盖掉，
  框架层更是一个监听都没有；
* 菜单 / 设置 / 房间 / 牌桌全部在**首次构建时**读一次 ``page.width``，
  ``Router`` 又把视图缓存起来。窗口从 800 拉到 1920 之后，卡片宽度、
  列数、棋盘尺寸永远停在「第一次进这个页面」时的数值；
* 各游戏的缩放逻辑普遍写成 ``min(固定上限, 可用宽度)``，只缩不放：
  宽屏上棋盘永远是手机时代那几百像素；
* ``page.width`` 在首帧可能还是 Flet 的默认小窗口值（甚至取不到），
  旧代码兜底成 420 的「手机宽」，于是把宽屏也画成窄屏。

本模块做四件事：

1. **唯一的 resize 所有者**：:func:`install` 只挂一次 ``page.on_resize``，
   之后所有页面用 :func:`subscribe` 登记回调，互不覆盖；
2. **尺寸真相**：:func:`page_width` / :func:`page_height` 优先取最近一次
   resize 事件的宽高，其次 ``page.width/height``，最后 ``page.window``；
3. **安全重排**：:func:`is_static_route` 标出哪些页面可以在尺寸变化后
   重建（菜单 / 设置这类无状态页）。正在进行的对局绝不重建，只走自己
   的订阅回调在原控件上改尺寸，棋局 / 分数 / 网络状态都不丢；
4. **根控件拉伸**：:func:`stretch_root` 让视图的根 Column 把整屏宽度
   传给顶栏与内容区（默认 ``CrossAxisAlignment.START`` 只给固有宽度）。
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

import flet as ft

# 拿不到任何尺寸时的兜底：按「普通桌面窗口」算，不再按 420 的手机宽算。
FALLBACK_WIDTH = 900.0
FALLBACK_HEIGHT = 700.0

# 哪些页面可以在窗口尺寸变化后「丢掉缓存重建」。
# 对局页 / 房间页 / 联机页有正在跑的协程、网络回调或棋局状态，一律不重建：
# 它们要么自己订阅 resize 原地改尺寸，要么下次进入时按新尺寸重建。
_STATIC_PATHS = {"/", "/single", "/profile", "/settings", "/history"}

# 状态挂在 page 实例上，避免模块级全局量在多 Page（web / 测试）之间串味。
_STATE_ATTR = "_atr_responsive_state"

# 订阅回调签名：(width, height)
ResizeCallback = Callable[[float, float], None]


class _State:
    """单个 Page 的响应式状态。"""

    def __init__(self) -> None:
        self.width = 0.0
        self.height = 0.0
        self.subscribers: dict[str, ResizeCallback] = {}
        self.on_change: Optional[ResizeCallback] = None
        self.previous: Optional[Callable] = None
        self.installed = False


def _state(page) -> _State:
    """取（必要时创建）该 Page 的响应式状态。"""
    st = getattr(page, _STATE_ATTR, None)
    if not isinstance(st, _State):
        st = _State()
        try:
            setattr(page, _STATE_ATTR, st)
        except Exception:                       # noqa: BLE001 — 只读桩对象
            pass
    return st


def _number(value) -> float:
    """把任意属性安全地转成正数，取不到就返回 0。"""
    try:
        n = float(value)
        return n if n > 0 else 0.0
    except Exception:                           # noqa: BLE001
        return 0.0


def _attr(obj, name: str) -> float:
    return _number(getattr(obj, name, None)) if obj is not None else 0.0


# ============================================================
# 尺寸读取
# ============================================================

def size(page) -> Tuple[float, float]:
    """当前可用视口尺寸（宽, 高），带多重兜底，永远不会返回 0。"""
    st = _state(page)
    w = st.width or _attr(page, "width") \
        or _attr(getattr(page, "window", None), "width")
    h = st.height or _attr(page, "height") \
        or _attr(getattr(page, "window", None), "height")
    return w or FALLBACK_WIDTH, h or FALLBACK_HEIGHT


def page_width(page, fallback: float = FALLBACK_WIDTH) -> float:
    """当前页面宽度（逻辑像素）。"""
    w = size(page)[0]
    return float(fallback) if w <= 0 else w


def page_height(page, fallback: float = FALLBACK_HEIGHT) -> float:
    """当前页面高度（逻辑像素）。"""
    h = size(page)[1]
    return float(fallback) if h <= 0 else h


def clamp(value: float, lo: float, hi: float) -> float:
    """把数值夹在 [lo, hi] 里。"""
    return max(lo, min(hi, value))


def zoom(page, base_width: float = 1100.0,
         lo: float = 1.0, hi: float = 1.5) -> float:
    """宽屏放大系数：按视口宽度线性放大，窄屏一律 1.0（不缩）。

    游戏里的「基准尺寸」都是按 1100 左右的中等桌面窗口定的；大屏乘上这个
    系数铺开，小屏保持原尺寸（原本的窄屏适配逻辑照旧负责缩小）。
    """
    return clamp(page_width(page) / float(base_width), lo, hi)


# ============================================================
# resize 事件总线
# ============================================================

def _dispatch(page, e) -> None:
    """唯一的 ``page.on_resize`` 处理器：先记尺寸，再分发给所有订阅者。"""
    st = _state(page)
    w = _number(getattr(e, "width", None)) or _attr(page, "width")
    h = _number(getattr(e, "height", None)) or _attr(page, "height")
    if w > 0:
        st.width = w
    if h > 0:
        st.height = h

    # 兼容 install 之前就挂了回调的老代码（例如第三方插件）。
    if st.previous is not None:
        try:
            st.previous(e)
        except Exception as exc:                # noqa: BLE001
            print(f"[responsive] 旧的 resize 回调出错：{exc!r}")

    w, h = size(page)
    for key, cb in list(st.subscribers.items()):
        try:
            cb(w, h)
        except Exception as exc:                # noqa: BLE001
            print(f"[responsive] 订阅者 {key} 重排失败：{exc!r}")
    if st.on_change is not None:
        try:
            st.on_change(w, h)
        except Exception as exc:                # noqa: BLE001
            print(f"[responsive] 全局重排失败：{exc!r}")


def install(page, on_change: Optional[ResizeCallback] = None) -> None:
    """安装全局 resize 分发器（幂等，重复调用只更新 ``on_change``）。"""
    st = _state(page)
    st.on_change = on_change
    if st.installed:
        return
    st.previous = getattr(page, "on_resize", None)
    st.installed = True

    def _handler(e):
        _dispatch(page, e)

    try:
        page.on_resize = _handler
    except Exception as exc:                    # noqa: BLE001 — 测试桩
        st.installed = False
        print(f"[responsive] 无法接管 on_resize：{exc!r}")


def subscribe(page, key: str, callback: ResizeCallback) -> None:
    """登记一个按 key 去重订阅者（同 key 后来者覆盖前者）。

    ``key`` 形如 ``"chess.play"``：路由缓存里可能同时存在旧 / 新两个对局
    实例，用 key 覆盖能保证只有**最新那一个**收到尺寸变化。
    """
    _state(page).subscribers[key] = callback


def unsubscribe(page, key: str, callback: Optional[ResizeCallback] = None) -> None:
    """注销订阅；给了 callback 时只在它仍是当前订阅者时才删。"""
    subs = _state(page).subscribers
    if callback is not None and subs.get(key) is not callback:
        return
    subs.pop(key, None)


def dispatch(page, width: float, height: float) -> None:
    """手动派发一次尺寸变化（窗口模式切换 / 测试时用）。"""
    st = _state(page)
    if width > 0:
        st.width = float(width)
    if height > 0:
        st.height = float(height)

    class _E:
        pass

    e = _E()
    e.width, e.height = size(page)
    _dispatch(page, e)


# ============================================================
# 布局辅助
# ============================================================

def is_static_route(path: str) -> bool:
    """这条路由能不能在窗口尺寸变化后安全重建？

    核心静态页 + 各游戏子菜单首页（``/g/<id>``，只有两段）可以；
    对局页、房间页、联机页等带状态的页面一律 False。
    """
    if not path:
        return False
    if path in _STATIC_PATHS:
        return True
    return path.startswith("/g/") and path.count("/") == 2


def stretch_root(control):
    """让视图根 Column 横向撑满（返回原控件，方便链式调用）。

    Flet 的 Column 默认 ``CrossAxisAlignment.START``：子控件只拿到「固有
    宽度」的宽松约束，顶栏和内容区都缩在左边。改成 STRETCH 后它们会收到
    整屏宽度的紧约束，卡片网格 / 顶栏才能铺满。
    """
    try:
        if isinstance(control, ft.Column) and \
                control.horizontal_alignment == ft.CrossAxisAlignment.START:
            control.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    except Exception:                           # noqa: BLE001
        pass
    return control

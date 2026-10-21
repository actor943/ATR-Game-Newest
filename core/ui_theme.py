# -*- coding: utf-8 -*-
"""界面风格总控：当前用哪套皮、怎么切、切完怎么让全世界立刻跟上。

三层配合
--------
1. **包**（``core/ui_packs/``）：自带颜色令牌与零件工厂；
2. **本模块**：读设置里的 ``ui_pack``，把当前包的分发函数暴露给视图
   （``ui.button`` / ``ui.panel`` / ``ui.text`` …）；
3. **``core/theme.T``**：切换时把包的令牌**覆写**到 ``T`` 上 —— 这样所有
   直接用 ``T.TEXT_PRIMARY`` 的老界面（掼蛋牌桌、设置页……）**一行不改**
   就跟着换色；明暗主题开关则把令牌恢复成默认包的那一套。

切换后要做两件事，缺一不可：
* ``invalidate`` 全部路由缓存（否则看到的还是旧控件树）；
* 重新 ``navigate`` 当前路径（重建视图，新皮才上身）。
"""

from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from core import settings as settings_mod
from core import theme
from core.ui_packs import registry as packs

_CURRENT_ID: Optional[str] = None


# ------------------------------------------------------------------
# 当前包
# ------------------------------------------------------------------

def current_id() -> str:
    """当前界面包 id（没设置过就默认包）。"""
    global _CURRENT_ID
    if _CURRENT_ID is None:
        try:
            _CURRENT_ID = settings_mod.Settings.load().ui_pack
        except Exception:                       # noqa: BLE001 — 设置坏了也要能跑
            _CURRENT_ID = packs.default_id()
    return _CURRENT_ID or packs.default_id()


def current():
    """当前界面包对象（永远有皮可穿）。"""
    return packs.get(current_id())


def colors():
    """当前包的颜色令牌（新代码取色统一走这里）。"""
    return current().colors


def tone(name: str) -> str:
    return current().tone(name)


# ------------------------------------------------------------------
# 切换
# ------------------------------------------------------------------

def apply(pack_id: str, *, persist: bool = True) -> bool:
    """切换到指定界面包；返回是否切换成功。

    * 同步覆写 ``theme.T``（老界面自动换色）；
    * 按需写回 settings.json（下次启动还是这套皮）。
    """
    pack = packs.get(pack_id)
    if pack is None:
        return False
    global _CURRENT_ID
    _CURRENT_ID = pack.meta.id
    if hasattr(pack, "resync"):               # 材料包要按明暗重新取令牌
        pack.resync()
    theme.apply_pack(pack)
    if persist:
        try:
            data = settings_mod.Settings.load()
            data.ui_pack = pack.meta.id
            data.save()
        except Exception:                       # noqa: BLE001
            pass
    return True


def refresh(page: ft.Page, navigate: Callable[[str], None]) -> None:
    """让界面立刻换成新皮：丢掉所有路由缓存，重建当前页。"""
    from core.registry import all_routes
    from core.router import Router

    router = Router.current
    path = router.current_path() if router is not None else "/"
    if router is not None:
        for spec in all_routes():
            router.invalidate(spec.path)
        router.invalidate(None)                 # 兜底：清整个缓存
    navigate(path or "/")


def ensure_loaded() -> None:
    """启动时调用一次：按设置把皮穿上（app.run 里用）。"""
    apply(current_id(), persist=False)


# ------------------------------------------------------------------
# 零件分发（视图层只 import 本模块）
# ------------------------------------------------------------------

def text(value: str, size: int = 13, tone: str = "",
         weight: Optional[ft.FontWeight] = None,
         spacing: float = 0.0) -> ft.Text:
    return current().text(value, size, tone, weight, spacing)


def hint(value: str, tone: str = "dim") -> ft.Text:
    return current().hint(value, tone)


def title(value: str, size: int = 20) -> ft.Control:
    return current().title(value, size)


def divider() -> ft.Control:
    return current().divider()


def pill(value: str, *, tone: str = "gold") -> ft.Control:
    return current().pill(value, tone=tone)


def panel(content: ft.Control, *, padding: int = 12,
          expand: Optional[bool] = None,
          bgcolor: Optional[str] = None) -> ft.Control:
    return current().panel(content, padding=padding, expand=expand,
                           bgcolor=bgcolor)


def scroll_box(content: ft.Control, *, height: Optional[int] = None,
               expand: bool = False) -> ft.Control:
    return current().scroll_box(content, height=height, expand=expand)


def button(text_: str, icon: Optional[str] = None,
           on_click: Optional[Callable] = None, *, primary: bool = True,
           enabled: bool = True, width: Optional[int] = None,
           height: int = 44) -> ft.Control:
    return current().button(text_, icon, on_click, primary=primary,
                            enabled=enabled, width=width, height=height)


def icon_button(icon: str, on_click: Optional[Callable] = None,
                *, tooltip: str = "") -> ft.Control:
    return current().icon_button(icon, on_click, tooltip=tooltip)


def chip(label: str, *, active: bool,
         on_click: Optional[Callable] = None) -> ft.Control:
    return current().chip(label, active=active, on_click=on_click)


def field(label: str, value: str = "", *, hint_: str = "",
          on_submit: Optional[Callable] = None, expand: bool = True,
          max_length: Optional[int] = None,
          ref: Optional[ft.Ref] = None) -> ft.Control:
    """输入框（参数名 ``hint_`` 是为了不和视图里的局部变量撞名）。"""
    return current().field(label, value, hint=hint_, on_submit=on_submit,
                           expand=expand, max_length=max_length, ref=ref)


def card(title_: str, description: str, icon: str,
         on_click: Optional[Callable] = None, *, available: bool = True,
         width: Optional[int] = None) -> ft.Control:
    return current().card(title_, description, icon, on_click,
                          available=available, width=width)


def bar(title_: str, on_back: Optional[Callable] = None,
        actions: Optional[List[ft.Control]] = None) -> ft.Control:
    return current().bar(title_, on_back, actions)


def page(title_: str, content: ft.Control,
         on_back: Optional[Callable] = None,
         actions: Optional[List[ft.Control]] = None) -> ft.Control:
    return current().page(title_, content, on_back, actions)


def wrap(control: ft.Control) -> ft.Control:
    return current().wrap(control)


# ---- 联机专用件 ----


def slot(label: str = "空位", *, on_click: Optional[Callable] = None,
         width: int = 150, height: int = 76) -> ft.Control:
    return current().slot(label, on_click=on_click, width=width, height=height)


def taken_slot(nick: str, *, host: bool = False, talking: bool = False,
               muted: bool = False, width: int = 150,
               height: int = 76) -> ft.Control:
    return current().taken_slot(nick, host=host, talking=talking, muted=muted,
                                width=width, height=height)


def chat_row(nick: str, text_: str, *, own: bool = False,
             system: bool = False) -> ft.Control:
    return current().chat_row(nick, text_, own=own, system=system)


def level_bar(level: float, width: int = 90) -> ft.Control:
    return current().level_bar(level, width)


def all_packs() -> List:
    """设置页用：全部可安装的界面包（含以后的社区包）。"""
    return packs.all()

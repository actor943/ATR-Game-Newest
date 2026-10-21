# -*- coding: utf-8 -*-
"""UI 包（界面皮肤）的**契约**：一个包要提供哪些颜色、哪些零件。

为什么要有这一层
----------------
以前界面零件散落在 ``core/ui_common.py`` 和 ``core/views/ui_rustic.py`` 两处，
想换风格就得改视图代码。0.4.7 起把「风格」抽成可安装的包：

* 每个包自带一套**颜色令牌**（:class:`ColorTokens`）和一组**零件工厂**
  （按钮 / 面板 / 输入框 / 标题 / 卡片……），签名完全一致；
* 视图只面向 :mod:`core.ui_theme` 编程，**不关心当前是哪套皮**；
* 想加第三套（社区包、节日皮、像素皮）只要再写一个模块并 ``register()``，
  设置页的「界面风格」下拉会自动多出一项。

给作者的话
----------
* 颜色别硬编码进零件：一律从 ``self.colors`` 取，否则换主题会漏；
* 语义色（``text`` / ``dim`` / ``gold`` / ``danger`` / ``ok``）由
  :meth:`BasePack.tone` 统一翻译，视图里只写语气不写色值；
* 所有零件都要在**窄屏**（360dp）下不溢出 —— 房间页要放 4 个席位，
  牌桌要放 27 张手牌，宽度是硬约束。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Protocol

import flet as ft


# ------------------------------------------------------------------
# 颜色令牌
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ColorTokens:
    """一套界面用到的全部颜色（视图不直接写字面色值，只拿令牌）。"""

    # 层次：底 → 面 → 浮起的面 → 描边 → 分割线
    bg: str = "#F6F7F9"
    surface: str = "#FFFFFF"
    surface_alt: str = "#EEF1F5"
    border: str = "#D8DEE6"
    divider: str = "#E5E9EF"
    # 文字
    text: str = "#1B2430"
    text_secondary: str = "#5A6675"
    text_muted: str = "#8A94A3"
    # 语义色
    primary: str = "#2563EB"
    on_primary: str = "#FFFFFF"
    accent: str = "#F59E0B"
    danger: str = "#DC2626"
    success: str = "#16A34A"
    # 强调（标题 / 房主标 / 金币）
    gold: str = "#B8860B"
    gold_light: str = "#8A6508"
    # 输入框凹槽
    ink: str = "#FFFFFF"
    slot_empty: str = "#F1F4F8"


# 语气 → 颜色字段名（视图只写语气，包里决定色值）
TONE_FIELDS: Dict[str, str] = {
    "": "text",
    "dim": "text_muted",
    "secondary": "text_secondary",
    "primary": "primary",
    "accent": "accent",
    "gold": "gold",
    "danger": "danger",
    "ok": "success",
    "on_primary": "on_primary",
}


# ------------------------------------------------------------------
# 零件工厂的协议（类型提示用，运行时不强制继承）
# ------------------------------------------------------------------

class UIPack(Protocol):
    """一个界面包要长相的东西。

    实现方（material / rustic / 未来的社区包）照抄这些方法名与签名即可。
    """

    meta: "PackMeta"
    colors: ColorTokens

    # ---- 颜色 ----
    def tone(self, name: str) -> str: ...

    # ---- 文字 ----
    def text(self, value: str, size: int = 13, tone: str = "",
             weight: Optional[ft.FontWeight] = None,
             spacing: float = 0.0) -> ft.Text: ...

    def hint(self, value: str, tone: str = "dim") -> ft.Text: ...

    def title(self, value: str, size: int = 20) -> ft.Control: ...

    def divider(self) -> ft.Control: ...

    def pill(self, value: str, *, tone: str = "gold") -> ft.Control: ...

    # ---- 容器 ----
    def panel(self, content: ft.Control, *, padding: int = 12,
              expand: Optional[bool] = None,
              bgcolor: Optional[str] = None) -> ft.Control: ...

    def scroll_box(self, content: ft.Control, *, height: Optional[int] = None,
                   expand: bool = False) -> ft.Control: ...

    # ---- 控件 ----
    def button(self, text: str, icon: Optional[str] = None,
               on_click: Optional[Callable] = None, *, primary: bool = True,
               enabled: bool = True, width: Optional[int] = None,
               height: int = 44) -> ft.Control: ...

    def icon_button(self, icon: str, on_click: Optional[Callable] = None,
                    *, tooltip: str = "") -> ft.Control: ...

    def chip(self, label: str, *, active: bool,
             on_click: Optional[Callable] = None) -> ft.Control: ...

    def field(self, label: str, value: str = "", *, hint: str = "",
              on_submit: Optional[Callable] = None, expand: bool = True,
              max_length: Optional[int] = None,
              ref: Optional[ft.Ref] = None) -> ft.Control: ...

    def card(self, title: str, description: str, icon: str,
             on_click: Optional[Callable] = None, *, available: bool = True,
             width: Optional[int] = None) -> ft.Control: ...

    # ---- 页面骨架 ----
    def bar(self, title_text: str, on_back: Optional[Callable] = None,
            actions: Optional[List[ft.Control]] = None) -> ft.Control: ...

    def page(self, title_text: str, content: ft.Control,
             on_back: Optional[Callable] = None,
             actions: Optional[List[ft.Control]] = None) -> ft.Control: ...

    def wrap(self, control: ft.Control) -> ft.Control: ...

    # ---- 联机专用件 ----
    def slot(self, label: str = "空位", *, on_click: Optional[Callable] = None,
             width: int = 150, height: int = 76) -> ft.Control: ...

    def taken_slot(self, nick: str, *, host: bool = False,
                   talking: bool = False, muted: bool = False,
                   width: int = 150, height: int = 76) -> ft.Control: ...

    def chat_row(self, nick: str, text: str, *, own: bool = False,
                 system: bool = False) -> ft.Control: ...

    def level_bar(self, level: float, width: int = 90) -> ft.Control: ...


# ------------------------------------------------------------------
# 元信息
# ------------------------------------------------------------------

@dataclass(frozen=True)
class PackMeta:
    """包的身份证（设置页里列给人看的就是这些）。"""

    id: str
    name: str
    description: str
    author: str = "ATR Game"
    version: str = "1.0"
    builtin: bool = True        # False = 社区包（以后从 packs/ 目录加载）


@dataclass
class BasePack:
    """公共底座：tone 翻译 + 一些两种风格都能复用的排版。"""

    meta: PackMeta
    colors: ColorTokens
    radius: int = 8
    padding: int = 16

    # ---------------- 颜色 ----------------

    def tone(self, name: str) -> str:
        """语气 → 具体色值（未知语气回落到正文色，不让界面变透明）。"""
        field_name = TONE_FIELDS.get(name, "text")
        return getattr(self.colors, field_name, self.colors.text)

    # ---------------- 文字 ----------------

    def text(self, value: str, size: int = 13, tone: str = "",
             weight: Optional[ft.FontWeight] = None,
             spacing: float = 0.0) -> ft.Text:
        return ft.Text(
            value, size=size, color=self.tone(tone), weight=weight,
            style=ft.TextStyle(letter_spacing=spacing) if spacing else None,
            selectable=True,
        )

    def hint(self, value: str, tone: str = "dim") -> ft.Text:
        return self.text(value, 12, tone)

    def pill(self, value: str, *, tone: str = "gold") -> ft.Control:
        bg = self.tone(tone)
        # 深色底配浅字、浅色底配深字（Container 没有 color 参数，别乱传）
        dark_bg = tone in ("primary", "accent", "gold", "danger")
        fg_tone = "on_primary" if dark_bg else "dim"
        return ft.Container(
            content=self.text(value, 11, fg_tone, ft.FontWeight.BOLD, 1.0),
            bgcolor=bg,
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
        )

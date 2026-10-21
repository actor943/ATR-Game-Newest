# -*- coding: utf-8 -*-
"""主题与配色：浅色 / 深色双配色板 + 动态代理 ``T``。

视图代码用法不变：``from core.theme import T``，然后 ``T.BG``。
``T`` 是一个代理对象，取属性时转发到「当前配色板」，
因此切换主题后**重建**的视图会自动取到新颜色。

牌面（``CARD_*`` / ``JOKER_*`` / ``WILD_*``）在两种主题下保持一致：
牌就是牌，白底红黑字不随主题变。
"""

from __future__ import annotations

from typing import Any

import flet as ft


class _LightPalette:
    """浅色配色板（默认，与 0.3 / 0.4.0 完全一致）。"""

    # 背景层
    BG = "#FAFAFA"
    SURFACE = "#FFFFFF"
    SURFACE_ALT = "#F1F4F8"

    # 强调
    PRIMARY = "#1976D2"
    PRIMARY_DARK = "#0D47A1"
    ACCENT = "#FF6F00"
    ACCENT_SOFT = "#FFE0B2"

    # 状态
    DANGER = "#E53935"
    DANGER_SOFT = "#FFEBEE"
    SUCCESS = "#2E7D32"
    WARNING = "#F9A825"
    LEVEL_INFO = "#7B1FA2"

    # 文本
    TEXT_PRIMARY = "#212121"
    TEXT_SECONDARY = "#616161"
    TEXT_MUTED = "#9E9E9E"
    TEXT_INVERT = "#FFFFFF"

    # 边框 / 分隔
    BORDER = "#E0E0E0"
    DIVIDER = "#ECEFF1"

    # 牌面（两种主题一致，与 0.3 保持不变）
    CARD_BG = "#FFFFFF"
    CARD_PLAYED = "#E0E0E0"
    CARD_BORDER = "#333333"
    WILD_BG = "#FFF9C4"
    WILD_BORDER = "#D4A017"
    JOKER_BG = "#FFF8E1"
    JOKER_BG_PLAYED = "#E0E0E0"
    JOKER_BORDER_BIG = "#FF6F00"
    JOKER_BORDER_SMALL = "#FFB300"
    JOKER_TEXT = "#BF360C"
    JOKER_TEXT_PLAYED = "#9E9E9E"

    # 等级按钮
    LEVEL_ACTIVE_BG = "#FFD54F"
    LEVEL_ACTIVE_TEXT = "#BF360C"

    # 尺寸
    CARD_W = 40
    CARD_H = 50
    JOKER_W = 48
    JOKER_H = 52
    GAP = 6
    PADDING = 16


class _DarkPalette:
    """深色配色板（Material 深色基准）。"""

    # 背景层
    BG = "#121212"
    SURFACE = "#1E1E1E"
    SURFACE_ALT = "#2A2A2A"

    # 强调
    PRIMARY = "#1976D2"
    PRIMARY_DARK = "#0D47A1"
    ACCENT = "#FFA726"
    ACCENT_SOFT = "#4E342E"

    # 状态
    DANGER = "#EF5350"
    DANGER_SOFT = "#3B1D1D"
    SUCCESS = "#66BB6A"
    WARNING = "#FDD835"
    LEVEL_INFO = "#CE93D8"

    # 文本
    TEXT_PRIMARY = "#EAEAEA"
    TEXT_SECONDARY = "#B0B0B0"
    TEXT_MUTED = "#808080"
    TEXT_INVERT = "#FFFFFF"

    # 边框 / 分隔
    BORDER = "#3A3A3A"
    DIVIDER = "#2C2C2C"

    # 牌面（两种主题一致）
    CARD_BG = "#FFFFFF"
    CARD_PLAYED = "#E0E0E0"
    CARD_BORDER = "#333333"
    WILD_BG = "#FFF9C4"
    WILD_BORDER = "#D4A017"
    JOKER_BG = "#FFF8E1"
    JOKER_BG_PLAYED = "#E0E0E0"
    JOKER_BORDER_BIG = "#FF6F00"
    JOKER_BORDER_SMALL = "#FFB300"
    JOKER_TEXT = "#BF360C"
    JOKER_TEXT_PLAYED = "#9E9E9E"

    # 等级按钮
    LEVEL_ACTIVE_BG = "#FFD54F"
    LEVEL_ACTIVE_TEXT = "#BF360C"

    # 尺寸
    CARD_W = 40
    CARD_H = 50
    JOKER_W = 48
    JOKER_H = 52
    GAP = 6
    PADDING = 16


LIGHT = _LightPalette()
DARK = _DarkPalette()

_current: Any = LIGHT
_pack: Any = None            # 当前界面包（None = 用明暗板原生的颜色）


class _ThemeProxy:
    """把 ``T.XXX`` 转发到当前配色板，实现「取色时」动态解析。

    若当前挂了界面包（见 :func:`apply_pack`），包的令牌**优先** ——
    这就是「切换界面风格，老界面一行不改也跟着换色」的原理。
    """

    def __getattr__(self, name: str) -> Any:
        if _pack is not None:
            override = _PACK_OVERRIDES.get(name)
            if override is not None:
                return getattr(_pack.colors, override)
        return getattr(_current, name)


T = _ThemeProxy()


# theme.T 的字段名 → 界面包令牌字段名（只映射颜色，尺寸/牌面不动）
_PACK_OVERRIDES = {
    "BG": "bg",
    "SURFACE": "surface",
    "SURFACE_ALT": "surface_alt",
    "PRIMARY": "primary",
    "TEXT_INVERT": "on_primary",
    "ACCENT": "accent",
    "DANGER": "danger",
    "SUCCESS": "success",
    "TEXT_PRIMARY": "text",
    "TEXT_SECONDARY": "text_secondary",
    "TEXT_MUTED": "text_muted",
    "BORDER": "border",
    "DIVIDER": "divider",
}


# ============================================================
# 主题切换 API
# ============================================================

def mode() -> str:
    """返回当前主题：``"light"`` 或 ``"dark"``。"""
    return "dark" if _current is DARK else "light"


def set_mode(theme: str) -> None:
    """切换当前配色板（不会自动刷新界面，视图需重建）。"""
    global _current
    _current = DARK if theme == "dark" else LIGHT


def apply_pack(pack: Any) -> None:
    """挂上 / 摘下界面包。

    * ``pack=None``：恢复明暗板原生颜色（默认皮 + 明暗开关的老行为）；
    * 传包：包的令牌按 :data:`_PACK_OVERRIDES` 覆写到 ``T`` 上，
      老界面（掼蛋牌桌、设置页等）自动换色，不用改一行代码。
    """
    global _pack
    _pack = pack


def apply_to_page(page: ft.Page) -> None:
    """把当前主题应用到 Page：theme_mode + 背景色。"""
    page.theme_mode = (
        ft.ThemeMode.DARK if _current is DARK else ft.ThemeMode.LIGHT
    )
    page.bgcolor = _current.BG

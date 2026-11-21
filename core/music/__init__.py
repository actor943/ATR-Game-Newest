# -*- coding: utf-8 -*-
"""内置音乐播放器（0.4.10 新增）。

对外只露四个入口，其余细节都在子模块里：

* :data:`player` —— 进程内唯一的播放状态与控制；
* :func:`install` —— 应用启动时把悬浮窗挂到 ``page.overlay``；
* :func:`show` / :func:`set_visible` —— 主菜单与设置页控制悬浮窗；
* :func:`refresh` —— 主题 / 语言切换后让悬浮窗重取颜色和文案。
"""

from __future__ import annotations

from typing import Optional

import flet as ft

from .floating import FloatingPlayer
from .player import MusicPlayer, player

_ACTIVE_ATTR = "_atr_music_overlay"


def active(page: ft.Page) -> Optional[FloatingPlayer]:
    """取这个 Page 上的悬浮窗实例（没装过返回 None）。"""
    return getattr(page, _ACTIVE_ATTR, None)


def install(page: ft.Page) -> FloatingPlayer:
    """在应用启动时安装悬浮窗（幂等，重复调用返回同一个实例）。"""
    instance = active(page)
    if instance is not None:
        return instance
    try:
        from core.settings import Settings
        visible = bool(Settings.load().music_visible)
    except Exception:                       # noqa: BLE001 — 设置坏了也照常显示
        visible = True
    instance = FloatingPlayer(page, player, visible=visible)
    try:
        setattr(page, _ACTIVE_ATTR, instance)
    except Exception:                       # noqa: BLE001 — 只读测试桩
        pass
    instance.attach()
    return instance


def show(page: ft.Page, *, expanded: bool = True) -> None:
    """显示（并可选展开）悬浮播放器；主菜单的「音乐」入口调用它。"""
    overlay = active(page) or install(page)
    overlay.show(expanded=expanded)


def set_visible(page: ft.Page, value: bool) -> None:
    """显示 / 隐藏悬浮播放器（设置页开关调用）。"""
    overlay = active(page) or install(page)
    overlay.set_visible(value)


def refresh(page: ft.Page) -> None:
    """主题 / 语言切换后让悬浮窗下一帧重绘文案与配色。"""
    overlay = active(page)
    if overlay is not None:
        overlay.refresh_now()


__all__ = [
    "FloatingPlayer", "MusicPlayer", "player",
    "active", "install", "show", "set_visible", "refresh",
]

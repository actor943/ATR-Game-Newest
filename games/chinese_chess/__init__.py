# -*- coding: utf-8 -*-
"""中国象棋（Chinese Chess）子游戏包。

Import 本包即触发 ``register_game(plugin)``，让主菜单与房间出现
Chinese Chess 的占位条目（当前「敬请期待」，暂未实现游戏逻辑与 AI）。
"""

from __future__ import annotations

from core.registry import register_game

from .plugin import plugin

register_game(plugin)

__all__ = ["plugin"]

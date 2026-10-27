# -*- coding: utf-8 -*-
"""俄罗斯方块插件声明：登记菜单项与路由。"""

from __future__ import annotations

import flet as ft

from core.registry import (
    GamePlugin, MenuItem, NavigateFn, RouteSpec, register_game,
)

from . import views
from . import history_view


def _home(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    return views.build_home(page, navigate)


def _play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    return views.build_play(page, navigate)


def _history(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    return history_view.build(page, navigate)


register_game(GamePlugin(
    id="tetris",
    players=1,                    # 单人上场；联机时可扩展为「每人一块板」对战
    online=False,                 # 纯单人游戏：不进「多人游戏 / 建房」的游戏列表
    menu_item=MenuItem(
        id="tetris",
        title="俄罗斯方块",
        icon="🧱",
        description="经典七种方块，消行、连击、Hold 与幽灵块",
        available=True,
        home_path="/g/tetris",
        title_key="route.tetris",
        desc_key="route.tetris.desc",
    ),
    routes=[
        RouteSpec("/g/tetris", "俄罗斯方块", _home,
                  title_key="route.tetris"),
        RouteSpec("/g/tetris/play", "俄罗斯方块 · 对局", _play,
                  title_key="route.tetris.play"),
        RouteSpec("/g/tetris/history", "俄罗斯方块 · 历史记录", _history,
                  title_key="tetris.history"),
    ],
))
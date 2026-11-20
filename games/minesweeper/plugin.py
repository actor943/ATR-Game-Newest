# -*- coding: utf-8 -*-
"""扫雷插件声明：登记菜单项与路由。"""

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
    id="minesweeper",
    players=1,                    # 单人上场
    online=False,                 # 纯单人游戏：不进「多人游戏 / 建房」列表
    menu_item=MenuItem(
        id="minesweeper",
        title="扫雷",
        icon="💣",
        description="经典扫雷：首击安全、右键插旗、三档难度",
        available=True,
        home_path="/g/minesweeper",
        title_key="route.minesweeper",
        desc_key="route.minesweeper.desc",
    ),
    routes=[
        RouteSpec("/g/minesweeper", "扫雷", _home,
                  title_key="route.minesweeper"),
        RouteSpec("/g/minesweeper/play", "扫雷 · 对局", _play,
                  title_key="route.minesweeper.play"),
        RouteSpec("/g/minesweeper/history", "扫雷 · 历史记录", _history,
                  title_key="minesweeper.history"),
    ],
))

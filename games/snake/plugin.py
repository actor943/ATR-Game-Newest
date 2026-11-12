# -*- coding: utf-8 -*-
"""贪吃蛇插件声明：登记菜单项与路由。"""

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
    id="snake",
    players=1,                    # 单人上场
    online=False,                 # 纯单人游戏：不进「多人游戏 / 建房」列表
    menu_item=MenuItem(
        id="snake",
        title="贪吃蛇",
        icon="🐍",
        description="复古像素风：吃食物变长，支持调速变速",
        available=True,
        home_path="/g/snake",
        title_key="route.snake",
        desc_key="route.snake.desc",
    ),
    routes=[
        RouteSpec("/g/snake", "贪吃蛇", _home,
                  title_key="route.snake"),
        RouteSpec("/g/snake/play", "贪吃蛇 · 对局", _play,
                  title_key="route.snake.play"),
        RouteSpec("/g/snake/history", "贪吃蛇 · 历史记录", _history,
                  title_key="snake.history"),
    ],
))

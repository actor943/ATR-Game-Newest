# -*- coding: utf-8 -*-
"""台球插件声明：登记菜单项与路由。"""

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
    id="billiards",
    players=2,                    # 双人对局：席位 0 / 1 = 1 号 / 2 号
    menu_item=MenuItem(
        id="billiards",
        title="台球",
        icon="🎱",
        description="俯视 2D 台球：拉弓击球、清自己的球再打 8 号",
        available=True,
        home_path="/g/billiards",
        title_key="route.billiards",
        desc_key="route.billiards.desc",
    ),
    routes=[
        RouteSpec("/g/billiards", "台球", _home,
                  title_key="route.billiards"),
        RouteSpec("/g/billiards/play", "台球 · 对局", _play,
                  title_key="route.billiards.play"),
        RouteSpec("/g/billiards/history", "台球 · 历史记录", _history,
                  title_key="billiards.history"),
    ],
))

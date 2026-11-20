# -*- coding: utf-8 -*-
"""弹球机插件声明：登记菜单项与路由。"""

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
    id="pinball",
    players=1,                    # 单人上场
    online=False,                 # 纯单人游戏：不进「多人游戏 / 建房」列表
    menu_item=MenuItem(
        id="pinball",
        title="弹球机",
        icon="🕹️",
        description="复古弹球台：蓄力发射、双挡板救球、撞保险杠得分",
        available=True,
        home_path="/g/pinball",
        title_key="route.pinball",
        desc_key="route.pinball.desc",
    ),
    routes=[
        RouteSpec("/g/pinball", "弹球机", _home,
                  title_key="route.pinball"),
        RouteSpec("/g/pinball/play", "弹球机 · 对局", _play,
                  title_key="route.pinball.play"),
        RouteSpec("/g/pinball/history", "弹球机 · 历史记录", _history,
                  title_key="pinball.history"),
    ],
))

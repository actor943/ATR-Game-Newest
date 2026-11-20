# -*- coding: utf-8 -*-
"""小恐龙插件声明：登记菜单项与路由。"""

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
    id="dino",
    players=1,                    # 单人上场
    online=False,                 # 纯单人游戏：不进「多人游戏 / 建房」列表
    menu_item=MenuItem(
        id="dino",
        title="小恐龙",
        icon="🦖",
        description="Chrome 离线恐龙：原生像素素材，跳过仙人掌、蹲过飞鸟，自动加速",
        available=True,
        home_path="/g/dino",
        title_key="route.dino",
        desc_key="route.dino.desc",
    ),
    routes=[
        RouteSpec("/g/dino", "小恐龙", _home,
                  title_key="route.dino"),
        RouteSpec("/g/dino/play", "小恐龙 · 对局", _play,
                  title_key="route.dino.play"),
        RouteSpec("/g/dino/history", "小恐龙 · 历史记录", _history,
                  title_key="dino.history"),
    ],
))

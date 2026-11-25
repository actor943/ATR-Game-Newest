# -*- coding: utf-8 -*-
"""3D 台球插件声明：登记菜单项与路由。"""

from __future__ import annotations

import flet as ft

from core.registry import (
    GamePlugin, MenuItem, NavigateFn, RouteSpec, register_game,
)

from . import views


def _home(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    return views.build_home(page, navigate)


def _play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    return views.build_play(page, navigate)


register_game(GamePlugin(
    id="billiards3d",
    players=1,                    # 本地单人：网页自身支持机器人/多人，但不接入房间
    online=False,
    menu_item=MenuItem(
        id="billiards3d",
        title="3D 台球",
        icon="🎱",
        description="开源 3D 台球：真实物理、多种规则，本地静态资源运行",
        available=True,
        home_path="/g/billiards3d",
        title_key="route.billiards3d",
        desc_key="route.billiards3d.desc",
    ),
    routes=[
        RouteSpec("/g/billiards3d", "3D 台球", _home,
                  title_key="route.billiards3d"),
        RouteSpec("/g/billiards3d/play", "3D 台球 · 对局", _play,
                  title_key="route.billiards3d.play"),
    ],
))

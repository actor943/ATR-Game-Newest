# -*- coding: utf-8 -*-
"""国际象棋（Chess）插件声明。"""

from __future__ import annotations

from core.registry import GamePlugin, MenuItem, RouteSpec

from . import views as _views
from .history_view import build as build_history

HOME_PATH = "/g/chess"

plugin = GamePlugin(
    id="chess",
    menu_item=MenuItem(
        id="chess",
        title="Chess",
        icon="♟️",
        description="双人对弈的经典国际象棋，含王车易位、吃过路兵、升变等特殊规则。",
        available=True,
        home_path=HOME_PATH,
    ),
    routes=[
        RouteSpec(
            path=HOME_PATH,
            title="Chess",
            builder=_views.build_home,
            group="chess",
        ),
        RouteSpec(
            path="/g/chess/play",
            title="对局",
            builder=_views.build_play,
            group="chess",
        ),
        RouteSpec(
            path="/g/chess/history",
            title="历史记录",
            builder=build_history,
            group="chess",
        ),
    ],
    players=2,  # 国际象棋：白方 + 黑方，各一人；多出来的人观战
)

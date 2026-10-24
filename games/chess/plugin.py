# -*- coding: utf-8 -*-
"""国际象棋（Chess）插件声明。

标题 / 说明走 i18n 键（换语言后由 :func:`core.i18n.refresh` 重建视图生效）。
"""

from __future__ import annotations

from core.registry import GamePlugin, MenuItem, RouteSpec

from . import views as _views
from .history_view import build as build_history

HOME_PATH = "/g/chess"

plugin = GamePlugin(
    id="chess",
    menu_item=MenuItem(
        id="chess",
        title="国际象棋",
        icon="♟️",
        description="双人对弈的经典国际象棋，含王车易位、吃过路兵、升变等特殊规则。",
        available=True,
        home_path=HOME_PATH,
        title_key="game.chess.title",
        desc_key="game.chess.desc",
    ),
    routes=[
        RouteSpec(
            path=HOME_PATH,
            title="国际象棋",
            builder=_views.build_home,
            group="chess",
            title_key="game.chess.title",
        ),
        RouteSpec(
            path="/g/chess/play",
            title="对局",
            builder=_views.build_play,
            group="chess",
            title_key="chess.home.play",
        ),
        RouteSpec(
            path="/g/chess/history",
            title="历史记录",
            builder=build_history,
            group="chess",
            title_key="chess.home.history",
        ),
    ],
    players=2,  # 国际象棋：白方 + 黑方，各一人；多出来的人观战
)

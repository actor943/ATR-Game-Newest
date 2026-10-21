# -*- coding: utf-8 -*-
"""掼蛋游戏插件声明。"""

from __future__ import annotations

from core.registry import GamePlugin, MenuItem, RouteSpec

from . import views as _views

plugin = GamePlugin(
    id="guandan",
    menu_item=MenuItem(
        id="guandan",
        title="掼蛋",
        icon="🀄",
        description="两副牌、四人两两结对、按级升级的经典牌类。",
        available=True,
        home_path="/g/guandan",
    ),
    routes=[
        RouteSpec(
            path="/g/guandan",
            title="掼蛋",
            builder=_views.build_home,
            group="guandan",
        ),
        RouteSpec(
            path="/g/guandan/play",
            title="对局",
            builder=_views.build_play,
            group="guandan",
        ),
        # 出牌记录（开始游戏每整场结束自动落盘，这里查看）
        RouteSpec(
            path="/g/guandan/history",
            title="历史记录",
            builder=_views.build_history,
            group="guandan",
        ),
        RouteSpec(
            path="/g/guandan/board",
            title="快速记牌",
            builder=_views.build_board,
            group="guandan",
        ),
        RouteSpec(
            path="/g/guandan/advisor",
            title="AI 建议",
            builder=_views.build_advisor,
            group="guandan",
        ),
        RouteSpec(
            path="/g/guandan/simulator",
            title="全模拟",
            builder=_views.build_simulator,
            group="guandan",
        ),
        RouteSpec(
            path="/g/guandan/types",
            title="牌型速查",
            builder=_views.build_types,
            group="guandan",
        ),
    ],
)

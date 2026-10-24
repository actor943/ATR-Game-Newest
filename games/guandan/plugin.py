# -*- coding: utf-8 -*-
"""掼蛋游戏插件声明。

标题与说明只写 i18n 键（``title_key`` / ``desc_key``），写死的 ``title``
与 ``description`` 当兜底 —— 换语言后由 :func:`core.i18n.refresh` 重建视图，
卡片与顶栏标题一起换（见 :attr:`core.registry.MenuItem.label`）。
"""

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
        title_key="game.guandan.title",
        desc_key="game.guandan.desc",
    ),
    routes=[
        RouteSpec(
            path="/g/guandan",
            title="掼蛋",
            builder=_views.build_home,
            group="guandan",
            title_key="game.guandan.title",
        ),
        RouteSpec(
            path="/g/guandan/play",
            title="对局",
            builder=_views.build_play,
            group="guandan",
            title_key="guandan.play",
        ),
        # 出牌记录（开始游戏每整场结束自动落盘，这里查看）
        RouteSpec(
            path="/g/guandan/history",
            title="历史记录",
            builder=_views.build_history,
            group="guandan",
            title_key="guandan.history",
        ),
        RouteSpec(
            path="/g/guandan/board",
            title="快速记牌",
            builder=_views.build_board,
            group="guandan",
            title_key="guandan.board",
        ),
        RouteSpec(
            path="/g/guandan/advisor",
            title="AI 建议",
            builder=_views.build_advisor,
            group="guandan",
            title_key="guandan.advisor",
        ),
        RouteSpec(
            path="/g/guandan/simulator",
            title="全模拟",
            builder=_views.build_simulator,
            group="guandan",
            title_key="guandan.simulator",
        ),
        RouteSpec(
            path="/g/guandan/types",
            title="牌型速查",
            builder=_views.build_types,
            group="guandan",
            title_key="guandan.types",
        ),
    ],
)

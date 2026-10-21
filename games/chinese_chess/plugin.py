# -*- coding: utf-8 -*-
"""中国象棋（Chinese Chess）插件声明：仅占位，未实现规则与 AI。"""

from __future__ import annotations

from core.registry import GamePlugin, MenuItem, RouteSpec

from ..placeholder import build_stub

HOME_PATH = "/room/chinese_chess"
STUB_NOTE = "中国象棋正在筹备中：棋盘、走子规则与 AI 对手将陆续开放。"

plugin = GamePlugin(
    id="chinese_chess",
    menu_item=MenuItem(
        id="chinese_chess",
        title="Chinese Chess",
        icon="🐘",
        description="楚河汉界、九宫纵横的传统象棋，马走日、象飞田各有章法。",
        available=False,
        home_path=HOME_PATH,
    ),
    routes=[
        RouteSpec(
            path=HOME_PATH,
            title="Chinese Chess",
            builder=lambda page, navigate: build_stub(
                page, navigate, "Chinese Chess", STUB_NOTE),
            group="chinese_chess",
        ),
    ],
)

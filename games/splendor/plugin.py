# -*- coding: utf-8 -*-
"""璀璨宝石（Splendor）插件声明：仅占位，未实现游戏逻辑。"""

from __future__ import annotations

from core.registry import GamePlugin, MenuItem, RouteSpec

from ..placeholder import build_stub

HOME_PATH = "/room/splendor"
STUB_NOTE = "璀璨宝石正在筹备中：宝石收集、发展卡与声望结算将陆续开放。"

plugin = GamePlugin(
    id="splendor",
    menu_item=MenuItem(
        id="splendor",
        title="Splendor",
        icon="💎",
        description="收集宝石、换取发展卡，率先累积 15 点声望取胜的轻策略桌游。",
        available=False,
        home_path=HOME_PATH,
    ),
    routes=[
        RouteSpec(
            path=HOME_PATH,
            title="Splendor",
            builder=lambda page, navigate: build_stub(
                page, navigate, "Splendor", STUB_NOTE),
            group="splendor",
        ),
    ],
)

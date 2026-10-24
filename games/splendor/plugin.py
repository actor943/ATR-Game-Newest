# -*- coding: utf-8 -*-
"""璀璨宝石（Splendor）插件声明：仅占位，未实现游戏逻辑。"""

from __future__ import annotations

from core.i18n import t
from core.registry import GamePlugin, MenuItem, RouteSpec

from ..placeholder import build_stub

HOME_PATH = "/room/splendor"


def _stub(page, navigate):
    """占位页：标题与说明都按当前语言取。"""
    return build_stub(page, navigate,
                      t("game.splendor.title"), t("splendor.stub"))


plugin = GamePlugin(
    id="splendor",
    menu_item=MenuItem(
        id="splendor",
        title="Splendor",
        icon="💎",
        description="收集宝石、换取发展卡，率先累积 15 点声望取胜的轻策略桌游。",
        available=False,
        home_path=HOME_PATH,
        title_key="game.splendor.title",
        desc_key="game.splendor.desc",
    ),
    routes=[
        RouteSpec(
            path=HOME_PATH,
            title="Splendor",
            builder=_stub,
            group="splendor",
            title_key="game.splendor.title",
        ),
    ],
)

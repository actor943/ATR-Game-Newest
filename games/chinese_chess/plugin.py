# -*- coding: utf-8 -*-
"""中国象棋（Chinese Chess）插件声明：仅占位，未实现规则与 AI。"""

from __future__ import annotations

from core.i18n import t
from core.registry import GamePlugin, MenuItem, RouteSpec

from ..placeholder import build_stub

HOME_PATH = "/room/chinese_chess"


def _stub(page, navigate):
    """占位页：标题与说明都按当前语言取。"""
    return build_stub(page, navigate,
                      t("game.chinese_chess.title"), t("chinese_chess.stub"))


# available=False：菜单里这一项会显示成灰的（还点不进去），
# 等游戏真正做完了再改成 True。
plugin = GamePlugin(
    id="chinese_chess",
    menu_item=MenuItem(
        id="chinese_chess",
        title="Chinese Chess",
        icon="🐘",
        description="楚河汉界、九宫纵横的传统象棋，马走日、象飞田各有章法。",
        available=False,
        home_path=HOME_PATH,
        title_key="game.chinese_chess.title",
        desc_key="game.chinese_chess.desc",
    ),
    routes=[
        RouteSpec(
            path=HOME_PATH,
            title="Chinese Chess",
            builder=_stub,
            group="chinese_chess",
            title_key="game.chinese_chess.title",
        ),
    ],
)

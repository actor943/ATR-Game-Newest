"""掼蛋游戏插件。

Import 本包即触发 ``register_game(plugin)``，让主菜单和路由表自动出现
掼蛋相关条目。
"""
# pyright: reportImportCycles=false

from .analyzer import (  # noqa: F401
    GdAnalyzer,
    INITIAL_HAND_SIZE,
    JOKERS,
    NUM_PLAYERS,
    OPPONENTS,
    PLAYER_NAMES,
    PlayRecord,
    RANKS,
    SUITS,
    TOTAL_CARDS,
    TOTAL_PER_RANK,
    WILD_SUIT,
)
from .plugin import plugin as _plugin
from core.registry import register_game

register_game(_plugin)

__all__ = [
    "GdAnalyzer",
    "PlayRecord",
    "RANKS",
    "SUITS",
    "JOKERS",
    "PLAYER_NAMES",
    "NUM_PLAYERS",
    "OPPONENTS",
    "TOTAL_CARDS",
    "TOTAL_PER_RANK",
    "INITIAL_HAND_SIZE",
    "WILD_SUIT",
]

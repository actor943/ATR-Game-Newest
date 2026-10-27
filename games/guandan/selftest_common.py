# -*- coding: utf-8 -*-
"""自检用的公共小工具：造牌、固定级牌背景。

所有用例都从这里拿 C（造一张牌）和几个固定的级牌背景，
免得每个用例各写一套、彼此对不上。
"""

from __future__ import annotations

from .cards import Card, GameContext
from .rules import parse

_C5 = GameContext("5")             # 双方都打 5（共有）
_C5_B = GameContext("5", (1,))     # 只有乙丁在打 5（上一把乙丁头游）
_C3 = GameContext("3", (0,))       # 只有甲丙在打 3
_C7_B = GameContext("7", (1,))     # 乙丁打 4 头游后升到 7


def C(rank: str, suit: str = "", ci: int = 0) -> Card:
    return Card(rank, suit, ci)


def _bomb(rank: str, n: int):
    suits = ["♠", "♥", "♣", "♦"]
    cards = [C(rank, suits[i % 4], i // 4) for i in range(n)]
    return parse(cards, _C5)

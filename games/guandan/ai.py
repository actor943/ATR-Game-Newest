# -*- coding: utf-8 -*-
"""简单贪心 AI：供自对弈验证与后续观战模式使用。

策略（v1，够用于逻辑验证）：
* 主动出牌：优先低层级牌型、不烧逢人配、先甩低牌、优先一次多出牌。
* 跟牌：搭档出的牌不压；否则用最小代价压过（普通牌型优先于炸弹、
  少用逢人配、点数尽量低）。
"""

from __future__ import annotations

from typing import Optional

from . import rules
from .engine import TEAM_OF, Hand
from .rules import TYPE_LEVEL, Combo


def choose(state: Hand, player: int) -> Optional[Combo]:
    """返回要出的牌型；None 表示过牌。"""
    if state.current is None:
        combos = rules.find_leads(state.hands[player], state.ctx)
        if not combos:
            return None                       # 不可能：有手牌必有单张
        return min(combos, key=_lead_cost)

    if TEAM_OF[state.combo_owner] == TEAM_OF[player]:
        return None                           # v1：不压搭档
    beats_ = rules.find_beats(state.hands[player], state.current, state.ctx)
    if not beats_:
        return None
    return min(beats_, key=_beat_cost)


def _lead_cost(combo: Combo):
    """主动出牌代价：层级低、不用野牌、点数低、一次多甩牌者优先。"""
    return (TYPE_LEVEL[combo.type], combo.wilds_used,
            combo.main_key - 3 * len(combo.cards))


def _beat_cost(combo: Combo):
    """跟牌代价：普通牌型优先、少用野牌、点数尽量低。"""
    return (TYPE_LEVEL[combo.type], combo.wilds_used, combo.main_key)

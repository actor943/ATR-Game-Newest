# -*- coding: utf-8 -*-
"""掼蛋电脑玩家：用 :mod:`games.guandan.ai_strategy` 挑一手牌。

骨架只做三件事：看现在该不该领出、是不是搭档牌权、要不要跟；具体取舍
（残局封锁、保护搭档、拆牌代价等）都在 ``ai_strategy`` 里，局面清单也
写在那个模块的文档里。

返回 ``None`` 表示过牌（首出时理论上不会：有手牌必有单张）。
"""

from __future__ import annotations

from typing import Optional

from . import ai_strategy as strategy
from . import rules
from .engine import TEAM_OF, Hand
from .rules import Combo


def choose(state: Hand, player: int) -> Optional[Combo]:
    """返回要出的牌型；``None`` 表示过牌。"""
    sit = strategy.inspect(state, player)

    if state.current is None:
        combos = rules.find_leads(state.hands[player], state.ctx)
        return strategy.choose_lead(combos, state, player, sit)

    if TEAM_OF[state.combo_owner] == TEAM_OF[player]:
        # 默认不压搭档；只有搭档领小单张、对手只剩 1 张且我有大单张时
        # 才破例一次（见 ai_strategy.partner_beat）
        return strategy.partner_beat(state, player, sit)

    beats = rules.find_beats(state.hands[player], state.current, state.ctx)
    return strategy.choose_beat(beats, state, player, sit)

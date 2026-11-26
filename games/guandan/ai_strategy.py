# -*- coding: utf-8 -*-
"""掼蛋 AI 的局面判断与出牌取舍（v2 残局策略，分析记录在这里）。

旧版 ``ai.py`` 只有一个贪心代价：

    (牌型层级, 逢人配张数, 点数 - 3 × 出牌张数)

它**完全不看另外三家的余牌**，于是出现用户反馈的那类失误：

    残局 1 对 1，对手只剩 1 张，自己手里明明有对子，却领出一张小单张；
    对手用最后一张牌压掉就出完了。

根因很直接：单张 3 的代价 ``(0,0,1-3)=(0,0,-2)``，对子 9 是
``(0,0,7-6)=(0,0,1)``，``min()`` 必然挑小单张。而 ``find_leads()`` 又先枚举
单张，同分时更是轮不到对子。

下面把这些"同类局面"逐条写下来，并给出对应的处理规则。所有规则只依赖
``Hand`` 里现成的信息（四家真实手牌、余牌数、出完顺序、当前待压），不引入
新数据源，也不做耗时的搜索。

局面清单与处理规则
------------------
1. **立即走完**：任意候选能一次出空手牌（``len(cards) == 余牌数``），
   直接出它，优先级高于一切代价计算，包括炸弹。旧版可能为了"层级低"
   先出小单张，把已经到手的胜利拖成另一轮。
2. **对手只剩 1 张（临界）**：领出时优先打"张数 > 对手余牌"的牌型
   （对子、三张、顺子……）。对手牌不够跟，天然压不过——这是最稳的封锁。
   没有这种牌型时，改出**最大**的单张，尽量让对手压不过，而不是出最小牌
   给他送牌权。
3. **对手只剩 2 张（危险）**：同样优先张数 > 2 的牌型；被逼跟牌时，
   能出多张牌型就出多张，出单张就出最大的。
4. **跟牌封路**：对手剩 1 张且当前是单张时，旧版用最小代价跟牌，正好
   让对手用最后一张更大的牌捡漏。现在按"普通牌型优先、点数尽量大"选，
   必要时用 A / 级牌 / 王去堵；反过来，如果我的牌型张数已经多于对手余牌
   （他根本跟不起），就出**最小**的那手，不浪费大牌。
5. **搭档只剩 1 张**：领出小单张，给搭档接走牌权的机会；不主动出炸弹、
   级牌或大单张把牌权抢在手里。旧版只看点数，常常一领就是个压死搭档的牌。
6. **搭档领牌、对手却只剩 1 张**：旧版"绝不压搭档"是硬规则，结果搭档
   一张小单张领出，对手最后一张牌直接走人。现在只在很窄的条件下破例：
   当前是小单张（点数 < A）、我手里有 A 以上的纯单张、且不用炸弹/逢人配；
   用这张大牌把对手堵在外面。搭档的牌已经够大（A / 级牌 / 王）时不破例。
7. **拆牌保护**：同等代价下优先保留对子 / 三张，不把成对的牌拆成散牌
   （用"出完这手后还剩几张孤牌"作最后一级比较）。
8. **炸弹克制**：非残局依旧不主动出炸弹（层级代价最高）；只有封锁临界
   对手、或能立刻出空手牌时才允许。

这些规则由 :func:`choose_lead` / :func:`choose_beat` 落到候选项上，
:mod:`games.guandan.ai` 只保留"选首出还是跟牌"的骨架。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from . import rules
from .engine import TEAM_OF, Hand
from .rules import TYPE_LEVEL, Combo, ComboType

# A 的自然序值：cards.rank_order("A") == 12；级牌 >=20、王 >=40。
# 用它判断"这张单张够不够大，值得在残局里拿来堵对手 / 压搭档"。
HIGH_SINGLE_KEY = 12

Cost = Tuple[int, ...]


@dataclass(frozen=True)
class Situation:
    """决策时看到的局面（只算一次，候选排序直接复用）。"""

    mine: int            # 我方余牌数
    min_opp: int         # 仍有牌的对手里，最少的一家有几张
    min_mate: int        # 仍有牌的搭档有几张（四家都活跃时通常是 27）
    opp_count: int       # 还有几家和我对着干

    @property
    def critical(self) -> bool:
        """有对手只剩最后一张 —— 他随时可能下一手就走。"""
        return self.min_opp == 1

    @property
    def danger(self) -> bool:
        """对手进入 1~2 张的危险区。"""
        return self.min_opp <= 2

    @property
    def mate_ready(self) -> bool:
        """搭档只剩一张，正等牌权走人。"""
        return self.min_mate == 1


def inspect(state: Hand, player: int) -> Situation:
    """从 ``Hand`` 里读局面；只统计还没出完的人。"""
    opponents: List[int] = []
    mates: List[int] = []
    for p in state.active_players():
        if p == player:
            continue
        if TEAM_OF[p] == TEAM_OF[player]:
            mates.append(p)
        else:
            opponents.append(p)
    return Situation(
        mine=state.hand_size(player),
        min_opp=min((state.hand_size(p) for p in opponents), default=99),
        min_mate=min((state.hand_size(p) for p in mates), default=99),
        opp_count=len(opponents),
    )


def is_finishing(combo: Combo, state: Hand, player: int) -> bool:
    """这一手是不是能直接出空手牌（赢下这一局的牌）。"""
    return len(combo.cards) == state.hand_size(player)


def _leftover_singles(state: Hand, player: int, combo: Combo) -> int:
    """出掉这手之后，手里还剩几张"落单"的点数（越少越好）。

    对子 / 三张 / 炸弹被拆开时会多出孤牌，这个数就上升；用它做最后一级
    比较，能在不牺牲主要策略的前提下减少乱拆牌（局面 7）。
    """
    played = set(combo.cards)
    counts = Counter(c.rank for c in state.hands[player] if c not in played)
    return sum(1 for n in counts.values() if n == 1)


def _base_cost(combo: Combo, state: Hand, player: int) -> Cost:
    """常规代价：保持旧版顺序，末尾补一个"别拆牌"的比较项。"""
    return (
        TYPE_LEVEL[combo.type],
        combo.wilds_used,
        combo.main_key - 3 * len(combo.cards),
        _leftover_singles(state, player, combo),
    )


def _safe_cost(combo: Combo, state: Hand, player: int) -> Cost:
    """封锁牌的代价：对手跟不起时，尽量省大牌、省炸弹、省逢人配。"""
    return (
        TYPE_LEVEL[combo.type],
        combo.wilds_used,
        _leftover_singles(state, player, combo),
        combo.main_key,
        -len(combo.cards),
    )


def _block_cost(combo: Combo, state: Hand, player: int) -> Cost:
    """不得不出小牌型时的代价：张数尽量多、点数尽量大，别送牌权。"""
    return (
        TYPE_LEVEL[combo.type],
        combo.wilds_used,
        -len(combo.cards),
        -combo.main_key,
        _leftover_singles(state, player, combo),
    )


def _beat_cost(combo: Combo, state: Hand, player: int) -> Cost:
    """常规跟牌：普通牌型优先、少野牌、点数低、不拆牌。"""
    return (
        TYPE_LEVEL[combo.type],
        combo.wilds_used,
        combo.main_key,
        _leftover_singles(state, player, combo),
    )


def _beat_block_cost(combo: Combo, state: Hand, player: int,
                     sit: Situation) -> Cost:
    """残局跟牌。

    我的牌型张数已经超过对手余牌时他跟不起，出最小的就行；否则（典型是
    对手剩 1 张、当前单张）必须出最大的那张，把他挡在门外。
    """
    if len(combo.cards) > sit.min_opp:
        return _safe_cost(combo, state, player)
    return _block_cost(combo, state, player)


def choose_lead(combos: Sequence[Combo], state: Hand, player: int,
                sit: Situation) -> Optional[Combo]:
    """从全部首出候选里挑一手（局面 1/2/3/5/7/8）。"""
    if not combos:
        return None

    # 1. 能一把出完就出，别把胜利拖到下一轮
    finishing = [c for c in combos if is_finishing(c, state, player)]
    if finishing:
        return min(finishing, key=lambda c: (TYPE_LEVEL[c.type],
                                             c.wilds_used))

    # 2/3. 对手进入危险区：优先出他牌数不够跟的牌型
    if sit.danger:
        safe = [c for c in combos if len(c.cards) > sit.min_opp]
        if safe:
            return min(safe, key=lambda c: _safe_cost(c, state, player))
        return min(combos, key=lambda c: _block_cost(c, state, player))

    # 5. 搭档只差一张：领小单张，把牌权让给他（不抢、不炸）
    if sit.mate_ready:
        singles = [c for c in combos
                   if c.type is ComboType.SINGLE and c.wilds_used == 0]
        if singles:
            return min(singles, key=lambda c: (c.main_key,
                                               _leftover_singles(state,
                                                                 player, c)))

    return min(combos, key=lambda c: _base_cost(c, state, player))


def choose_beat(beats: Sequence[Combo], state: Hand, player: int,
                sit: Situation) -> Optional[Combo]:
    """从能压过当前牌的候选里挑一手（局面 1/4/7/8）。"""
    if not beats:
        return None

    finishing = [c for c in beats if is_finishing(c, state, player)]
    if finishing:
        return min(finishing, key=lambda c: (TYPE_LEVEL[c.type],
                                             c.wilds_used))

    if sit.danger:
        return min(beats, key=lambda c: _beat_block_cost(c, state, player,
                                                         sit))
    return min(beats, key=lambda c: _beat_cost(c, state, player))


def partner_beat(state: Hand, player: int,
                 sit: Situation) -> Optional[Combo]:
    """是否要破例压搭档一手（局面 6），要压则返回那手牌。

    条件故意设得很窄：搭档领的是小单张（A 以下）、对手只剩 1 张、我手里
    有 A 以上的纯单张。只有这时"放走对手"的损失才大于"压搭档"的代价。
    搭档本身领的是大牌时不插手，炸弹 / 逢人配也不拿来压搭档。
    """
    if not sit.critical or state.current is None:
        return None
    if state.current.type is not ComboType.SINGLE:
        return None
    if state.current.main_key >= HIGH_SINGLE_KEY:
        return None
    candidates = [
        c for c in rules.find_beats(state.hands[player], state.current,
                                    state.ctx)
        if c.type is ComboType.SINGLE
        and c.wilds_used == 0
        and c.main_key >= HIGH_SINGLE_KEY
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda c: c.main_key)

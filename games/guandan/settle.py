# -*- coding: utf-8 -*-
"""掼蛋一手结束后的「结算」：升级 + 下一把的进贡安排。

两个函数：

* :func:`settle` —— 一手打完后的升级结算（就地更新 ``MatchState``）；
* :func:`plan_tribute` —— 按游序排出下一把的进贡安排。

两者都在「一手牌结束」这一刻被调用：界面层先调 :func:`settle` 拿到结算
面板，再由下一手发牌时（:class:`~games.guandan.hand.Hand`）消费
``match.pending_tribute``，展开成一步步可执行的进贡动作。
"""

from __future__ import annotations

from typing import Sequence

from .cards import advance_level
from .hand import Hand
from .state import NUM_PLAYERS, TEAM_OF, HandResult, MatchState, TributePlan

def settle(match: MatchState, hand: Hand) -> HandResult:
    """一手牌结束后的升级结算（就地更新 MatchState）。"""
    out = list(hand.out_order)
    assert len(out) == NUM_PLAYERS, "结算时必须已有完整游序"
    winner = out[0]
    team = TEAM_OF[winner]
    mate = next(p for p in out[1:] if TEAM_OF[p] == team)
    upgrade = 4 - out.index(mate)            # 二游=3 / 三游=2 / 末游=1

    match_over = match.levels[team] == "A"    # A 级头游即胜
    if not match_over:
        match.levels[team] = advance_level(match.levels[team], upgrade)
    match.next_leader = winner               # 下一局头游先出（简化：未含进贡）
    match.hand_no += 1
    # 下一把的级牌点数 = 本把头游方**升级之后**的分数。
    # 一把只有一个级牌点数：对方正在打的点数（哪怕也在升级）不算级牌，
    # 所以「甲丙打 3、乙丁打 4，上把乙丁头游」之后，红桃 3 不再是逢人配。
    match.level_rank = match.levels[team]
    # 谁在打这个点数：头游方自己；两队级数恰好相同时（含开局都打 2）双方共有。
    match.level_owner = tuple(
        t for t in (0, 1) if match.levels[t] == match.level_rank
    )

    result = HandResult(
        out_order=out,
        winner_team=team,
        upgrade=upgrade,
        levels_after=(match.levels[0], match.levels[1]),
        match_over=match_over,
    )
    match.history.append(result)
    if match_over:
        match.winner = team
        match.pending_tribute = None          # 整场结束，没有下一手
    else:
        match.pending_tribute = plan_tribute(out)
    return result


def plan_tribute(out_order: Sequence[int]) -> TributePlan:
    """按游序排出进贡安排。

    * 一般情况：末游 → 头游；
    * 双下（赢家包揽前两名）：三游 + 末游 都要进贡，头游拿大的、二游拿小的。

    抗贡（末游两张大王）与选贡（双下时两张贡牌点数相等）要等下一手发完牌、
    看到具体手牌才能判定，放在 :class:`Tribute` 里。
    """
    out = tuple(out_order)
    first, second = out[0], out[1]
    double = TEAM_OF[first] == TEAM_OF[second]
    if double:
        payers = (out[2], out[3])             # 三游、末游
        receivers = (first, second)           # 头游拿大的、二游拿小的
    else:
        payers = (out[3],)                    # 末游
        receivers = (first,)
    return TributePlan(out_order=out, payers=payers, receivers=receivers,
                       double=double)

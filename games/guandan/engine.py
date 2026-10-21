# -*- coding: utf-8 -*-
"""掼蛋对局引擎：一手牌的出牌状态机 + 整场升级流程。

纯逻辑模块，不依赖 flet。

一局（Hand）的流程
------------------
1. 洗牌发牌：108 张，每人 27 张；由 ``next_leader`` 先出。
2. 轮流出牌：首出任意合法牌型；之后必须同型同长且更大，或用
   炸弹 / 同花顺 / 天王炸压。
3. 过牌一圈无人再压 → 本轮结束，最后出牌者获得下一轮出牌权。
4. 有人出完牌即「游」：头游 → 二游 → 三游，三家出完后局面结束
   （第四家自动为末游）。
5. 接风：头游（或任何出完者）最后一手牌无人压时，出牌权交给其
   **搭档**；搭档已出完则顺延下家。
6. 结算：头游方升级 —— 搭档位次为二游升3级 / 三游升2级 / 末游升1级；
   级数封顶在 A；**在 A 级获胜即赢得整场**。
7. 下一把的级牌点数 = 本把头游方**升级之后**的分数（一把只有一个级牌）。
   所以两队级数不同时（甲丙打 3、乙丁打 4），只有上把头游方正在打的那个
   点数算级牌、其红桃牌才是逢人配；对方点数的红桃牌只是普通牌。

尚未实现（后续版本待补）
------------------------
* 进贡 / 还贡 / 抗贡（每局开始前的贡牌流程）；
* 打 A 必须双下的竞赛变体（当前采用「A 级头游即胜」的通用打法）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from . import rules
from .cards import (
    Card,
    GameContext,
    advance_level,
    build_deck,
    sort_hand,
)
from .rules import Combo
from .tribute import Tribute

NUM_PLAYERS = 4
TEAM_OF = (0, 1, 0, 1)     # 玩家 -> 队伍（0/2 一队，1/3 一队）
HAND_SIZE = 27
MAX_MOVES_PER_HAND = 3000  # 防御性上限：单局总步数


class IllegalMove(Exception):
    """非法动作（不是你的轮次 / 牌不在手上 / 牌型非法 / 压不过等）。"""


@dataclass
class Move:
    """一步操作记录。"""

    player: int
    action: str                  # "play" | "pass"
    combo: Optional[Combo] = None


@dataclass
class HandResult:
    """一手牌结束后的结算信息。"""

    out_order: List[int]         # 头游 → 末游（4 个玩家下标）
    winner_team: int
    upgrade: int                 # 头游方升级数（3/2/1）
    levels_after: Tuple[str, str]
    match_over: bool             # 头游方在 A 级获胜，整场结束


@dataclass
class TributePlan:
    """一手结束后的进贡安排（只记座位，发好下一手再解析成具体动作）。

    掼蛋的进贡发生在**下一手牌发好之后**（先发牌再进贡），所以这里先只记录
    「谁给谁」，等下一手 :class:`Hand` 发完牌再由 :class:`Tribute` 结合手牌
    展开成一步步的可执行动作。
    """

    out_order: Tuple[int, ...]   # 头游 → 末游
    payers: Tuple[int, ...]      # 进贡方：末游；双下时为三游 + 末游
    receivers: Tuple[int, ...]   # 收贡方：头游；双下时为头游 + 二游
    double: bool                 # 是否双下（赢家包揽前两名）


@dataclass
class MatchState:
    """整场对局：双方级数与逐局推进。

    ``levels`` 是两队各自的**分数/级数**（队 0 / 队 1，见 :data:`TEAM_OF`）。
    本把的级牌点数只有**一个**：``level_rank`` —— 上一把头游方升级之后的
    分数，``level_owner`` 记着这个点数是谁在打（见 :meth:`ctx`）。
    """

    levels: List[str]
    rng: random.Random
    next_leader: int = 0
    hand_no: int = 0
    winner: Optional[int] = None          # 胜利队伍
    level_rank: str = "2"                 # 本把唯一的级牌点数
    level_owner: Tuple[int, ...] = (0, 1)  # 谁在打这个点数（开局双方都打 2）
    history: List[HandResult] = field(default_factory=list)
    # 下一手发完牌后要执行的进贡安排（settle 写入，Hand 消费后清空）
    pending_tribute: Optional[TributePlan] = None

    @property
    def ctx(self) -> GameContext:
        """本把的静态背景：唯一的级牌点数 + 归属。

        一把只有一个级牌点数（上把头游方升级后的分数），它大于所有自然牌；
        对方级数的红桃牌在本把不是逢人配。
        """
        return GameContext(self.level_rank, self.level_owner)


def new_match(seed: Optional[int] = None) -> MatchState:
    """新开一场：双方都从打 2 开始，首局随机先出。"""
    rng = random.Random(seed)
    return MatchState(levels=["2", "2"], rng=rng,
                      next_leader=rng.randrange(NUM_PLAYERS))


class Hand:
    """一手牌的状态机：出牌 / 跟牌 / 过牌 / 接风 / 出完判定。

    发牌之后如果上一手留有进贡安排（``match.pending_tribute``），会先建立
    :class:`Tribute` 状态机放在 ``self.tribute`` 上——掼蛋是**先发牌再进贡**，
    进贡用的就是这一手刚发好的牌。``self.tribute`` 走完（或无需进贡）后才开始打牌。
    """

    def __init__(self, match: MatchState):
        self.match = match
        self.ctx = match.ctx
        deck = build_deck()
        match.rng.shuffle(deck)
        self.hands: List[List[Card]] = [
            sort_hand(deck[i * HAND_SIZE:(i + 1) * HAND_SIZE], self.ctx)
            for i in range(NUM_PLAYERS)
        ]
        self.out_order: List[int] = []
        self.moves: List[Move] = []
        self.turn: int = match.next_leader
        self.current: Optional[Combo] = None   # 当前待压的牌型
        self.combo_owner: int = -1
        self.passes = 0
        self.ended: bool = False

        # 进贡阶段（用刚发好的牌执行；None 表示这一手不用进贡）
        plan = match.pending_tribute
        if plan is not None:
            match.pending_tribute = None
            self.tribute: Optional[Tribute] = Tribute(self, plan)
            # 抗贡时没有换牌动作（apply 不会被调用），这里先把先出方定下来：
            # 抗贡 = 原来的收贡方（头游）先出；正常进贡则由 apply() 改成末游。
            if self.tribute.refused:
                self.turn = self.tribute.first_leader()
        else:
            self.tribute = None

    # ---------------- 查询 ----------------

    def active_players(self) -> List[int]:
        return [p for p in range(NUM_PLAYERS) if p not in self.out_order]

    def hand_size(self, player: int) -> int:
        return len(self.hands[player])

    def legal_moves(self, player: int) -> List[Combo]:
        """当前轮次玩家的全部合法出牌候选。"""
        if self.ended or player != self.turn:
            return []
        hand = self.hands[player]
        if self.current is None:
            return rules.find_leads(hand, self.ctx)
        return rules.find_beats(hand, self.current, self.ctx)

    # ---------------- 动作 ----------------

    def play(self, player: int, cards: Sequence[Card]) -> Combo:
        """出牌。返回引擎实际采纳的牌型（就高解释）。"""
        if self.ended:
            raise IllegalMove("本局已结束")
        if player != self.turn:
            raise IllegalMove(f"当前轮到玩家{self.turn}，不是玩家{player}")
        cards = tuple(cards)
        if len(cards) != len(set(cards)):
            raise IllegalMove("出牌中有重复牌")
        hand_set = set(self.hands[player])
        for card in cards:
            if card not in hand_set:
                raise IllegalMove(f"{card} 不在玩家{player}手牌中")
        combo = rules.parse(cards, self.ctx)
        if combo is None:
            raise IllegalMove("不是合法牌型")
        if self.current is not None and not rules.beats(combo, self.current):
            raise IllegalMove(f"{combo} 压不过 {self.current}")

        played_set = set(cards)
        self.hands[player] = [c for c in self.hands[player]
                              if c not in played_set]
        self.current = combo
        self.combo_owner = player
        self.passes = 0
        self.moves.append(Move(player, "play", combo))

        if not self.hands[player]:            # 出完：游
            self.out_order.append(player)
            if len(self.out_order) >= 3:      # 三家出完，本局结束
                self._finish()
                return combo
        self._next_turn_from(self.turn)
        return combo

    def pass_turn(self, player: int) -> None:
        """过牌（首出不允许过）。"""
        if self.ended:
            raise IllegalMove("本局已结束")
        if player != self.turn:
            raise IllegalMove(f"当前轮到玩家{self.turn}，不是玩家{player}")
        if self.current is None:
            raise IllegalMove("首出必须出牌，不能过")

        self.moves.append(Move(player, "pass"))
        self.passes += 1
        active = self.active_players()
        need = len(active) - (1 if self.combo_owner in active else 0)
        if self.passes >= need:
            self._end_trick()
        else:
            self._next_turn_from(self.turn)

    # ---------------- 内部流转 ----------------

    def _next_turn_from(self, start: int) -> None:
        """把轮次移到 start 的下一个未出完玩家。"""
        p = start
        for _ in range(NUM_PLAYERS):
            p = (p + 1) % NUM_PLAYERS
            if p not in self.out_order:
                self.turn = p
                return

    def _end_trick(self) -> None:
        """一圈无人再压：赢家拿牌权；赢家已出完则「接风」。"""
        owner = self.combo_owner
        partner = (owner + 2) % NUM_PLAYERS
        if owner in self.out_order:
            if partner not in self.out_order:
                self.turn = partner          # 接风：搭档获得出牌权
            else:
                self._next_turn_from(owner)   # 搭档也出完了，顺延下家
        else:
            self.turn = owner
        self.current = None
        self.combo_owner = -1
        self.passes = 0

    def _finish(self) -> None:
        """三家出完：第四家自动末游，本局结束。"""
        last = [p for p in range(NUM_PLAYERS) if p not in self.out_order][0]
        self.out_order.append(last)
        self.ended = True
        self.current = None
        self.combo_owner = -1


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

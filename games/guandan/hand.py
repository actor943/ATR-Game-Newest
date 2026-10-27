# -*- coding: utf-8 -*-
"""掼蛋「一手牌」的状态机：出牌 / 跟牌 / 过牌 / 接风 / 出完判定。

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

进贡 / 还贡 / 抗贡的规则见 :mod:`games.guandan.tribute`；打 A 必须双下的
竞赛变体当前未采用（用「A 级头游即胜」的通用打法）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from . import rules
from .rules import Combo
from .cards import Card, GameContext, build_deck, sort_hand
from .state import HAND_SIZE, NUM_PLAYERS, IllegalMove, MatchState, Move
from .tribute import Tribute

class Hand:
    """一手牌的状态机：出牌 / 跟牌 / 过牌 / 接风 / 出完判定。

    发牌之后如果上一手留有进贡安排（``match.pending_tribute``），会先建立
    :class:`Tribute` 状态机放在 ``self.tribute`` 上——掼蛋是**先发牌再进贡**，
    进贡用的就是这一手刚发好的牌。``self.tribute`` 走完（或无需进贡）后才开始打牌。

    联机时本机不洗牌：房主发好牌后把整手局面广播下来，客人用
    ``Hand(match, dealt=...)`` 直接采用（见 :func:`load_match`）。
    """

    def __init__(self, match: MatchState, dealt: Optional[Dict[str, Any]] = None):
        self.match = match
        self.ctx = match.ctx
        self.moves: List[Move] = []
        if dealt is None:
            deck = build_deck()
            match.rng.shuffle(deck)
            self.hands: List[List[Card]] = [
                sort_hand(deck[i * HAND_SIZE:(i + 1) * HAND_SIZE], self.ctx)
                for i in range(NUM_PLAYERS)
            ]
            self.out_order: List[int] = []
            self.turn: int = match.next_leader
            self.current: Optional[Combo] = None   # 当前待压的牌型
            self.combo_owner: int = -1
            self.passes = 0
            self.ended: bool = False
        else:
            # 反序列化工具在 serialize 模块里，而 serialize 又要 import 本模块，
            # 所以这里用「函数内 import」断开循环（只执行一次，开销可忽略）。
            from .serialize import (
                _combo_from_json,
                _tribute_from_json,
                cards_from_json,
            )
            hands_raw = dealt["hands"]
            if (not isinstance(hands_raw, (list, tuple))
                    or len(hands_raw) != NUM_PLAYERS):
                raise ValueError("快照里的手牌不是 4 家")
            hands: List[List[Card]] = []
            for raw in hands_raw:
                cards = cards_from_json(raw)
                if cards is None:
                    raise ValueError("快照里的手牌解析失败")
                hands.append(cards)
            self.hands = hands
            self.out_order = list(dealt["out_order"])
            self.turn = int(dealt["turn"])
            self.current = _combo_from_json(dealt.get("current"))
            self.combo_owner = int(dealt["combo_owner"])
            self.passes = int(dealt["passes"])
            self.ended = bool(dealt["ended"])
            # 这一手自己的级牌背景：settle 之后 match.level_rank 已经变成下一手
            # 的级牌，而**这一手**的牌面排序 / 逢人配判定仍按发牌时的级牌
            # （0.4.8-fix：客人若用 match.ctx，刚结束那手会牌序错乱）。
            ctx_raw = dealt.get("ctx")
            if isinstance(ctx_raw, dict):
                try:
                    self.ctx = GameContext(
                        str(ctx_raw["level"]),
                        tuple(int(x) for x in ctx_raw.get("owners", (0, 1))))
                except (KeyError, TypeError, ValueError):
                    pass

        # 进贡阶段（用刚发好的牌执行；None 表示这一手不用进贡）
        if dealt is None:
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
        else:
            # 联网：进贡进度也由房主的快照还原（迟到的观战者看到一致的状态）
            self.tribute = _tribute_from_json(self, dealt.get("tribute"))

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

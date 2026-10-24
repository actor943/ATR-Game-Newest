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
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import rules
from .cards import (
    Card,
    GameContext,
    advance_level,
    build_deck,
    sort_hand,
)
from .rules import Combo, ComboType
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


# ============================================================
# 网络同步：整场 + 当前一手 的序列化 / 还原（房主权威，JSON 友好）
# ============================================================
#
# 联机对局里**只有房主洗牌**：房主把 ``serialize_match`` 的结果广播给所有人，
# 客人 ``load_match`` 之后与本机局面完全一致（级数、手牌、进贡进度、轮到谁）。
# 之后每有一个动作，房主就重推一次快照，客人按 ``seq`` 只接受更新的快照 ——
# 乱序 / 重传的旧快照直接丢弃，天然收敛，不存在「各玩各的」。


def card_to_json(card: Card) -> List[Any]:
    return [card.rank, card.suit, card.copy_index]


def card_from_json(raw: Any) -> Optional[Card]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        return None
    try:
        return Card(str(raw[0]), str(raw[1]), int(raw[2]))
    except (TypeError, ValueError):
        return None


def cards_to_json(cards: Sequence[Card]) -> List[List[Any]]:
    return [card_to_json(c) for c in cards]


def cards_from_json(raw: Any) -> Optional[List[Card]]:
    if not isinstance(raw, (list, tuple)):
        return None
    out: List[Card] = []
    for item in raw:
        card = card_from_json(item)
        if card is None:
            return None
        out.append(card)
    return out


def _combo_to_json(combo: Optional[Combo]) -> Optional[Dict[str, Any]]:
    if combo is None:
        return None
    return {"t": combo.type.value, "c": cards_to_json(combo.cards),
            "sz": combo.size, "k": combo.main_key, "w": combo.wilds_used,
            "label": combo.label}


def _combo_from_json(raw: Any) -> Optional[Combo]:
    if not isinstance(raw, dict):
        return None
    try:
        ctype = ComboType(str(raw["t"]))
    except ValueError:
        return None
    cards = cards_from_json(raw.get("c"))
    if cards is None:
        return None
    try:
        return Combo(type=ctype, cards=tuple(cards), size=int(raw["sz"]),
                     main_key=int(raw["k"]), wilds_used=int(raw.get("w", 0)),
                     label=str(raw.get("label", "")))
    except (KeyError, TypeError, ValueError):
        return None


def _plan_to_json(plan: Optional[TributePlan]) -> Optional[Dict[str, Any]]:
    if plan is None:
        return None
    return {"out": list(plan.out_order), "payers": list(plan.payers),
            "receivers": list(plan.receivers), "double": plan.double}


def _plan_from_json(raw: Any) -> Optional[TributePlan]:
    if not isinstance(raw, dict):
        return None
    try:
        return TributePlan(
            out_order=tuple(int(x) for x in raw["out"]),
            payers=tuple(int(x) for x in raw["payers"]),
            receivers=tuple(int(x) for x in raw["receivers"]),
            double=bool(raw["double"]))
    except (KeyError, TypeError, ValueError):
        return None


def _card_map_to_json(mapping: Dict[int, Card]) -> Dict[str, List[Any]]:
    return {str(k): card_to_json(v) for k, v in mapping.items()}


def _card_map_from_json(raw: Any) -> Dict[int, Card]:
    out: Dict[int, Card] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            seat = int(k)
        except (TypeError, ValueError):
            continue
        card = card_from_json(v)
        if card is not None:
            out[seat] = card
    return out


def _tribute_to_json(tr: Optional[Tribute]) -> Optional[Dict[str, Any]]:
    if tr is None:
        return None
    return {"plan": _plan_to_json(tr.plan),
            "gifts": _card_map_to_json(tr.gifts),
            "picks": _card_map_to_json(tr.picks),
            "returns": _card_map_to_json(tr.returns),
            "return_picks": _card_map_to_json(tr.return_picks),
            "pairs": {str(k): int(v) for k, v in tr.pairs.items()},
            # refused / choose_gift 是**发牌那一刻**按当时手牌定下的
            # （抗贡方可能随后把大王打出去），不能按当前手牌重算 ——
            # 否则联机客人会看到一个已经不存在的进贡面板（0.4.8-fix）
            "refused": tr.refused,
            "choose_gift": tr.choose_gift,
            "refuse_holders": list(tr.refuse_holders)}


def _tribute_from_json(hand: "Hand", raw: Any) -> Optional[Tribute]:
    """按快照还原进贡状态机。"""
    if not isinstance(raw, dict):
        return None
    plan = _plan_from_json(raw.get("plan"))
    if plan is None:
        return None
    tr = Tribute(hand, plan)
    tr.gifts = _card_map_from_json(raw.get("gifts"))
    tr.picks = _card_map_from_json(raw.get("picks"))
    tr.returns = _card_map_from_json(raw.get("returns"))
    tr.return_picks = _card_map_from_json(raw.get("return_picks"))
    pairs = raw.get("pairs")
    if isinstance(pairs, dict):
        for k, v in pairs.items():
            try:
                tr.pairs[int(k)] = int(v)
            except (TypeError, ValueError):
                continue
    if "refused" in raw:
        tr.refused = bool(raw["refused"])
    if "choose_gift" in raw:
        tr.choose_gift = bool(raw["choose_gift"])
    holders = raw.get("refuse_holders")
    if isinstance(holders, (list, tuple)):
        try:
            tr.refuse_holders = tuple(int(x) for x in holders)
        except (TypeError, ValueError):
            pass
    return tr


def _hand_to_json(hand: Hand) -> Dict[str, Any]:
    return {
        "hands": [cards_to_json(h) for h in hand.hands],
        "out_order": list(hand.out_order),
        "turn": hand.turn,
        "current": _combo_to_json(hand.current),
        "combo_owner": hand.combo_owner,
        "passes": hand.passes,
        "ended": hand.ended,
        "tribute": _tribute_to_json(hand.tribute),
        # 这一手发牌时的级牌背景（见 Hand.__init__ 的 dealt 分支）
        "ctx": {"level": hand.ctx.level,
                "owners": list(hand.ctx.owner_teams)},
    }


def _result_to_json(r: Optional[HandResult]) -> Optional[Dict[str, Any]]:
    if r is None:
        return None
    return {"out_order": list(r.out_order), "winner_team": r.winner_team,
            "upgrade": r.upgrade, "levels_after": list(r.levels_after),
            "match_over": r.match_over}


def result_from_json(raw: Any) -> Optional[HandResult]:
    """还原一手牌的结算结果（联机客人显示「下一局 / 整场结束」面板用）。"""
    if not isinstance(raw, dict):
        return None
    try:
        return HandResult(
            out_order=[int(x) for x in raw["out_order"]],
            winner_team=int(raw["winner_team"]),
            upgrade=int(raw["upgrade"]),
            levels_after=(str(raw["levels_after"][0]),
                          str(raw["levels_after"][1])),
            match_over=bool(raw["match_over"]))
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def serialize_match(match: MatchState, hand: Hand,
                    result: Optional[HandResult] = None) -> Dict[str, Any]:
    """导出整场 + 当前一手的完整局面（可被 JSON 编码，联机广播用）。

    ``result`` 是当前一手的结算（房主 ``_after_action`` 后的 ``self.result``），
    客人靠它渲染结算面板 —— 一手牌由谁走完不一定，客人不能只靠自己本地推导。
    """
    return {
        "levels": list(match.levels),
        "next_leader": match.next_leader,
        "hand_no": match.hand_no,
        "winner": match.winner,
        "level_rank": match.level_rank,
        "level_owner": list(match.level_owner),
        "pending_tribute": _plan_to_json(match.pending_tribute),
        "res": _result_to_json(result),
        "hand": _hand_to_json(hand),
    }


def load_match(match: MatchState, raw: Dict[str, Any]) -> Optional[Hand]:
    """把房主广播的整场局面写进 ``match``，返回重建出的当前一手。

    任何字段缺失 / 非法都返回 ``None``（调用方应忽略这帧，继续用旧局面），
    不抛异常 —— 网络线程里不能炸。
    """
    if not isinstance(raw, dict):
        return None
    try:
        levels = [str(x) for x in raw["levels"]]
        if len(levels) != 2:
            return None
        winner = raw.get("winner")
        match.levels = levels
        match.next_leader = int(raw["next_leader"])
        match.hand_no = int(raw["hand_no"])
        match.winner = None if winner is None else int(winner)
        match.level_rank = str(raw["level_rank"])
        match.level_owner = tuple(int(x) for x in raw["level_owner"])
        match.pending_tribute = _plan_from_json(raw.get("pending_tribute"))
        hand = Hand(match, dealt=raw["hand"])
    except (KeyError, TypeError, ValueError):
        return None
    return hand

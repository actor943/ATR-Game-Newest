# -*- coding: utf-8 -*-
"""进贡 / 还贡：一手牌结束后的换牌阶段。

规则（0.4.6，按用户确认的口径）
--------------------------------
* 上一局的**末游**把自己手里**最大的一张牌**（红桃级牌除外）交给**头游**；
  头游随便还一张 **10 以下（含 10）**的牌。
* **抗贡**：进贡方凑得出**两张大王**就不用交 —— 单人进贡看他自己的手牌；
  双下时两个输家**合计**有两张大王同样抗贡（一人两张、两人各一张都算）。
* **双下**（赢家包揽前两名）时两个输家都要进贡，**头游拿大的、二游拿小的**。
* 双下且两张贡牌**点数相等**时可以**选贡**：赢家沟通后各挑各的；
  还贡时输家也各挑各的（方便凑炸弹 / 同花顺）。

谁先出牌
--------
* **正常进贡**：由**贡牌方（末游）**先出（交了贡的人先走牌）；
* **抗贡**：牌没换，仍由**原来的收贡方（头游）**先出。

时序
----
掼蛋是**先发牌再进贡**：进贡用的是下一手刚发好的牌。所以
:class:`Tribute` 由一个已发好牌的 :class:`~games.guandan.engine.Hand`
加一份 :class:`~games.guandan.engine.TributePlan` 构造，期间手牌张数保持 27，
换牌完成后才进入出牌阶段。

本模块不依赖 flet，可被引擎 / AI / 界面 / 自检共用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .cards import (
    Card,
    GameContext,
    card_order,
    is_wild,
    sort_hand,
)

# 还贡能还给对方的牌：10 以下（含 10）的非王牌。
# 「10 以下」按中文习惯含 10 本身；如需改成不含 10，只改这一个常量。
RETURN_MAX_RANK = "10"
_RETURN_RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10")

BIG_JOKER = "大王"

# 动作类型
GIFT = "gift"                # 输家选贡牌
PICK_GIFT = "pick_gift"      # 选贡：赢家挑贡牌
RETURN = "return"            # 赢家选还牌
PICK_RETURN = "pick_return"  # 选贡：输家挑还牌

_ACTION_PROMPTS = {
    GIFT: "选择要进贡的牌（必须是手里最大的牌，红桃级牌除外）",
    PICK_GIFT: "两张贡牌点数相同，请选择你要收的那一张",
    RETURN: "选择一张 10 以下（含 10）的牌还给对方",
    PICK_RETURN: "请选择你要收回的还牌",
}


@dataclass(frozen=True)
class TributeAction:
    """进贡阶段的一个待办动作。"""

    kind: str      # GIFT / PICK_GIFT / RETURN / PICK_RETURN
    player: int    # 行动方座位
    prompt: str    # 给界面用的提示文案


class Tribute:
    """一手牌之间的进贡状态机。

    典型流程（双下 + 选贡）：::

        末游/三游 选贡牌 → 头游/二游 各挑一张 → 赢家各选还牌 → 输家各挑一张

    一般情况只有「末游选贡牌 → 头游选还牌」两步；抗贡则一步都没有。
    """

    def __init__(self, hand, plan):
        """
        Args:
            hand: 已发好牌的 :class:`~games.guandan.engine.Hand`。
            plan: 上一手结算产生的 :class:`~games.guandan.engine.TributePlan`。
        """
        self.hand = hand
        self.ctx: GameContext = hand.ctx
        self.plan = plan
        self.double: bool = plan.double

        self.gifts: Dict[int, Card] = {}            # 进贡方 -> 贡牌
        self.picks: Dict[int, Card] = {}            # 收贡方 -> 挑中的贡牌
        self.returns: Dict[int, Card] = {}          # 收贡方 -> 还牌
        self.return_picks: Dict[int, Card] = {}     # 进贡方 -> 挑中的还牌
        self.pairs: Dict[int, int] = {}             # 进贡方 -> 收贡方

        # 抗贡：进贡方凑得出两张大王就不用交。
        # 单人进贡看他自己的手牌；双下时两个输家**合计**有两张大王也算抗贡
        # （一人两张、两人各一张，都算「凑出两张大王」）。
        self.refuse_holders: Tuple[int, ...] = tuple(
            p for p in plan.payers
            if _count_big_jokers(hand.hands[p]) > 0)
        self.refused = (sum(_count_big_jokers(hand.hands[p])
                            for p in plan.payers) >= 2)

        # 选贡：双下且两张（预期）贡牌点数相等
        self.choose_gift = bool(self.double) and self._gifts_same_rank()

    # ---------------- 查询 ----------------

    @property
    def active(self) -> bool:
        """这一手到底要不要进贡（抗贡 / 无双下关系时为 False）。"""
        return not self.refused and bool(self.plan.payers)

    @property
    def done(self) -> bool:
        return self.current() is None

    def current(self) -> Optional[TributeAction]:
        """当前待办动作；全部完成返回 None。"""
        if not self.active:
            return None
        for payer in self.plan.payers:              # 1. 选贡牌
            if payer not in self.gifts:
                return TributeAction(GIFT, payer, _ACTION_PROMPTS[GIFT])
        if self.choose_gift:                        # 2. 赢家挑贡牌
            for receiver in self.plan.receivers:
                if receiver not in self.picks:
                    return TributeAction(PICK_GIFT, receiver,
                                         _ACTION_PROMPTS[PICK_GIFT])
        else:
            self._assign_pairs_by_size()
        for receiver in self.plan.receivers:        # 3. 赢家选还牌
            if receiver not in self.returns:
                return TributeAction(RETURN, receiver,
                                     _ACTION_PROMPTS[RETURN])
        if self.choose_gift:                        # 4. 输家挑还牌
            for payer in self.plan.payers:
                if payer not in self.return_picks:
                    return TributeAction(PICK_RETURN, payer,
                                         _ACTION_PROMPTS[PICK_RETURN])
        return None

    def options(self, action: Optional[TributeAction] = None) -> List[Card]:
        """某个动作当前可选的牌（默认取当前动作）。"""
        action = action or self.current()
        if action is None:
            return []
        if action.kind == GIFT:
            return gift_candidates(self.hand.hands[action.player], self.ctx)
        if action.kind == RETURN:
            return return_candidates(self.hand.hands[action.player], self.ctx)
        if action.kind == PICK_GIFT:
            return [c for c in self.gifts.values() if c not in
                    self.picks.values()]
        if action.kind == PICK_RETURN:
            return [c for c in self.returns.values() if c not in
                    self.return_picks.values()]
        return []

    # ---------------- 交互 ----------------

    def choose(self, card: Card) -> bool:
        """执行当前动作（选定一张牌）。非法选择返回 False。"""
        action = self.current()
        if action is None or card not in self.options(action):
            return False
        if action.kind == GIFT:
            self.gifts[action.player] = card
            if not self.choose_gift:
                self._assign_pairs_by_size()
        elif action.kind == PICK_GIFT:
            self.picks[action.player] = card
            payer = next(p for p, c in self.gifts.items() if c == card)
            self.pairs[payer] = action.player
        elif action.kind == RETURN:
            self.returns[action.player] = card
        elif action.kind == PICK_RETURN:
            self.return_picks[action.player] = card
        return True

    # ---------------- 结果 ----------------

    def first_leader(self) -> int:
        """进贡结束后谁先出牌。

        * **抗贡**：牌没换，由**原来的收贡方**（头游）先出；
        * **正常进贡**：按掼蛋惯例由**贡牌方**（末游）先出 —— 交了贡的人
          先走牌，这也是「进贡方先出」补偿。
        """
        if self.refused or not self.plan.payers:
            return self.plan.out_order[0]      # 头游
        return self.plan.out_order[-1]         # 末游

    def received_gifts(self, player: int) -> List[Card]:
        """``player`` 在本轮会收到的贡牌（还贡时把「刚进来的牌」标出来）。"""
        out = [gift for payer, gift in self.gifts.items()
               if self.pairs.get(payer) == player]
        if not out and len(self.gifts) == 1 and len(self.plan.receivers) == 1:
            out = list(self.gifts.values())     # 单进贡：配对未落定时直接取
        return out

    def refuse_note(self) -> str:
        """抗贡的一句话说明（写进日志）。"""
        if not self.refused:
            return ""
        names = _seat_names()
        total = sum(_count_big_jokers(self.hand.hands[p])
                    for p in self.plan.payers)
        who = "、".join(names[p] for p in self.plan.payers
                        if _count_big_jokers(self.hand.hands[p]) > 0)
        tag = "双下·" if self.double else ""
        return (f"{tag}抗贡：{who} 共握有 {total} 张大王，本轮不进贡，"
                f"由{names[self.first_leader()]}先出")

    def apply(self) -> List[str]:
        """执行换牌，返回人类可读的事件行（用于日志）。

        换牌（或抗贡）之后会顺带定下**谁先出牌**（见 :meth:`first_leader`）。
        """
        if self.refused:
            self.hand.turn = self.first_leader()   # 抗贡：收贡方先出
            return [self.refuse_note()]
        if not self.active:
            return []
        events: List[str] = []
        names = _seat_names()
        for payer, gift in self.gifts.items():
            receiver = self.pairs.get(payer)
            if receiver is None:
                continue
            _move(self.hand.hands, payer, receiver, gift)
            events.append(
                f"{names[payer]} 进贡 {gift} 给 {names[receiver]}")
        for receiver, card in self.returns.items():
            target = self._return_target(receiver, card)
            if target is None:
                continue
            _move(self.hand.hands, receiver, target, card)
            events.append(
                f"{names[receiver]} 还贡 {card} 给 {names[target]}")
        # 交过贡的人先走牌（抗贡时上面已处理，这里只管正常进贡）
        self.hand.turn = self.first_leader()
        names = _seat_names()
        events.append(f"{names[self.hand.turn]} 先出牌")
        return events

    def summary(self) -> str:
        """一句话说明这一手的进贡安排（设置/日志用）。"""
        if self.refused:
            return self.refuse_note()
        if not self.active:
            return "本轮无需进贡"
        names = _seat_names()
        parts = [f"{names[p]}→{names[r]}" for p, r in zip(
            self.plan.payers, self.plan.receivers)]
        tag = "双下·" if self.double else ""
        chooser = "（选贡）" if self.choose_gift else ""
        return f"{tag}进贡：{'、'.join(parts)}{chooser}"

    # ---------------- 内部 ----------------

    def _gifts_same_rank(self) -> bool:
        """双下时两张预期贡牌的点数是否相同（相同才能选贡）。"""
        if len(self.plan.payers) != 2:
            return False
        ranks = []
        for payer in self.plan.payers:
            cands = gift_candidates(self.hand.hands[payer], self.ctx)
            if not cands:
                return False
            ranks.append(cands[0].rank)
        return ranks[0] == ranks[1]

    def _assign_pairs_by_size(self) -> None:
        """非选贡：大的贡牌给头游、小的给二游（单进贡时就是末游→头游）。"""
        if len(self.gifts) != len(self.plan.payers):
            return
        if self.choose_gift:
            return                       # 选贡的配对由挑牌决定
        order = sorted(self.plan.payers,
                       key=lambda p: card_order(self.gifts[p], self.ctx),
                       reverse=True)
        self.pairs = dict(zip(order, self.plan.receivers))

    def _return_target(self, receiver: int, card: Card) -> Optional[int]:
        """一张还牌最终给谁：选贡时由输家挑，否则按配对。"""
        for payer, picked in self.return_picks.items():
            if picked == card:
                return payer
        for payer, rcv in self.pairs.items():
            if rcv == receiver:
                return payer
        return None


# ============================================================
# 候选牌与工具
# ============================================================


def gift_candidates(cards: List[Card], ctx: GameContext) -> List[Card]:
    """可以当贡牌的牌：手里最大的那些牌（红桃级牌除外）。

    同点数多张时全部列出（两副牌里同点同花色有两张），让玩家按花色挑，
    双下选贡时这一点尤其有用。
    """
    pool = [c for c in cards if not is_wild(c, ctx)]
    if not pool:                         # 全是逢人配（理论上不可能）
        pool = list(cards)
    if not pool:
        return []
    top = max(card_order(c, ctx) for c in pool)
    return [c for c in pool if card_order(c, ctx) == top]


def return_candidates(cards: List[Card], ctx: GameContext) -> List[Card]:
    """可以当还牌的牌：10 以下（含 10）的非王牌。

    逢人配（红桃级牌）虽然常常也是小点数，但还出去等于把万能牌送人，
    一律排除（``auto_pick`` 的策略说明里也是这么写的）。
    """
    out = [c for c in cards
           if not c.is_joker and not is_wild(c, ctx)
           and c.rank in _RETURN_RANKS]
    return sort_hand(out, ctx)


def _count_big_jokers(cards: List[Card]) -> int:
    """手里有几张大王（两副牌共两张）。"""
    return sum(1 for c in cards if c.rank == BIG_JOKER)


def _has_two_big_jokers(cards: List[Card]) -> bool:
    """手里是否有两张大王（单人视角的抗贡条件）。"""
    return _count_big_jokers(cards) >= 2


def _move(hands: List[List[Card]], src: int, dst: int, card: Card) -> None:
    """把一张牌从 src 的手牌移到 dst。"""
    hands[src] = [c for c in hands[src] if c != card]
    hands[dst] = list(hands[dst]) + [card]


def _seat_names() -> Tuple[str, ...]:
    """座位名（避免反向依赖 engine 的常量）。"""
    from .config import SEAT_NAMES
    return tuple(SEAT_NAMES)


def auto_pick(tribute: Tribute) -> Optional[Card]:
    """给电脑位挑一个贡牌 / 还牌 / 选贡 / 选还。

    策略都很朴素（够用即可）：
    * 贡牌：最大点数的牌里，挑花色最稀有的（把手上的同花色留住，方便凑同花顺）；
    * 还贡：最便宜的那张（点数最低），绝不还逢人配；
    * 选贡 / 选还：优先能凑炸弹（点数已在手上）或同花顺（花色在手牌里最多）的牌。
    """
    action = tribute.current()
    if action is None:
        return None
    options = tribute.options(action)
    if not options:
        return None
    hand = tribute.hand.hands[action.player]
    ctx = tribute.ctx

    if action.kind == GIFT:
        return _pick_gift(options, hand, ctx)
    if action.kind == RETURN:
        return _pick_return(options, ctx)
    return _pick_for_hand(options, hand, ctx)


def _pick_gift(options: List[Card], hand: List[Card],
               ctx: GameContext) -> Card:
    """贡牌：同点数的候选里挑花色最稀有的那张。"""
    suits = {}
    for c in hand:
        suits[c.suit] = suits.get(c.suit, 0) + 1
    return min(options, key=lambda c: (suits.get(c.suit, 0),
                                       card_order(c, ctx)))


def _pick_return(options: List[Card], ctx: GameContext) -> Card:
    """还贡：点数最低的那张；王与逢人配本就不在候选里。"""
    return min(options, key=lambda c: card_order(c, ctx))


def _pick_for_hand(options: List[Card], hand: List[Card],
                   ctx: GameContext) -> Card:
    """选贡 / 选还：优先凑炸弹，其次凑同花顺，最后挑大的。"""
    ranks = {}
    suits = {}
    for c in hand:
        ranks[c.rank] = ranks.get(c.rank, 0) + 1
        suits[c.suit] = suits.get(c.suit, 0) + 1

    def score(c: Card) -> Tuple[int, int, int]:
        bomb = ranks.get(c.rank, 0)              # 已有同点 → 凑炸弹
        flush = suits.get(c.suit, 0)             # 同花色多 → 凑同花顺
        return (bomb, flush, card_order(c, ctx))

    return max(options, key=score)


def run_auto(tribute: Optional[Tribute]) -> List[str]:
    """全部自动走完进贡，返回事件行。

    用于无头自对弈与自检；界面版由真人逐个动作驱动，电脑位调 :func:`auto_pick`。
    """
    if tribute is None:
        return []
    if tribute.refused:                  # 抗贡：不用换牌，只要定下谁先出
        return tribute.apply()
    if not tribute.active:
        return []
    events: List[str] = []
    while not tribute.done:
        card = auto_pick(tribute)
        if card is None:
            break
        tribute.choose(card)
    events.extend(tribute.apply())
    return events

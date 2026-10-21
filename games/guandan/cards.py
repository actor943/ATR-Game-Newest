# -*- coding: utf-8 -*-
"""掼蛋牌面模型：Card、两副牌堆、级牌感知的大小排序。

纯逻辑模块，不依赖 flet，可被引擎 / AI / 界面共用。

大小规则（从大到小）::

    大王 > 小王 > 级牌 > A > K > Q > ... > 3 > 2

* **不打 2 时，2 是最小的牌**（比 3 还小）；本把打 2 时四张 2 全是级牌、
  比 A 还大。级牌永远大于所有自然牌。
* **一把只有一个级牌点数**，等于上一把**头游方**升级之后的分数。
  所以不会出现「甲丙打 3、乙丁打 4，上把乙丁头游了，甲丙还能拿红桃 3
  当逢人配」这种两个点数同时算级牌的情况 —— 乙丁头游之后，本把只认
  乙丁的新级数，红桃 3 立刻退回普通牌。
* 该点数的**红桃**牌是本把唯一的「逢人配」万能牌（见 rules.py）。
* 顺子 / 连对 / 三顺（钢板）里**不能出现王**；2 与级牌实体牌都可以出现
  （2 是本作最小的自然牌，级牌按它本来的点数占位，不再被排除）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

_TOTAL_DECKS = 2
TOTAL_CARDS = 108

# 自然点数：不打 2 时 2 最小、A 最大（级牌另算，见 card_order）
NATURAL_RANKS: List[str] = ["2", "3", "4", "5", "6", "7", "8", "9", "10",
                            "J", "Q", "K", "A"]
# 顺子 / 连对 / 三顺（钢板）可用的连续点数：2..A。
# 本作里 2 是**最小的自然牌**（见 NATURAL_RANKS），所以它也排在顺子里的最低位，
# 「23456」就是最小的一条顺子；级牌同样可以进顺子（见 rules._only_window_cards）。
RUN_RANKS: List[str] = list(NATURAL_RANKS)      # ["2".."A"]
SUITS: List[str] = ["♠", "♥", "♣", "♦"]
JOKERS: List[str] = ["小王", "大王"]
LEVEL_SEQUENCE: List[str] = ["2", "3", "4", "5", "6", "7", "8", "9",
                             "10", "J", "Q", "K", "A"]  # 级数从2打到A

# 排序用基准值
_JOKER_ORDER = {"小王": 40, "大王": 41}
_LEVEL_ORDER_BASE = 20  # 级牌排在 2(=12) 之后：20 + 自然序


@dataclass(frozen=True)
class Card:
    """一张牌。两副牌中同点数同花色有两张，用 ``copy_index`` 区分。"""

    rank: str           # 点数，或 "小王"/"大王"
    suit: str           # 花色；王为空字符串
    copy_index: int = 0  # 同名牌的第几张（0/1）

    @property
    def is_joker(self) -> bool:
        return self.suit == ""

    def __str__(self) -> str:
        return self.rank if self.is_joker else f"{self.rank}{self.suit}"


TEAM_LABELS: Tuple[str, str] = ("甲丙", "乙丁")   # 队 0（玩家甲丙）/ 队 1（乙丁）


@dataclass(frozen=True)
class GameContext:
    """一手牌的静态背景：**本把唯一的级牌点数** + 它属于哪一队。

    ``level`` 是唯一的级牌点数，等于上一把**头游方**升级之后的分数。一把里
    只有这一个点数是级牌：即便两队级数不同（甲丙打 3、乙丁打 4），本把也只认
    上把头游方那一个点数 —— 所以「甲丙打 3、乙丁打 4，上把乙丁头游了」时，
    红桃 3 不再是逢人配，只有红桃 4 是。

    ``owner_teams`` 回答「这个点数是谁在打」：

    * 只有头游方在打它 → 一队独有，如 ``(1,)``；
    * 两队级数恰好相同（含开局双方都打 2）→ 双方共有 ``(0, 1)``。
    """

    level: str                          # 本把唯一的级牌点数，例如 "5"
    owner_teams: Tuple[int, ...] = (0, 1)   # 谁在打这个点数

    def __post_init__(self) -> None:
        lv = self.level
        if isinstance(lv, tuple):
            # 兼容旧写法；一把只有一个级牌点数，给两个视为用法错误
            if len(lv) != 1:
                raise ValueError("一把只有一个级牌点数，不能同时给两个")
            lv = lv[0]
        owners = tuple(self.owner_teams)
        if not owners or any(t not in (0, 1) for t in owners):
            raise ValueError("owner_teams 只能是 (0,) / (1,) / (0, 1)")
        object.__setattr__(self, "owner_teams", owners)

    # ---- 归属查询 ----

    def level_teams(self, rank: str) -> Tuple[int, ...]:
        """该点数是哪几队的级牌；非级牌返回 ``()``。"""
        return self.owner_teams if rank == self.level else ()

    def level_team(self, rank: str) -> Optional[int]:
        """唯一归属的队；双方共有（或不是级牌）时返回 ``None``。"""
        teams = self.level_teams(rank)
        return teams[0] if len(teams) == 1 else None

    def is_my_level(self, rank: str, team: int) -> bool:
        """该点数是不是 ``team`` 这一队正在打的级牌。"""
        return rank == self.level and team in self.owner_teams

    def level_owner_label(self, rank: str) -> str:
        """级牌归属文案：``"甲丙"`` / ``"乙丁"`` / ``"双方共有"`` / ``""``。"""
        teams = self.level_teams(rank)
        if not teams:
            return ""
        if len(teams) == 2:
            return "双方共有"
        return TEAM_LABELS[teams[0]]

    # ---- 兼容旧接口 ----

    def is_level_rank(self, rank: str) -> bool:
        """该点数是不是本把的级牌（全把只有一个）。"""
        return rank == self.level

    @property
    def level_rank(self) -> str:
        """兼容别名：本把唯一的级牌点数。"""
        return self.level

    @property
    def levels(self) -> Tuple[str, ...]:
        """级牌点数列表（只有一个）；供界面按点数遍历。"""
        return (self.level,)


def build_deck() -> List[Card]:
    """两副牌共 108 张（104 普通牌 + 4 王）。"""
    deck: List[Card] = []
    for _ in range(_TOTAL_DECKS):
        for rank in NATURAL_RANKS:
            for suit in SUITS:
                deck.append(Card(rank, suit))
        for name in JOKERS:
            deck.append(Card(name, ""))
    # 同名牌 copy_index 标为 0/1
    seen: dict[tuple[str, str], int] = {}
    result: List[Card] = []
    for card in deck:
        key = (card.rank, card.suit)
        idx = seen.get(key, 0)
        seen[key] = idx + 1
        result.append(Card(card.rank, card.suit, idx))
    return result


def is_wild(card: Card, ctx: GameContext) -> bool:
    """红桃级牌 = 逢人配（万能牌）。

    一把只有一个级牌点数，因此也**只有一种逢人配**：上一把头游方正在打的
    那个点数的红桃牌。对方级数的红桃牌（哪怕对方正在打它）在本把也不是万能牌。
    """
    return (card.suit == "♥" and not card.is_joker
            and ctx.is_level_rank(card.rank))


def wild_owner(card: Card, ctx: GameContext) -> Tuple[int, ...]:
    """这张逢人配原本属于哪一队；非逢人配返回 ``()``。

    只有头游方在打这个点数时归其独有，如 ``(1,)``；两队级数相同时
    （含开局都打 2）双方共有 ``(0, 1)``。
    """
    if not is_wild(card, ctx):
        return ()
    return ctx.level_teams(card.rank)


def wild_owner_label(card: Card, ctx: GameContext) -> str:
    """逢人配归属文案：``"甲丙的"`` / ``"乙丁的"`` / ``"双方共有的"`` / ``""``。"""
    teams = wild_owner(card, ctx)
    if not teams:
        return ""
    if len(teams) == 2:
        return "双方共有的"
    return f"{TEAM_LABELS[teams[0]]}的"


def wild_label(card: Card, ctx: GameContext) -> str:
    """逢人配的 tooltip 后缀；非逢人配返回 ""。"""
    return "逢人配·万能牌" if is_wild(card, ctx) else ""


def level_label(card: Card, ctx: GameContext) -> str:
    """级牌的 tooltip 后缀；非级牌返回 ""。

    注意红桃级牌同时是逢人配，由 :func:`wild_owner_label` 优先表达。
    """
    if card.is_joker or is_wild(card, ctx):
        return ""
    if ctx.is_level_rank(card.rank):
        return f"级牌·{ctx.level_owner_label(card.rank)}·大于所有自然牌"
    return ""


def card_order(card: Card, ctx: GameContext) -> int:
    """单张大小序值：大王 > 小王 > 级牌 > A > ... > 3 > 2。

    不打 2 时 2 是最小的自然牌；本把打 2 时 2 是级牌，抬到所有自然牌之上。
    """
    if card.is_joker:
        return _JOKER_ORDER[card.rank]
    if ctx.is_level_rank(card.rank):
        return _LEVEL_ORDER_BASE + NATURAL_RANKS.index(card.rank)
    return NATURAL_RANKS.index(card.rank)  # 0..12（不打 2 时 2 最小）


def rank_order(rank: str, ctx: GameContext) -> int:
    """按点数取序值（不含具体花色）；王也可作「对子」点数。"""
    if rank in _JOKER_ORDER:
        return _JOKER_ORDER[rank]
    if ctx.is_level_rank(rank):
        return _LEVEL_ORDER_BASE + NATURAL_RANKS.index(rank)
    return NATURAL_RANKS.index(rank)


def run_rank_order(rank: str) -> int:
    """顺子类牌型内部的点数次序（2..A，永远不含王）。

    级牌按它本来的点数占位（打 4 时 4 就是顺子里的 4），不再单独抬升。
    """
    return RUN_RANKS.index(rank)


def sort_hand(cards: Iterable[Card], ctx: GameContext) -> List[Card]:
    """手牌从大到小排序，方便展示与选牌。"""
    return sorted(cards, key=lambda c: (card_order(c, ctx),
                                         c.suit, c.copy_index),
                  reverse=True)


def advance_level(level: str, gain: int) -> str:
    """升级：封顶在 A（打过 A 的胜利判定见 engine）。"""
    idx = min(LEVEL_SEQUENCE.index(level) + gain,
              len(LEVEL_SEQUENCE) - 1)
    return LEVEL_SEQUENCE[idx]


# ============================================================
# 界面辅助：把「级牌有多大」说清楚
# ============================================================


def level_ranks_desc(ctx: GameContext) -> str:
    """本把级牌说明（一把只有一个级牌点数）。

    例：``"级牌 5（乙丁，上把头游方）"``、``"级牌 2（双方共有）"``
    """
    owner = ctx.level_owner_label(ctx.level)
    if owner == "双方共有":
        return f"级牌 {ctx.level}（双方共有）"
    return f"级牌 {ctx.level}（{owner}，上把头游方）"


def size_order_hint(ctx: GameContext) -> str:
    """一句话说清单张大小顺序，级牌以【】标出。

    本把只有一个级牌点数，它大于 2；其余牌按自然点数（2 > A > … > 3）。
    结尾额外说明「【】里的是级牌、2 是除级牌外最大的自然牌」—— 因为级牌和
    自然 2 都排在 A 前面，光看顺序分不清哪张是级牌，容易被误读成「2 也是级牌」。
    """
    parts = ["大王", "小王", f"【{ctx.level}】"]
    normal = [r for r in reversed(NATURAL_RANKS) if r != ctx.level]
    if len(normal) > 3:                 # 中间压缩，避免界面撑爆
        normal = normal[:2] + ["…"] + normal[-1:]
    parts.extend(normal)
    order = "  >  ".join(parts)
    if ctx.level == "2":       # 本把打 2：所有 2 都是级牌，没有「自然 2」
        return f"{order}（【2】= 级牌；本把打 2，四张 2 全是级牌、比 A 大）"
    return (f"{order}（【{ctx.level}】= 级牌；不打 2 时 2 是最小的自然牌，"
            f"比 3 还小）")

# -*- coding: utf-8 -*-
"""掼蛋牌型规则（对外统一入口）：识别 + 比较 + 从手牌枚举牌型。

这个文件原来把三件不同的事塞在一起，接近 600 行。现在拆成几个小模块，
职责清楚后更好读、也更好改：

====================== ============================================ ==========
模块                   负责什么                                    行数量级
====================== ============================================ ==========
``rules_base.py``      牌型枚举 / 牌型数据结构 / 共用小工具        约 100
``rules_parse.py``     识别：给一组牌判断它是什么牌型              约 230
``rules_compare.py``   比较：这一手牌能不能压过那一手              约 40
``rules.py``（本文件） 枚举：从手牌里列出所有能真正打出的牌型      约 280
====================== ============================================ ==========

对外的用法**完全没变**，仍然这样导入::

    from games.guandan.rules import ComboType, beats, parse
    from games.guandan.rules import find_leads, find_beats, iter_combos

压牌层级
--------
::

    天王炸(4王) > 同花顺(≥5同花色连续) > 炸弹(≥4同点) > 普通牌型

普通牌型必须**同型同长**才能互压：

* 单张 / 对子 / 三张 / 三带二 / 顺子(恰好5张) / 连对(恰好3对) /
  钢板(恰好2组三张)；
* 王对（小王+小王 / 大王+大王）是合法对子。

关键规则
--------
* 级牌（上把头游方升级后的分数）大于所有自然牌，可正常组对 / 三张 / 炸弹。
  单张大小：大王 > 小王 > 级牌 > A > K > … > 3 > 2（不打 2 时 2 最小）。
* 顺子 / 连对 / 钢板 / 同花顺**不能包含王**；2 与**级牌实体牌都能参加**
  （级牌按它本来的点数占位，如打 4 时「23456」是合法顺子）；逢人配
  （红桃级牌）可代替其中任意一张。
* 逢人配单独打出时按级牌本身计；逢人配不能代替王。
* 炸弹比大小：先比张数再比点数；同花顺同理（先张数再比最高牌）。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from .cards import (
    Card,
    GameContext,
    RUN_RANKS,
    SUITS,
    card_order,
    is_wild,
    rank_order,
    run_rank_order,
)
from .rules_base import (
    Combo,
    ComboType,
    TYPE_LEVEL,
    _is_joker_rank,
    _mk,
    _run_windows,
)
from .rules_compare import beats
from .rules_parse import parse

# ---- 再导出：让历史代码只需要 import rules 一个模块 ----
__all__ = [
    "Combo", "ComboType", "TYPE_LEVEL", "beats", "parse",
    "iter_combos", "find_leads", "find_beats",
]


# ============================================================
# 从手牌枚举牌型（供 AI 主动出牌 / 跟牌用）
# ============================================================

@dataclass
class _HandView:
    """手牌的一次「拆解视图」：把牌分成普通牌（按点数归堆）和逢人配。"""

    by_rank: Dict[str, List[Card]]     # 自然牌（不含逢人配），稳定排序
    wilds: List[Card]
    counts: Counter


def _hand_view(hand: Iterable[Card], ctx: GameContext) -> _HandView:
    """把手牌拆成「按点数的普通牌」+「逢人配」两份清单。"""
    by_rank: Dict[str, List[Card]] = {}
    wilds: List[Card] = []
    for card in hand:
        if is_wild(card, ctx):
            wilds.append(card)
        else:
            by_rank.setdefault(card.rank, []).append(card)
    return _HandView(by_rank, wilds, Counter(
        {r: len(c) for r, c in by_rank.items()}))


class _Sel:
    """单个组合内部的选牌器：按点数偏移取牌，保证同一张牌不被重复选中。"""

    def __init__(self, view: _HandView):
        self.view = view
        self.used: Counter = Counter()      # 每个点数已取走几张
        self.wild_used = 0                  # 逢人配已取走几张

    def take(self, rank: str, k: int) -> List[Card]:
        """按点数取 k 张普通牌（跳过之前已取走的那几张）。"""
        start = self.used[rank]
        self.used[rank] = start + k
        return self.view.by_rank.get(rank, [])[start:start + k]

    def wilds(self, k: int) -> List[Card]:
        """取 k 张逢人配（同样跳过已取走的）。"""
        start = self.wild_used
        self.wild_used += k
        return self.view.wilds[start:start + k]


def _window_fill(window: Sequence[str], per: int, counts: Counter,
                 ctx: GameContext, wild_budget: int) -> Optional[int]:
    """窗口需要的野牌数；超预算返回 ``None``。

    级牌实体牌自己就能占位（打 4 时手上的 4 直接用，不必拿逢人配去补），
    所以这里对级牌点数一视同仁。
    """
    fills = 0
    for rank in window:
        take = min(counts.get(rank, 0), per)
        fills += per - take
    return fills if fills <= wild_budget else None


def _take_window(sel: _Sel, window: Sequence[str], per: int,
                 counts: Counter, ctx: GameContext) -> Tuple[List[Card], int]:
    """按窗口把牌取出来，并返回「取到的牌」与「还差几张要逢人配补」。"""
    cards: List[Card] = []
    fills = 0
    for rank in window:
        take = min(counts.get(rank, 0), per)
        cards.extend(sel.take(rank, take))
        fills += per - take
    return cards, fills


def _cheapest_pair(sel: _Sel, rem: Counter, wild_budget: int,
                   ctx: GameContext) -> Optional[Tuple[List[Card], int]]:
    """从剩余点数中配一个最便宜的对子：先自然对，再单+野，再双野。"""
    for rank, c in sorted(rem.items(), key=lambda kv: rank_order(kv[0], ctx)):
        if c < 2:
            continue
        if _is_joker_rank(rank) or c >= 2:
            return sel.take(rank, 2), 0        # 王对也算（极贵，排最后）
    for rank, c in sorted(rem.items(), key=lambda kv: rank_order(kv[0], ctx)):
        if c == 1 and not _is_joker_rank(rank) and wild_budget >= 1:
            return sel.take(rank, 1) + sel.wilds(1), 1
    if wild_budget >= 2:
        return sel.wilds(2), 2
    return None


def _iter_raw_combos(hand: Sequence[Card], ctx: GameContext) -> Iterator[Combo]:
    """枚举意图牌型（未做规范化）；见 :func:`iter_combos`。"""
    view = _hand_view(hand, ctx)
    w = len(view.wilds)
    counts = view.counts

    # ---- 单张 ----
    for rank, cards_ in view.by_rank.items():
        yield _mk(ComboType.SINGLE, cards_[:1], 1, rank_order(rank, ctx), 0,
                  f"单张({rank})")
    for card in view.wilds:                     # 逢人配单张按级牌本身计
        yield _mk(ComboType.SINGLE, [card], 1, card_order(card, ctx), 0,
                  f"单张({card.rank})")

    # ---- 对子 / 三张 / 炸弹（同点聚合 + 野牌补足）----
    for rank, c in counts.items():
        key = rank_order(rank, ctx)
        if _is_joker_rank(rank):
            if c >= 2:
                sel = _Sel(view)
                yield _mk(ComboType.PAIR, sel.take(rank, 2), 1, key, 0,
                          f"对子({rank})")
            continue                           # 王不能被野牌补充
        if c >= 2:
            sel = _Sel(view)
            yield _mk(ComboType.PAIR, sel.take(rank, 2), 1, key, 0,
                      f"对子({rank})")
        elif c == 1 and w >= 1:
            sel = _Sel(view)
            yield _mk(ComboType.PAIR, sel.take(rank, 1) + sel.wilds(1), 1,
                      key, 1, f"对子({rank})")
        if c >= 1 and c + w >= 3:
            sel = _Sel(view)
            take = min(c, 3)
            yield _mk(ComboType.TRIPLE,
                      sel.take(rank, take) + sel.wilds(3 - take), 1,
                      key, 3 - take, f"三张({rank})")
        for size in range(4, c + w + 1):
            sel = _Sel(view)
            take = min(c, size)
            yield _mk(ComboType.BOMB,
                      sel.take(rank, take) + sel.wilds(size - take), size,
                      key, size - take, f"炸弹({rank}×{size})")
    if w >= 2:                                  # 双逢人配互为对子
        top = max((c.rank for c in view.wilds),
                  key=lambda r: rank_order(r, ctx))
        yield _mk(ComboType.PAIR, view.wilds[:2], 1, rank_order(top, ctx), 2,
                  f"对子({top})")

    # ---- 三带二 ----
    for rank, c in counts.items():
        if _is_joker_rank(rank) or c < 1 or c + w < 3:
            continue
        take = min(c, 3)
        fill_t = 3 - take
        if fill_t > w:
            continue
        rem = counts.copy()
        rem[rank] -= take
        sel = _Sel(view)
        body = sel.take(rank, take) + sel.wilds(fill_t)
        pair = _cheapest_pair(sel, rem, w - fill_t, ctx)
        if pair is None:
            continue
        pair_cards, pair_wilds = pair
        yield _mk(ComboType.FULL_HOUSE, body + pair_cards, 1,
                  rank_order(rank, ctx), fill_t + pair_wilds,
                  f"三带二({rank})")

    # ---- 顺子（恰好 5 张）----
    for window in _run_windows(5):
        if _window_fill(window, 1, counts, ctx, w) is None:
            continue
        sel = _Sel(view)
        cards_, fills = _take_window(sel, window, 1, counts, ctx)
        top = window[-1]
        yield _mk(ComboType.STRAIGHT, cards_ + sel.wilds(fills), 5,
                  run_rank_order(top), fills,
                  f"顺子(5张,{window[0]}~{top})")

    # ---- 连对（恰好 3 对）----
    for window in _run_windows(3):
        if _window_fill(window, 2, counts, ctx, w) is None:
            continue
        sel = _Sel(view)
        cards_, fills = _take_window(sel, window, 2, counts, ctx)
        top = window[-1]
        yield _mk(ComboType.PAIR_SEQ, cards_ + sel.wilds(fills), 3,
                  run_rank_order(top), fills,
                  f"连对(3连,{window[0]}~{top})")

    # ---- 钢板（恰好 2 组三张）----
    for window in _run_windows(2):
        if _window_fill(window, 3, counts, ctx, w) is None:
            continue
        sel = _Sel(view)
        cards_, fills = _take_window(sel, window, 3, counts, ctx)
        top = window[-1]
        yield _mk(ComboType.TRIPLE_SEQ, cards_ + sel.wilds(fills), 2,
                  run_rank_order(top), fills,
                  f"钢板(2组,{window[0]}~{top})")

    # ---- 同花顺 ----
    for suit in SUITS:
        suit_hand = [c for c in hand if c.suit == suit]
        suit_view = _hand_view(suit_hand, ctx)
        sw = len(suit_view.wilds)
        for length in range(5, len(RUN_RANKS) + 1):
            for window in _run_windows(length):
                if _window_fill(window, 1, suit_view.counts, ctx, sw) is None:
                    continue
                sel = _Sel(suit_view)
                cards_, fills = _take_window(sel, window, 1, suit_view.counts,
                                             ctx)
                top = window[-1]
                yield _mk(ComboType.FLUSH_STRAIGHT, cards_ + sel.wilds(fills),
                          length, run_rank_order(top), fills,
                          f"同花顺({length}张{suit},{window[0]}~{top})")

    # ---- 天王炸 ----
    if len(view.by_rank.get("大王", [])) == 2 \
            and len(view.by_rank.get("小王", [])) == 2:
        yield _mk(ComboType.JOKER_BOMB,
                  view.by_rank["大王"] + view.by_rank["小王"], 4, 41, 0,
                  "天王炸")


def iter_combos(hand: Sequence[Card], ctx: GameContext) -> Iterator[Combo]:
    """枚举手牌中所有**可真正打出**的牌型，含用逢人配补的变体。

    这里做的是「规范化」：把每个意图牌型按 :func:`parse` 的口径重解一遍，
    只输出重解结果本身。

    为什么必须规范化：引擎（``Hand.play``）拿到的是一组散牌，会用
    ``parse`` 的「就高解释」自行定类型。同一组牌可能存在多种解释，例如：

    * ``9♣ 9♠ 10♦ 10♥ J♥ J♥``（打 J/K）本意连对 8~10，实际会被判成钢板 9~10；
    * 五张同为 3 的牌本意三带二，实际会被判成 5 张炸弹。

    若不规范化，枚举出来的候选与引擎最终采纳的牌型不一致，跟牌时就会出现
    「AI 以为能压、引擎判定压不过」的 IllegalMove；界面上的「能不能压」提示
    也会与实际不符。
    """
    seen: Set[Tuple[ComboType, int, int, Tuple[Card, ...]]] = set()
    for combo in _iter_raw_combos(hand, ctx):
        canonical = parse(combo.cards, ctx)
        if canonical is None:
            continue
        key = (canonical.type, canonical.size, canonical.main_key,
               canonical.cards)
        if key in seen:                     # 不同起意可能收敛到同一手牌
            continue
        seen.add(key)
        yield canonical


def find_leads(hand: Sequence[Card], ctx: GameContext) -> List[Combo]:
    """主动出牌时的全部候选牌型（本轮由你先出，没人压）。"""
    return list(iter_combos(hand, ctx))


def find_beats(hand: Sequence[Card], target: Combo,
               ctx: GameContext) -> List[Combo]:
    """跟牌时所有能压住 ``target`` 的候选。"""
    return [c for c in iter_combos(hand, ctx) if beats(c, target)]

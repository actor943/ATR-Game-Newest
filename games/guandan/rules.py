# -*- coding: utf-8 -*-
"""掼蛋牌型规则：识别（含逢人配）、大小比较、出牌 / 跟牌候选生成。

压牌层级
--------
::

    天王炸(4王) > 同花顺(≥5同花色连续) > 炸弹(≥4同点) > 普通牌型

普通牌型必须**同型同长**才能互压：

* 单张 / 对子 / 三张 / 三带二 / 顺子(恰好5张) / 连对(恰好3对) /
  钢板(恰好2组三张)
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

import enum
from collections import Counter
from dataclasses import dataclass
from typing import (Dict, Iterable, Iterator, List, Optional, Sequence, Set,
                    Tuple)

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

_JOKER_RANKS = ("小王", "大王")


class ComboType(enum.Enum):
    SINGLE = "单张"
    PAIR = "对子"
    TRIPLE = "三张"
    FULL_HOUSE = "三带二"
    STRAIGHT = "顺子"
    PAIR_SEQ = "连对"
    TRIPLE_SEQ = "钢板"
    BOMB = "炸弹"
    FLUSH_STRAIGHT = "同花顺"
    JOKER_BOMB = "天王炸"


# 压牌层级：普通=0 < 炸弹=1 < 同花顺=2 < 天王炸=3
TYPE_LEVEL: Dict[ComboType, int] = {
    ComboType.SINGLE: 0,
    ComboType.PAIR: 0,
    ComboType.TRIPLE: 0,
    ComboType.FULL_HOUSE: 0,
    ComboType.STRAIGHT: 0,
    ComboType.PAIR_SEQ: 0,
    ComboType.TRIPLE_SEQ: 0,
    ComboType.BOMB: 1,
    ComboType.FLUSH_STRAIGHT: 2,
    ComboType.JOKER_BOMB: 3,
}


@dataclass(frozen=True)
class Combo:
    """一次可打出的牌型。"""

    type: ComboType
    cards: Tuple[Card, ...]
    size: int          # 顺子/连对/钢板长度、炸弹/同花顺张数；其它为 1
    main_key: int      # 主体最高牌序值（同型同长时比这个）
    wilds_used: int = 0
    label: str = ""    # 人读标签，如 "对子(K)"

    def __str__(self) -> str:
        return f"{self.label}[{'+'.join(str(c) for c in self.cards)}]"


def _mk(t: ComboType, cards: Iterable[Card], size: int, key: int,
        wilds_used: int, label: str) -> Combo:
    return Combo(t, tuple(cards), size, key, wilds_used, label)


# ============================================================
# 比较规则
# ============================================================

def beats(candidate: Combo, target: Combo) -> bool:
    """candidate 能否压住 target。"""
    lv_c = TYPE_LEVEL[candidate.type]
    lv_t = TYPE_LEVEL[target.type]
    if lv_c != lv_t:
        return lv_c > lv_t
    if candidate.type in (ComboType.BOMB, ComboType.FLUSH_STRAIGHT):
        # 先比张数，再比点数
        return (candidate.size, candidate.main_key) > (target.size,
                                                       target.main_key)
    if candidate.type is not target.type or candidate.size != target.size:
        return False
    return candidate.main_key > target.main_key


# ============================================================
# 牌型识别（对外主入口）
# ============================================================

def parse(cards: Sequence[Card], ctx: GameContext) -> Optional[Combo]:
    """识别一组牌是什么牌型；非法返回 None。

    多种解释并存时返回最高层级（炸弹 > 同花顺 > ... > 单张），
    即「就高解释」，对出牌人永远不亏。
    """
    cards = tuple(cards)
    n = len(cards)
    if n == 0:
        return None
    if n == 4 and all(c.is_joker for c in cards):
        return _mk(ComboType.JOKER_BOMB, cards, 4, 41, 0, "天王炸")

    wilds = [c for c in cards if is_wild(c, ctx)]
    fixed = [c for c in cards if not is_wild(c, ctx)]
    w = len(wilds)
    counts: Counter = Counter(c.rank for c in fixed)

    for matcher in (
        _parse_bomb, _parse_flush, _parse_full_house,
        _parse_triple_seq, _parse_pair_seq,
        _parse_straight, _parse_triple, _parse_pair, _parse_single,
    ):
        combo = matcher(cards, fixed, wilds, w, counts, ctx, n)
        if combo is not None:
            return combo
    return None


# ---------- 各牌型识别（所有牌都必须用上） ----------

def _is_joker_rank(rank: str) -> bool:
    return rank in _JOKER_RANKS


def _parse_single(cards, fixed, wilds, w, counts, ctx, n):
    if n != 1:
        return None
    c = cards[0]
    return _mk(ComboType.SINGLE, cards, 1, card_order(c, ctx), 0,
                f"单张({c.rank})")


def _parse_pair(cards, fixed, wilds, w, counts, ctx, n):
    if n != 2:
        return None
    if len(fixed) == 2:                       # 含王对
        if len(counts) == 1:
            rank = fixed[0].rank
            return _mk(ComboType.PAIR, cards, 1, rank_order(rank, ctx), 0,
                        f"对子({rank})")
        return None
    if len(fixed) == 1:                       # 1 自然 + 1 野
        if fixed[0].is_joker:
            return None                       # 野牌不能代替王
        rank = fixed[0].rank
        return _mk(ComboType.PAIR, cards, 1, rank_order(rank, ctx), 1,
                    f"对子({rank})")
    # 两张全是逢人配：按较高点数的级牌计
    top = max((c.rank for c in wilds), key=lambda r: rank_order(r, ctx))
    return _mk(ComboType.PAIR, cards, 1, rank_order(top, ctx), 2,
                f"对子({top})")


def _parse_triple(cards, fixed, wilds, w, counts, ctx, n):
    if n != 3:
        return None
    if len(fixed) == 3:
        if len(counts) == 1 and not fixed[0].is_joker:
            rank = fixed[0].rank
            return _mk(ComboType.TRIPLE, cards, 1, rank_order(rank, ctx), 0,
                        f"三张({rank})")
        return None
    if len(fixed) in (1, 2):
        if len(counts) != 1 or fixed[0].is_joker:
            return None
        rank = fixed[0].rank
        return _mk(ComboType.TRIPLE, cards, 1, rank_order(rank, ctx),
                    3 - len(fixed), f"三张({rank})")
    # 三张全是逢人配
    top = max((c.rank for c in wilds), key=lambda r: rank_order(r, ctx))
    return _mk(ComboType.TRIPLE, cards, 1, rank_order(top, ctx), 3,
                f"三张({top})")


def _parse_bomb(cards, fixed, wilds, w, counts, ctx, n):
    if n < 4 or len(counts) != 1:
        return None
    rank = fixed[0].rank
    if fixed[0].is_joker:
        return None                           # 王不能与野牌组炸弹
    return _mk(ComboType.BOMB, cards, n, rank_order(rank, ctx), w,
                f"炸弹({rank}×{n})")


def _parse_full_house(cards, fixed, wilds, w, counts, ctx, n):
    if n != 5:
        return None
    # 情形 A：三张主体来自自然牌
    for t, c_t in counts.items():
        if _is_joker_rank(t) or c_t > 3:
            continue
        fill_t = 3 - c_t
        if fill_t > w:
            continue
        rem = counts.copy()
        del rem[t]                            # c_t ≤ 3，全部进主体
        rem_fixed = sum(rem.values())
        if rem_fixed > 2 or len(rem) > 1:
            continue
        if rem_fixed == 2:
            p = next(iter(rem))
            wild_used = fill_t
        elif rem_fixed == 1:
            p = next(iter(rem))
            if _is_joker_rank(p) or w - fill_t < 1:
                continue
            wild_used = fill_t + 1
        else:
            if w - fill_t < 2:
                continue
            p = max((c.rank for c in wilds), key=lambda r: rank_order(r, ctx))
            if p == t:
                continue
            wild_used = fill_t + 2
        return _mk(ComboType.FULL_HOUSE, cards, 1, rank_order(t, ctx),
                    wild_used, f"三带二({t}+{p})")
    # 情形 B：三张主体全由逢人配充当
    if w >= 3:
        t = max((c.rank for c in wilds), key=lambda r: rank_order(r, ctx))
        rem_w = w - 3
        for p, c_p in counts.items():
            if p == t:
                continue
            if c_p == 2:
                return _mk(ComboType.FULL_HOUSE, cards, 1, rank_order(t, ctx),
                            3, f"三带二({t}+{p})")
            if c_p == 1 and not _is_joker_rank(p) and rem_w >= 1:
                return _mk(ComboType.FULL_HOUSE, cards, 1, rank_order(t, ctx),
                            4, f"三带二({t}+{p})")
    return None


def _run_windows(length: int) -> List[List[str]]:
    """3..A 上所有长度为 length 的连续窗口。"""
    return [RUN_RANKS[i:i + length]
            for i in range(0, len(RUN_RANKS) - length + 1)]


def _only_window_cards(fixed: Sequence[Card], window: Sequence[str], per: int,
                       ctx: GameContext) -> bool:
    """所有自然牌都落在窗口内且不超配额。

    级牌实体牌**可以**进顺子（打 4 时「23456」就是合法顺子，4 按它本来的
    点数占位）；只有王不在 :data:`~cards.RUN_RANKS` 里，自然被 ``rank not in
    window`` 挡掉，不需要额外判断 ``ctx.is_level_rank``。
    """
    cnt = Counter(c.rank for c in fixed)
    for rank, c in cnt.items():
        if rank not in window or c > per:
            return False
    return True


def _scan_windows(fixed: Sequence[Card], length: int, per: int,
                  ctx: GameContext) -> Optional[Tuple[int, str, str]]:
    """在所有可用窗口中取**最高**解释。

    带逢人配时同一组牌可能匹配多个窗口（如 [4~J]+野牌 既可作 3~J
    也可作 4~Q），取最高窗口与「就高解释」原则一致，
    供 AI 枚举出的高点牌型在引擎复检时结果相同。
    返回 (main_key, 窗口起点, 窗口终点)。
    """
    best = None
    for window in _run_windows(length):
        if not _only_window_cards(fixed, window, per, ctx):
            continue
        top = window[-1]
        key = run_rank_order(top)
        if best is None or key > best[0]:
            best = (key, window[0], top)
    return best


def _parse_straight(cards, fixed, wilds, w, counts, ctx, n):
    if n != 5:
        return None
    best = _scan_windows(fixed, n, 1, ctx)
    if best is None:
        return None
    key, lo, top = best
    return _mk(ComboType.STRAIGHT, cards, n, key, w, f"顺子({n}张,{lo}~{top})")


def _parse_flush(cards, fixed, wilds, w, counts, ctx, n):
    if n < 5 or len({c.suit for c in fixed}) > 1:
        return None
    best = _scan_windows(fixed, n, 1, ctx)
    if best is None:
        return None
    key, lo, top = best
    return _mk(ComboType.FLUSH_STRAIGHT, cards, n, key, w,
               f"同花顺({n}张,{lo}~{top})")


def _parse_pair_seq(cards, fixed, wilds, w, counts, ctx, n):
    if n != 6:
        return None
    k = 3
    best = _scan_windows(fixed, k, 2, ctx)
    if best is None:
        return None
    key, lo, top = best
    return _mk(ComboType.PAIR_SEQ, cards, k, key, w, f"连对({k}连,{lo}~{top})")


def _parse_triple_seq(cards, fixed, wilds, w, counts, ctx, n):
    if n != 6:
        return None
    k = 2
    best = _scan_windows(fixed, k, 3, ctx)
    if best is None:
        return None
    key, lo, top = best
    return _mk(ComboType.TRIPLE_SEQ, cards, k, key, w, f"钢板({k}组,{lo}~{top})")


# ============================================================
# 从手牌枚举牌型（供 AI 主动出牌 / 跟牌用）
# ============================================================

@dataclass
class _HandView:
    by_rank: Dict[str, List[Card]]     # 自然牌（不含逢人配），稳定排序
    wilds: List[Card]
    counts: Counter


def _hand_view(hand: Iterable[Card], ctx: GameContext) -> _HandView:
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
        self.used: Counter = Counter()
        self.wild_used = 0

    def take(self, rank: str, k: int) -> List[Card]:
        start = self.used[rank]
        self.used[rank] = start + k
        return self.view.by_rank.get(rank, [])[start:start + k]

    def wilds(self, k: int) -> List[Card]:
        start = self.wild_used
        self.wild_used += k
        return self.view.wilds[start:start + k]


def _window_fill(window: Sequence[str], per: int, counts: Counter,
                 ctx: GameContext, wild_budget: int) -> Optional[int]:
    """窗口需要的野牌数；超预算返回 None。

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
    ``parse`` 的「就高解释」自行定类型。同一组牌可能存在多种解释，例如

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
    """主动出牌时的全部候选牌型。"""
    return list(iter_combos(hand, ctx))


def find_beats(hand: Sequence[Card], target: Combo,
               ctx: GameContext) -> List[Combo]:
    """跟牌时所有能压住 target 的候选。"""
    return [c for c in iter_combos(hand, ctx) if beats(c, target)]
# -*- coding: utf-8 -*-
"""掼蛋牌型识别：给一组牌，判断它「是什么牌型」。

对外只有一个主入口 :func:`parse`。内部按 **从高到低** 的顺序逐个试匹配器，
第一个匹配成功就返回 —— 这就是掼蛋里说的「**就高解释**」：

    天王炸 > 炸弹 > 同花顺 > 三带二 > 钢板 > 连对 > 顺子 > 三张 > 对子 > 单张

就高解释对出牌人永远不亏：同样这 5 张牌，按「三带二」打出去没人管，
按「炸弹」打出去对手就得按炸弹接。

关键规则
--------
* 级牌（上把头游方升级后的分数）大于所有自然牌，可正常组对 / 三张 / 炸弹。
  单张大小：大王 > 小王 > 级牌 > A > K > … > 3 > 2（不打 2 时 2 最小）。
* 顺子 / 连对 / 钢板 / 同花顺**不能包含王**；2 与**级牌实体牌都能参加**
  （级牌按它本来的点数占位，如打 4 时「23456」是合法顺子）；逢人配
  （红桃级牌）可代替其中任意一张。
* 逢人配单独打出时按级牌本身计；逢人配不能代替王。
"""

from __future__ import annotations

from collections import Counter
from typing import Optional, Sequence, Tuple

from .cards import (
    Card,
    GameContext,
    card_order,
    is_wild,
    rank_order,
    run_rank_order,
)
from .rules_base import (
    Combo,
    ComboType,
    _is_joker_rank,
    _mk,
    _run_windows,
)


def parse(cards: Sequence[Card], ctx: GameContext) -> Optional[Combo]:
    """识别一组牌是什么牌型；非法返回 ``None``。

    多种解释并存时返回**最高层级**（炸弹 > 同花顺 > … > 单张），
    即「就高解释」，对出牌人永远不亏。

    参数
    ----
    cards
        要判断的那几张牌（顺序无所谓）。
    ctx
        本把的级牌背景（级牌点数 + 归属），决定级牌大小与逢人配是谁的。
    """
    cards = tuple(cards)
    n = len(cards)
    if n == 0:
        return None
    if n == 4 and all(c.is_joker for c in cards):
        return _mk(ComboType.JOKER_BOMB, cards, 4, 41, 0, "天王炸")

    # 把牌分成「逢人配（万能牌）」和「普通牌」两堆
    wilds = [c for c in cards if is_wild(c, ctx)]
    fixed = [c for c in cards if not is_wild(c, ctx)]
    w = len(wilds)                                 # 逢人配张数
    counts: Counter = Counter(c.rank for c in fixed)   # 普通牌按点数计数

    # 从高到低依次尝试；谁先匹配上就算谁
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
#
# 每个匹配器签名一致：
#   (cards, fixed, wilds, w, counts, ctx, n) -> Optional[Combo]
#   cards  = 全部牌；fixed = 非逢人配的牌；wilds = 逢人配；
#   w      = 逢人配张数；counts = 普通牌点数计数；ctx = 级牌背景；n = 总张数


def _parse_single(cards, fixed, wilds, w, counts, ctx, n):
    """单张：任何一张牌都能单独出（逢人配单出按级牌本身计）。"""
    if n != 1:
        return None
    c = cards[0]
    return _mk(ComboType.SINGLE, cards, 1, card_order(c, ctx), 0,
                f"单张({c.rank})")


def _parse_pair(cards, fixed, wilds, w, counts, ctx, n):
    """对子：两张同点；也可以 1 自然牌 + 1 逢人配；王对合法。"""
    if n != 2:
        return None
    if len(fixed) == 2:                       # 两张都是自然牌（含王对）
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
    """三张：三张同点；可以用逢人配补足。"""
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
    """炸弹：4 张及以上同点（王不能与逢人配组炸弹）。"""
    if n < 4 or len(counts) != 1:
        return None
    rank = fixed[0].rank
    if fixed[0].is_joker:
        return None                           # 王不能与野牌组炸弹
    return _mk(ComboType.BOMB, cards, n, rank_order(rank, ctx), w,
                f"炸弹({rank}×{n})")


def _parse_full_house(cards, fixed, wilds, w, counts, ctx, n):
    """三带二：3 张同点 + 一对（成对的那两张可以是逢人配）。"""
    if n != 5:
        return None
    # 情形 A：三张主体来自自然牌
    for t, c_t in counts.items():
        if _is_joker_rank(t) or c_t > 3:
            continue
        fill_t = 3 - c_t                     # 主体还差几张要靠逢人配补
        if fill_t > w:
            continue
        rem = counts.copy()
        del rem[t]                            # c_t ≤ 3，全部进主体
        rem_fixed = sum(rem.values())
        if rem_fixed > 2 or len(rem) > 1:
            continue
        if rem_fixed == 2:
            p = next(iter(rem))              # 对子由两张自然牌组成
            wild_used = fill_t
        elif rem_fixed == 1:
            p = next(iter(rem))
            if _is_joker_rank(p) or w - fill_t < 1:
                continue
            wild_used = fill_t + 1           # 另一张用逢人配补
        else:
            if w - fill_t < 2:
                continue
            p = max((c.rank for c in wilds), key=lambda r: rank_order(r, ctx))
            if p == t:
                continue
            wild_used = fill_t + 2           # 对子两张全是逢人配
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


def _only_window_cards(fixed: Sequence[Card], window: Sequence[str], per: int,
                       ctx: GameContext) -> bool:
    """所有自然牌是否都落在窗口内且不超配额。

    级牌实体牌**可以**进顺子（打 4 时「23456」就是合法顺子，4 按它本来的
    点数占位）；只有王不在 :data:`~games.guandan.cards.RUN_RANKS` 里，自然被
    ``rank not in window`` 挡掉，不需要额外判断 ``ctx.is_level_rank``。
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
    返回 ``(main_key, 窗口起点, 窗口终点)``。
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
    """顺子：恰好 5 张连续单牌。"""
    if n != 5:
        return None
    best = _scan_windows(fixed, n, 1, ctx)
    if best is None:
        return None
    key, lo, top = best
    return _mk(ComboType.STRAIGHT, cards, n, key, w, f"顺子({n}张,{lo}~{top})")


def _parse_flush(cards, fixed, wilds, w, counts, ctx, n):
    """同花顺：5 张及以上同花色的连续牌。"""
    if n < 5 or len({c.suit for c in fixed}) > 1:
        return None
    best = _scan_windows(fixed, n, 1, ctx)
    if best is None:
        return None
    key, lo, top = best
    return _mk(ComboType.FLUSH_STRAIGHT, cards, n, key, w,
               f"同花顺({n}张,{lo}~{top})")


def _parse_pair_seq(cards, fixed, wilds, w, counts, ctx, n):
    """连对：恰好 3 组连续对子（6 张）。"""
    if n != 6:
        return None
    k = 3
    best = _scan_windows(fixed, k, 2, ctx)
    if best is None:
        return None
    key, lo, top = best
    return _mk(ComboType.PAIR_SEQ, cards, k, key, w, f"连对({k}连,{lo}~{top})")


def _parse_triple_seq(cards, fixed, wilds, w, counts, ctx, n):
    """钢板：恰好 2 组连续三张（6 张）。"""
    if n != 6:
        return None
    k = 2
    best = _scan_windows(fixed, k, 3, ctx)
    if best is None:
        return None
    key, lo, top = best
    return _mk(ComboType.TRIPLE_SEQ, cards, k, key, w, f"钢板({k}组,{lo}~{top})")

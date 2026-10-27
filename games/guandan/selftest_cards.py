# -*- coding: utf-8 -*-
"""自检用例（牌与牌型）：牌堆、大小顺序、牌型识别、逢人配、炸弹与顺子。

被 games.guandan.selftest 汇总调用。
"""

from __future__ import annotations

from collections import Counter

from .cards import (
    GameContext,
    advance_level,
    build_deck,
    card_order,
    is_wild,
    rank_order,
)
from .rules import ComboType, beats, parse
from .selftest_common import C, _C3, _C5, _bomb

def test_cards():
    deck = build_deck()
    assert len(deck) == 108, "两副牌应为 108 张"
    assert len(set(deck)) == 108, "每张牌应唯一"
    cnt = Counter((c.rank, c.suit) for c in deck)
    assert all(v == 2 for v in cnt.values()), "每种牌应恰有 2 张"

    # 大小顺序（不打 2 时 2 最小）：2 < 3 < ... < A < 级牌 < 小王 < 大王
    assert card_order(C("2", "♠"), _C5) < card_order(C("3", "♠"), _C5)
    assert card_order(C("3", "♠"), _C5) < card_order(C("A", "♠"), _C5)
    assert card_order(C("A", "♠"), _C5) < card_order(C("5", "♠"), _C5)
    assert card_order(C("5", "♠"), _C5) < card_order(C("小王"), _C5)
    assert card_order(C("小王"), _C5) < card_order(C("大王"), _C5)
    # 4 个 2 打不过 4 个 A（2 是最小的自然牌）
    a4 = parse([C("A", "♦"), C("A", "♥"), C("A", "♣"), C("A", "♠")], _C5)
    b2 = parse([C("2", "♦"), C("2", "♥"), C("2", "♣"), C("2", "♠")], _C5)
    assert a4.type is ComboType.BOMB and b2.type is ComboType.BOMB
    assert beats(a4, b2) and not beats(b2, a4)
    # 本把打 2 时四张 2 是级牌，比 A 大
    _C2 = GameContext("2")
    assert card_order(C("2", "♠"), _C2) > card_order(C("A", "♠"), _C2)
    assert is_wild(C("2", "♥"), _C2)
    # 一把只有一个级牌点数：非本把级牌的点数就是普通牌，不被抬高
    assert card_order(C("4", "♠"), _C5) == card_order(C("4", "♠"), _C3)
    # 逢人配 = 红桃级牌（全把只有一种）
    assert is_wild(C("5", "♥"), _C5)
    assert not is_wild(C("5", "♦"), _C5)
    assert is_wild(C("3", "♥"), _C3) and not is_wild(C("2", "♥"), _C3)
    assert not is_wild(C("5", "♥"), GameContext("2"))
    assert advance_level("K", 3) == "A"
    assert advance_level("A", 3) == "A"     # 封顶
    assert advance_level("2", 1) == "3"
    # 给两个级牌点数是用法错误：一把不可能同时有两个级牌
    try:
        GameContext(("3", "2"))
        raise AssertionError("同时给两个级牌点数应抛 ValueError")
    except ValueError:
        pass


def test_parse_basic():
    assert parse([C("A", "♠"), C("A", "♥")], _C5).type is ComboType.PAIR
    assert parse([C("A", "♠"), C("A", "♥"), C("A", "♦")],
                 _C5).type is ComboType.TRIPLE
    # 逢人配补对子 / 三张
    p = parse([C("A", "♠"), C("5", "♥")], _C5)
    assert p.type is ComboType.PAIR and p.wilds_used == 1
    t = parse([C("3", "♠"), C("3", "♥"), C("5", "♥")], _C5)
    assert t.type is ComboType.TRIPLE and t.wilds_used == 1
    # 三张全是逢人配（两副红桃级牌）
    t2 = parse([C("5", "♥", 0), C("5", "♥", 1), C("3", "♠")], _C5)
    assert t2.type is ComboType.TRIPLE
    assert t2.main_key == rank_order("3", _C5)   # 三张3
    # 三带二
    fh = parse([C("3", "♠"), C("3", "♥"), C("3", "♦"),
                C("2", "♠"), C("2", "♥")], _C5)
    assert fh.type is ComboType.FULL_HOUSE
    # 王对合法；王不能配野牌
    assert parse([C("大王", ci=0), C("大王", ci=1)], _C5).type is ComboType.PAIR
    assert parse([C("小王", ci=0), C("小王", ci=1)], _C5).type is ComboType.PAIR
    assert parse([C("大王"), C("5", "♥")], _C5) is None
    # 天王炸
    jb = parse([C("小王", ci=0), C("小王", ci=1),
                C("大王", ci=0), C("大王", ci=1)], _C5)
    assert jb.type is ComboType.JOKER_BOMB


def test_parse_bombs_and_runs():
    # 炸弹：4 张同点；级牌炸也合法
    b4 = _bomb("K", 4)
    assert b4.type is ComboType.BOMB and b4.size == 4
    b5 = parse([C("K", "♠"), C("K", "♥"), C("K", "♣"), C("K", "♦"),
                C("5", "♥")], _C5)
    assert b5.type is ComboType.BOMB and b5.size == 5
    # 张数多的炸弹大；同张数比点数；级牌炸大于 K 炸
    assert beats(b5, b4)
    assert beats(_bomb("5", 4), b4)
    assert not beats(b4, b5)
    # 同花顺 > 炸弹；天王炸 > 同花顺
    flush = parse([C("3", "♠"), C("4", "♠"), C("6", "♠"),
                   C("7", "♠"), C("5", "♥")], _C5)
    assert flush.type is ComboType.FLUSH_STRAIGHT
    assert beats(flush, b5)
    jb = parse([C("小王", ci=0), C("小王", ci=1),
                C("大王", ci=0), C("大王", ci=1)], _C5)
    assert beats(jb, flush)
    # 顺子**可以**含级牌实体牌（打5时 5♦ 就是顺子里的 5）；逢人配仍可补点位
    st_lv = parse([C("3", "♠"), C("4", "♥"), C("5", "♦"),
                   C("6", "♣"), C("7", "♠")], _C5)
    assert st_lv is not None and st_lv.type is ComboType.STRAIGHT, st_lv
    st = parse([C("3", "♠"), C("4", "♥"), C("6", "♦"),
                C("7", "♣"), C("5", "♥")], _C5)
    assert st.type is ComboType.STRAIGHT and st.size == 5
    # 2 是本作最小的自然牌，可以进顺子：「23456」是最低的一条顺子
    st2 = parse([C("2", "♠"), C("3", "♠"), C("4", "♥"),
                 C("5", "♦"), C("6", "♣")], _C5)
    assert st2 is not None and st2.type is ComboType.STRAIGHT, st2
    # 王永远不能进顺子
    assert parse([C("3", "♠"), C("4", "♥"), C("5", "♦"),
                  C("6", "♣"), C("小王")], _C5) is None
    # 顺子只能 5 张，6 张非法
    st6 = parse([C("3", "♠"), C("4", "♥"), C("6", "♦"), C("7", "♣"),
                 C("8", "♠"), C("5", "♥")], _C5)
    assert st6 is None
    # 连对 / 钢板 / 三顺带对（打5时连对/顺子不能含级牌点，故避开 5）
    ps = parse([C("6", "♠"), C("6", "♥"), C("7", "♠"), C("7", "♥"),
                C("8", "♠"), C("8", "♥")], _C5)
    assert ps.type is ComboType.PAIR_SEQ and ps.size == 3
    ts = parse([C("3", "♠"), C("3", "♥"), C("3", "♣"),
                C("4", "♠"), C("4", "♥"), C("4", "♦")], _C5)
    assert ts.type is ComboType.TRIPLE_SEQ and ts.size == 2
    # 三顺带对不是合法牌型
    tsp = parse([C("3", "♠"), C("3", "♥"), C("3", "♣"),
                 C("4", "♠"), C("4", "♥"), C("4", "♦"),
                 C("7", "♠"), C("7", "♥"), C("8", "♠"), C("8", "♥")],
                _C5)
    assert tsp is None
    # 连对超过 3 对非法（4 对 = 8 张）
    ps4 = parse([C("6", "♠"), C("6", "♥"), C("7", "♠"), C("7", "♥"),
                 C("8", "♠"), C("8", "♥"), C("9", "♠"), C("9", "♥")], _C5)
    assert ps4 is None
    # 钢板超过 2 组非法（3 组 = 9 张）
    ts3 = parse([C("3", "♠"), C("3", "♥"), C("3", "♣"),
                 C("4", "♠"), C("4", "♥"), C("4", "♦"),
                 C("6", "♠"), C("6", "♥"), C("6", "♣")], _C5)
    assert ts3 is None
    # 单张逢人配按级牌本身计
    single = parse([C("5", "♥")], _C5)
    assert single.type is ComboType.SINGLE
    assert beats(single, parse([C("2", "♠")], _C5))

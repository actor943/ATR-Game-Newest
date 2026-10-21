# -*- coding: utf-8 -*-
"""掼蛋底层逻辑自检：规则单元用例 + 自对弈不变量。

用法::

    ./venv/bin/python3 -m games.guandan.selftest
"""

from __future__ import annotations

from collections import Counter

from . import simulator
from .cards import (
    Card,
    GameContext,
    advance_level,
    build_deck,
    card_order,
    is_wild,
    rank_order,
    wild_owner,
    wild_owner_label,
)
from .engine import (
    HAND_SIZE,
    Hand,
    IllegalMove,
    MatchState,
    new_match,
    plan_tribute,
    settle,
)
from .rules import ComboType, beats, parse
from .tribute import Tribute

_C5 = GameContext("5")             # 双方都打 5（共有）
_C5_B = GameContext("5", (1,))     # 只有乙丁在打 5（上一把乙丁头游）
_C3 = GameContext("3", (0,))       # 只有甲丙在打 3
_C7_B = GameContext("7", (1,))     # 乙丁打 4 头游后升到 7


def C(rank: str, suit: str = "", ci: int = 0) -> Card:
    return Card(rank, suit, ci)


def _bomb(rank: str, n: int):
    suits = ["♠", "♥", "♣", "♦"]
    cards = [C(rank, suits[i % 4], i // 4) for i in range(n)]
    return parse(cards, _C5)


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


def test_engine_guards():
    match = new_match(seed=7)
    hand = Hand(match)
    # 轮次之外的玩家不能动作
    other = (hand.turn + 1) % 4
    try:
        hand.play(other, [hand.hands[other][0]])
        raise AssertionError("应当在非法轮次抛 IllegalMove")
    except IllegalMove:
        pass
    # 首出不能过
    try:
        hand.pass_turn(hand.turn)
        raise AssertionError("首出过牌应抛 IllegalMove")
    except IllegalMove:
        pass
    # 出不在手上的牌
    try:
        hand.play(hand.turn, [Card("3", "♠", 9)])
        raise AssertionError("应抛 IllegalMove")
    except IllegalMove:
        pass
    # 正常首出一张单牌
    lead = min(hand.legal_moves(hand.turn),
               key=lambda c: (c.wilds_used, c.main_key))
    combo = hand.play(hand.turn, lead.cards)
    assert combo.type is not None


def test_simulation():
    for seed in (1, 2, 3):
        stats = simulator.play_match(seed)
        assert stats["winner"] in (0, 1), "必须有胜方"
        assert 0 < stats["hands"] < 60, "场局数异常"
        levels = stats["levels"]
        assert "A" in levels, "胜方应停在 A"
        print(f"  seed={seed}: 胜方=队{stats['winner']} "
              f"局数={stats['hands']} 炸弹={stats['bombs']} "
              f"天王炸={stats['joker_bombs']}")


def test_level_ownership():
    """级牌不变量：**一把只有一个级牌点数**。

    规则：级牌点数 = 上一把**头游方**升级之后的分数。因此即使两队级数不同
    （甲丙打 3、乙丁打 4），本把也只有上把头游方那一个点数是级牌；
    对方点数的红桃牌在本把不是逢人配。
    """
    # 1) 双方级数相同（含开局都打 2）：级牌双方共有，两队都认
    same = GameContext("3", (0, 1))
    assert same.level_teams("3") == (0, 1), same.level_teams("3")
    assert same.level_team("3") is None, "双方共有时 level_team 必须返回 None"
    assert same.is_my_level("3", 0) and same.is_my_level("3", 1)
    assert same.level_owner_label("3") == "双方共有"
    assert same.is_level_rank("3") and not same.is_level_rank("2")
    # 2 不是级牌 → 序值回到普通 2，低于级牌 3
    assert card_order(C("2", "♠"), same) < card_order(C("3", "♠"), same)

    # 2) 只有一方在打这个点数：归属唯一，另一个点数**不是**级牌
    mine = GameContext("3", (0,))          # 上一把甲丙头游，升到 3
    assert mine.level_teams("3") == (0,)
    assert mine.level_team("3") == 0
    assert mine.is_my_level("3", 0) and not mine.is_my_level("3", 1)
    assert mine.level_owner_label("3") == "甲丙"
    # 对方正在打 4，但 4 不是本把级牌：序值与普通牌一样
    assert mine.level_teams("4") == ()
    assert not mine.is_level_rank("4")
    assert card_order(C("4", "♠"), mine) == card_order(C("4", "♠"), same)
    assert card_order(C("3", "♠"), mine) > card_order(C("2", "♠"), mine)

    # 3) 级牌**可以**进顺子（打 3 时 3 按它本来的点数占位）
    assert parse([C("3", "♠"), C("4", "♠"), C("5", "♠"),
                  C("6", "♠"), C("7", "♠")], mine) is not None
    assert parse([C("4", "♠"), C("5", "♠"), C("6", "♠"),
                  C("7", "♠"), C("8", "♠")], mine) is not None

    # 4) 非级牌的点数归属为空
    for rank in ("4", "5", "K", "A", "2"):
        assert mine.level_teams(rank) == ()
        assert mine.level_team(rank) is None
        assert mine.level_owner_label(rank) == ""

    # 5) 逢人配 = 红桃级牌，全把只有一种；非红桃 / 非级牌都不是
    assert is_wild(C("3", "♥"), mine), "3 是本把级牌，3♥ 应为逢人配"
    assert not is_wild(C("3", "♦"), mine), "非红桃不是逢人配"
    assert not is_wild(C("4", "♥"), mine), "4 不是本把级牌，4♥ 不是逢人配"
    assert not is_wild(C("5", "♥"), mine), "5 不是级牌"
    assert is_wild(C("3", "♥"), same) and not is_wild(C("2", "♥"), same)

    # 6) **用户描述的场景**：甲丙打 3、乙丁打 4，上把乙丁头游。
    #    乙丁从 4 升到 7 → 本把级牌是 7，红桃 3 立刻退回普通牌，
    #    只有乙丁能用红桃 7 当逢人配；甲丙不能再拿红桃 3 当万能牌。
    after = _C7_B
    assert after.level_rank == "7" and after.level_teams("7") == (1,)
    assert is_wild(C("7", "♥"), after)
    assert not is_wild(C("3", "♥"), after), "乙丁头游后甲丙的 3♥ 不再是逢人配"
    assert not is_wild(C("4", "♥"), after), "乙丁自己的 4♥ 也不再是逢人配"
    assert wild_owner(C("3", "♥"), after) == ()
    assert wild_owner(C("7", "♥"), after) == (1,)
    assert wild_owner_label(C("7", "♥"), after) == "乙丁的"
    assert wild_owner_label(C("3", "♥"), after) == ""

    # 7) 逢人配归属：一队独有标该队，两队共有标「双方共有」
    assert wild_owner(C("3", "♥"), mine) == (0,)
    assert wild_owner_label(C("3", "♥"), mine) == "甲丙的"
    assert wild_owner(C("3", "♥"), same) == (0, 1)
    assert wild_owner_label(C("3", "♥"), same) == "双方共有的"
    assert wild_owner(C("5", "♠"), mine) == ()      # 非逢人配

    # 8) 逢人配可以凑炸弹（除王外可代替任意牌）
    cb = parse([C("J", "♥"), C("J", "♣"), C("J", "♣", 1), C("J", "♠"),
                C("3", "♥")], mine)                  # 用本把的 3♥ 凑 J×5
    assert cb is not None and cb.size == 5, cb
    assert cb.wilds_used == 1, cb
    cb2 = parse([C("10", "♦"), C("10", "♣"), C("10", "♣", 1), C("10", "♠"),
                 C("10", "♠", 1), C("3", "♥")], mine)   # 凑 10×6
    assert cb2 is not None and cb2.size == 6, cb2
    # 对方点数的红桃牌不能当万能牌凑炸弹（打 3 时 4♥ 只是普通 4）
    assert parse([C("J", "♥"), C("J", "♣"), C("J", "♣", 1), C("J", "♠"),
                  C("4", "♥")], mine) is None
    # 逢人配不能代王
    assert parse([C("大王", ""), C("小王", ""), C("大王", "", 1),
                  C("3", "♥")], mine) is None


def test_level_rank_follows_winner():
    """整场不变量：每把的级牌点数 = 上一把头游方升级后的分数，且只有一个。

    这正是用户强调的规则：不会出现「甲丙打 3、乙丁打 4，上把乙丁头游了，
    甲丙还能拿红桃 3 当逢人配」的情况 —— 乙丁头游后本把只认乙丁的新级数。
    """
    from .ai import choose

    for seed in (1, 2, 3):
        match = new_match(seed)
        # 开局双方都打 2：级牌 2 双方共有，红桃 2 是双方共有的逢人配
        assert match.level_rank == "2" and match.level_owner == (0, 1)
        assert is_wild(C("2", "♥"), match.ctx)
        while match.winner is None:
            hand = Hand(match)
            while not hand.ended:
                player = hand.turn
                combo = choose(hand, player)
                if combo is None:
                    hand.pass_turn(player)
                else:
                    hand.play(player, combo.cards)
            result = settle(match, hand)
            winner_team = result.winner_team
            # 级牌点数 = 头游方升级后的分数；只有这一个点数是级牌
            assert match.level_rank == match.levels[winner_team]
            assert match.ctx.is_level_rank(match.level_rank)
            assert match.level_owner == tuple(
                t for t in (0, 1) if match.levels[t] == match.level_rank)
            # 红桃级牌是逢人配；对方级数的红桃牌不是（除非恰好同级）
            assert is_wild(C(match.level_rank, "♥"), match.ctx)
            other = match.levels[1 - winner_team]
            if other != match.level_rank:
                assert not is_wild(C(other, "♥"), match.ctx), (
                    f"红桃 {other} 不应该是逢人配（本把打 {match.level_rank}）")


def _fake_hand(hands, level: str = "5", owner=(1,)):
    """造一个不发牌的 Hand（直接塞手牌），用于进贡等单测。

    ``hands`` 是 4 个座位的手牌列表；级牌点数与归属可指定。
    """
    match = new_match(seed=1)
    match.level_rank = level
    match.level_owner = owner
    hand = Hand(match)                 # 正常发牌一遍，再换成测试手牌
    hand.hands = [list(h) for h in hands]
    hand.ctx = match.ctx
    return hand


def test_tribute_normal():
    """一般进贡：末游把最大的牌（红桃级牌除外）给头游，头游还一张 10 以下。"""
    # 头游甲(0)、二游乙(1)、三游丙(2)、末游丁(3) —— 不同队，非双下
    hands = [
        [C("7", "♠"), C("8", "♦"), C("9", "♣")],          # 甲：头游
        [C("6", "♠")],                                    # 乙
        [C("4", "♠")],                                    # 丙
        [C("A", "♠"), C("A", "♥"), C("K", "♠"),           # 丁：末游
         C("5", "♥"), C("3", "♦")],                       # 5♥ 是逢人配，不能当贡牌
    ]
    hand = _fake_hand(hands, level="5", owner=(1,))
    plan = plan_tribute([0, 1, 2, 3])
    assert not plan.double and plan.payers == (3,) and plan.receivers == (0,)

    tr = Tribute(hand, plan)
    assert tr.active and not tr.refused and not tr.choose_gift
    # 1) 末游选贡牌：只能是最大的 A（逢人配 5♥ 被排除）
    act = tr.current()
    assert act.kind == "gift" and act.player == 3, act
    assert tr.options(act) == [C("A", "♠"), C("A", "♥")], tr.options(act)
    assert not tr.choose(C("K", "♠")), "非最大牌不能当贡牌"
    assert tr.choose(C("A", "♠"))
    # 2) 头游还牌：只能 10 以下（含 10）的非王牌
    act = tr.current()
    assert act.kind == "return" and act.player == 0, act
    assert [str(c) for c in tr.options(act)] == ["9♣", "8♦", "7♠"], \
        tr.options(act)
    assert not tr.choose(C("J", "♠")), "10 以上不能当还牌"
    assert tr.choose(C("7", "♠"))
    assert tr.done
    # 3) 换牌结果
    events = tr.apply()
    assert C("A", "♠") in hand.hands[0] and C("A", "♠") not in hand.hands[3]
    assert C("7", "♠") in hand.hands[3] and C("7", "♠") not in hand.hands[0]
    # 进贡、还贡、以及「谁先出」三行事件
    assert len(events) == 3, events
    assert len(hand.hands[0]) == 3 and len(hand.hands[3]) == 5


def test_tribute_refuse():
    """抗贡：进贡方凑得出两张大王就不用交；抗贡由**收贡方（头游）**先出。"""
    hands = [
        [C("7", "♠")],
        [C("6", "♠")],
        [C("4", "♠")],
        [C("大王", "", 0), C("大王", "", 1), C("A", "♠")],   # 两 chi 大王
    ]
    hand = _fake_hand(hands, level="5", owner=(1,))
    tr = Tribute(hand, plan_tribute([0, 1, 2, 3]))
    assert tr.refused and not tr.active and tr.done
    assert tr.first_leader() == 0, "抗贡：原来的收贡方（头游）先出"
    events = tr.apply()
    assert len(events) == 1 and "抗贡" in events[0], events
    assert hand.turn == 0
    assert len(hand.hands[3]) == 3, "抗贡不应该动牌"


def test_tribute_refuse_shared_jokers():
    """双下时两个输家**合计**凑出两张大王也算抗贡（一人两张 / 两人各一张）。"""
    # 1) 两人各一张大王 → 抗贡
    hands = [
        [C("7", "♠")],                              # 甲：头游
        [C("K", "♠"), C("大王", "", 0)],             # 乙：三游
        [C("9", "♣")],                              # 丙：二游
        [C("A", "♦"), C("大王", "", 1)],             # 丁：末游
    ]
    hand = _fake_hand(hands, level="5", owner=(1,))
    tr = Tribute(hand, plan_tribute([0, 2, 1, 3]))
    assert tr.double and tr.refused, "两人各一张大王应抗贡"
    assert tr.first_leader() == 0

    # 2) 只有一个输家有一张大王 → 不够，照常进贡
    hands2 = [
        [C("7", "♠")],
        [C("K", "♠"), C("大王", "", 0)],
        [C("9", "♣")],
        [C("A", "♦"), C("3", "♠")],
    ]
    hand2 = _fake_hand(hands2, level="5", owner=(1,))
    tr2 = Tribute(hand2, plan_tribute([0, 2, 1, 3]))
    assert tr2.double and not tr2.refused, "只有一张大王不能抗贡"
    assert tr2.active

    # 3) 单人进贡：末游一人两张大王 → 抗贡（老规则仍然成立）
    hands3 = [
        [C("7", "♠")],
        [C("6", "♠")],
        [C("4", "♠")],
        [C("大王", "", 0), C("大王", "", 1)],
    ]
    hand3 = _fake_hand(hands3, level="5", owner=(1,))
    tr3 = Tribute(hand3, plan_tribute([0, 1, 2, 3]))
    assert tr3.refused and tr3.first_leader() == 0


def test_tribute_first_leader():
    """谁先出牌：正常进贡 = 贡牌方（末游）先出；抗贡 = 收贡方（头游）先出。"""
    # 正常进贡（沿用 test_tribute_normal 的牌面）：末游丁(3) 先出
    hands = [
        [C("7", "♠"), C("8", "♦"), C("9", "♣")],
        [C("6", "♠")],
        [C("4", "♠")],
        [C("A", "♠"), C("A", "♥"), C("K", "♠"), C("5", "♥"), C("3", "♦")],
    ]
    hand = _fake_hand(hands, level="5", owner=(1,))
    tr = Tribute(hand, plan_tribute([0, 1, 2, 3]))
    assert tr.first_leader() == 3, "正常进贡由末游先出"
    assert tr.choose(C("A", "♠"))
    assert tr.choose(C("7", "♠"))
    events = tr.apply()
    assert hand.turn == 3, "换牌后出牌权交给贡牌方（末游）"
    assert any("先出" in e for e in events), events


def test_tribute_double_down():
    """双下：两个输家都进贡，头游拿大的、二游拿小的。"""
    # 头游甲(0)、二游丙(2) 同队 → 双下；三游乙(1)、末游丁(3) 进贡
    hands = [
        [C("7", "♠"), C("8", "♦")],                    # 甲：头游
        [C("K", "♠"), C("K", "♥")],                    # 乙：三游，最大 K
        [C("9", "♣")],                                 # 丙：二游
        [C("A", "♦"), C("A", "♣"), C("2", "♠")],       # 丁：末游，最大 A
    ]
    hand = _fake_hand(hands, level="5", owner=(1,))
    plan = plan_tribute([0, 2, 1, 3])
    assert plan.double and plan.payers == (1, 3) and plan.receivers == (0, 2)

    tr = Tribute(hand, plan)
    assert tr.active and not tr.refused
    # 两张贡牌点数不同（K vs A）→ 不选贡
    assert not tr.choose_gift
    # 依次选贡牌：乙 K、丁 A
    assert tr.current().player == 1
    assert tr.choose(C("K", "♠"))
    assert tr.current().player == 3
    assert tr.choose(C("A", "♦"))
    # 头游拿大的（A）、二游拿小的（K）
    assert tr.pairs == {3: 0, 1: 2}, tr.pairs
    # 还牌：甲、丙 各还一张
    assert tr.current().kind == "return" and tr.current().player == 0
    assert tr.choose(C("7", "♠"))
    assert tr.current().kind == "return" and tr.current().player == 2
    assert tr.choose(C("9", "♣"))
    assert tr.done
    tr.apply()
    assert C("A", "♦") in hand.hands[0]     # 头游拿到大的
    assert C("K", "♠") in hand.hands[2]     # 二游拿到小的
    assert C("7", "♠") in hand.hands[3]     # 还给了末游
    assert C("9", "♣") in hand.hands[1]     # 还给了三游


def test_tribute_choose_gift():
    """选贡：双下且两张贡牌点数相等 → 赢家各挑各的，输家也各挑各的还牌。"""
    hands = [
        [C("7", "♠"), C("8", "♦")],                    # 甲：头游
        [C("A", "♠"), C("K", "♠")],                    # 乙：三游，最大 A
        [C("9", "♣"), C("10", "♦")],                   # 丙：二游
        [C("A", "♦"), C("3", "♠")],                    # 丁：末游，最大 A
    ]
    hand = _fake_hand(hands, level="5", owner=(1,))
    tr = Tribute(hand, plan_tribute([0, 2, 1, 3]))
    assert tr.double and tr.choose_gift, "点数相同应该可以选贡"

    # 1) 两个输家先选贡牌
    assert tr.current().kind == "gift" and tr.current().player == 1
    assert tr.choose(C("A", "♠"))
    assert tr.current().kind == "gift" and tr.current().player == 3
    assert tr.choose(C("A", "♦"))
    # 2) 赢家挑：甲挑 A♠（来自乙）、丙挑 A♦（来自丁）
    act = tr.current()
    assert act.kind == "pick_gift" and act.player == 0, act
    assert [str(c) for c in tr.options(act)] == ["A♠", "A♦"]
    assert tr.choose(C("A", "♠"))
    assert tr.pairs == {1: 0}, tr.pairs
    act = tr.current()
    assert act.kind == "pick_gift" and act.player == 2
    assert tr.choose(C("A", "♦"))
    assert tr.pairs == {1: 0, 3: 2}, tr.pairs
    # 3) 赢家各还一张 10 以下的牌
    assert tr.current().kind == "return" and tr.current().player == 0
    assert tr.choose(C("7", "♠"))
    assert tr.current().kind == "return" and tr.current().player == 2
    assert tr.choose(C("9", "♣"))
    # 4) 输家挑还牌：乙挑 7♠、丁挑 9♣
    act = tr.current()
    assert act.kind == "pick_return" and act.player == 1, act
    assert [str(c) for c in tr.options(act)] == ["7♠", "9♣"]
    assert tr.choose(C("7", "♠"))
    act = tr.current()
    assert act.kind == "pick_return" and act.player == 3
    assert tr.choose(C("9", "♣"))
    assert tr.done
    tr.apply()
    assert C("A", "♠") in hand.hands[0] and C("7", "♠") in hand.hands[1]
    assert C("A", "♦") in hand.hands[2] and C("9", "♣") in hand.hands[3]


def test_tribute_auto_and_engine_hook():
    """电脑自动进贡能走完；settle 会留下进贡安排，Hand 发牌后自动承接。"""
    from .tribute import run_auto

    hands = [
        [C("7", "♠")],
        [C("K", "♠")],
        [C("4", "♠")],
        [C("A", "♦"), C("2", "♠")],
    ]
    hand = _fake_hand(hands, level="5", owner=(1,))
    tr = Tribute(hand, plan_tribute([0, 1, 2, 3]))
    events = run_auto(tr)
    assert tr.done and events, "自动进贡应该走完并产出事件"
    assert C("A", "♦") in hand.hands[0]
    # 还的牌必须 10 以下
    back = [c for c in hand.hands[3] if c not in hands[3]]
    assert back and all(c.rank in ("2", "3", "4", "5", "6", "7", "8", "9", "10")
                        for c in back), back

    # 引擎钩子：settle 之后 pending_tribute 有值，下一手 Hand 自动建 Tribute
    match = new_match(seed=3)
    h1 = Hand(match)
    while not h1.ended:
        p = h1.turn
        from .ai import choose
        combo = choose(h1, p)
        if combo is None:
            h1.pass_turn(p)
        else:
            h1.play(p, combo.cards)
    settle(match, h1)
    assert match.pending_tribute is not None, "非终局应留下进贡安排"
    h2 = Hand(match)
    assert h2.tribute is not None and match.pending_tribute is None
    run_auto(h2.tribute)
    for p in range(4):
        assert len(h2.hands[p]) == HAND_SIZE


def main():
    for test in (test_cards, test_parse_basic, test_parse_bombs_and_runs,
                 test_engine_guards, test_level_ownership,
                 test_level_rank_follows_winner,
                 test_tribute_normal, test_tribute_refuse,
                 test_tribute_refuse_shared_jokers, test_tribute_first_leader,
                 test_tribute_double_down, test_tribute_choose_gift,
                 test_tribute_auto_and_engine_hook, test_simulation):
        name = test.__name__
        try:
            test()
            print(f"PASS {name}")
        except AssertionError as exc:
            print(f"FAIL {name}: {exc}")
            raise
    print("ALL OK")


if __name__ == "__main__":
    main()
# -*- coding: utf-8 -*-
"""自检用例（进贡 / 还贡）：一般进贡、抗贡、双下、选贡、谁先出。

被 games.guandan.selftest 汇总调用。
"""

from __future__ import annotations

from .engine import (
    HAND_SIZE,
    Hand,
    new_match,
    plan_tribute,
    settle,
)
from .selftest_common import C
from .tribute import Tribute

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

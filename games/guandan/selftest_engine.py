# -*- coding: utf-8 -*-
"""自检用例（对局引擎）：动作守卫、级牌归属不变量、自对弈收尾。

被 games.guandan.selftest 汇总调用。
"""

from __future__ import annotations

from . import simulator
from .cards import (
    Card,
    GameContext,
    card_order,
    is_wild,
    wild_owner,
    wild_owner_label,
)
from .engine import Hand, IllegalMove, new_match, settle
from .rules import parse
from .selftest_common import C, _C7_B

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

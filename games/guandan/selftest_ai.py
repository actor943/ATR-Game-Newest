# -*- coding: utf-8 -*-
"""AI 出牌质量自检：固定残局 + 自对弈冒烟。

用例都直接造一个 ``Hand`` 局面（不跑随机发牌），这样"对手剩 1 张、
我有对子"这类问题才能稳定复现，不会被运气掩盖。
"""

from __future__ import annotations

from .ai import choose
from .cards import Card, GameContext
from .engine import Hand, new_match
from .rules import ComboType, parse
from .selftest_common import C

# 级牌取 4：3 最小、A 最大，测"最大单张"时不会被级牌抢走语义
CTX = GameContext("4")


def _hand(mine, *, others=None, current=None, owner=0, turn=0,
          out_order=()) -> Hand:
    """造一个可控局面：其余三家默认各 10 张无关牌。"""
    hand = Hand(new_match(seed=1))
    hand.ctx = CTX
    filler = [C("2", s, i // 4) for i, s in enumerate("♠♥♣♦")]
    filler += [C("6", s, i // 4) for i, s in enumerate("♠♥♣♦")]
    hands = [list(filler) for _ in range(4)]
    hands[turn] = list(mine)
    if others:
        for seat, cards in others.items():
            hands[seat] = list(cards)
    hand.hands = hands
    hand.current = parse(list(current), CTX) if current else None
    hand.combo_owner = owner
    hand.turn = turn
    hand.out_order = list(out_order)
    hand.ended = False
    hand.tribute = None
    return hand


def _rank(combo) -> str:
    return combo.cards[0].rank


def test_ai_block_single_card_opponent():
    """用户反馈：对手 1 张、我有对子，必须出对子封锁，不能出小单张。"""
    mine = [C("9", "♠"), C("9", "♥"), C("3", "♣"),
            C("4", "♦"), C("5", "♣")]
    hand = _hand(mine, others={1: [C("8", "♠")]}, turn=0)
    combo = choose(hand, 0)
    assert combo is not None, "有对子却过牌"
    assert combo.type is ComboType.PAIR, f"应出对子封锁，实际 {combo}"
    assert _rank(combo) == "9", f"应出 9 的对子，实际 {combo}"


def test_ai_forced_single_plays_highest():
    """没有多张牌型可封锁时，出最大单张，而不是把小牌送给对手。"""
    mine = [C("3", "♣"), C("K", "♥"), C("A", "♠")]
    hand = _hand(mine, others={1: [C("8", "♠")]}, turn=0)
    combo = choose(hand, 0)
    assert combo is not None and combo.type is ComboType.SINGLE
    assert _rank(combo) == "A", f"残局应出最大单张 A，实际 {combo}"


def test_ai_finishes_when_possible():
    """能一把出空手牌就直接走，不再为了牌型层级拖一轮。"""
    mine = [C("7", "♠"), C("7", "♥")]
    hand = _hand(mine, turn=0)
    combo = choose(hand, 0)
    assert combo is not None and len(combo.cards) == 2, f"应直接出完：{combo}"
    assert combo.type is ComboType.PAIR


def test_ai_follow_blocks_one_card_opponent():
    """跟牌时对手只剩 1 张：用最大的单张堵住，不按最小代价出小牌。"""
    mine = [C("5", "♦"), C("K", "♥"), C("A", "♠")]
    hand = _hand(mine, others={1: [C("8", "♠")]},
                 current=[C("3", "♣")], owner=3, turn=0)
    combo = choose(hand, 0)
    assert combo is not None and _rank(combo) == "A", (
        f"应用 A 堵住对手，实际 {combo}")


def test_ai_safe_beat_saves_big_cards():
    """我的对子已经比对面的余牌多时，用最小的对子压，省下大牌。"""
    mine = [C("5", "♠"), C("5", "♥"), C("K", "♠"), C("K", "♥")]
    hand = _hand(mine, others={1: [C("8", "♠")]},
                 current=[C("3", "♣"), C("3", "♦")], owner=3, turn=0)
    combo = choose(hand, 0)
    assert combo is not None and combo.type is ComboType.PAIR
    assert _rank(combo) == "5", f"封锁已成立，应出小对子，实际 {combo}"


def test_ai_lets_partner_run():
    """搭档只剩 1 张且对手还很远时，领小单张让搭档接走牌权。"""
    mine = [C("3", "♣"), C("K", "♠"), C("K", "♥")]
    hand = _hand(mine, others={2: [C("9", "♠")]}, turn=0)
    combo = choose(hand, 0)
    assert combo is not None and combo.type is ComboType.SINGLE
    assert _rank(combo) == "3", f"应领小单张给搭档，实际 {combo}"


def test_ai_takes_partner_only_to_block():
    """搭档领小单张、对手只剩 1 张时破例压一次；搭档牌够大就不压。"""
    mine = [C("A", "♠"), C("5", "♦")]
    hand = _hand(mine, others={1: [C("8", "♠")], 2: [C("4", "♣")]},
                 current=[C("3", "♣")], owner=2, turn=0)
    combo = choose(hand, 0)
    assert combo is not None and _rank(combo) == "A", (
        f"应用 A 堵住对手最后一张牌，实际 {combo}")

    mine_big = [C("大王", ""), C("5", "♦")]
    hand_big = _hand(mine_big, others={1: [C("8", "♠")], 2: [C("4", "♣")]},
                     current=[C("A", "♣")], owner=2, turn=0)
    assert choose(hand_big, 0) is None, "搭档的 A 已经够大，不该压搭档"


def test_ai_normal_play_unchanged():
    """非残局维持旧习惯：小单张先走，不为了出牌数乱甩对子。"""
    mine = [C("9", "♠"), C("9", "♥"), C("3", "♣")]
    hand = _hand(mine, turn=0)
    combo = choose(hand, 0)
    assert combo is not None and combo.type is ComboType.SINGLE
    assert _rank(combo) == "3", f"普通局面应保持低牌先走，实际 {combo}"


def test_ai_simulation_smoke():
    """新策略下整场自对弈仍能跑完，且没有非法出牌 / 死循环。"""
    from .simulator import play_match

    for seed in (1, 2, 3):
        stats = play_match(seed)
        assert stats["winner"] in (0, 1)
        assert 0 < stats["hands"] < 60


def main() -> None:
    for test in (
        test_ai_block_single_card_opponent,
        test_ai_forced_single_plays_highest,
        test_ai_finishes_when_possible,
        test_ai_follow_blocks_one_card_opponent,
        test_ai_safe_beat_saves_big_cards,
        test_ai_lets_partner_run,
        test_ai_takes_partner_only_to_block,
        test_ai_normal_play_unchanged,
        test_ai_simulation_smoke,
    ):
        test()
        print(f"PASS {test.__name__}")
    print("AI OK")


if __name__ == "__main__":
    main()

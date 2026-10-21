# -*- coding: utf-8 -*-
"""Headless 自对弈模拟器：四位 AI 打完整场掼蛋。

用法::

    ./venv/bin/python3 -m games.guandan.simulator --matches 5 --seed 42
"""

from __future__ import annotations

import argparse
from typing import Dict, List

from . import rules
from . import tribute
from .ai import choose
from .cards import TOTAL_CARDS
from .engine import HAND_SIZE, MAX_MOVES_PER_HAND, Hand, MatchState, new_match, settle
from .rules import ComboType


def play_hand(match: MatchState, verbose: bool = False) -> Hand:
    """用 AI 打完一手牌，返回状态机（含全部步谱）。"""
    hand = Hand(match)
    # 先走完进贡（先发牌再进贡），再开始出牌
    for line in tribute.run_auto(hand.tribute):
        if verbose:
            print("  " + line)
    _check_dealt(hand)
    for _ in range(MAX_MOVES_PER_HAND):
        if hand.ended:
            break
        player = hand.turn
        combo = choose(hand, player)
        if combo is None:
            hand.pass_turn(player)
        else:
            hand.play(player, combo.cards)
    else:
        raise RuntimeError("单局步数超上限，疑似死循环")
    _check_invariants(hand)
    return hand


def _check_dealt(hand: Hand) -> None:
    """发牌 + 进贡之后：每人 27 张、合计 108 张且无重复。"""
    for p in range(4):
        assert len(hand.hands[p]) == HAND_SIZE, (
            f"玩家{p}手牌数 {len(hand.hands[p])} != {HAND_SIZE}")
    all_cards = [c for h in hand.hands for c in h]
    assert len(all_cards) == TOTAL_CARDS, "进贡后总牌数不是 108"
    assert len(set(all_cards)) == TOTAL_CARDS, "进贡后出现重复牌"


def _check_invariants(hand: Hand) -> None:
    """牌数守恒与游序完整性。"""
    played = sum(len(m.combo.cards) for m in hand.moves
                 if m.action == "play" and m.combo is not None)
    remaining = sum(len(h) for h in hand.hands)
    assert played + remaining == TOTAL_CARDS, "牌数不守恒"
    assert sorted(hand.out_order) == [0, 1, 2, 3], "游序不完整"
    for i in hand.out_order[:3]:
        assert not hand.hands[i], f"玩家{i}已游但仍有手牌"


def play_match(seed, verbose: bool = False) -> Dict:
    """打完整场，返回统计信息。"""
    match = new_match(seed)
    bombs = joker_bombs = 0
    while match.winner is None:
        hand = play_hand(match, verbose=verbose)
        settle(match, hand)
        for move in hand.moves:
            if move.action == "play" and move.combo is not None:
                if move.combo.type is ComboType.BOMB:
                    bombs += 1
                elif move.combo.type is ComboType.JOKER_BOMB:
                    joker_bombs += 1
    return {"winner": match.winner, "hands": match.hand_no,
            "levels": tuple(match.levels), "bombs": bombs,
            "joker_bombs": joker_bombs}


def main() -> None:
    parser = argparse.ArgumentParser(description="掼蛋 AI 自对弈模拟器")
    parser.add_argument("--matches", type=int, default=5)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    winners: List[int] = []
    total_hands = total_bombs = 0
    for i in range(args.matches):
        seed = None if args.seed is None else args.seed + i
        stats = play_match(seed, verbose=args.verbose)
        winners.append(stats["winner"])
        total_hands += stats["hands"]
        total_bombs += stats["bombs"] + stats["joker_bombs"]
        print(f"场{i + 1}: 胜方=队{stats['winner']} 局数={stats['hands']} "
              f"级数={list(stats['levels'])} 炸弹={stats['bombs']} "
              f"天王炸={stats['joker_bombs']}")
    print("-" * 40)
    print(f"共 {args.matches} 场：队0 胜 {winners.count(0)} 场，"
          f"队1 胜 {winners.count(1)} 场")
    print(f"平均每场 {total_hands / args.matches:.1f} 局，"
          f"累计炸弹 {total_bombs} 个")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
掼蛋记牌与概率推断算法（纯逻辑模块，不依赖任何 UI 库）
====================================================

牌桌共 4 人（我 / 下家 / 对家 / 上家），两副牌共 108 张，每人起手 27 张。

程序已知信息
------------
* 每一张被打出的牌，以及它是**哪一家**打出的（由界面记录）
* 当前级牌点数（红桃级牌为赖子，可当任意牌用）

由此可以精确推出
----------------
* 每家已出张数  ->  每家剩余张数 = 27 - 已出张数
* 某个点数还剩几张、王还剩几张

概率模型
--------
未出的牌分布在四家手中，且每家手牌张数精确已知，
所以"某点数剩余 k 张，其中某一家手里恰有 x 张"服从**超几何分布**：

    P(X = x) = C(k, x) * C(N - k, n - x) / C(N, n)

其中 N = 未出总张数（= 四家手牌张数之和），n = 该家剩余张数。

* 炸弹需要 4 张同点数，故单家概率 = P(X >= 4)
* 赖子（红桃级牌）可替代其它点数，因此非级牌点数的炸弹要把赖子并进来
* "三家对手中至少一家有炸"需要考虑三家手牌互斥的**联合分布**，
  用多元超几何分布精确枚举（枚举量很小，可在线计算）
* 天王炸（4 张王全在同一家）各家事件互斥，直接相加即可
* 同花顺不在计算范围内
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

# ============================================================
# 牌面常量
# ============================================================

RANKS: List[str] = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS: List[str] = ["♠", "♥", "♣", "♦"]
JOKERS: List[str] = ["小王", "大王"]
WILD_SUIT = "♥"  # 红桃级牌是赖子

TOTAL_PER_RANK = 8   # 每种点数 4 花色 × 2 副
TOTAL_JOKERS = 4     # 小王 ×2 + 大王 ×2
TOTAL_CARDS = 108
INITIAL_HAND_SIZE = 27
NUM_PLAYERS = 4
PLAYER_NAMES: Tuple[str, ...] = ("我", "下家", "对家", "上家")
OPPONENTS: Tuple[int, ...] = (1, 2, 3)  # 三家对手
BOMB_SIZE = 4                            # 炸弹至少 4 张


def _comb(n: int, k: int) -> int:
    """组合数，越界返回 0（便于直接写概率公式）。"""
    if n < 0 or k < 0 or k > n:
        return 0
    return math.comb(n, k)


@dataclass
class PlayRecord:
    """一次出牌记录。"""

    player: int          # 出牌人下标（0=我, 1=下家, 2=对家, 3=上家）
    rank: str            # 点数，或王的名称
    suit: str            # 花色；王为空字符串
    kind: str = "normal"  # normal=普通牌, joker=王
    copy_index: int = 0   # 同花色同点数的第几张（0 或 1）


class GdAnalyzer:
    """掼蛋记牌 + 三家视角概率推断。

    视角下标：0 = 我，1 = 下家，2 = 对家，3 = 上家。
    """

    def __init__(self, level_rank: Optional[str] = None) -> None:
        self.level_rank: Optional[str] = None
        # played[点数][花色] = 已出张数（0..2）
        self.played: Dict[str, Dict[str, int]] = {
            rank: {suit: 0 for suit in SUITS} for rank in RANKS
        }
        # played_jokers[王名] = 已出张数（0..2）
        self.played_jokers: Dict[str, int] = {name: 0 for name in JOKERS}
        # 出牌历史（用于撤销）
        self.history: List[PlayRecord] = []
        # 每家已出张数
        self._played_by_player: List[int] = [0] * NUM_PLAYERS
        if level_rank is not None:
            self.set_level_rank(level_rank)

    # ============================================================
    # 状态修改
    # ============================================================

    def set_level_rank(self, rank: Optional[str]) -> None:
        """设置级牌点数，None 表示取消。"""
        if rank is not None and rank not in RANKS:
            raise ValueError(f"非法级牌点数: {rank!r}")
        self.level_rank = rank

    def reset(self) -> None:
        """清空所有记录（含级牌设置）。"""
        self.__init__()

    def _pop_record(self, kind: str, rank: str, suit: str) -> Optional[PlayRecord]:
        """从历史中删除最后一条匹配的记录并返回。"""
        for i in range(len(self.history) - 1, -1, -1):
            rec = self.history[i]
            if rec.kind == kind and rec.rank == rank and rec.suit == suit:
                return self.history.pop(i)
        return None

    def toggle_card(self, player: int, rank: str, suit: str,
                    copy_index: int = 0) -> bool:
        """记录 / 撤销「某一家打出某张牌」。返回状态是否变化。

        copy_index 用于区分同一花色点数的两张牌（0 或 1）。
        """
        if rank not in RANKS or suit not in SUITS:
            return False
        if not 0 <= player < NUM_PLAYERS:
            return False

        current = self.played[rank][suit]
        if current > copy_index:
            # 已经打出 -> 撤销这一张
            rec = self._pop_record("normal", rank, suit)
            if rec is None:
                return False
            self.played[rank][suit] -= 1
            self._played_by_player[rec.player] = max(
                0, self._played_by_player[rec.player] - 1)
            return True

        if current == copy_index:
            # 前面几张必须先已打出，保证点击顺序与真实出牌顺序一致
            if copy_index > 0 and not all(
                    self.played[rank][suit] > i for i in range(copy_index)):
                return False
            self.played[rank][suit] += 1
            self._played_by_player[player] += 1
            self.history.append(
                PlayRecord(player, rank, suit, "normal", copy_index))
            return True

        return False

    def toggle_joker(self, player: int, name: str, copy_index: int = 0) -> bool:
        """记录 / 撤销某一家打出的一张王。"""
        if name not in JOKERS or not 0 <= player < NUM_PLAYERS:
            return False

        current = self.played_jokers[name]
        if current > copy_index:
            rec = self._pop_record("joker", name, "")
            if rec is None:
                return False
            self.played_jokers[name] -= 1
            self._played_by_player[rec.player] = max(
                0, self._played_by_player[rec.player] - 1)
            return True

        if current == copy_index:
            if copy_index > 0 and not all(
                    self.played_jokers[name] > i for i in range(copy_index)):
                return False
            self.played_jokers[name] += 1
            self._played_by_player[player] += 1
            self.history.append(PlayRecord(player, name, "", "joker", copy_index))
            return True

        return False

    def undo_last(self) -> Optional[PlayRecord]:
        """撤销最近一次出牌（不分谁打的）。"""
        if not self.history:
            return None
        rec = self.history.pop()
        if rec.kind == "joker":
            self.played_jokers[rec.rank] = max(0, self.played_jokers[rec.rank] - 1)
        else:
            self.played[rec.rank][rec.suit] = max(
                0, self.played[rec.rank][rec.suit] - 1)
        self._played_by_player[rec.player] = max(
            0, self._played_by_player[rec.player] - 1)
        return rec

    # ============================================================
    # 状态查询
    # ============================================================

    def total_played(self) -> int:
        played = sum(sum(v.values()) for v in self.played.values())
        return played + sum(self.played_jokers.values())

    def remaining_cards(self) -> int:
        """未出的总张数（四种手牌之和）。"""
        return TOTAL_CARDS - self.total_played()

    def played_by_player(self, player: int) -> int:
        return self._played_by_player[player]

    def hand_size(self, player: int) -> int:
        """某家当前剩余手牌张数（起手 27 张，出多少减多少）。"""
        return max(0, INITIAL_HAND_SIZE - self._played_by_player[player])

    def hand_sizes(self) -> List[int]:
        return [self.hand_size(p) for p in range(NUM_PLAYERS)]

    def is_played(self, rank: str, suit: str, copy_index: int = 0) -> bool:
        return self.played.get(rank, {}).get(suit, 0) > copy_index

    def is_joker_played(self, name: str, copy_index: int = 0) -> bool:
        return self.played_jokers.get(name, 0) > copy_index

    def remaining_by_rank(self, rank: str) -> int:
        """某点数还剩几张（含赖子自身）。"""
        return TOTAL_PER_RANK - sum(self.played[rank].values())

    def remaining_jokers(self) -> int:
        return TOTAL_JOKERS - sum(self.played_jokers.values())

    def wild_remaining(self) -> int:
        """赖子（红桃级牌）还剩几张。未设级牌时为 0。"""
        if self.level_rank is None:
            return 0
        return max(0, 2 - self.played[self.level_rank][WILD_SUIT])

    # ============================================================
    # 概率推断
    # ============================================================

    @staticmethod
    def _hypergeom_at_least(N: int, K: int, n: int, need: int) -> float:
        """P(X >= need)，其中 X ~ 超几何分布(N, K, n)。

        N: 总体张数, K: 目标牌张数, n: 抽取张数
        """
        if N <= 0 or n <= 0 or K <= 0 or need <= 0 or need > n:
            return 0.0
        denom = _comb(N, n)
        if denom == 0:
            return 0.0
        total = 0
        for x in range(max(need, 0), min(K, n) + 1):
            total += _comb(K, x) * _comb(N - K, n - x)
        return total / denom

    @staticmethod
    def _compositions(total: int, caps: Sequence[int],
                      idx: int = 0) -> Iterator[Tuple[int, ...]]:
        """生成满足 0 <= x_i <= caps[i] 且 sum(x) == total 的所有组合。"""
        if idx == len(caps) - 1:
            if 0 <= total <= caps[idx]:
                yield (total,)
            return
        for value in range(min(total, caps[idx]) + 1):
            for rest in GdAnalyzer._compositions(total - value, caps, idx + 1):
                yield (value,) + rest

    def _threat_groups(self, rank: str) -> Tuple[int, int, int]:
        """返回 (N, k_rank, k_wild)。

        N       : 未出总张数
        k_rank  : 该点数剩余张数
        k_wild  : 能替代它的赖子张数（若 rank 就是级牌本身，则赖子已含在
                  k_rank 内，避免重复计数，返回 0）
        """
        N = self.remaining_cards()
        k_rank = self.remaining_by_rank(rank)
        k_wild = 0 if rank == self.level_rank else self.wild_remaining()
        return N, k_rank, k_wild

    def bomb_prob_for_player(self, player: int, rank: str) -> float:
        """某一家持有该点数炸弹的概率（含赖子替代）。"""
        N, k_rank, k_wild = self._threat_groups(rank)
        n = self.hand_size(player)
        if N <= 0 or n < BOMB_SIZE:
            return 0.0

        if k_wild == 0:
            # 单一牌组：直接超几何
            return self._hypergeom_at_least(N, k_rank, n, BOMB_SIZE)

        if k_rank + k_wild < BOMB_SIZE:
            return 0.0

        rest = N - k_rank - k_wild
        denom = _comb(N, n)
        if denom == 0:
            return 0.0
        total = 0
        for r in range(k_rank + 1):
            for w in range(k_wild + 1):
                if r + w < BOMB_SIZE or r + w > n:
                    continue
                total += _comb(k_rank, r) * _comb(k_wild, w) * _comb(
                    rest, n - r - w)
        return total / denom

    def bomb_prob_any_opponent(self, rank: str) -> float:
        """三家对手中至少一家持有该点数炸弹的概率。

        三家手牌互斥（抽样不放回），用多元超几何分布精确枚举
        该点数与赖子在四家之间的分配，再取"三家都没有炸弹"的补概率。
        """
        N, k_rank, k_wild = self._threat_groups(rank)
        if N <= 0 or k_rank + k_wild < BOMB_SIZE:
            return 0.0

        sizes = self.hand_sizes()
        rest = N - k_rank - k_wild
        if rest < 0:
            return 0.0

        fact = math.factorial
        # 多元超几何：分配该点数 / 赖子 / 其它牌的概率分母
        scale = (fact(k_rank) * fact(k_wild) * fact(rest)
                 * math.prod(fact(n) for n in sizes) / fact(N))

        prob_no_bomb = 0.0
        for a in self._compositions(k_rank, sizes):
            caps_b = [sizes[i] - a[i] for i in range(NUM_PLAYERS)]
            if min(caps_b) < 0:
                continue
            for b in self._compositions(k_wild, caps_b):
                # 三家对手（下标 1..3）都没有凑够 4 张，才算"无炸弹"
                if any(a[i] + b[i] >= BOMB_SIZE for i in OPPONENTS):
                    continue
                d = [sizes[i] - a[i] - b[i] for i in range(NUM_PLAYERS)]
                if any(x < 0 for x in d):
                    continue
                prob_no_bomb += scale / (
                    math.prod(fact(x) for x in a)
                    * math.prod(fact(x) for x in b)
                    * math.prod(fact(x) for x in d)
                )
        return min(1.0, max(0.0, 1.0 - prob_no_bomb))

    def joker_bomb_prob_for_player(self, player: int) -> float:
        """某一家持有天王炸（4 张王全在这一家）的概率。"""
        k = self.remaining_jokers()
        if k < TOTAL_JOKERS:
            return 0.0
        N = self.remaining_cards()
        n = self.hand_size(player)
        if N <= 0 or n < TOTAL_JOKERS:
            return 0.0
        denom = _comb(N, n)
        if denom == 0:
            return 0.0
        return _comb(N - k, n - k) / denom

    def joker_bomb_prob(self) -> float:
        """三家对手中至少一家持有天王炸的概率（各家事件互斥，可相加）。"""
        return min(1.0, sum(self.joker_bomb_prob_for_player(p)
                            for p in OPPONENTS))

    def bomb_summary(self, threshold: float = 0.005) -> Dict[str, float]:
        """所有可能炸弹的"至少一家对手有炸"概率，按概率从高到低排序。"""
        result: Dict[str, float] = {}
        for rank in RANKS:
            prob = self.bomb_prob_any_opponent(rank)
            if prob > threshold:
                result[rank] = prob
        prob_joker = self.joker_bomb_prob()
        if prob_joker > threshold:
            result["天王"] = prob_joker
        return dict(sorted(result.items(), key=lambda kv: -kv[1]))

    def bomb_detail(self, label: str) -> List[Tuple[int, float]]:
        """某个炸弹（点数或"天王"）在三个对手身上的概率明细。"""
        if label == "天王":
            return [(p, self.joker_bomb_prob_for_player(p)) for p in OPPONENTS]
        return [(p, self.bomb_prob_for_player(p, label)) for p in OPPONENTS]

    # ============================================================
    # 单张牌分布
    # ============================================================

    def card_location_prob(self, player: int, rank: str, suit: str) -> float:
        """某张具体的牌落在某一家手中的概率（均匀性假设下 = n_i / N）。"""
        if rank in RANKS:
            if self.played[rank][suit] >= 2:
                return 0.0
        N = self.remaining_cards()
        if N <= 0:
            return 0.0
        return self.hand_size(player) / N

    def expected_rank_count(self, player: int, rank: str) -> float:
        """某一家手上该点数剩余张数的期望值。"""
        N = self.remaining_cards()
        if N <= 0:
            return 0.0
        return self.hand_size(player) * self.remaining_by_rank(rank) / N

    # ============================================================
    # 调试/展示辅助
    # ============================================================

    def hand_state(self) -> Dict[str, object]:
        """当前状态快照，便于界面或调试使用。"""
        return {
            "remaining": self.remaining_cards(),
            "level_rank": self.level_rank,
            "wild_remaining": self.wild_remaining(),
            "hand_sizes": self.hand_sizes(),
            "played_by_player": list(self._played_by_player),
            "remaining_by_rank": {r: self.remaining_by_rank(r) for r in RANKS},
            "remaining_jokers": self.remaining_jokers(),
        }

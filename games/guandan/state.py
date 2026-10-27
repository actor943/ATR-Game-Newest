# -*- coding: utf-8 -*-
"""掼蛋对局的「静态状态」：常量、数据结构、开新场。

这里放的是**整场对局都只读或只被整体替换**的东西：两队级数、轮到谁、
谁出了几手、上一把的进贡安排……不含任何「一手牌怎么打」的流程逻辑。

模块划分（配合 :mod:`games.guandan.engine` 这个门面）：

====================== ============================================ ==========
模块                   负责什么                                    行数量级
====================== ============================================ ==========
``state.py``（本文件）  常量 + 数据结构 + 开新场                   约 160
``hand.py``             一手牌的状态机（出牌 / 跟牌 / 过牌 / 接风）  约 200
``settle.py``           一手结束后的升级结算 + 进贡安排            约 80
``serialize.py``        联机用的 JSON 序列化 / 还原                约 250
``engine.py``           门面：把上面四个模块再导出一遍            约 60
====================== ============================================ ==========

老代码 ``from .engine import Hand, new_match, settle`` 之类的写法完全不变。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .cards import GameContext
from .rules_base import Combo

NUM_PLAYERS = 4
TEAM_OF = (0, 1, 0, 1)     # 玩家 -> 队伍（0/2 一队，1/3 一队）
HAND_SIZE = 27             # 每人每手 27 张（两副牌 108 张 ÷ 4 家）
MAX_MOVES_PER_HAND = 3000  # 防御性上限：单局总步数


class IllegalMove(Exception):
    """非法动作（不是你的轮次 / 牌不在手上 / 牌型非法 / 压不过等）。"""


@dataclass
class Move:
    """一步操作记录。"""

    player: int
    action: str                  # "play" | "pass"
    combo: Optional[Combo] = None   # Combo 对象（出牌时才有）


@dataclass
class HandResult:
    """一手牌结束后的结算信息。"""

    out_order: List[int]         # 头游 → 末游（4 个玩家下标）
    winner_team: int
    upgrade: int                 # 头游方升级数（3/2/1）
    levels_after: Tuple[str, str]
    match_over: bool             # 头游方在 A 级获胜，整场结束


@dataclass
class TributePlan:
    """一手结束后的进贡安排（只记座位，发好下一手再解析成具体动作）。

    掼蛋的进贡发生在**下一手牌发好之后**（先发牌再进贡），所以这里先只记录
    「谁给谁」，等下一手 :class:`~games.guandan.hand.Hand` 发完牌再由
    :class:`~games.guandan.tribute.Tribute` 结合手牌展开成一步步的可执行动作。
    """

    out_order: Tuple[int, ...]   # 头游 → 末游
    payers: Tuple[int, ...]      # 进贡方：末游；双下时为三游 + 末游
    receivers: Tuple[int, ...]   # 收贡方：头游；双下时为头游 + 二游
    double: bool                 # 是否双下（赢家包揽前两名）


@dataclass
class MatchState:
    """整场对局：双方级数与逐局推进。

    ``levels`` 是两队各自的**分数/级数**（队 0 / 队 1，见 :data:`TEAM_OF`）。
    本把的级牌点数只有**一个**：``level_rank`` —— 上一把头游方升级之后的
    分数，``level_owner`` 记着这个点数是谁在打（见 :meth:`ctx`）。
    """

    levels: List[str]
    rng: random.Random
    next_leader: int = 0
    hand_no: int = 0
    winner: Optional[int] = None          # 胜利队伍
    level_rank: str = "2"                 # 本把唯一的级牌点数
    level_owner: Tuple[int, ...] = (0, 1)  # 谁在打这个点数（开局双方都打 2）
    history: List[HandResult] = field(default_factory=list)
    # 下一手发完牌后要执行的进贡安排（settle 写入，Hand 消费后清空）
    pending_tribute: Optional[TributePlan] = None

    @property
    def ctx(self) -> GameContext:
        """本把的静态背景：唯一的级牌点数 + 归属。

        一把只有一个级牌点数（上把头游方升级后的分数），它大于所有自然牌；
        对方级数的红桃牌在本把不是逢人配。
        """
        return GameContext(self.level_rank, self.level_owner)


def new_match(seed: Optional[int] = None) -> MatchState:
    """新开一场：双方都从打 2 开始，首局随机先出。

    ``seed`` 传同一个值就能复现同一场牌（自检与模拟器都靠它）。
    """
    rng = random.Random(seed)
    return MatchState(levels=["2", "2"], rng=rng,
                      next_leader=rng.randrange(NUM_PLAYERS))

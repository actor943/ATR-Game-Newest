# -*- coding: utf-8 -*-
"""掼蛋牌型的「公共零件」：牌型枚举、牌型数据结构、几个共用小工具。

本模块只放**不依赖其它牌型逻辑**的基础件，好让下面三个模块都能安全地
import 它，彼此不会形成循环引用：

* :mod:`games.guandan.rules_parse`   —— 识别「这一手牌是什么牌型」
* :mod:`games.guandan.rules_compare` —— 比较「这一手牌能不能压过那一手」
* :mod:`games.guandan.rules`         —— 从手牌里枚举「所有能打出的牌型」

对外仍然统一从 :mod:`games.guandan.rules` 导入（那里做了再导出），
所以历史代码 ``from .rules import ComboType, beats, parse`` 不受影响。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .cards import RUN_RANKS, Card

# 两种王牌的花色名（大王 / 小王）。它们不在 RUN_RANKS 里，
# 因此任何「连续点数」的牌型（顺子 / 连对 / 钢板 / 同花顺）都天然不含王。
_JOKER_RANKS = ("小王", "大王")


class ComboType(enum.Enum):
    """掼蛋里所有合法的牌型。枚举值就是给人看的中文名。"""

    SINGLE = "单张"              # 1 张
    PAIR = "对子"                # 2 张同点（含王对）
    TRIPLE = "三张"              # 3 张同点
    FULL_HOUSE = "三带二"        # 3 张同点 + 一对
    STRAIGHT = "顺子"            # 恰好 5 张连续单牌
    PAIR_SEQ = "连对"            # 恰好 3 组连续对子（6 张）
    TRIPLE_SEQ = "钢板"          # 恰好 2 组连续三张（6 张）
    BOMB = "炸弹"                # 4 张及以上同点
    FLUSH_STRAIGHT = "同花顺"    # 5 张及以上同花色连续
    JOKER_BOMB = "天王炸"        # 4 张王（大王×2 + 小王×2）


# 压牌层级：普通牌型=0 < 炸弹=1 < 同花顺=2 < 天王炸=3。
# 只有**层级相同**的牌型才能互比大小（见 rules_compare.beats）。
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
    """一次可打出的牌型（识别结果 / 枚举结果都用它表示）。

    字段说明
    --------
    type
        牌型种类。
    cards
        实际打出的那些牌（tuple，保证顺序稳定、可哈希）。
    size
        「同型同长」里的长度：顺子=5、连对=3、钢板=2、炸弹=张数；
        其余牌型统一记 1。
    main_key
        主体牌的序值（越大越强）。同型同长时就是比这个。
    wilds_used
        这一手里用了几张逢人配（万能牌）。
    label
        给人看的标签，如 ``对子(K)``。
    """

    type: ComboType
    cards: Tuple[Card, ...]
    size: int
    main_key: int
    wilds_used: int = 0
    label: str = ""

    def __str__(self) -> str:
        return f"{self.label}[{'+'.join(str(c) for c in self.cards)}]"


def _mk(t: ComboType, cards: Iterable[Card], size: int, key: int,
        wilds_used: int, label: str) -> Combo:
    """构造 :class:`Combo` 的小帮手（统一把 cards 转成 tuple）。"""
    return Combo(t, tuple(cards), size, key, wilds_used, label)


def _is_joker_rank(rank: str) -> bool:
    """这个点数是不是王（大王 / 小王）。"""
    return rank in _JOKER_RANKS


def _run_windows(length: int) -> List[List[str]]:
    """3..A 范围内所有长度为 ``length`` 的连续点数窗口。

    例如 ``length=5`` 会得到 ``[['3','4','5','6','7'], ..., ['10','J','Q','K','A']]``。
    顺子 / 连对 / 钢板 / 同花顺都靠它在这些窗口里找可解释的组合。
    """
    return [RUN_RANKS[i:i + length]
            for i in range(0, len(RUN_RANKS) - length + 1)]

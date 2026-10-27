# -*- coding: utf-8 -*-
"""掼蛋「谁压谁」的比较规则。

只有一条主线：**先看层级，再看同型同长，最后比主体点数**。

层级（:data:`~games.guandan.rules_base.TYPE_LEVEL`）::

    天王炸(4王) > 同花顺(≥5同花色连续) > 炸弹(≥4同点) > 普通牌型

普通牌型（单张 / 对子 / 三张 / 三带二 / 顺子 / 连对 / 钢板）必须
**同型同长**才能互压 —— 三张压不了对子，5 张顺子压不了 6 张连对。
"""

from __future__ import annotations

from .rules_base import Combo, ComboType, TYPE_LEVEL


def beats(candidate: Combo, target: Combo) -> bool:
    """``candidate`` 能否压住 ``target``。

    判定顺序：

    1. 层级不同 → 层级高的赢（炸弹压普通牌、同花顺压炸弹、天王炸压一切）；
    2. 层级相同且是炸弹 / 同花顺 → 先比张数，张数多的大；张数一样再比主体点数；
    3. 层级相同且是普通牌型 → 必须**同型同长**，然后主体点数大者赢。
    """
    lv_c = TYPE_LEVEL[candidate.type]
    lv_t = TYPE_LEVEL[target.type]
    if lv_c != lv_t:
        return lv_c > lv_t
    if candidate.type in (ComboType.BOMB, ComboType.FLUSH_STRAIGHT):
        # 炸弹 / 同花顺：先比张数，再比点数
        return (candidate.size, candidate.main_key) > (target.size,
                                                       target.main_key)
    if candidate.type is not target.type or candidate.size != target.size:
        return False
    return candidate.main_key > target.main_key

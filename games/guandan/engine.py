# -*- coding: utf-8 -*-
"""掼蛋对局引擎（门面模块）：一手牌的出牌状态机 + 整场升级流程。

原 engine.py 把「状态 / 一手牌 / 结算 / 序列化」四件事写在一起，接近 600 行。
现在拆成四个小模块，本文件只做**再导出**，保证
``from .engine import Hand, new_match, settle`` 这类老写法完全不用改。

模块划分
--------
====================== ============================================ ==========
模块                   负责什么                                    行数量级
====================== ============================================ ==========
``state.py``           常量 + 数据结构（MatchState 等）+ 开新场     约 160
``hand.py``            一手牌的状态机（出牌 / 跟牌 / 过牌 / 接风）  约 220
``settle.py``          一手结束后的升级结算 + 进贡安排            约 80
``serialize.py``       联机用的 JSON 序列化 / 还原                约 260
``engine.py``（本文件）门面：把上面四个模块再导出一遍            约 70
====================== ============================================ ==========

一局（Hand）的流程
------------------
1. 洗牌发牌：108 张，每人 27 张；由 ``next_leader`` 先出。
2. 轮流出牌：首出任意合法牌型；之后必须同型同长且更大，或用
   炸弹 / 同花顺 / 天王炸压。
3. 过牌一圈无人再压 → 本轮结束，最后出牌者获得下一轮出牌权。
4. 有人出完牌即「游」：头游 → 二游 → 三游，三家出完后局面结束
   （第四家自动为末游）。
5. 接风：头游（或任何出完者）最后一手牌无人压时，出牌权交给其
   **搭档**；搭档已出完则顺延下家。
6. 结算：头游方升级 —— 搭档位次为二游升3级 / 三游升2级 / 末游升1级；
   级数封顶在 A；**在 A 级获胜即赢得整场**。
7. 下一把的级牌点数 = 本把头游方**升级之后**的分数（一把只有一个级牌）。
   所以两队级数不同时（甲丙打 3、乙丁打 4），只有上把头游方正在打的那个
   点数算级牌、其红桃牌才是逢人配；对方点数的红桃牌只是普通牌。

纯逻辑模块，不依赖 flet。
"""

from __future__ import annotations

# ---- 状态与数据结构 ----
from .state import (
    HAND_SIZE,
    MAX_MOVES_PER_HAND,
    NUM_PLAYERS,
    TEAM_OF,
    HandResult,
    IllegalMove,
    MatchState,
    Move,
    TributePlan,
    new_match,
)

# ---- 一手牌的状态机 ----
from .hand import Hand

# ---- 结算与进贡安排 ----
from .settle import plan_tribute, settle

# ---- 联机用的序列化 / 还原 ----
from .serialize import (
    card_from_json,
    card_to_json,
    cards_from_json,
    cards_to_json,
    load_match,
    result_from_json,
    serialize_match,
)

__all__ = [
    "NUM_PLAYERS", "TEAM_OF", "HAND_SIZE", "MAX_MOVES_PER_HAND",
    "IllegalMove", "Move", "HandResult", "TributePlan", "MatchState",
    "new_match", "Hand", "settle", "plan_tribute",
    "card_to_json", "card_from_json", "cards_to_json", "cards_from_json",
    "result_from_json", "serialize_match", "load_match",
]

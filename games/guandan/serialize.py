# -*- coding: utf-8 -*-
"""联机同步用的 JSON 序列化 / 还原（房主权威）。

联机对局里**只有房主洗牌**：房主把 :func:`serialize_match` 的结果广播给
所有人，客人 :func:`load_match` 之后与本机局面完全一致（级数、手牌、
进贡进度、轮到谁）。之后每有一个动作，房主就重推一次快照，客人按
``seq`` 只接受更新的快照 —— 乱序 / 重传的旧快照直接丢弃，天然收敛，
不存在「各玩各的」。

本模块只负责「数据 <-> JSON」，不含任何规则判断；规则在
:mod:`games.guandan.rules` 与 :mod:`games.guandan.hand` 里。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .cards import Card
from .hand import Hand
from .rules import Combo, ComboType
from .state import HandResult, MatchState, TributePlan
from .tribute import Tribute

# ============================================================
# 网络同步：整场 + 当前一手 的序列化 / 还原（房主权威，JSON 友好）
# ============================================================
#
# 联机对局里**只有房主洗牌**：房主把 ``serialize_match`` 的结果广播给所有人，
# 客人 ``load_match`` 之后与本机局面完全一致（级数、手牌、进贡进度、轮到谁）。
# 之后每有一个动作，房主就重推一次快照，客人按 ``seq`` 只接受更新的快照 ——
# 乱序 / 重传的旧快照直接丢弃，天然收敛，不存在「各玩各的」。


def card_to_json(card: Card) -> List[Any]:
    return [card.rank, card.suit, card.copy_index]


def card_from_json(raw: Any) -> Optional[Card]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        return None
    try:
        return Card(str(raw[0]), str(raw[1]), int(raw[2]))
    except (TypeError, ValueError):
        return None


def cards_to_json(cards: Sequence[Card]) -> List[List[Any]]:
    return [card_to_json(c) for c in cards]


def cards_from_json(raw: Any) -> Optional[List[Card]]:
    if not isinstance(raw, (list, tuple)):
        return None
    out: List[Card] = []
    for item in raw:
        card = card_from_json(item)
        if card is None:
            return None
        out.append(card)
    return out


def _combo_to_json(combo: Optional[Combo]) -> Optional[Dict[str, Any]]:
    if combo is None:
        return None
    return {"t": combo.type.value, "c": cards_to_json(combo.cards),
            "sz": combo.size, "k": combo.main_key, "w": combo.wilds_used,
            "label": combo.label}


def _combo_from_json(raw: Any) -> Optional[Combo]:
    if not isinstance(raw, dict):
        return None
    try:
        ctype = ComboType(str(raw["t"]))
    except ValueError:
        return None
    cards = cards_from_json(raw.get("c"))
    if cards is None:
        return None
    try:
        return Combo(type=ctype, cards=tuple(cards), size=int(raw["sz"]),
                     main_key=int(raw["k"]), wilds_used=int(raw.get("w", 0)),
                     label=str(raw.get("label", "")))
    except (KeyError, TypeError, ValueError):
        return None


def _plan_to_json(plan: Optional[TributePlan]) -> Optional[Dict[str, Any]]:
    if plan is None:
        return None
    return {"out": list(plan.out_order), "payers": list(plan.payers),
            "receivers": list(plan.receivers), "double": plan.double}


def _plan_from_json(raw: Any) -> Optional[TributePlan]:
    if not isinstance(raw, dict):
        return None
    try:
        return TributePlan(
            out_order=tuple(int(x) for x in raw["out"]),
            payers=tuple(int(x) for x in raw["payers"]),
            receivers=tuple(int(x) for x in raw["receivers"]),
            double=bool(raw["double"]))
    except (KeyError, TypeError, ValueError):
        return None


def _card_map_to_json(mapping: Dict[int, Card]) -> Dict[str, List[Any]]:
    return {str(k): card_to_json(v) for k, v in mapping.items()}


def _card_map_from_json(raw: Any) -> Dict[int, Card]:
    out: Dict[int, Card] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            seat = int(k)
        except (TypeError, ValueError):
            continue
        card = card_from_json(v)
        if card is not None:
            out[seat] = card
    return out


def _tribute_to_json(tr: Optional[Tribute]) -> Optional[Dict[str, Any]]:
    if tr is None:
        return None
    return {"plan": _plan_to_json(tr.plan),
            "gifts": _card_map_to_json(tr.gifts),
            "picks": _card_map_to_json(tr.picks),
            "returns": _card_map_to_json(tr.returns),
            "return_picks": _card_map_to_json(tr.return_picks),
            "pairs": {str(k): int(v) for k, v in tr.pairs.items()},
            # refused / choose_gift 是**发牌那一刻**按当时手牌定下的
            # （抗贡方可能随后把大王打出去），不能按当前手牌重算 ——
            # 否则联机客人会看到一个已经不存在的进贡面板（0.4.8-fix）
            "refused": tr.refused,
            "choose_gift": tr.choose_gift,
            "refuse_holders": list(tr.refuse_holders)}


def _tribute_from_json(hand: "Hand", raw: Any) -> Optional[Tribute]:
    """按快照还原进贡状态机。"""
    if not isinstance(raw, dict):
        return None
    plan = _plan_from_json(raw.get("plan"))
    if plan is None:
        return None
    tr = Tribute(hand, plan)
    tr.gifts = _card_map_from_json(raw.get("gifts"))
    tr.picks = _card_map_from_json(raw.get("picks"))
    tr.returns = _card_map_from_json(raw.get("returns"))
    tr.return_picks = _card_map_from_json(raw.get("return_picks"))
    pairs = raw.get("pairs")
    if isinstance(pairs, dict):
        for k, v in pairs.items():
            try:
                tr.pairs[int(k)] = int(v)
            except (TypeError, ValueError):
                continue
    if "refused" in raw:
        tr.refused = bool(raw["refused"])
    if "choose_gift" in raw:
        tr.choose_gift = bool(raw["choose_gift"])
    holders = raw.get("refuse_holders")
    if isinstance(holders, (list, tuple)):
        try:
            tr.refuse_holders = tuple(int(x) for x in holders)
        except (TypeError, ValueError):
            pass
    return tr


def _hand_to_json(hand: Hand) -> Dict[str, Any]:
    return {
        "hands": [cards_to_json(h) for h in hand.hands],
        "out_order": list(hand.out_order),
        "turn": hand.turn,
        "current": _combo_to_json(hand.current),
        "combo_owner": hand.combo_owner,
        "passes": hand.passes,
        "ended": hand.ended,
        "tribute": _tribute_to_json(hand.tribute),
        # 这一手发牌时的级牌背景（见 Hand.__init__ 的 dealt 分支）
        "ctx": {"level": hand.ctx.level,
                "owners": list(hand.ctx.owner_teams)},
    }


def _result_to_json(r: Optional[HandResult]) -> Optional[Dict[str, Any]]:
    if r is None:
        return None
    return {"out_order": list(r.out_order), "winner_team": r.winner_team,
            "upgrade": r.upgrade, "levels_after": list(r.levels_after),
            "match_over": r.match_over}


def result_from_json(raw: Any) -> Optional[HandResult]:
    """还原一手牌的结算结果（联机客人显示「下一局 / 整场结束」面板用）。"""
    if not isinstance(raw, dict):
        return None
    try:
        return HandResult(
            out_order=[int(x) for x in raw["out_order"]],
            winner_team=int(raw["winner_team"]),
            upgrade=int(raw["upgrade"]),
            levels_after=(str(raw["levels_after"][0]),
                          str(raw["levels_after"][1])),
            match_over=bool(raw["match_over"]))
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def serialize_match(match: MatchState, hand: Hand,
                    result: Optional[HandResult] = None) -> Dict[str, Any]:
    """导出整场 + 当前一手的完整局面（可被 JSON 编码，联机广播用）。

    ``result`` 是当前一手的结算（房主 ``_after_action`` 后的 ``self.result``），
    客人靠它渲染结算面板 —— 一手牌由谁走完不一定，客人不能只靠自己本地推导。
    """
    return {
        "levels": list(match.levels),
        "next_leader": match.next_leader,
        "hand_no": match.hand_no,
        "winner": match.winner,
        "level_rank": match.level_rank,
        "level_owner": list(match.level_owner),
        "pending_tribute": _plan_to_json(match.pending_tribute),
        "res": _result_to_json(result),
        "hand": _hand_to_json(hand),
    }


def load_match(match: MatchState, raw: Dict[str, Any]) -> Optional[Hand]:
    """把房主广播的整场局面写进 ``match``，返回重建出的当前一手。

    任何字段缺失 / 非法都返回 ``None``（调用方应忽略这帧，继续用旧局面），
    不抛异常 —— 网络线程里不能炸。
    """
    if not isinstance(raw, dict):
        return None
    try:
        levels = [str(x) for x in raw["levels"]]
        if len(levels) != 2:
            return None
        winner = raw.get("winner")
        match.levels = levels
        match.next_leader = int(raw["next_leader"])
        match.hand_no = int(raw["hand_no"])
        match.winner = None if winner is None else int(winner)
        match.level_rank = str(raw["level_rank"])
        match.level_owner = tuple(int(x) for x in raw["level_owner"])
        match.pending_tribute = _plan_from_json(raw.get("pending_tribute"))
        hand = Hand(match, dealt=raw["hand"])
    except (KeyError, TypeError, ValueError):
        return None
    return hand

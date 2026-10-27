# -*- coding: utf-8 -*-
"""掼蛋牌桌的「常量」与「纯函数工具」。

放在最前面单独一个文件，是因为下面五个 mixin 都要用它们：
配色、尺寸、时间参数、逢人配的框色逻辑……把它们集中在一处，
改一次配色 / 尺寸不用翻遍五个文件。
"""

from __future__ import annotations

from typing import List, Optional

from games.guandan.cards import TEAM_LABELS, Card, is_wild, wild_owner
from games.guandan.engine import NUM_PLAYERS, TributePlan
from games.guandan.rules import ComboType

NAMES = ("甲", "乙", "丙", "丁")

TEAM_COLOR = ("#3B82F6", "#F59E0B")   # 队0 蓝 / 队1橙
BOMB_COLOR = "#EF4444"
WIN_COLOR = "#10B981"
HEAD_COLOR = "#8B5CF6"
MUTED = "#9CA3AF"
FG = "#E5E7EB"
LEVEL_GOLD = "#FFD54F"          # 级牌实体牌金框
LEVEL_MY = "#FFD54F"           # 己方级牌（含双方同级）
LEVEL_FOE = "#FFB300"          # 对方级牌
WILD_MY = "#FF4D4F"            # 己方逢人配
WILD_FOE = "#FF8A65"           # 对方逢人配（自己的万能牌是亮红，借来的偏橙红）
WILD_SHARED = "#F06292"        # 双方共有的逢人配（两队级数相同）
TRIBUTE_OK = "#22C55E"         # 进贡面板里「这一手可以选」的描边
TRIBUTE_DIM = 0.32             # 进贡面板里不能选的牌压暗到这个透明度

AI_DELAY = 0.55                # 电脑出牌前停顿（只为看清，不是倒计时）
HUMAN_POLL = 0.08              # 等真人操作时的轮询间隔

# 进贡各动作的中文动词（等待提示用）
_TRIBUTE_VERBS = {
    "gift": "进贡",
    "pick_gift": "选贡",
    "return": "还贡",
    "pick_return": "选还贡",
}

CARD_W, CARD_H = 42, 58
PLAY_W, PLAY_H = 38, 53
HAND_SPACING = -16
LIFT = -0.30                   # 选中牌的抬升偏移

MAX_EVENTS = 5000             # 出牌记录全量保留（TextSpan 很轻，见 0.4.3）
EVENTS_HEIGHT = 180           # 事件窗口高度；内部可滚动看全部记录
HAND_BOX_HEIGHT = 150         # 手牌/进贡面板高度（进贡面板要放提示+牌+按钮）

# 事件日志的着色随联机快照一起广播（颜色名 <-> 色值），
# 保证客人看到的「近期事件」与房主逐字逐色一致。
_LOG_COLORS = {
    "fg": "#E5E7EB",
    "muted": MUTED,
    "win": WIN_COLOR,
    "head": HEAD_COLOR,
    "gold": LEVEL_GOLD,
    "bomb": BOMB_COLOR,
    "team0": TEAM_COLOR[0],
    "team1": TEAM_COLOR[1],
}
_LOG_COLOR_KEYS = {v: k for k, v in _LOG_COLORS.items()}

# ---- 窄屏（手机）适配 ----
# 手牌原来只有一行叠放：27 张 × 净宽 26 ≈ 700dp，手机 360dp 放不下，
# 只能横向拖着看，永远看不全。现在按可用宽度自动换行成多行，
# 手牌盒高度跟着行数长，超过上限才内部滚动。
HAND_ROW_GAP = 4              # 换行后的行间距
HAND_BOX_MAX_HEIGHT = 300     # 手牌区最大高度
_FALLBACK_WIDTH = 420.0       # 拿不到页面宽度时按手机宽度兜底


def _is_bomb(combo) -> bool:

    """这个牌型是不是炸弹（含同花顺 / 天王炸）。"""
    return combo is not None and combo.type in (
        ComboType.BOMB, ComboType.FLUSH_STRAIGHT, ComboType.JOKER_BOMB,
    )


def _is_seat(value) -> bool:
    """网络上传来的座位号是否合法（bool 是 int 的子类，要排除）。"""
    return isinstance(value, int) and not isinstance(value, bool) \
        and 0 <= value < NUM_PLAYERS


def _plan_summary(plan: TributePlan) -> str:
    """进贡安排的一句话说明（日志用；与 Tribute.summary 保持一致口径）。"""
    names = ("甲", "乙", "丙", "丁")
    parts = [f"{names[p]}→{names[r]}"
             for p, r in zip(plan.payers, plan.receivers)]
    tag = "双下·" if plan.double else ""
    return f"{tag}进贡 {'、'.join(parts)}"


def wild_style(card: Card, ctx, ref_team: int) -> tuple[Optional[str], str]:
    """逢人配的框色与文案（相对 ``ref_team``）；非逢人配返回 ``(None, "")``。

    双方级数不同时有**两个不同的逢人配**，必须按归属区分，否则两边长得一样，
    分不清是谁在用谁的万能牌。
    """
    teams = wild_owner(card, ctx)
    if not teams:
        return None, ""
    if len(teams) == 2:
        return WILD_SHARED, "逢人配·万能牌·双方共有的"
    if teams[0] == ref_team:
        return WILD_MY, "逢人配·万能牌·本方的"
    return WILD_FOE, f"逢人配·万能牌·{TEAM_LABELS[teams[0]]}的"


_RUN_TYPES = (ComboType.STRAIGHT, ComboType.PAIR_SEQ,
              ComboType.TRIPLE_SEQ, ComboType.FLUSH_STRAIGHT)


def _wild_role(cards, ctx, combo) -> str:
    """逢人配在这一手里**充当了什么**，写进日志防止误读。

    典型误解：`炸弹(A×4)[A♦+A♥+A♠+3♥]` 里有张 3♥（级牌），就被读成
    「3 的炸弹」，进而怀疑「2 怎么能压 3」。其实 3♥ 是当 A 用补第 4 张 A，
    这一手是 A 的炸弹。所以必须把「当 X 用」写出来。
    """
    if combo is None:
        return ""
    if combo.type is ComboType.SINGLE:
        return "按级牌本身打出"          # 单张逢人配就是级牌自己
    if combo.type in _RUN_TYPES:
        return f"补{combo.type.value}空位"
    fixed = [c for c in cards if not is_wild(c, ctx)]
    ranks = {c.rank for c in fixed}
    if len(ranks) == 1:                  # 其余牌同点 → 逢人配补的就是这个点数
        return f"当 {next(iter(ranks))} 用"
    return "凑牌型用"


def combo_wild_note(cards, ctx, actor_team: int, combo=None) -> str:
    """一手牌用到的逢人配说明，追加在日志 / 待压区文案后面。

    两件事都说清：这张万能牌**原本是谁的**，以及它在这手里**当什么用**
    （见 :func:`_wild_role`）。只写前者会被误读成「级牌本身」。
    """
    notes: List[str] = []
    seen: dict[tuple[str, str], int] = {}
    for c in cards:
        teams = wild_owner(c, ctx)
        if not teams:
            continue
        owner = ("双方共有的" if len(teams) == 2
                 else f"{TEAM_LABELS[teams[0]]}的")
        key = (str(c), owner)
        seen[key] = seen.get(key, 0) + 1
    role = _wild_role(cards, ctx, combo)
    for (card, owner), n in seen.items():
        cnt = f"×{n}" if n > 1 else ""
        body = f"{card}{cnt} {role}".strip()
        notes.append(f"{body}（{owner}）")
    return ("逢人配 " + "、".join(notes)) if notes else ""


# ============================================================
# 会话
# ============================================================

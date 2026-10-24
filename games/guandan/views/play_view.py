# -*- coding: utf-8 -*-
"""掼蛋对局牌桌：真人 + 电脑混战（0.4.5）。

进入路径：掼蛋子菜单 → 开始游戏 → 选好配置 → 进入本页。

设计要点
--------
* **没有出牌倒计时**。轮到你时手牌区可点牌，点「出牌」/「过牌」；
  不点就一直等着，不催你。电脑位由 :mod:`asyncio` 协程自动出牌，
  ``AI_DELAY`` 只是为了让牌面看得清，不是倒计时。
* 座位配置来自 :class:`games.guandan.config.MatchConfig`（单人 / 三人机 /
  自定义），决定哪个座位由你亲手操作。
* 本机只有一个玩家：非本机的真人位按「托管」处理，由电脑代打。
* 近期事件沿用全模拟的终端写法（单个 ``ft.Text`` + spans，固定高度可滚动），
  Mac 上可整段复制。

联机对局（0.4.8-fix：开始游戏后所有人必须是**同一副牌**）
--------------------------------------------------------
从房间「开始」进来的对局，**房主是唯一权威**：只有房主洗牌发牌，之后每有一个
动作（出牌 / 过牌 / 进贡 / 发下一手）房主就把整场局面连同新的事件日志重推一次
快照；所有人按 ``seq`` 只采用更新的快照，乱序 / 重传的旧包直接丢弃。客人不本地
洗牌、不本地跑 AI、不本地写日志 —— 全部等房主快照，从根上杜绝「各玩各的」。
房间 0~3 号座对应牌桌甲~丁，空位由电脑补；4 号位起的人只围观（看不到任何手牌）。

暂未实现：炸弹特效、悔牌。
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import replace
from typing import Deque, Dict, List, Optional, Set, Tuple

import flet as ft

from core import history
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, fit_card_row, page_width
from core.profile import ensure_nick
from core.net import session as _sess
from games.guandan import config as cfgmod
from games.guandan.config import SEAT_AI, SEAT_HUMAN
from games.guandan.views.history_view import open_history
from games.guandan.ai import choose
from games.guandan.assets import card_image_src
from games.guandan.cards import (
    TEAM_LABELS,
    Card,
    is_wild,
    level_ranks_desc,
    size_order_hint,
    sort_hand,
    wild_owner,
    wild_owner_label,
)
from games.guandan.engine import (
    NUM_PLAYERS,
    Hand,
    IllegalMove,
    MatchState,
    TributePlan,
    card_to_json,
    cards_from_json,
    cards_to_json,
    load_match,
    new_match,
    result_from_json,
    serialize_match,
    settle,
)
from games.guandan.rules import ComboType, beats, parse
from games.guandan.tribute import GIFT, RETURN, auto_pick

# ============================================================
# 常量
# ============================================================

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


class _Play:
    """一局牌桌的全部状态与界面引用。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self.cfg: cfgmod.MatchConfig = cfgmod.active()

        # ---- 联机房间开起来的对局 ----
        # 权威在房主：只有房主洗牌发牌，之后每有个动作房主重推一次整局快照，
        # 所有人按 seq 采用最新快照 —— 开始游戏后大家必然是**同一副牌**
        # （0.4.8-fix：此前各客户端各自 new_match() 随机发牌，各玩各的）。
        self.net = _sess.current()
        self.is_host = bool(self.net and self.net.is_host)
        self.my_seat = 0                   # 本机玩家坐在哪（甲=0 … 丁=3）
        self.spectator = False             # 房间 4 号位起 / 没入座 = 旁观
        self.remote_nicks: Dict[int, str] = {}   # 牌桌座位 -> 远端真人昵称
        self._seq = 0                      # 房主：已推快照的序号
        self._last_seq = -1                # 已应用的最新快照序号（防乱序 / 重传）
        self._synced = self.net is None or self.is_host
        self._result_hand_no = -1          # 结算面板对应的是第几手
        if self.net is not None:
            self._setup_net_seats()
        # 联机房间开起来的对局：本机玩家用昵称，而不是「你」
        if self.net is not None:
            self.cfg = replace(self.cfg, local_nick=ensure_nick())

        self.match: MatchState = new_match()
        self.hand: Hand = Hand(self.match)
        self.selected: Set[Card] = set()
        self.tribute_sel: Set[Card] = set()      # 进贡阶段选中的牌
        self.gift_marks: Set[Card] = set()       # 本轮进贡**得来**的牌（手牌里标出来）
        self.result = None                  # 上一手结算结果
        self.alive = True

        self._events: Deque[ft.TextSpan] = deque(maxlen=MAX_EVENTS)
        self._log_lines: Deque[str] = deque(maxlen=MAX_EVENTS)  # 纯文本，供落盘
        # 每条日志的 (颜色, 加粗) —— 联机快照要把着色一起广播，客人才不会
        # 看到一串白字（0.4.8-fix：事件记录也是「要同步的内容」）
        self._log_meta: Deque[Tuple[str, bool]] = deque(maxlen=MAX_EVENTS)
        self._log_sent = 0                  # 房主：已随快照发出去的日志条数
        self._log_have = 0                  # 客人：已收到的日志条数（对齐用）
        self._log_saved = False        # 这一场是否已经落盘（防止重复写文件）
        self._ai_task = None

        # ---- 界面引用 ----
        self.score_text = ft.Text("", size=13, weight=ft.FontWeight.BOLD,
                                  color=T.TEXT_PRIMARY)
        self.level_note = ft.Text("", size=11, color=MUTED)
        self.net_text = ft.Text("", size=11, color=MUTED)
        self.turn_text = ft.Text("", size=12)
        self.seat_row = ft.Row(spacing=8, wrap=True)
        self.target_box = ft.Container()
        self.hand_box: Optional[ft.Container] = None   # 手牌盒：高度随行数变化
        self.my_hand_col = ft.Column(
            spacing=HAND_ROW_GAP, scroll=ft.ScrollMode.AUTO,
            auto_scroll=False, expand=True)
        self.play_btn: ft.Button = ft.Button(
            content=ft.Text("出牌"), height=40, width=110,
            bgcolor=T.PRIMARY, color=T.TEXT_INVERT, on_click=self._on_play)
        self.pass_btn: ft.Button = ft.Button(
            content=ft.Text("过牌"), height=40, width=110,
            bgcolor=T.SURFACE_ALT, color=T.TEXT_PRIMARY,
            on_click=self._on_pass)
        self.clear_btn: ft.Button = ft.Button(
            content=ft.Text("清空选择"), height=40,
            bgcolor=T.SURFACE_ALT, color=T.TEXT_SECONDARY,
            on_click=self._on_clear)
        self.hint_text = ft.Text("", size=12, color=T.TEXT_MUTED)
        self.result_box = ft.Container()
        self.events_text = ft.Text(
            value="", spans=[], selectable=True, font_family="monospace",
            size=12, no_wrap=False, opacity=1.0,
            animate_opacity=0, animate_size=0,
        )
        self.events_inner = ft.Column(
            controls=[self.events_text], scroll=ft.ScrollMode.AUTO,
            auto_scroll=True, expand=True, spacing=0,
            animate_opacity=0, animate_size=0,
        )

    # ============================================================
    # 界面组装
    # ============================================================

    def build(self) -> ft.Control:
        events_box = ft.Container(
            content=self.events_inner,
            height=EVENTS_HEIGHT,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            opacity=1.0, animate_opacity=0, animate_size=0,
        )
        events_section = ft.Container(
            bgcolor=T.SURFACE,
            border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.all(10),
            content=ft.Column(
                [ft.Text("── 近期事件 ──", size=11, color=MUTED),
                 ft.Container(height=4),
                 events_box],
                spacing=0,
            ),
        )

        top_bar = ft.Container(
            bgcolor=T.SURFACE,
            border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.all(12),
            content=ft.Row(
                [
                    ft.Column(
                        [self.score_text, self.level_note, self.net_text],
                        spacing=2, expand=True,
                    ),
                    self.turn_text,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        table_box = ft.Container(
            bgcolor=T.SURFACE,
            border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.all(10),
            content=ft.Column(
                [self.seat_row, ft.Container(height=8), self.target_box],
                spacing=0,
            ),
        )

        self.hand_box = ft.Container(
            bgcolor=T.SURFACE,
            border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            height=HAND_BOX_HEIGHT,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=self.my_hand_col,
        )

        actions = ft.Row(
            [self.play_btn, self.pass_btn, self.clear_btn,
             ft.Container(expand=True), self.hint_text],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        body = ft.Column(
            [
                top_bar,
                ft.Container(height=8),
                table_box,
                ft.Container(height=8),
                self.result_box,
                self.hand_box,
                ft.Container(height=8),
                actions,
                ft.Container(height=8),
                events_section,
            ],
            spacing=0,
            # 手机上竖直空间不够（手牌可能换成多行），整页可滚，保证都能看到
            scroll=ft.ScrollMode.AUTO,
        )

        view = ft.Column(
            [
                app_bar(
                    "对局",
                    on_back=self._on_back,
                    actions=[
                        ft.TextButton(
                            content=ft.Row(
                                [
                                    ft.Icon(ft.Icons.HISTORY, size=16,
                                            color=T.TEXT_PRIMARY),
                                    ft.Text("历史记录", size=12,
                                            color=T.TEXT_PRIMARY),
                                ],
                                spacing=4, tight=True,
                            ),
                            on_click=self._on_history,
                            tooltip="查看往期出牌记录",
                        ),
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.all(12),
                    content=body,
                    expand=True,
                ),
            ],
            expand=True,
        )
        self._log(f"对局开始：{self._seat_summary()}", HEAD_COLOR, bold=True)
        if self.net is not None:
            # 联机：接管会话的玩法消息；房主当即推牌，客人向房主要牌
            global _CURRENT_PLAY
            _CURRENT_PLAY = self
            self.net.set_game_handler(self._on_net)
            if self.is_host:
                self._push_state()
                self._start_ai()
            else:
                self.net.send_game_to_host({"k": "req_state"})
                self.page.run_task(self._sync_wait)      # 传方法，别带括号！
            self.page.run_task(self._net_poll)
        self._refresh()
        if self.net is None:
            self._start_ai()
        return view

    # ============================================================
    # 刷新
    # ============================================================

    def _refresh(self):
        if not self._synced:
            self._render_waiting()
            return
        self._render_top()
        self._render_seats()
        self._render_target()
        self._render_my_hand()
        self._render_result()
        self._render_buttons()
        self.page.update()

    def _render_waiting(self):
        """客人还没拿到房主的快照：只显示「等待发牌」，不渲染本地那副随机牌。"""
        self.turn_text.value = "等待房主发牌…"
        self.turn_text.color = MUTED
        self.net_text.value = "正在与房主同步局面…"
        self.net_text.color = MUTED
        self.seat_row.controls = [
            ft.Text("等待房主发牌…", size=12, color=MUTED)]
        self.target_box.content = ft.Container()
        self.my_hand_col.controls = [
            ft.Text("正在与房主同步局面…", size=13, color=MUTED)]
        if self.hand_box is not None:
            self.hand_box.height = HAND_BOX_HEIGHT
        self.result_box.visible = False
        self.play_btn.disabled = True
        self.pass_btn.disabled = True
        self.clear_btn.disabled = True
        self.page.update()

    def _render_top(self):
        m = self.match
        lv = m.levels
        mine = self.cfg.my_team()
        self.score_text.value = (
            f"第 {m.hand_no + 1} 局    甲丙 {lv[0]}    乙丁 {lv[1]}"
        )
        self.score_text.color = TEAM_COLOR[mine]
        self.level_note.value = (
            f"{level_ranks_desc(self.hand.ctx)}"
            f"    ·    逢人配：红桃级牌可当任意牌"
        )
        self.level_note.color = MUTED
        self._render_net_text()

        if m.winner is not None:
            self.turn_text.value = f"整场结束 · 队{m.winner} 获胜"
            self.turn_text.color = WIN_COLOR
            return
        if self.hand.ended:
            self.turn_text.value = "本局已结束"
            self.turn_text.color = WIN_COLOR
            return
        turn = self.hand.turn
        self.turn_text.value = f"当前：{NAMES[turn]}（{self._controller(turn)}）"
        self.turn_text.color = (MUTED if self._is_auto(turn)
                                else TEAM_COLOR[self.cfg.team_of(turn)])

    def _render_net_text(self):
        """顶栏那行联机状态（本地单人模式留空）。"""
        if self.net is None:
            self.net_text.value = ""
            return
        if self.spectator:
            self.net_text.value = "联机观战中 · 只读牌桌"
        else:
            self.net_text.value = (f"联机对局 · 你是{NAMES[self.my_seat]}"
                                   f"（{self.cfg.local_nick or '你'}）")
        self.net_text.color = MUTED

    def _render_seats(self):
        chips: List[ft.Control] = []
        for p in range(4):
            n = self.hand.hand_size(p)
            out = p in self.hand.out_order
            place = (self.hand.out_order.index(p) + 1) if out else None
            place_text = "已出完" if out else f"{n} 张"
            active = self.hand.turn == p and not self.hand.ended
            chips.append(
                ft.Container(
                    bgcolor=T.SURFACE_ALT,
                    border=ft.Border.all(
                        2 if active else 1,
                        TEAM_COLOR[self.cfg.team_of(p)] if active else T.BORDER,
                    ),
                    border_radius=8,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                    content=ft.Row(
                        [
                            ft.Text(NAMES[p], size=14,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEAM_COLOR[self.cfg.team_of(p)]),
                            ft.Container(width=8),
                            ft.Column(
                                [
                                    ft.Text(self._controller(p), size=11,
                                            color=T.TEXT_SECONDARY),
                                    ft.Text(
                                        place_text, size=12,
                                        color=MUTED if not out else WIN_COLOR),
                                ],
                                spacing=0,
                            ),
                            ft.Container(width=8),
                            ft.Text(f"{place}游", size=11,
                                    color=WIN_COLOR) if place
                            else ft.Container(),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )
        self.seat_row.controls = chips

    def _render_target(self):
        combo = self.hand.current
        if self.hand.ended:
            text, color, imgs = "本局结束", MUTED, []
        elif combo is None:
            text, color, imgs = "自由出牌（本轮由首位玩家先出）", HEAD_COLOR, []
        else:
            owner = self.hand.combo_owner
            note = combo_wild_note(combo.cards, self.hand.ctx,
                                   self.cfg.team_of(owner), combo)
            text = (f"待压：{combo}（{NAMES[owner]}）"
                    + (f"    {note}" if note else ""))
            color = (BOMB_COLOR if _is_bomb(combo)
                     else TEAM_COLOR[self.cfg.team_of(owner)])
            imgs = []
            for c in combo.cards:
                wcolor, wlabel = wild_style(c, self.hand.ctx,
                                            self.cfg.my_team())
                mine_lv = (not c.is_joker
                           and self.hand.ctx.is_my_level(
                               c.rank, self.cfg.my_team()))
                tip = str(c)
                if wlabel:
                    tip += f"（{wlabel}）"
                elif not c.is_joker and self.hand.ctx.is_level_rank(c.rank):
                    tip += (f"（级牌·"
                            f"{self.hand.ctx.level_owner_label(c.rank)}）")
                imgs.append(
                    ft.Container(
                        border=ft.Border.all(
                            2 if (wcolor or mine_lv
                                  or (not c.is_joker
                                      and self.hand.ctx.is_level_rank(c.rank)))
                            else 0,
                            wcolor or (LEVEL_MY if mine_lv else LEVEL_FOE),
                        ),
                        border_radius=4,
                        content=ft.Image(
                            src=card_image_src(c), width=PLAY_W,
                            height=PLAY_H, fit=ft.BoxFit.CONTAIN,
                            tooltip=tip,
                        ),
                    )
                )
        self.target_box.content = ft.Row(
            [ft.Text(text, size=12, color=color), ft.Container(width=10), *imgs],
            spacing=2,
            # 长顺子/钢板有十几张牌，窄屏一行放不下，允许自动换行
            wrap=True,
            run_spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # ============================================================
    # 窄屏适配：手牌换行
    # ============================================================

    def _available_width(self) -> float:
        """手牌区可用宽度（页面宽 − 页面内边距 − 手牌盒内边距与边框）。"""
        w = page_width(self.page, _FALLBACK_WIDTH)   # 首帧取不到时按手机宽兜底
        return max(200.0, w - 2 * T.PADDING - 22)

    def _hand_layout(self, cards: List[Card]):
        """按可用宽度算排布：``(每行牌列表, 牌宽, 牌高, 行内负间距)``。

        宽屏一行放得下就原样返回（仍是紧凑叠放的老样子）；窄屏交给
        :func:`~core.ui_common.fit_card_row`：先加大重叠、不够再整体缩牌，
        保证 27 张一张都不被挤掉，不用横向拖着找牌。
        """
        if not cards:
            return [], CARD_W, CARD_H, HAND_SPACING
        cw, ch, sp, per_row, rows = fit_card_row(
            self._available_width(), len(cards),
            CARD_W, CARD_H, HAND_SPACING)
        if rows <= 1:
            return [cards], cw, ch, sp
        # 均衡分行：避免「13+13+1」这种最后一行只有一两张的排布
        per = min(-(-len(cards) // rows), per_row)      # ceil(count/rows)
        return ([cards[i:i + per] for i in range(0, len(cards), per)],
                cw, ch, sp)

    def _hand_box_height(self, rows: int, card_h: int = CARD_H) -> float:
        """手牌盒高度随行数增长，上限 HAND_BOX_MAX_HEIGHT（超了内部滚动）。"""
        need = 20 + rows * (card_h + HAND_ROW_GAP) + 46  # 内边距+牌行+说明行
        return float(min(HAND_BOX_MAX_HEIGHT, max(HAND_BOX_HEIGHT, need)))

    def _card_widget(self, c: Card, mine_turn: bool,
                     w: int = CARD_W, h: int = CARD_H) -> ft.Control:
        """单张手牌：选中抬升 + 级牌/逢人配描边（窄屏时 w/h 会被缩小）。

        本轮进贡**得来**的牌另加金框与「贡」标注，方便一眼看出哪张是别人给的。
        """
        ctx = self.hand.ctx
        sel = c in self.selected
        is_gift = c in self.gift_marks
        wcolor, wlabel = wild_style(c, ctx, self.cfg.my_team())
        mine_lv = (not c.is_joker
                   and ctx.is_my_level(c.rank, self.cfg.my_team()))
        tip = str(c)
        if wlabel:
            tip += f"（{wlabel}）"
        elif not c.is_joker and ctx.is_level_rank(c.rank):
            owner = ctx.level_owner_label(c.rank)
            tip += f"（级牌·{owner}）"
        if is_gift:
            tip += "（本轮进贡得来的牌）"
        return ft.Container(
            on_click=(lambda _e, cc=c: self._toggle_card(cc))
            if mine_turn else None,
            ink=mine_turn,
            offset=ft.Offset(0, LIFT) if sel else None,
            border=ft.Border.all(
                2 if (sel or is_gift or wcolor or mine_lv
                      or (not c.is_joker
                          and ctx.is_level_rank(c.rank))) else 0,
                T.PRIMARY if sel else
                (LEVEL_GOLD if is_gift else
                 (wcolor or (LEVEL_MY if mine_lv else LEVEL_FOE))),
            ),
            border_radius=5,
            content=ft.Image(
                src=card_image_src(c), width=w, height=h,
                fit=ft.BoxFit.CONTAIN, tooltip=tip,
            ),
        )

    def _render_my_hand(self):
        me = self.cfg.local_seat
        ctx = self.hand.ctx
        if self.spectator:
            # 旁观者不展示任何一家的手牌（联机时手牌信息只属于座上玩家）
            self.my_hand_col.controls = [
                ft.Text("观战中 · 手牌仅座上玩家可见", size=13, color=MUTED),
                ft.Text("出牌记录见下方「近期事件」", size=11, color=MUTED),
            ]
            if self.hand_box is not None:
                self.hand_box.height = HAND_BOX_HEIGHT
            return
        if self._tribute_active():
            # 进贡阶段：手牌区改成进贡面板（先发牌再进贡，用的是这一手的牌）
            self.my_hand_col.controls = [
                self._tribute_panel(),
                ft.Text("进贡阶段 · 出牌记录见下方「近期事件」",
                        size=11, color=MUTED),
            ]
            if self.hand_box is not None:
                self.hand_box.height = HAND_BOX_HEIGHT
            return
        cards = sort_hand(self.hand.hands[me], ctx)
        mine_turn = (self.hand.turn == me and not self.hand.ended
                     and self.match.winner is None and self._is_local(me))
        if not cards:
            rows: List[ft.Control] = [ft.Text("— 已出完 —", size=13,
                                              color=MUTED)]
            if self.hand_box is not None:
                self.hand_box.height = HAND_BOX_HEIGHT
        else:
            chunks, cw, ch, sp = self._hand_layout(cards)
            rows = [
                ft.Row([self._card_widget(c, mine_turn, cw, ch) for c in chunk],
                       spacing=sp,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER)
                for chunk in chunks
            ]
            if self.hand_box is not None:
                self.hand_box.height = self._hand_box_height(len(chunks), ch)
        caption = (f"你的手牌 · {NAMES[me]} · "
                   + (f"已选 {len(self.selected)} 张" if mine_turn
                      else "等待其他玩家出牌"))
        if self.gift_marks:
            caption += "    金框＝本轮进贡得来的牌"
        self.my_hand_col.controls = [
            *rows,
            ft.Text(caption, size=11, color=MUTED),
            self._level_note(ctx),
        ]

    def _level_note(self, ctx) -> ft.Control:
        """手牌下方一行说明：级牌是谁的、大小顺序（消除「2 怎么还最大」的误解）。"""
        return ft.Container(
            margin=ft.Margin.only(top=2),
            content=ft.Row(
                [
                    ft.Text("单张大小：", size=11, color=MUTED),
                    ft.Text(size_order_hint(ctx), size=11, color=LEVEL_GOLD),
                ],
                spacing=4, wrap=True,
            ),
        )

    def _render_result(self):
        if self.result is None:
            self.result_box.visible = False
            self.result_box.content = ft.Container()
            return
        r = self.result
        win = (r.winner_team == self.cfg.my_team())
        order = "   ".join(f"{i + 1}游 {NAMES[p]}"
                           for i, p in enumerate(r.out_order))
        if r.match_over:
            head = f"整场结束 · 队{r.winner_team} 获胜"
        else:
            head = (f"本局结束 · 头游 {NAMES[r.out_order[0]]}（队{r.winner_team}）"
                    f" 升 {r.upgrade} 级 → "
                    f"{r.levels_after[0]} / {r.levels_after[1]}")
        btn = ft.Button(
            content=ft.Text("返回掼蛋菜单" if r.match_over else "下一局"),
            height=38,
            bgcolor=T.SURFACE_ALT if r.match_over else T.PRIMARY,
            color=T.TEXT_PRIMARY if r.match_over else T.TEXT_INVERT,
            on_click=self._on_after_hand,
        )
        self.result_box.visible = True
        self.result_box.content = ft.Container(
            bgcolor=WIN_COLOR if win else T.SURFACE,
            border=ft.Border.all(1, WIN_COLOR),
            border_radius=8,
            padding=ft.Padding.all(12),
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(head, size=14, weight=ft.FontWeight.BOLD,
                                    color=T.TEXT_INVERT if win
                                    else T.TEXT_PRIMARY),
                            ft.Container(height=4),
                            ft.Text(order, size=12,
                                    color=T.TEXT_INVERT if win
                                    else T.TEXT_SECONDARY),
                        ],
                        spacing=0, expand=True,
                    ),
                    btn,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _render_buttons(self):
        me = self.cfg.local_seat
        if self._tribute_active():
            # 进贡阶段不能出牌：三个按钮全禁用，提示走进贡流程
            self.play_btn.disabled = True
            self.pass_btn.disabled = True
            self.clear_btn.disabled = True
            self.play_btn.content = ft.Text("出牌")
            self.hint_text.value = "先进贡 / 还贡，再开始出牌"
            self.hint_text.color = T.TEXT_MUTED
            return
        live = (not self.hand.ended) and self.match.winner is None
        my_turn = live and self.hand.turn == me and self._is_local(me)
        self.play_btn.disabled = not my_turn
        self.pass_btn.disabled = not my_turn
        self.clear_btn.disabled = not my_turn or not self.selected
        self.play_btn.content = ft.Text(
            f"出牌（{len(self.selected)}）" if self.selected else "出牌")
        if not my_turn:
            return
        if self.hand.current is None:
            # 首出必须出牌，不能过
            self.pass_btn.disabled = True
            return
        # 手上压不过当前牌型时，把「出牌」也禁用（legal_moves 约0.5ms）
        if not self.hand.legal_moves(me):
            self.play_btn.disabled = True
            self.hint_text.value = "无牌可压，请过牌"
            self.hint_text.color = T.DANGER

    # ============================================================
    # 事件日志（单 Text + spans）
    # ============================================================

    def _log(self, text: str, color: str = FG, bold: bool = False):
        """写一条事件日志。

        联机时**客人不本地写日志**：所有人的着法都由房主记，随快照增量广播
        下来（见 ``_push_state`` / ``_apply_state``），避免同一步出现两遍。
        """
        if self.net is not None and not self.is_host:
            return
        self._append_log(text, color, bold)

    def _append_log(self, text: str, color: str, bold: bool) -> None:
        """无条件追加一条日志（本地或来自快照增量都走这里）。"""
        style = ft.TextStyle(
            color=color, size=12, font_family="monospace",
            weight=ft.FontWeight.BOLD if bold else ft.FontWeight.NORMAL,
        )
        self._events.append(ft.TextSpan(text + "\n", style))
        self._log_lines.append(text)          # 纯文本副本，赛后落盘用
        self._log_meta.append((color, bold))
        self.events_text.spans = list(self._events)
        self.events_text.value = ""
        # 跟随到底部靠 events_inner 的 auto_scroll=True；不再手动 scroll_to ——
        # flet 1.0 里它是协程，不 await 只会刷「never awaited」告警

    # ============================================================
    # 真人操作
    # ============================================================

    def _toggle_card(self, card: Card):
        if card in self.selected:
            self.selected.discard(card)
        else:
            self.selected.add(card)
        self.hint_text.color = T.TEXT_MUTED
        self.hint_text.value = self._preview_hint()
        self._render_my_hand()
        self._render_buttons()
        self.page.update()

    def _preview_hint(self) -> str:
        """选中后立刻判断这手牌能不能压，让「谁大」一目了然。"""
        if not self.selected:
            return ""
        me = self.cfg.local_seat
        cards = sorted(self.selected, key=str)
        probe = parse(cards, self.hand.ctx)
        if probe is None:
            return f"选中的 {len(cards)} 张不是合法牌型"
        lv = {r: f"级牌·{self.hand.ctx.level_owner_label(r)}"
              for r in dict.fromkeys(self.hand.ctx.levels)
              if self.hand.ctx.is_level_rank(r)}
        if self.hand.current is None:
            hint = "自由出牌（本轮由你先出）"
        elif beats(probe, self.hand.current):
            hint = f"能压过「{self.hand.current}」"
        else:
            hint = f"压不过「{self.hand.current}」"
        tags = sorted({lv[c.rank] for c in cards if lv.get(c.rank)})
        if tags:
            hint += f"    含 {'、'.join(tags)}（级牌大于 2）"
        return hint

    def _on_clear(self, _e):
        self.selected.clear()
        self._render_my_hand()
        self._render_buttons()
        self.page.update()

    def _on_play(self, _e):
        me = self.cfg.local_seat
        if not self._is_local(me):
            return
        if self.hand.ended or self.hand.turn != me or not self.selected:
            return
        try:
            combo = self.hand.play(me, sorted(self.selected, key=str))
        except IllegalMove as e:
            self.hint_text.value = f"出不了：{e}"
            self.hint_text.color = T.DANGER
            self.page.update()
            return
        self.selected.clear()
        self.hint_text.value = ""
        self.hint_text.color = T.TEXT_MUTED
        bomb = _is_bomb(combo)
        self._log_play(me, combo, bomb)
        if me in self.hand.out_order:
            self._log(f"★ {NAMES[me]} 出完（{len(self.hand.out_order)}游）",
                      WIN_COLOR, bold=True)
        self._after_action()
        # 联机：把这一步告诉房主（房主应用后重推快照给所有人）
        self._notify_host({"k": "mv", "p": me,
                           "c": cards_to_json(sorted(combo.cards, key=str))})

    def _on_pass(self, _e):
        me = self.cfg.local_seat
        if not self._is_local(me):
            return
        if self.hand.ended or self.hand.turn != me:
            return
        if self.hand.current is None:
            self.hint_text.value = "首出必须出牌，不能过"
            self.hint_text.color = T.DANGER
            self.page.update()
            return
        try:
            self.hand.pass_turn(me)
        except IllegalMove as e:
            self.hint_text.value = f"不能过：{e}"
            self.hint_text.color = T.DANGER
            self.page.update()
            return
        self.selected.clear()
        self.hint_text.value = ""
        self.hint_text.color = T.TEXT_MUTED
        self._log(f"{NAMES[me]} 过", MUTED)
        self._after_action()

    # ============================================================
    # 进贡
    # ============================================================

    def _tribute_active(self) -> bool:
        """这一手是否正处于进贡阶段（还没走完）。"""
        tr = self.hand.tribute
        return tr is not None and tr.active and not tr.done

    def _tribute_panel(self) -> ft.Control:
        """进贡阶段占住手牌区：提示 + **整排手牌** + 确定按钮。

        选贡牌 / 选还牌都直接摆出自己的全部手牌（点不了的压暗），这样能
        照着整排牌面挑，不用在一小撮候选里猜；进贡得来的牌另打「贡」标识。
        """
        tr = self.hand.tribute
        act = tr.current() if tr is not None else None
        head = ft.Text("── 进贡 ──", size=11, color=LEVEL_GOLD,
                       weight=ft.FontWeight.BOLD)
        if act is None:
            return head
        me = self.cfg.local_seat
        if not self._is_local(act.player):
            who = f"{NAMES[act.player]}（{self._controller(act.player)}）"
            return ft.Column(
                [head,
                 ft.Text(f"等待 {who} {_TRIBUTE_VERBS.get(act.kind, '操作')}…",
                         size=13, color=MUTED)],
                spacing=4,
            )

        options = tr.options(act)
        # 选贡 / 选还的候选牌在别人手里，只能列候选；自己手上的两步摆全手牌
        show_all = act.kind in (GIFT, RETURN)
        cards = (sort_hand(self.hand.hands[me], self.hand.ctx) if show_all
                 else list(options))
        gifts = set(tr.received_gifts(me)) if tr is not None else set()
        chunks, cw, ch, sp = self._hand_layout(cards)

        rows: List[ft.Control] = []
        for chunk in chunks:
            imgs: List[ft.Control] = []
            for c in chunk:
                ok = c in options
                sel = c in self.tribute_sel
                is_gift = c in gifts
                tip = str(c)
                if is_gift:
                    tip += "（本轮进贡得来的牌）"
                elif not ok:
                    tip += "（这一步不能选）"
                color = (T.PRIMARY if sel else
                         (LEVEL_GOLD if is_gift else
                          (TRIBUTE_OK if ok else T.BORDER)))
                imgs.append(
                    ft.Container(
                        on_click=(lambda _e, cc=c: self._toggle_tribute_card(cc))
                        if ok else None,
                        ink=ok,
                        offset=ft.Offset(0, LIFT) if sel else None,
                        opacity=1.0 if ok else TRIBUTE_DIM,
                        border=ft.Border.all(
                            2 if (sel or ok or is_gift) else 1, color),
                        border_radius=5,
                        content=ft.Image(
                            src=card_image_src(c), width=cw, height=ch,
                            fit=ft.BoxFit.CONTAIN, tooltip=tip),
                    )
                )
            rows.append(ft.Row(imgs, spacing=sp, wrap=True,
                               run_spacing=HAND_ROW_GAP,
                               vertical_alignment=ft.CrossAxisAlignment.CENTER))
        # 上贡来的牌单独标出来（还贡时它还在对方手里，手牌里看不到）
        gift_row: List[ft.Control] = []
        if gifts and act.kind == RETURN:
            gift_row = [
                ft.Row(
                    [ft.Text("本轮收到的贡牌：", size=11, color=LEVEL_GOLD)]
                    + [ft.Container(
                        border=ft.Border.all(2, LEVEL_GOLD),
                        border_radius=5,
                        content=ft.Image(
                            src=card_image_src(c), width=cw, height=ch,
                            fit=ft.BoxFit.CONTAIN,
                            tooltip=f"{c}（本轮进贡得来的牌）"))
                        for c in sorted(gifts, key=str)],
                    spacing=6, wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(height=6),
            ]

        if self.hand_box is not None:
            # 手牌区要给提示行 + 贡牌行 + 确定按钮留地方，高度按行数一起长
            extra = 76 + (26 if gift_row else 0)
            need = 20 + len(rows) * (ch + HAND_ROW_GAP) + 46 + extra
            self.hand_box.height = float(
                min(HAND_BOX_MAX_HEIGHT, max(HAND_BOX_HEIGHT, need)))

        confirm = ft.Button(
            content=ft.Text("确定"), height=40, width=110,
            bgcolor=T.PRIMARY, color=T.TEXT_INVERT,
            disabled=not self.tribute_sel,
            on_click=self._on_tribute_confirm,
        )
        note = (f"整排手牌里，亮着的（{len(options)} 张）可以选" if show_all
                else "点一张牌再按确定")
        return ft.Column(
            [
                head,
                ft.Text(act.prompt, size=12, color=T.TEXT_SECONDARY),
                ft.Container(height=6),
                *gift_row,
                *rows,
                ft.Container(height=8),
                ft.Row(
                    [confirm, ft.Container(width=10),
                     ft.Text(note, size=11, color=MUTED)],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=0,
        )

    def _toggle_tribute_card(self, card: Card):
        if card in self.tribute_sel:
            self.tribute_sel.discard(card)
        else:
            self.tribute_sel.add(card)
        self._refresh()

    def _on_tribute_confirm(self, _e):
        tr = self.hand.tribute
        if tr is None or tr.done:
            return
        act = tr.current()
        if act is None or not self._is_local(act.player):
            return
        if len(self.tribute_sel) != 1:
            self.hint_text.value = "请先点一张牌"
            self.hint_text.color = T.DANGER
            self.page.update()
            return
        card = next(iter(self.tribute_sel))
        if not tr.choose(card):
            self.hint_text.value = "这张牌不符合当前步骤的要求"
            self.hint_text.color = T.DANGER
            self.page.update()
            return
        self.tribute_sel.clear()
        self.hint_text.value = ""
        self.hint_text.color = T.TEXT_MUTED
        self._tribute_after_step(tr)
        self._refresh()
        self._start_ai()
        # 联机：把这次进贡 / 还贡的选择告诉房主
        self._notify_host({"k": "tribute", "card": card_to_json(card)})

    def _tribute_after_step(self, tr):
        """进贡走完：真正换牌、把事件写进日志，并记下进贡得来的牌。"""
        if not tr.done:
            return
        me = self.cfg.local_seat
        for line in tr.apply():
            self._log(line, LEVEL_GOLD)
        self.gift_marks = set(tr.received_gifts(me))

    def _tribute_ai_step(self, tr) -> None:
        """电脑位自动完成当前进贡动作。"""
        act = tr.current()
        if act is None:
            return
        card = auto_pick(tr)
        if card is None or not tr.choose(card):
            return
        self._tribute_after_step(tr)

    # ============================================================
    # 电脑代打
    # ============================================================

    def _start_ai(self):
        if self._ai_task is None or self._ai_task.done():
            self._ai_task = self.page.run_task(self._ai_loop)

    async def _ai_loop(self):
        # 联机时**只有房主跑电脑代打**：房主每步都会重推快照，客人照抄即可；
        # 两边都跑 AI 只会无故分歧（0.4.8-fix）。
        if self.net is not None and not self.is_host:
            return
        while self.alive:
            if self.match.winner is not None:
                return
            # ---- 进贡阶段：电脑位自动进贡 / 还贡 ----
            tr = self.hand.tribute
            if tr is not None and tr.active and not tr.done:
                await asyncio.sleep(AI_DELAY)
                if not self.alive:
                    return
                tr = self.hand.tribute
                if tr is None or not tr.active or tr.done:
                    continue
                act = tr.current()
                if act is None:
                    continue
                if not self._is_auto(act.player):
                    await asyncio.sleep(HUMAN_POLL)   # 等真人，无倒计时
                    continue
                self._tribute_ai_step(tr)
                self._refresh()
                self._push_state()
                continue
            if self.hand.ended:
                return
            turn = self.hand.turn
            if not self._is_auto(turn):
                await asyncio.sleep(HUMAN_POLL)     # 等真人，无倒计时
                continue
            await asyncio.sleep(AI_DELAY)
            if self.hand.ended or self.match.winner is not None:
                return
            turn = self.hand.turn                  # 等待期间可能已换人
            if not self._is_auto(turn):
                continue
            self._ai_step(turn)
            self._after_action()
            self._push_state()

    def _ai_step(self, turn: int):
        combo = choose(self.hand, turn)
        try:
            if combo is None:
                self.hand.pass_turn(turn)
                self._log(f"{NAMES[turn]} 过", MUTED)
                return
            played = self.hand.play(turn, combo.cards)
        except IllegalMove as e:
            # 理论上不会发生；出现就跳过，避免协程空转
            self._log(f"{NAMES[turn]} 出牌异常：{e}", BOMB_COLOR)
            return
        bomb = _is_bomb(played)
        self._log_play(turn, played, bomb)
        if turn in self.hand.out_order:
            self._log(f"★ {NAMES[turn]} 出完（{len(self.hand.out_order)}游）",
                      WIN_COLOR, bold=True)

    def _log_play(self, seat: int, combo, bomb: bool):
        """出牌日志：牌型 + 队色；用了逢人配时追加「当什么用、原本是谁的」。"""
        note = combo_wild_note(combo.cards, self.hand.ctx,
                               self.cfg.team_of(seat), combo)
        self._log(f"{NAMES[seat]} 出 {combo}" + (f"    {note}" if note else ""),
                  BOMB_COLOR if bomb else TEAM_COLOR[self.cfg.team_of(seat)],
                  bold=bomb)

    # ============================================================
    # 联机同步（房主权威：发牌 + 每步重推整局快照）
    # ============================================================

    def _setup_net_seats(self) -> None:
        """按房间席位表排座：房间 0~3 号座 = 牌桌 甲~丁，空位给电脑。

        房间 4 号位起（或还没入座）的人只围观，不看任何一手牌。
        """
        members = self.net.roster()
        by_seat = {m.seat: m for m in members if m.seat >= 0}
        seats = list(self.cfg.seats)
        for i in range(4):
            seats[i] = SEAT_HUMAN if i in by_seat else SEAT_AI
        if all(s == SEAT_AI for s in seats):        # 兜底：不能全电脑
            seats[0] = SEAT_HUMAN
        my_room_seat = self.net.me.seat
        if 0 <= my_room_seat < 4:
            self.my_seat = my_room_seat
            self.spectator = False
        else:
            self.my_seat = 0
            self.spectator = True
        self.remote_nicks = {
            i: by_seat[i].nick for i in range(4)
            if i in by_seat and by_seat[i].mid != self.net.me.mid
        }
        self.cfg = replace(self.cfg, seats=tuple(seats),
                           local_seat=self.my_seat)

    def _is_local(self, seat: int) -> bool:
        """这个座位是不是由本机玩家亲手操作（旁观者谁都不操作）。"""
        return not self.spectator and seat == self.my_seat

    def _is_auto(self, seat: int) -> bool:
        """这个座位是否由电脑代打：本机玩家与远端真人之外的座位。

        联机时远端真人的座位**不**交给电脑 —— 他的着法会随房主快照到达。
        """
        if self._is_local(seat):
            return False
        if seat in self.remote_nicks:
            return False
        return True

    def _controller(self, seat: int) -> str:
        """界面上的控制器标签：你 / 远端昵称 / 电脑。"""
        if self._is_local(seat):
            return self.cfg.local_nick or "你"
        if seat in self.remote_nicks:
            return self.remote_nicks[seat]
        return "电脑"

    def _seat_summary(self) -> str:
        """座位一览（写进日志 / 落盘元信息）。"""
        if self.net is None:
            return self.cfg.summary()
        return "  ".join(f"{NAMES[p]}·{self._controller(p)}"
                         for p in range(4))

    def _notify_host(self, data: Dict[str, Any]) -> None:
        """客人：把本地这一步动作单播给房主（房主应用后重推快照）。"""
        if self.net is not None and not self.is_host:
            self.net.send_game_to_host(data)

    def _detach_net(self) -> None:
        """离开牌桌：摘掉网络回调，别让旧实例继续收玩法消息。"""
        if self.net is not None:
            self.net.set_game_handler(None)
        global _CURRENT_PLAY
        if _CURRENT_PLAY is self:
            _CURRENT_PLAY = None

    def _push_state(self) -> None:
        """房主：把整场局面 + 新的事件日志广播给房间里其他所有人。"""
        if self.net is None or not self.is_host:
            return
        self._seq += 1
        lines = self._log_lines
        start = min(self._log_sent, len(lines))
        delta = [[text, _LOG_COLOR_KEYS.get(color, "fg"), bool(bold)]
                 for text, (color, bold) in zip(
                     list(lines)[start:], list(self._log_meta)[start:])]
        self._log_sent = len(lines)
        self.net.send_game({"k": "state", "seq": self._seq,
                            "log_from": start, "log": delta,
                            "s": serialize_match(self.match, self.hand,
                                                 self.result)})

    def _on_net(self, msg):
        """收到房间里的玩法消息。

        房主是权威：只处理客人的动作请求（mv / pass / tribute / next）与
        req_state；客人只接受房主的 state 快照（按 seq 只采用更新的）。
        """
        if self is not _CURRENT_PLAY or not self.alive or self.net is None:
            return
        data = msg.get("data") or {}
        k = data.get("k")
        try:
            if k == "req_state":
                if self.net.is_host:
                    self._push_state()
            elif k == "state":
                if not self.net.is_host:
                    self._apply_state(data)
            elif k == "mv":
                if self.net.is_host:
                    self._host_apply_play(data)
            elif k == "pass":
                if self.net.is_host:
                    self._host_apply_pass(data)
            elif k == "tribute":
                if self.net.is_host:
                    self._host_apply_tribute(data)
            elif k == "next":
                if self.net.is_host:
                    self._host_next_hand()
        except Exception:                     # noqa: BLE001
            # 网络线程里不能炸；坏包忽略即可
            pass

    def _apply_state(self, data: Dict[str, Any]) -> None:
        """采用房主推来的整局快照（乱序 / 重传的旧包直接丢弃）。"""
        try:
            seq = int(data.get("seq", 0))
        except (TypeError, ValueError):
            return
        if seq <= self._last_seq:
            return
        hand = load_match(self.match, data.get("s") or {})
        if hand is None:
            return
        self.hand = hand
        self._last_seq = seq
        # ---- 事件日志增量（漏过的开头补一句说明，后续按条数对齐）----
        try:
            log_from = int(data.get("log_from", 0) or 0)
        except (TypeError, ValueError):
            log_from = self._log_have
        if log_from > self._log_have:
            self._append_log(f"……（漏过 {log_from - self._log_have} 条事件）",
                             MUTED, False)
            self._log_have = log_from
        for entry in (data.get("log") or []):
            try:
                text = str(entry[0])
                color = _LOG_COLORS.get(str(entry[1]), FG)
                bold = bool(entry[2])
            except (IndexError, TypeError, ValueError):
                continue
            self._append_log(text, color, bold)
            self._log_have += 1
        # ---- 局面 ----
        # 结算面板：一手可能由任意一家（含房主上的电脑）走完，客人不本地推导，
        # 直接用快照里房主的结算结果（0.4.8-fix）。房主发了下一手（res 为空、
        # 牌局未结束）就清掉面板 —— 不能靠 hand_no 判断：settle 时它已经 +1 了，
        # 发新手不会再变（0.4.8-fix2：客人会卡在上一手的结算面板上）。
        if self.hand.ended:
            res = result_from_json(data.get("res"))
            if res is not None:
                self.result = res
                self._result_hand_no = self.match.hand_no
        else:
            self.result = None
        self.selected.clear()
        self.tribute_sel.clear()
        tr = self.hand.tribute
        if tr is None or tr.done:
            # 进贡得来的牌：走完才标（中途不标，牌还没换过来）
            self.gift_marks = (set(tr.received_gifts(self.my_seat))
                               if tr is not None else set())
        if not self._synced:
            self._synced = True
            self._start_ai()
        # 整场结束由房主的快照确认，客人在这一刻才落盘（日志已齐）
        if self.match.winner is not None and not self._log_saved:
            self._save_match_log()
        self._refresh()

    # ---------------- 房主：应用客人的动作 ----------------

    def _host_apply_play(self, data: Dict[str, Any]) -> None:
        seat = data.get("p")
        cards = cards_from_json(data.get("c"))
        if not _is_seat(seat) or cards is None:
            return
        if self.hand.ended or self.hand.turn != seat:
            return
        try:
            combo = self.hand.play(seat, cards)
        except IllegalMove:
            return                          # 客人的局面过期 → 忽略，快照会纠正
        self._log_play(seat, combo, _is_bomb(combo))
        if seat in self.hand.out_order:
            self._log(f"★ {NAMES[seat]} 出完（{len(self.hand.out_order)}游）",
                      WIN_COLOR, bold=True)
        self._after_action()
        self._push_state()

    def _host_apply_pass(self, data: Dict[str, Any]) -> None:
        seat = data.get("p")
        if not _is_seat(seat):
            return
        if self.hand.ended or self.hand.turn != seat:
            return
        try:
            self.hand.pass_turn(seat)
        except IllegalMove:
            return
        self._log(f"{NAMES[seat]} 过", MUTED)
        self._after_action()
        self._push_state()

    def _host_apply_tribute(self, data: Dict[str, Any]) -> None:
        tr = self.hand.tribute
        if tr is None or tr.done:
            return
        card = card_from_json(data.get("card"))
        if card is None or not tr.choose(card):
            return
        self._tribute_after_step(tr)
        self._refresh()
        self._push_state()

    def _host_next_hand(self) -> None:
        r = self.result
        if r is None or r.match_over:
            return
        self._deal_next_hand()

    # ---------------- 客人：要牌 / 席位变化 ----------------

    async def _sync_wait(self) -> None:
        """没拿到房主快照就周期性重问（房主的视图可能比我们晚建好）。"""
        for _ in range(40):                     # 最多 20 秒
            if not self.alive or self._synced or self is not _CURRENT_PLAY:
                return
            self.net.send_game_to_host({"k": "req_state"})
            await asyncio.sleep(0.5)

    async def _net_poll(self) -> None:
        """联机时周期性按席位表刷新控制器标注（有人入座 / 离开）。"""
        while self.alive and self is _CURRENT_PLAY and self.net is not None:
            try:
                self._refresh_seats_from_room()
            except Exception:                 # noqa: BLE001
                pass
            await asyncio.sleep(1.0)

    def _refresh_seats_from_room(self) -> None:
        """席位表变了 → 重算远端真人；离开的座位交给电脑代打（房主接管）。"""
        if self.net is None:
            return
        members = self.net.roster()
        by_seat = {m.seat: m for m in members if m.seat >= 0}
        remote = {i: by_seat[i].nick for i in range(4)
                  if i in by_seat and by_seat[i].mid != self.net.me.mid}
        if remote != self.remote_nicks:
            gone = [n for s, n in self.remote_nicks.items() if s not in remote]
            self.remote_nicks = remote
            if gone and self._synced:
                self._log(f"（联机）{'、'.join(gone)} 离开了牌桌，"
                          f"空位由电脑代打", MUTED)
            if self._synced:
                self._refresh()

    # ============================================================
    # 流转
    # ============================================================

    def _after_action(self):
        """任何一次出牌/过牌之后：结算或继续。"""
        if self.hand.ended:
            self.result = settle(self.match, self.hand)
            self._result_hand_no = self.match.hand_no
            r = self.result
            self._log(
                "本局结束：" + "  ".join(NAMES[p] for p in r.out_order), MUTED)
            if r.match_over:
                self._log(f"◆ 整场结束 · 队{r.winner_team} 获胜",
                          WIN_COLOR, bold=True)
                # 联机客人不在此刻落盘：他的日志要等房主快照补齐，
                # 统一在 _apply_state 里确认 winner 后才写（见那里）
                if self.net is None or self.is_host:
                    self._save_match_log()
            else:
                self._log(
                    f"队{r.winner_team} 升 {r.upgrade} 级 → "
                    f"{r.levels_after[0]}/{r.levels_after[1]}", HEAD_COLOR)
                plan = self.match.pending_tribute
                if plan is not None:
                    self._log(
                        f"下一手进贡：{_plan_summary(plan)}", LEVEL_GOLD)
            self.selected.clear()
        self._refresh()

    def _save_match_log(self, finished: bool = True) -> None:
        """把这一场的完整出牌记录落盘到应用数据目录。

        整场结束（``finished=True``）会存，**中途离开也会存**（标成「中途结束」），
        这样历史记录里每一场都留得下，不会白打。同一场只写一次文件。
        """
        if self._log_saved or not self._log_lines:
            return
        self._log_saved = True
        state = "整场结束" if finished else "中途结束（未打完）"
        winner = (f"队{self.result.winner_team}" if self.result
                  else ("未分胜负" if not finished else "未知"))
        lines = list(self._log_lines) + [
            f"◆ 记录结束：{state} · 打完 {self.match.hand_no} 局 · "
            f"级数 {self.match.levels[0]}/{self.match.levels[1]}",
        ]
        try:
            path = history.save_match_log(
                "guandan", lines,
                meta={
                    "状态": state,
                    "胜方": winner,
                    "局数": self.match.hand_no,
                    "级数": f"{self.match.levels[0]}/{self.match.levels[1]}",
                    "座位": self._seat_summary(),
                },
            )
        except Exception as e:                      # noqa: BLE001
            self._log(f"保存出牌记录失败：{e}", BOMB_COLOR)
            return
        if path and str(path):
            self._log(f"出牌记录已保存：{path}", MUTED)
        else:
            self._log("出牌记录保存失败（数据目录不可写？）", BOMB_COLOR)

    def _in_progress(self) -> bool:
        """当前是否还有没打完的对局（整场结束 / 已分胜负就不算）。"""
        if self.match.winner is not None:
            return False
        return not (self.result is not None and self.result.match_over)

    def _leave_target(self) -> str:
        """回哪：这局是从联机房间开起来的就回房间，否则回掼蛋子菜单。"""
        return "/room" if _sess.current() is not None else "/g/guandan"

    def _on_back(self, _e):
        """顶栏返回：牌没打完先问一句，避免误触丢掉这一局。"""
        if self._in_progress():
            self._confirm_leave(lambda: self.navigate(self._leave_target()))
            return
        self._save_match_log(False)
        self.alive = False
        self._detach_net()
        self.navigate(self._leave_target())

    def _on_history(self, _e):
        """顶栏「历史记录」：看往期出牌记录（同理先确认）。"""
        if self._in_progress():
            self._confirm_leave(lambda: open_history(self.navigate))
            return
        self._save_match_log(False)
        self.alive = False
        self._detach_net()
        open_history(self.navigate)

    def _confirm_leave(self, go):
        """离开前确认；``go`` 是确认后真正执行的跳转。"""
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("离开当前对局？"),
                content=ft.Text(
                    "这局还没打完：离开后无法继续打，但出牌记录会自动存进"
                    "「历史记录」。", size=13),
                actions=[
                    ft.TextButton(content=ft.Text("取消"),
                                  on_click=lambda _e: self.page.pop_dialog()),
                    ft.TextButton(content=ft.Text("离开"),
                                  on_click=lambda _e: self._leave_to(go)),
                ],
            )
        )

    def _leave_to(self, go):
        self.page.pop_dialog()
        self._save_match_log(False)     # 中途退出也留一份记录
        self.alive = False
        self._detach_net()
        go()

    def _on_after_hand(self, _e):
        r = self.result
        if r is not None and r.match_over:
            self.alive = False
            self._detach_net()
            self.navigate(self._leave_target())
            return
        if self.net is not None and not self.is_host:
            # 客人不洗牌：请房主发下一手，快照回来自然换手（0.4.8-fix：
            # 此前客人本地 Hand() 会自己随机发一副，又变成各玩各的）
            self.net.send_game_to_host({"k": "next"})
            self.hint_text.value = "已请求房主发下一手…"
            self.hint_text.color = T.TEXT_MUTED
            self._refresh()
            return
        self._deal_next_hand()

    def _deal_next_hand(self):
        """本地（房主 / 单人）发下一手，并把新局面推给联机房间。"""
        r = self.result
        self.result = None
        self.match.next_leader = (
            r.out_order[0] if r is not None else self.match.next_leader
        )
        self.hand = Hand(self.match)
        self.selected.clear()
        self.tribute_sel.clear()
        self.gift_marks.clear()          # 上一轮进贡得来的标记只管那一轮
        self._log(f"── 第 {self.match.hand_no + 1} 局 ──", HEAD_COLOR, bold=True)
        tr = self.hand.tribute
        if tr is not None and (tr.active or tr.refused):
            # 先发牌再进贡：进贡用的是这一手刚发好的牌（抗贡时 summary 说抗贡）
            self._log(tr.summary(), LEVEL_GOLD)
            if tr.refused:
                self._log(f"抗贡不换牌，由{NAMES[self.hand.turn]}先出",
                          HEAD_COLOR)
        self._refresh()
        self._start_ai()
        self._push_state()

    def dispose(self):
        """视图被丢弃：兜底再存一次（正常退出走 _on_back，这里是保险）。"""
        self._save_match_log(False)
        self.alive = False
        self._detach_net()


_ACTIVE: List[_Play] = []          # 当前/上一张牌桌（换场时用来收尾）
# 同一时刻只有「当前正在显示」的牌桌响应网络消息（防路由器缓存里的旧实例）
_CURRENT_PLAY: "Optional[_Play]" = None


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """建一张新牌桌；上一场还没收尾就先存盘并停掉它的协程。"""
    for old in _ACTIVE:
        old.dispose()
    _ACTIVE.clear()
    view = _Play(page, navigate)
    _ACTIVE.append(view)
    return view.build()
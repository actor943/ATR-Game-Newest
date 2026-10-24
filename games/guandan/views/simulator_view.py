# -*- coding: utf-8 -*-
"""全模拟：图形化观战视图（0.4.4）。

把 0.4.3 的终端日志换成真实牌图：

* 四家手牌 → 各自一行 ``ft.Image``（野牌加红框），按级牌感知排序
* 最近出牌 → 居中一行大图，显示当前这手最后打出的牌型
* 近期事件 → 小段文字流（保留叙事，含「过」、升级、整场结束等）
* 控制条：▶播放 / ⏸暂停 / 单步 / 新一场 / 变速（与 0.4.3 同）
* 牌桌风格配色：深底 + 队色（蓝/橙）+ 炸弹红 + 赢家绿
* 动画全关，避免 flet 1.0 默认过渡造成「淡化」

炸弹特效、牌面飞入动画等留待后续版本。
"""

from __future__ import annotations

import asyncio
import random
from collections import deque
from typing import Deque, List, Optional, Tuple

import flet as ft

from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, fit_card_row, page_padding, page_width
from games.guandan.ai import choose
from games.guandan.assets import card_image_src
from games.guandan.cards import size_order_hint, sort_hand, wild_owner
from games.guandan.engine import Hand, MatchState, TEAM_OF, new_match, settle
from games.guandan.rules import Combo, ComboType

# 牌桌风格配色（深底亮字，不随应用主题切换）
TEAM_COLOR = ("#3B82F6", "#F59E0B")   # 队0 蓝 / 队1 橙
BOMB_COLOR = "#EF4444"
WIN_COLOR = "#10B981"
HEAD_COLOR = "#8B5CF6"
TURN_COLOR = "#FBBF24"
MUTED = "#9CA3AF"
SURFACE = "#1F2937"
SURFACE_ALT = "#374151"
TEXT = "#F9FAFB"

PLAYER_NAMES = ("甲", "乙", "丙", "丁")
OUT_NAMES = ("头游", "二游", "三游", "末游")
SPEEDS = (("慢", 0.9), ("中", 0.45), ("快", 0.15), ("极快", 0.03))

CARD_W, CARD_H = 34, 48               # 手牌牌图尺寸
PLAY_W, PLAY_H = 48, 67               # 最近出牌牌图尺寸（略大）
HAND_SPACING = -10                     # 手牌重叠像素
# 窄屏（手机）适配：27 张 × 净宽 24 ≈ 650dp，手机只有 360dp，原来靠 wrap 硬挤，
# 重叠得太狠认不出牌。现在先加大重叠、再整体缩小牌面，保证一张都不被切掉。
MIN_CARD_STEP = 20                     # 叠放时每张至少露出的像素
MIN_CARD_W = 24                        # 牌面缩到这个宽就不再缩了
SIM_MAX_ROWS = 2                       # 一家手牌最多占几行（观战页地方有限）
# 可用宽度 = 页宽 − 页面内边距 − 区块内边距 − 边框 − 余量
HAND_WIDTH_MARGIN = T.PADDING * 2 + 10 * 2 + 2 + 8
MAX_EVENTS = 40# 近期事件保留条数（超出自动裁剪，滚动查看）
EVENTS_HEIGHT = 112                # 事件窗口固定高度（≈6 行），超出由内部 Column 滚动
EVENT_LINE_H = 18
LEVEL_GOLD = "#FFD54F"                     # 级牌金框（观战无「我方」，统一金色）
WILD_MINE = "#FF4D4F"                     # 甲丙的逢人配
WILD_THEIRS = "#FF8A65"                   # 乙丁的逢人配
WILD_SHARED = "#F06292"                   # 双方共有的逢人配


def wild_border(card, ctx):
    """观战下按归属区分两个逢人配（0=甲丙 1=乙丁 共用=粉）。"""
    teams = wild_owner(card, ctx)
    if not teams:
        return None
    if len(teams) == 2:
        return WILD_SHARED
    return WILD_MINE if teams[0] == 0 else WILD_THEIRS


def card_tile(card, ctx, width: int, height: int) -> ft.Control:
    """一张牌图：逢人配按归属上色、级牌金框，tooltip 说明身份。

    双方级数不同时有两个不同的逢人配，必须按归属区分，否则看不出谁在借谁的牌。
    """
    wcolor = wild_border(card, ctx)
    is_lv = not card.is_joker and ctx.is_level_rank(card.rank)
    tip = str(card)
    if wcolor:
        tip += (f"（逢人配·万能牌·可当任意牌·"
                f"{ctx.level_owner_label(card.rank)}的）")
    elif is_lv:
        tip += f"（级牌·{ctx.level_owner_label(card.rank)}）"
    if not wcolor and not is_lv:
        return ft.Image(src=card_image_src(card), width=width, height=height,
                        fit=ft.BoxFit.CONTAIN, tooltip=tip)
    return ft.Container(
        content=ft.Image(src=card_image_src(card), width=width, height=height,
                         fit=ft.BoxFit.CONTAIN, tooltip=tip),
        border=ft.Border.all(2, wcolor or LEVEL_GOLD),
        border_radius=4,
    )


def _pname(p: int) -> str:
    return PLAYER_NAMES[p]


class _Session:
    """对局会话：asyncio 协程驱动；UI 控件由 build() 传入，会话只更新它们。"""

    def __init__(self, page: ft.Page,
                 hand_rows: List[ft.Row], hand_headers: List[ft.Text],
                 last_play_label: ft.Text, last_play_row: ft.Row,
                 events_text: ft.Text, status: ft.Text,
                 events_scroll: ft.Column,
                 play_btn: ft.Button, speed_btn: ft.Button):
        self.page = page
        self.hand_rows = hand_rows
        self.hand_headers = hand_headers
        self.last_play_label = last_play_label
        self.last_play_row = last_play_row
        self.events_text = events_text
        self.events_scroll = events_scroll
        self.status = status
        self.play_btn = play_btn
        self.speed_btn = speed_btn
        self.running = asyncio.Event()
        self.speed_idx = 1
        self.match: Optional[MatchState] = None
        self.hand: Optional[Hand] = None
        self.finished = False
        self._task: Optional[asyncio.Task] = None
        self.last_play: Optional[Tuple[int, Combo]] = None
        self._events: Deque[ft.TextSpan] = deque(maxlen=MAX_EVENTS)

    # ---------- 对局推进 ----------

    def new_match(self):
        self.match = new_match(random.randrange(10 ** 6))
        self.hand = None
        self.finished = False
        self.last_play = None
        self._events.clear()
        self._add_event("新的一场开始：甲丙 vs 乙丁，从「打 2」起步",
                        HEAD_COLOR, bold=True)
        self._reset_visuals()
        self._refresh()

    def step_once(self) -> bool:
        if self.match is None or self.finished:
            return False
        if self.hand is None or self.hand.ended:
            self.hand = Hand(self.match)
            self._add_event(
                f"── 第 {self.match.hand_no + 1} 局 · "
                f"级数 {self.match.levels[0]}/{self.match.levels[1]} · "
                f"{_pname(self.match.next_leader)}先出 ──", HEAD_COLOR)
        else:
            self._play_one_move()
        self._update_hands()
        if self.hand.ended:
            self._settle_and_log()
        self._update_status()
        self._refresh()
        return not self.finished

    def _play_one_move(self):
        hand = self.hand
        player = hand.turn
        is_lead = hand.current is None
        combo = choose(hand, player)
        if combo is None:
            hand.pass_turn(player)
            self._add_event(f"{_pname(player)} 过", MUTED)
            return
        hand.play(player, combo.cards)
        self.last_play = (player, combo)
        is_bomb = combo.type in (ComboType.BOMB, ComboType.JOKER_BOMB,
                                 ComboType.FLUSH_STRAIGHT)
        color = (BOMB_COLOR if is_bomb
                 else TEAM_COLOR[TEAM_OF[player]])
        tag = "领出" if is_lead else "压"
        self._add_event(f"{_pname(player)} {tag} {combo}", color)
        if not hand.hands[player]:
            rank = len(hand.out_order) - 1
            self._add_event(
                f"  ★ {_pname(player)} 出完 → {OUT_NAMES[rank]}！",
                WIN_COLOR, bold=True)

    def _settle_and_log(self):
        result = settle(self.match, self.hand)
        order = " > ".join(OUT_NAMES[i] + "(" + _pname(p) + ")"
                           for i, p in enumerate(result.out_order))
        self._add_event(f"第 {self.match.hand_no} 局结束：{order}", MUTED)
        self._add_event(
            f"  队{result.winner_team} 升 {result.upgrade} 级 → "
            f"级数 {result.levels_after[0]} / {result.levels_after[1]}",
            TEAM_COLOR[result.winner_team], bold=True)
        if result.match_over:
            self.finished = True
            self._add_event(
                f"◆ 整场结束：队{result.winner_team} 在 A 级获胜！",
                WIN_COLOR, bold=True)

    # ---------- 视图更新 ----------

    def _card_layout(self, count: int, card_w: int, card_h: int,
                     spacing: int, max_rows: int) -> Tuple[int, int, int]:
        """按可用宽度算「牌宽 / 牌高 / 间距」，窄屏自动缩小牌面。

        手机竖屏下一家 27 张排不开，光靠 wrap 会把牌压成一条缝。
        这里用 :func:`core.ui_common.fit_card_row`：先加大重叠，
        行数还是超就整体缩小牌面（宽高等比），保证一张牌都不被切掉。
        """
        avail = max(180.0, page_width(self.page, 420.0) - HAND_WIDTH_MARGIN)
        w, h, gap, _per_row, _rows = fit_card_row(
            avail, count, card_w, card_h, spacing,
            min_step=MIN_CARD_STEP, max_rows=max_rows, min_card_w=MIN_CARD_W)
        return w, h, gap

    def _update_hands(self):
        m = self.match
        h = self.hand
        if m is None or h is None:
            return
        ctx = m.ctx
        for p in range(4):
            remaining = len(h.hands[p])
            team = TEAM_OF[p]
            is_turn = (h.turn == p and not h.ended)
            badge = "  ⚡轮到TA" if is_turn else ""
            self.hand_headers[p].value = (
                f"{_pname(p)}  ·  队{team}  ·  剩 {remaining}{badge}"
            )
            if is_turn:
                self.hand_headers[p].color = TURN_COLOR
            elif remaining == 0:
                self.hand_headers[p].color = MUTED
            else:
                self.hand_headers[p].color = TEAM_COLOR[team]

            if remaining == 0:
                rank = h.out_order.index(p) if p in h.out_order else -1
                out_name = OUT_NAMES[rank] if rank >= 0 else "已出完"
                self.hand_rows[p].controls = [
                    ft.Container(
                        content=ft.Text(f"✓ {out_name}", size=14,
                                        color=WIN_COLOR,
                                        weight=ft.FontWeight.BOLD),
                        padding=ft.Padding.all(10),
                        alignment=ft.alignment.Alignment.CENTER,
                    )
                ]
                continue
            ordered = sort_hand(h.hands[p], ctx)
            w, c_h, gap = self._card_layout(len(ordered), CARD_W, CARD_H,
                                            HAND_SPACING, SIM_MAX_ROWS)
            self.hand_rows[p].spacing = gap
            self.hand_rows[p].controls = [
                card_tile(c, ctx, w, c_h) for c in ordered
            ]

        # 最近出牌
        if self.last_play is not None:
            player, combo = self.last_play
            is_bomb = combo.type in (ComboType.BOMB, ComboType.JOKER_BOMB,
                                     ComboType.FLUSH_STRAIGHT)
            color = (BOMB_COLOR if is_bomb
                     else TEAM_COLOR[TEAM_OF[player]])
            self.last_play_label.value = f"{_pname(player)} · {combo}"
            self.last_play_label.color = color
            pw, ph, pgap = self._card_layout(len(combo.cards), PLAY_W, PLAY_H,
                                             -6, SIM_MAX_ROWS)
            self.last_play_row.spacing = pgap
            self.last_play_row.controls = [
                card_tile(c, m.ctx, pw, ph) for c in combo.cards
            ]
        else:
            self.last_play_label.value = "（暂无出牌）"
            self.last_play_label.color = MUTED
            self.last_play_row.controls = []

    def _add_event(self, text: str, color: str = MUTED, bold: bool = False):
        # 0.4.3 模式：单 Text + spans，只设 spans，value 永远 ""
        # ——多行可整段选中复制，无 value+spans 重复渲染、无淡化动画
        style = ft.TextStyle(
            color=color, size=12, font_family="monospace",
            weight=ft.FontWeight.BOLD if bold else ft.FontWeight.NORMAL,
        )
        self._events.append(ft.TextSpan(text + "\n", style))
        self.events_text.spans = list(self._events)
        self.events_text.value = ""
        self._scroll_events()

    def _scroll_events(self):
        """新行跟随到底部由 events_scroll 的 auto_scroll=True 负责。

        （原先这里手动 scroll_to，但 flet 1.0 里它是协程，不 await 只会刷
        「coroutine never awaited」告警，故移除。）
        """

    def _reset_visuals(self):
        for p in range(4):
            self.hand_rows[p].controls = []
            self.hand_headers[p].value = f"{_pname(p)}  ·  队 -  ·  剩 -"
            self.hand_headers[p].color = MUTED
        self.last_play_label.value = "（暂无出牌）"
        self.last_play_label.color = MUTED
        self.last_play_row.controls = []
        self._events.clear()
        self.events_text.spans = []
        self.events_text.value = ""

    def _update_status(self):
        m = self.match
        sp = SPEEDS[self.speed_idx][0]
        if m is None:
            self.status.value = "未开始"
        elif self.finished:
            self.status.value = (f"整场结束 · 共 {m.hand_no} 局 · "
                                 f"队{m.winner} 获胜  ·  速度 {sp}")
        elif self.hand is not None and self.hand.ended:
            self.status.value = (f"已完成 {m.hand_no} 局 · "
                                 f"级数 {m.levels[0]}/{m.levels[1]}  ·  速度 {sp}")
        else:
            self.status.value = (f"第 {m.hand_no + 1} 局 · "
                                 f"级数 {m.levels[0]}/{m.levels[1]}  ·  速度 {sp}")
        # 顺带把单张大小顺序写出来（升级后最容易误解的地方）
        ctx = self.hand.ctx if self.hand is not None else m.ctx
        self.status.value += f"  ·  {size_order_hint(ctx)}"

    def _refresh(self):
        self.page.update()

    # ---------- 播放控制 ----------

    def toggle(self) -> bool:
        if self.match is None:
            self.new_match()
        if not self.finished:
            if self.running.is_set():
                self.running.clear()
            else:
                self.running.set()
                self._ensure_task()
        return self.running.is_set()

    def single_step(self):
        self.running.clear()
        if self.match is None:
            self.new_match()
        if not self.finished:
            self.step_once()

    def cycle_speed(self):
        self.speed_idx = (self.speed_idx + 1) % len(SPEEDS)
        self._update_status()
        self._refresh()

    def new_game(self):
        self.running.clear()
        self.new_match()
        self._update_status()
        self._refresh()

    def _ensure_task(self):
        if self._task is None or self._task.done():
            self._task = self.page.run_task(self._runner)

    async def _runner(self):
        while True:
            if not self.running.is_set():
                await asyncio.sleep(0.05)
                continue
            cont = self.step_once()
            if not cont or not self.running.is_set():
                await asyncio.sleep(0.05)
                continue
            await asyncio.sleep(SPEEDS[self.speed_idx][1])


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """全模拟视图：状态栏 + 4 家手牌 + 最近出牌 + 近期事件 + 控制。"""
    go_back = lambda _e: navigate("/g/guandan")

    # 四家手牌：header + Row（重叠排列）
    hand_rows: List[ft.Row] = [
        ft.Row(wrap=True, spacing=HAND_SPACING, run_spacing=4) for _ in range(4)
    ]
    hand_headers: List[ft.Text] = [
        ft.Text("", size=13, weight=ft.FontWeight.BOLD) for _ in range(4)
    ]
    player_sections: List[ft.Control] = []
    for p in range(4):
        player_sections.append(
            ft.Container(
                content=ft.Column(
                    [hand_headers[p],
                     ft.Container(height=4),
                     hand_rows[p]],
                    spacing=0,
                ),
                padding=ft.Padding.all(10),
                border=ft.Border.all(1, SURFACE_ALT),
                border_radius=8,
                bgcolor=SURFACE,
            )
        )

    # 最近出牌
    last_play_label = ft.Text("（暂无出牌）", size=14,
                              weight=ft.FontWeight.BOLD)
    last_play_row = ft.Row(wrap=True, spacing=-6, run_spacing=4,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER)
    last_play_section = ft.Container(
        content=ft.Column(
            [ft.Text("── 最近出牌 ──", size=11, color=MUTED),
             ft.Container(height=4),
             last_play_label,
             ft.Container(height=6),
             last_play_row],
            spacing=0,
        ),
        padding=ft.Padding.all(10),
        border=ft.Border.all(1, SURFACE_ALT),
        border_radius=8,
        bgcolor=SURFACE,
    )

    # 近期事件：单ft.Text + spans（继承 0.4.3 终端模式，Mac 可整段复制）
    events_text = ft.Text(
        value="",
        spans=[],
        selectable=True,
        font_family="monospace",
        size=12,
        no_wrap=False,
        opacity=1.0,
        animate_opacity=0,
        animate_size=0,
    )
    # 关键（同 0.4.3 终端）：固定高度窗口 + 内部 Column 负责滚动
    events_inner = ft.Column(
        controls=[events_text],
        scroll=ft.ScrollMode.AUTO,
        auto_scroll=True,                   # 新行自动跟随到底部
        expand=True,
        spacing=0,
        animate_opacity=0,
        animate_size=0,
    )
    events_box = ft.Container(
        content=events_inner,
        height=EVENTS_HEIGHT,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        opacity=1.0,
        animate_opacity=0,
        animate_size=0,
    )
    events_section = ft.Container(
        content=ft.Column(
            [ft.Text("── 近期事件 ──", size=11, color=MUTED),
             ft.Container(height=4),
             events_box],
            spacing=0,
        ),
        padding=ft.Padding.all(10),
        border=ft.Border.all(1, SURFACE_ALT),
        border_radius=8,
        bgcolor=SURFACE,
        opacity=1.0,
        animate_opacity=0,
    )

    # 状态栏 + 控制
    status = ft.Text("未开始", size=13, weight=ft.FontWeight.BOLD,
                     color=T.TEXT_PRIMARY)
    play_btn = ft.Button(content=ft.Text("▶ 播放"), height=38,
                         bgcolor=T.PRIMARY, color=T.TEXT_INVERT)
    speed_btn = ft.Button(
        content=ft.Text(f"速度: {SPEEDS[1][0]}"), height=38,
        bgcolor=T.SURFACE_ALT, color=T.TEXT_PRIMARY)

    session = _Session(page, hand_rows, hand_headers,
                       last_play_label, last_play_row,
                       events_text, status, events_inner,
                       play_btn, speed_btn)

    def on_play(_e):
        playing = session.toggle()
        play_btn.content.value = "⏸ 暂停" if playing else "▶ 播放"
        play_btn.bgcolor = T.ACCENT if playing else T.PRIMARY
        page.update()

    def on_step(_e):
        play_btn.content.value = "▶ 播放"
        play_btn.bgcolor = T.PRIMARY
        session.single_step()

    def on_new(_e):
        play_btn.content.value = "▶ 播放"
        play_btn.bgcolor = T.PRIMARY
        session.new_game()

    def on_speed(_e):
        session.cycle_speed()
        speed_btn.content.value = f"速度: {SPEEDS[session.speed_idx][0]}"
        page.update()

    play_btn.on_click = on_play
    speed_btn.on_click = on_speed

    buttons = ft.Row(
        [
            play_btn,
            ft.Button(content=ft.Text("单步"), icon=ft.Icons.SKIP_NEXT,
                      on_click=on_step, height=38,
                      bgcolor=T.SURFACE_ALT, color=T.TEXT_PRIMARY),
            ft.Button(content=ft.Text("新一场"), icon=ft.Icons.REFRESH,
                      on_click=on_new, height=38,
                      bgcolor=T.SURFACE_ALT, color=T.TEXT_PRIMARY),
            speed_btn,
        ],
        spacing=10,
        wrap=True,
    )

    body = ft.Column(
        [status,
         ft.Container(height=8),
         *player_sections,
         ft.Container(height=8),
         last_play_section,
         ft.Container(height=8),
         events_section,
         ft.Container(height=8),
         buttons],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    return ft.Column(
        [
            app_bar("全模拟", on_back=go_back),
            page_padding(body),
        ],
        expand=True,
    )

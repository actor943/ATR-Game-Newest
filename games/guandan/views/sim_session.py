# -*- coding: utf-8 -*-
"""掼蛋全模拟观战页的「会话」：自己跑一整场牌，把过程画出来。

观战页不需要联网，用 :mod:`games.guandan.simulator` 在本机跑 AI 对局，
再把每一步渲染成牌桌动画 —— 用来欣赏 AI 打法、演示规则。
"""

from __future__ import annotations

import asyncio
import random
from collections import deque
from typing import Deque, List, Optional, Tuple

import flet as ft

from core.ui_common import fit_card_row, page_width
from games.guandan.ai import choose
from games.guandan.cards import size_order_hint, sort_hand
from games.guandan.engine import Hand, MatchState, TEAM_OF, new_match, settle
from games.guandan.rules import Combo, ComboType
from games.guandan.views.sim_const import (
    BOMB_COLOR,
    CARD_H,
    CARD_W,
    HAND_SPACING,
    HAND_WIDTH_MARGIN,
    HEAD_COLOR,
    MAX_EVENTS,
    MIN_CARD_STEP,
    MIN_CARD_W,
    MUTED,
    OUT_NAMES,
    PLAY_H,
    PLAY_W,
    SIM_MAX_ROWS,
    SPEEDS,
    TEAM_COLOR,
    TURN_COLOR,
    WIN_COLOR,
    _pname,
    card_tile,
)

class _Session:
    """对局会话：asyncio 协程驱动；UI 控件由 build() 传入，会话只更新它们。"""

    def __init__(self, page: ft.Page,
                 hand_rows: List[ft.Row], hand_headers: List[ft.Text],
                 last_play_label: ft.Text, last_play_row: ft.Row,
                 events_text: ft.Text, status: ft.Text,
                 events_scroll: ft.Column,
                 play_btn: ft.Button, speed_btn: ft.Button):

        """准备观战会话：控件引用、事件列表、当前局面。"""
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

    # ---------- 开局与推进 ----------
    def new_match(self):

        """重新开一场：洗牌发牌并把画面重置。"""
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

        """单步：让 AI 走一手（牌型合法的那种）。"""
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

        """让某个座位出一手牌（交给 AI 选牌）。"""
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

        """一手结束后结算升级，并把结果写进事件流。"""
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

    # ---------- 画面刷新 ----------
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

        """重画四家的手牌（按级牌感知排序，逢人配加框）。"""
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

    # ---------- 事件流 ----------
    def _add_event(self, text: str, color: str = MUTED, bold: bool = False):
        # 0.4.3 模式：单 Text + spans，只设 spans，value 永远 ""
        # ——多行可整段选中复制，无 value+spans 重复渲染、无淡化动画
        """往事件流里加一条文字。"""
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

        """清画面：手牌、事件、状态全部重置。"""
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

        """刷新顶部状态（当前手数 / 级牌 / 谁该出牌）。"""
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

        """整体刷新一次界面。"""
        self.page.update()

    # ---------- 播放控制 ----------

    # ---------- 控制条动作 ----------
    def toggle(self) -> bool:

        """播放 / 暂停切换，返回现在是不是在播。"""
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

        """单步走一手（暂停状态下用）。"""
        self.running.clear()
        if self.match is None:
            self.new_match()
        if not self.finished:
            self.step_once()

    def cycle_speed(self):

        """切换速度档位（慢 / 中 / 快 / 极快）。"""
        self.speed_idx = (self.speed_idx + 1) % len(SPEEDS)
        self._update_status()
        self._refresh()

    def new_game(self):

        """换一场新的。"""
        self.running.clear()
        self.new_match()
        self._update_status()
        self._refresh()

    def _ensure_task(self):

        """确保后台播放协程在跑（没在跑就起一个）。"""
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

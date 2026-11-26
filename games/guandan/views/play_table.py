# -*- coding: utf-8 -*-
"""掼蛋牌桌的「画面」那一半（0.5 四方位牌桌）。

只负责把当前局面画出来，不改任何状态；由
:class:`games.guandan.views.play_view._Play` 与回放页以 mixin 的方式继承。

0.5 起按市面上斗地主 / 掼蛋客户端的视角重做：

* 绿呢牌桌 + 四个方位：对家在上、对门两家在左右、自己在下；
* 每家席位显示昵称 / 控制器 / 余牌数 / 游次，当前出牌者高亮；
* 对手手牌在牌桌上以牌背表示；**回放时改成全部明牌**（同样的牌桌 UI）；
* 各家最近一手牌留在自己席位旁，中央仍是本轮待压的牌；
* 自己的手牌在牌桌下方单独成排，点选抬升、级牌 / 逢人配描边照旧。

:func:`build_table_screen` 是实时对局与回放共用的骨架，保证两者视角一致。
"""

from __future__ import annotations

from typing import Dict, List, Optional

import flet as ft

from core.theme import T
from core.ui_common import app_bar, fit_card_row, page_width
from games.guandan.assets import card_back_image, card_image_src
from games.guandan.cards import (
    Card,
    level_ranks_desc,
    size_order_hint,
    sort_hand,
)
from games.guandan.views.play_const import (
    BOMB_COLOR,
    HAND_ROW_GAP,
    HEAD_COLOR,
    LEVEL_FOE,
    LEVEL_GOLD,
    LEVEL_MY,
    LIFT,
    MUTED,
    NAMES,
    OPP_CARD_SCALE,
    SEAT_PANEL,
    SEAT_PANEL_ACTIVE,
    TABLE_CENTER,
    TABLE_FELT,
    TABLE_FELT_EDGE,
    TEAM_COLOR,
    WIN_COLOR,
    _is_bomb,
    combo_wild_note,
    wild_style,
)


def build_table_screen(view, *, actions: ft.Control, title: str,
                       on_back,
                       app_actions: Optional[List[ft.Control]] = None) -> ft.Control:
    """实时对局 / 回放共用的整页骨架（顶栏 + 牌桌 + 手牌 + 事件）。

    调用方只需先准备好 ``score_text`` / ``target_box`` / ``my_hand_col`` /
    ``events_inner`` 等控件引用；这里负责把它们拼成同一套出牌视角。
    """
    events_box = ft.Container(
        content=view.events_inner,
        height=view.m["events"],
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
                    [view.score_text, view.level_note, view.net_text],
                    spacing=2, expand=True,
                ),
                view.turn_text,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    table_box = ft.Container(
        bgcolor=TABLE_FELT,
        border=ft.Border.all(1, TABLE_FELT_EDGE),
        border_radius=16,
        padding=ft.Padding.all(10),
        content=view._build_table(),
    )

    view.hand_box = ft.Container(
        bgcolor=T.SURFACE,
        border=ft.Border.all(1, T.BORDER),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        height=view.m["hand_box"],
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=view.my_hand_col,
    )

    body = ft.Column(
        [
            top_bar,
            ft.Container(height=8),
            table_box,
            ft.Container(height=8),
            view.result_box,
            view.hand_box,
            ft.Container(height=8),
            actions,
            ft.Container(height=8),
            events_section,
        ],
        spacing=0,
        # 手机上竖直空间不够（手牌可能换成多行），整页可滚，保证都能看到
        scroll=ft.ScrollMode.AUTO,
    )

    return ft.Column(
        [
            app_bar(title, on_back=on_back, actions=app_actions),
            ft.Container(
                padding=ft.Padding.all(12),
                content=body,
                expand=True,
            ),
        ],
        expand=True,
    )


class PlayTableMixin:
    """画面：四方位牌桌 / 待压区 / 手牌 / 结算 / 按钮。"""

    # ---------- 牌桌骨架 ----------
    def _build_table(self) -> ft.Control:
        """搭出「上 / 左 / 中 / 右 / 下」五个区域，返回整块牌桌。"""
        w = page_width(self.page, 900.0)
        wide = min(360.0, max(190.0, w * 0.32))
        side = min(210.0, max(112.0, w * 0.18))
        self._seat_widths = (wide, side, wide, side)
        self.seat_panels: List[ft.Container] = []
        for p in range(4):
            self.seat_panels.append(ft.Container(
                width=self._seat_widths[p],
                bgcolor=SEAT_PANEL,
                border=ft.Border.all(1, TABLE_FELT_EDGE),
                border_radius=12,
                padding=ft.Padding.all(6),
            ))
        center = ft.Container(
            content=self.target_box,
            expand=True,
            bgcolor=TABLE_CENTER,
            border_radius=12,
            padding=ft.Padding.symmetric(horizontal=6, vertical=8),
        )
        return ft.Column(
            [
                ft.Row([self.seat_panels[2]],
                       alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(height=6),
                ft.Row(
                    [self.seat_panels[3], center, self.seat_panels[1]],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=6),
                ft.Row([self.seat_panels[0]],
                       alignment=ft.MainAxisAlignment.CENTER),
            ],
            spacing=0,
        )

    def _seat_panel_content(self, p: int) -> ft.Control:
        """一个方位的信息：队色点 + 昵称 + 余牌 / 游次 + 手牌 + 最近一手。"""
        n = self.hand.hand_size(p)
        out = p in self.hand.out_order
        place = (self.hand.out_order.index(p) + 1) if out else 0
        color = TEAM_COLOR[self.cfg.team_of(p)]
        active = (self.hand.turn == p and not self.hand.ended
                  and self.match.winner is None)
        info = ft.Row(
            [
                ft.Container(width=7, height=7, border_radius=4,
                             bgcolor=color if active else TABLE_FELT_EDGE),
                ft.Text(NAMES[p], size=13, weight=ft.FontWeight.BOLD,
                        color=color),
                ft.Text(f"· {self._controller(p)}", size=10,
                        color=T.TEXT_SECONDARY),
                ft.Container(expand=True),
                ft.Text(f"{place}游" if place else f"{n} 张", size=11,
                        color=WIN_COLOR if place else MUTED),
            ],
            spacing=4, tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return ft.Column(
            [info, ft.Container(height=3), self._seat_hand_row(p),
             self._last_play_row(p)],
            spacing=0,
        )

    def _seat_hand_row(self, p: int) -> ft.Control:
        """对手手牌：实时只给牌背；回放把四家手牌全部摊开。"""
        replay = bool(getattr(self, "replay_mode", False))
        if p == self.cfg.local_seat:
            return ft.Row(
                [
                    ft.Icon(ft.Icons.ARROW_DOWNWARD, size=11, color=MUTED),
                    ft.Text("你的手牌见下方" + ("（明牌）" if replay else ""),
                            size=10, color=MUTED),
                ],
                spacing=2,
            )
        cards = self.hand.hands[p]
        if not cards:
            return ft.Text("— 已出完 —", size=10, color=MUTED)

        mini_w = max(18, int(round(self.m["card_w"] * OPP_CARD_SCALE)))
        mini_h = max(24, int(round(
            mini_w * self.m["card_h"] / max(1, self.m["card_w"]))))
        if not replay:
            backs = [
                ft.Container(content=card_back_image(width=mini_w,
                                                     height=mini_h))
                for _ in range(min(len(cards), 6))
            ]
            return ft.Row(
                [*backs, ft.Text(f"×{len(cards)}", size=10, color=MUTED)],
                spacing=-int(mini_w * 0.62),
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        ordered = sort_hand(cards, self.hand.ctx)
        avail = max(70.0, float(self._seat_widths[p]) - 18)
        w, h, sp, _per, _rows = fit_card_row(
            avail, len(ordered), mini_w, mini_h,
            -int(mini_w * 0.45),
            min_step=11, max_rows=3, min_card_w=16,
        )
        return ft.Row(
            [self._card_widget(c, False, w, h) for c in ordered],
            spacing=sp, wrap=True, run_spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _last_play_row(self, p: int) -> ft.Control:
        """留在某个席位旁边的「最近一手」（本轮新开时清掉）。"""
        plays: Dict[int, object] = getattr(self, "last_plays", None) or {}
        combo = plays.get(p)
        if combo is None or not getattr(combo, "cards", None):
            return ft.Container()
        cards = list(getattr(combo, "cards"))[:12]
        w = max(16, int(round(self.m["play_w"] * 0.72)))
        h = max(22, int(round(self.m["play_h"] * 0.72)))
        return ft.Column(
            [
                ft.Container(height=4),
                ft.Text("最近一手", size=9, color=MUTED),
                ft.Row(
                    [
                        ft.Image(src=card_image_src(c), width=w, height=h,
                                 fit=ft.BoxFit.CONTAIN, tooltip=str(c))
                        for c in cards
                    ],
                    spacing=1, wrap=True, run_spacing=1,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=0,
        )

    # ---------- 顶栏与座位 ----------
    def _render_top(self):
        """重画顶栏：级牌 / 比分 / 座位 / 联机状态。"""
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
        """顶栏那行联机状态（本地单人 / 回放留空）。"""
        if getattr(self, "net", None) is None:
            self.net_text.value = ""
            return
        if self.spectator:
            self.net_text.value = "联机观战中 · 只读牌桌"
        else:
            self.net_text.value = (f"联机对局 · 你是{NAMES[self.my_seat]}"
                                   f"（{self.cfg.local_nick or '你'}）")
        self.net_text.color = MUTED

    def _render_seats(self):
        """重画四方位席位：高亮当前出牌者，明牌 / 牌背随模式切换。"""
        if not getattr(self, "seat_panels", None):
            return
        for p in range(4):
            panel = self.seat_panels[p]
            active = (self.hand.turn == p and not self.hand.ended
                      and self.match.winner is None)
            panel.bgcolor = SEAT_PANEL_ACTIVE if active else SEAT_PANEL
            panel.border = ft.Border.all(
                2 if active else 1,
                TEAM_COLOR[self.cfg.team_of(p)] if active else TABLE_FELT_EDGE,
            )
            panel.content = self._seat_panel_content(p)

    # ---------- 中间「当前待压的牌」 ----------
    def _render_target(self):
        """重画牌桌中央「当前待压的牌」。"""
        combo = self.hand.current
        if self.hand.ended:
            text, color, imgs = "本局结束", MUTED, []
        elif combo is None:
            text, color, imgs = "自由出牌 · 本轮由首位玩家先出", HEAD_COLOR, []
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
                            src=card_image_src(c), width=self.m["play_w"],
                            height=self.m["play_h"], fit=ft.BoxFit.CONTAIN,
                            tooltip=tip,
                        ),
                    )
                )
        self.target_box.content = ft.Column(
            [
                ft.Text(text, size=11, color=color,
                        text_align=ft.TextAlign.CENTER),
                ft.Container(height=6),
                ft.Row(
                    imgs,
                    spacing=2, wrap=True, run_spacing=4,
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

    # ============================================================
    # 窄屏适配：手牌换行
    # ============================================================

    # ---------- 我的手牌区 ----------
    def _available_width(self) -> float:
        """手牌区可用宽度（页面宽 − 页面内边距 − 手牌盒内边距与边框）。"""
        w = page_width(self.page, 900.0)
        return max(200.0, w - 2 * T.PADDING - 22)

    def _hand_layout(self, cards: List[Card]):
        """按可用宽度算排布：``(每行牌列表, 牌宽, 牌高, 行内负间距)``。"""
        if not cards:
            return [], self.m["card_w"], self.m["card_h"], self.m["spacing"]
        cw, ch, sp, per_row, rows = fit_card_row(
            self._available_width(), len(cards),
            self.m["card_w"], self.m["card_h"], self.m["spacing"])
        if rows <= 1:
            return [cards], cw, ch, sp
        per = min(-(-len(cards) // rows), per_row)      # ceil(count/rows)
        return ([cards[i:i + per] for i in range(0, len(cards), per)],
                cw, ch, sp)

    def _hand_box_height(self, rows: int, card_h: int = 58) -> float:
        """手牌盒高度随行数增长，上限按视口放大（超了内部滚动）。"""
        need = 20 + rows * (card_h + HAND_ROW_GAP) + 46
        return float(min(self.m["hand_box_max"],
                         max(self.m["hand_box"], need)))

    def _card_widget(self, c: Card, mine_turn: bool,
                     w: Optional[int] = None,
                     h: Optional[int] = None) -> ft.Control:
        """单张牌：选中抬升 + 级牌/逢人配描边（宽屏放大 / 窄屏缩小）。"""
        w = self.m["card_w"] if w is None else w
        h = self.m["card_h"] if h is None else h
        ctx = self.hand.ctx
        sel = c in getattr(self, "selected", set())
        is_gift = c in getattr(self, "gift_marks", set())
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
        """重画下方我自己的手牌（回放里同样位置，但不可点）。"""
        replay = bool(getattr(self, "replay_mode", False))
        me = self.cfg.local_seat
        ctx = self.hand.ctx
        if self.spectator and not replay:
            self.my_hand_col.controls = [
                ft.Text("观战中 · 手牌仅座上玩家可见", size=13, color=MUTED),
                ft.Text("出牌记录见下方「近期事件」", size=11, color=MUTED),
            ]
            if self.hand_box is not None:
                self.hand_box.height = self.m["hand_box"]
            return
        if self._tribute_active():
            self.my_hand_col.controls = [
                self._tribute_panel(),
                ft.Text("进贡阶段 · 出牌记录见下方「近期事件」",
                        size=11, color=MUTED),
            ]
            if self.hand_box is not None:
                self.hand_box.height = self.m["hand_box"]
            return
        cards = sort_hand(self.hand.hands[me], ctx)
        mine_turn = (not replay and self.hand.turn == me
                     and not self.hand.ended
                     and self.match.winner is None and self._is_local(me))
        if not cards:
            rows: List[ft.Control] = [ft.Text("— 已出完 —", size=13,
                                              color=MUTED)]
            if self.hand_box is not None:
                self.hand_box.height = self.m["hand_box"]
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
        if replay:
            caption = f"回放 · {NAMES[me]} 的手牌（明牌） · 共 {len(cards)} 张"
        else:
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
        """手牌下方一行说明：级牌是谁的、大小顺序。"""
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

    # ---------- 结算面板与底部按钮 ----------
    def _render_result(self):
        """重画结算面板（一手结束后显示谁先谁后）。"""
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
        if getattr(self, "replay_mode", False):
            btn: ft.Control = ft.Container()
        else:
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
        """重画底部按钮（出牌 / 过牌 / 清空 / 提示）。"""
        if getattr(self, "replay_mode", False):
            self.play_btn.disabled = True
            self.pass_btn.disabled = True
            self.clear_btn.disabled = True
            return
        me = self.cfg.local_seat
        if self._tribute_active():
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
        if not self.hand.legal_moves(me):
            self.play_btn.disabled = True
            self.hint_text.value = "无牌可压，请过牌"
            self.hint_text.color = T.DANGER

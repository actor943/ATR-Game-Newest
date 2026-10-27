# -*- coding: utf-8 -*-
"""掼蛋牌桌的「画面」那一半：顶栏、席位、待压区、手牌、结算、按钮。

只负责把当前局面画出来，不改任何状态；由
:class:`games.guandan.views.play_view._Play` 以 mixin 的方式继承。
"""

from __future__ import annotations

from typing import List

import flet as ft

from core.theme import T
from core.ui_common import fit_card_row, page_width
from games.guandan.assets import card_image_src
from games.guandan.cards import (
    Card,
    level_ranks_desc,
    size_order_hint,
    sort_hand,
)
from games.guandan.views.play_const import (
    BOMB_COLOR,
    CARD_H,
    CARD_W,
    _FALLBACK_WIDTH,
    HAND_BOX_HEIGHT,
    HAND_BOX_MAX_HEIGHT,
    HAND_ROW_GAP,
    HAND_SPACING,
    HEAD_COLOR,
    LEVEL_FOE,
    LEVEL_GOLD,
    LEVEL_MY,
    LIFT,
    MUTED,
    NAMES,
    PLAY_H,
    PLAY_W,
    TEAM_COLOR,
    WIN_COLOR,
    _is_bomb,
    combo_wild_note,
    wild_style,
)

class PlayTableMixin:
    """画面：顶栏 / 席位 / 待压区 / 手牌 / 结算 / 按钮。"""

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

        """重画四个座位：昵称、剩余张数、正在出牌的人。"""
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

    # ---------- 中间「当前待压的牌」 ----------
    def _render_target(self):

        """重画中间「当前待压的牌」区域。"""
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

    # ---------- 我的手牌区 ----------
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

        """重画我自己的手牌。"""
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

# -*- coding: utf-8 -*-
"""掼蛋牌桌的「真人操作」那一半：选牌、出牌、过牌、进贡 / 还贡面板。

由 :class:`games.guandan.views.play_view._Play` 以 mixin 的方式继承。
"""

from __future__ import annotations

from typing import List

import flet as ft

from core.theme import T
from games.guandan.assets import card_image_src
from games.guandan.cards import Card, sort_hand
from games.guandan.engine import (
    IllegalMove,
    card_to_json,
    cards_to_json,
)
from games.guandan.rules import beats, parse
from games.guandan.tribute import GIFT, RETURN, auto_pick
from games.guandan.views.play_const import (
    FG,
    HAND_BOX_HEIGHT,
    HAND_BOX_MAX_HEIGHT,
    HAND_ROW_GAP,
    LEVEL_GOLD,
    LIFT,
    MUTED,
    NAMES,
    TRIBUTE_DIM,
    TRIBUTE_OK,
    WIN_COLOR,
    _TRIBUTE_VERBS,
    _is_bomb,
)

class PlayActionsMixin:
    """真人操作：选牌 / 出牌 / 过牌 / 进贡。"""

    # ---------- 事件日志 ----------
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

    # ---------- 选牌 / 出牌 / 过牌 ----------
    def _toggle_card(self, card: Card):

        """点一张手牌：选中 / 取消选中。"""
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

        """清空当前选中的牌。"""
        self.selected.clear()
        self._render_my_hand()
        self._render_buttons()
        self.page.update()

    def _on_play(self, _e):

        """点「出牌」：检查合法性 → 本地出牌 → 通知房主。"""
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
        # 房主自己出的牌**也**要广播出去（0.4.8-fix）：以前这一路只在
        # 「自己是客人」时才有内容，房主出牌 / 过牌 / 进贡全都没人知道 ——
        # 客人的牌桌一直停在发牌那一刻，看着就像两边手牌一样、也不更新。
        self._publish_if_host()

    def _on_pass(self, _e):

        """点「过牌」：首出不允许过，否则交给引擎处理。"""
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
        # 联机：告诉房主（房主应用后重推快照）；房主自己则直接推快照
        self._notify_host({"k": "pass", "p": me})
        self._publish_if_host()

    # ============================================================
    # 进贡
    # ============================================================

    # ---------- 进贡 / 还贡 ----------
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

        """进贡面板里点一张牌：选中 / 取消。"""
        if card in self.tribute_sel:
            self.tribute_sel.discard(card)
        else:
            self.tribute_sel.add(card)
        self._refresh()

    def _on_tribute_confirm(self, _e):

        """确认进贡：把选中的牌交给引擎。"""
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
        # 房主自己选的贡牌也要广播（0.4.8-fix，同出牌）
        self._publish_if_host()

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

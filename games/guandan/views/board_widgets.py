# -*- coding: utf-8 -*-
"""快速记牌页的「牌面组件」：普通牌按钮与王牌按钮。

拆出来是因为这两个类跟页面逻辑无关，单独放更好读也更好复用。
"""

from __future__ import annotations

import flet as ft

from core.theme import T

SUIT_NAMES = {"♠": "黑桃", "♥": "红心", "♣": "梅花", "♦": "方片"}
SUIT_COLORS = {"♠": "#333333", "♥": "#E53935", "♣": "#2E7D32", "♦": "#E53935"}


# ============================================================
# 牌面组件
# ============================================================

class CardButton(ft.Container):
    """单张牌按钮（同一花色点数有两张，用 copy_index 区分）"""

    def __init__(self, rank: str, suit: str, copy_index: int,
                 on_toggle, played: bool = False, is_wild: bool = False):

        """建好这张牌按钮：底色、点数、点击回调。"""
        self.rank = rank
        self.suit = suit
        self.copy_index = copy_index
        self._on_toggle = on_toggle
        self._played = played
        self._is_wild = is_wild

        color = SUIT_COLORS[suit]
        bg = self._get_bg(played, is_wild)

        self.top_text = ft.Text(
            suit if played else rank,
            size=14 if played else 13,
            color=color,
            weight=ft.FontWeight.BOLD,
        )
        bottom_label = "赖子" if is_wild else SUIT_NAMES[suit]
        self.suit_label = ft.Text(
            bottom_label, size=8,
            color="#D4A017" if is_wild else color,
        )

        border_color = "#D4A017" if is_wild else color
        super().__init__(
            width=T.CARD_W, height=T.CARD_H,
            bgcolor=bg,
            border=ft.Border.all(1.5 if not is_wild else 2, color=border_color),
            border_radius=6,
            alignment=ft.alignment.Alignment.CENTER,
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
            on_click=self._handle_click,
            content=ft.Column(
                [self.top_text, self.suit_label],
                spacing=0,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _get_bg(self, played: bool, is_wild: bool) -> str:

        """算这张牌当前的底色：已出 / 逢人配 / 普通 三种状态。"""
        if is_wild:
            return T.CARD_PLAYED if played else T.WILD_BG
        return T.CARD_PLAYED if played else T.CARD_BG

    @property
    def played(self):

        """这张牌有没有被标记成「已出」。"""
        return self._played

    @property
    def is_wild(self):

        """这张牌是不是逢人配（红桃级牌）。"""
        return self._is_wild

    def _handle_click(self, e):

        """点击这张牌：把「已出」状态取反。"""
        self._on_toggle(self)

    def update_state(self, played: bool):

        """刷新「已出」状态并重画。"""
        self._played = played
        color = SUIT_COLORS[self.suit]
        self.bgcolor = self._get_bg(played, self._is_wild)
        self.top_text.value = self.suit if played else self.rank
        self.top_text.color = color
        bottom_label = "赖子" if self._is_wild else SUIT_NAMES[self.suit]
        self.suit_label.value = bottom_label
        self.suit_label.color = "#D4A017" if self._is_wild else color
        border_color = "#D4A017" if self._is_wild else color
        self.border = ft.Border.all(
            1.5 if not self._is_wild else 2, color=border_color)

    def set_wild(self, is_wild: bool):

        """切换逢人配标记（用户可以手动改）。"""
        if self._is_wild == is_wild:
            return
        self._is_wild = is_wild
        self.update_state(self._played)


class JokerButton(ft.Container):
    """王牌按钮"""

    def __init__(self, name: str, copy_index: int, on_toggle,
                 played: bool = False):

        """建好这张牌按钮：底色、点数、点击回调。"""
        self.name = name
        self.copy_index = copy_index
        self._on_toggle = on_toggle
        self._played = played

        self.label = ft.Text(
            name, size=13, weight=ft.FontWeight.BOLD,
            color=T.JOKER_TEXT if not played else T.JOKER_TEXT_PLAYED,
        )
        super().__init__(
            width=T.JOKER_W, height=T.JOKER_H,
            bgcolor=T.CARD_PLAYED if played else T.JOKER_BG,
            border=ft.Border.all(2, color=T.JOKER_BORDER_BIG if name == "大王"
                                        else T.JOKER_BORDER_SMALL),
            border_radius=8,
            alignment=ft.alignment.Alignment.CENTER,
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
            on_click=self._handle_click,
            content=self.label,
        )

    @property
    def played(self):

        """这张牌有没有被标记成「已出」。"""
        return self._played

    def _handle_click(self, e):

        """点击这张牌：把「已出」状态取反。"""
        self._on_toggle(self)

    def update_state(self, played: bool):

        """刷新「已出」状态并重画。"""
        self._played = played
        self.bgcolor = T.CARD_PLAYED if played else T.JOKER_BG
        self.label.color = T.JOKER_TEXT_PLAYED if played else T.JOKER_TEXT


# ============================================================
# 视图构建
# ============================================================

# -*- coding: utf-8 -*-
"""AI 建议视图（0.5 规划中）。"""

from __future__ import annotations

import flet as ft

from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, page_padding


def build(_page: ft.Page, navigate: NavigateFn) -> ft.Control:
    def go_back(_e):
        navigate("/g/guandan")

    body = ft.Column(
        [
            ft.Text("🤖", size=64, text_align=ft.TextAlign.CENTER),
            ft.Container(height=12),
            ft.Text("AI 建议模式", size=20, weight=ft.FontWeight.BOLD,
                    color=T.TEXT_PRIMARY),
            ft.Container(height=8),
            ft.Text(
                "输入自己的手牌，算法会基于已记到的牌和手牌组成，"
                "给出当前最优的出牌建议。",
                size=13, color=T.TEXT_SECONDARY,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(height=16),
            ft.Container(
                content=ft.Text("0.5 上线", size=12, color=T.TEXT_INVERT,
                                weight=ft.FontWeight.BOLD),
                bgcolor=T.ACCENT,
                border_radius=10,
                padding=ft.Padding.symmetric(horizontal=12, vertical=4),
            ),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=0,
    )

    return ft.Column(
        [
            app_bar("AI 建议", on_back=go_back),
            page_padding(
                ft.Container(
                    content=body,
                    alignment=ft.alignment.Alignment.CENTER,
                    expand=True,
                )
            ),
        ],
        expand=True,
    )

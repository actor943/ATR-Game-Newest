# -*- coding: utf-8 -*-
"""AI 建议视图（0.5 规划中）：目前只是一个占位页。

设想是：把当前手牌交给 :mod:`games.guandan.ai` 分析，
在牌桌上直接给出「建议出哪手 / 怎么留牌」的提示。
功能还没做，先摆个说明页占住菜单里的位置。
"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, page_padding


def build(_page: ft.Page, navigate: NavigateFn) -> ft.Control:

    """AI 建议页（占位页）：还没实现，先摆个机器人图标说明规划中。"""
    def go_back(_e):
        navigate("/g/guandan")

    # 占位页就三样东西：一个机器人图标、一句标题、一段说明文字
    # 占位页就三样东西：一个机器人图标、一句标题、一段说明文字
    # 占位页就三样东西：一个机器人图标、一句标题、一段说明文字
    # 占位页就三样东西：一个机器人图标、一句标题、一段说明文字
    # 占位页就三样东西：一个机器人图标、一句标题、一段说明文字
    body = ft.Column(
        [
            ft.Text("🤖", size=64, text_align=ft.TextAlign.CENTER),
            ft.Container(height=12),
            ft.Text(t("guandan.advisor_heading"), size=20,
                    weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY),
            ft.Container(height=8),
            ft.Text(t("guandan.advisor_body"),
                    size=13, color=T.TEXT_SECONDARY,
                    text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(height=16),
            ft.Container(
                content=ft.Text(t("guandan.advisor_badge"), size=12,
                                color=T.TEXT_INVERT,
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
            app_bar(t("guandan.advisor"), on_back=go_back),
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

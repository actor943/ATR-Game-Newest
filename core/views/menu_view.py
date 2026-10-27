# -*- coding: utf-8 -*-
"""主菜单：两扇门（单人游戏 / 多人游戏）+ 右下角「我的」+ 右上「设置」。

0.4.7 起首页不再直接摊一堆游戏图标 —— 游戏多了会变成图标墙，很难找。
首页只保留几个「去向」：

* **单人游戏**：所有单机内容（陪 AI 玩 / 记牌器之类）；
* **多人游戏**：局域网联机，创建或搜索房间；
* **游玩记录**：所有游戏玩过的历史记录都汇在这一页（0.4.9 新增）；
* **我的**：改名字（房间里别人看到的名字）。

右下角「我的」参考多数游戏的 Profile 入口位置，顺手且不容易误触。
界面风格（默认 / 暗黑2）由 :mod:`core.ui_theme` 分发，本文件不写死任何颜色。
"""

from __future__ import annotations

import flet as ft

from core import ui_theme as ui
from core.i18n import t
from core.profile import Profile
from core.registry import NavigateFn


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    profile = Profile.load()
    nick = profile.nick or t("menu.no_nick")

    def go(path: str):
        def _handler(_e):
            navigate(path)
        return _handler

    def big_door(title: str, desc: str, icon: str, path: str,
                 tone: str) -> ft.Control:
        """首页的一扇「门」：大图标 + 标题 + 说明。"""
        return ui.card(title, desc, icon, go(path), width=300)

    header = ft.Row(
        [
            ft.Container(expand=True),
            ft.Container(
                content=ui.text(t("menu.settings"), 12, "secondary"),
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                border_radius=4, ink=True, on_click=go("/settings"),
            ),
        ],
    )

    # 右下角「我的」：改名字最顺手的位置
    me_card = ft.Container(
        content=ft.Row(
            [
                ft.Text("🛡️", size=18, color=ui.tone("primary")),
                ft.Container(width=8),
                ft.Column(
                    [
                        ui.text(t("menu.me"), 13, "", ft.FontWeight.BOLD),
                        ui.text(nick, 11, "dim"),
                    ],
                    spacing=0,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=ui.colors().surface,
        border=ft.Border.all(1, ui.colors().border),
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        ink=True, on_click=go("/profile"),
    )

    body = ft.Column(
        [
            header,
            ft.Container(height=8),
            ui.text(t("route.home"), 26, "", ft.FontWeight.BOLD),
            ui.text(t("menu.where"), 13, "secondary"),
            ft.Container(height=26),
            ft.Row(
                [
                    big_door(t("menu.single"), t("menu.single_desc"),
                             "🎮", "/single", "primary"),
                    big_door(t("menu.multiplayer"), t("menu.multiplayer_desc"),
                             "⚔️", "/multiplayer", "accent"),
                    big_door(t("menu.history"), t("menu.history_desc"),
                             "🕘", "/history", "gold"),
                ],
                wrap=True, spacing=14, run_spacing=14,
            ),
            ft.Container(expand=True),
            ft.Row(
                [
                    ft.Container(expand=True),
                    me_card,
                ],
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
            ft.Container(height=10),
            ft.Text(t("menu.footer"), size=10,
                    color=ui.colors().text_muted,
                    text_align=ft.TextAlign.CENTER),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.START,
        expand=True,
    )

    return ft.Column(
        [
            ui.bar(t("route.home")),
            ft.Container(
                padding=ft.Padding.all(16),
                content=body,
                expand=True,
            ),
        ],
        expand=True,
    )

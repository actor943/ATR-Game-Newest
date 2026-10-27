# -*- coding: utf-8 -*-
"""掼蛋子菜单。"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, menu_card
from games.guandan.views.history_view import open_history


def build(_page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """掼蛋子菜单：开始游戏 / 记牌 / 模拟 / 历史记录 / 牌型速查。

每个功能一张大卡片，点了就跳到对应的页面。
"""

    def go_play(_e):
        # 每次进对局都重建视图（丢掉路由缓存）：否则上一局（尤其是上一场
        # 联机对局）的牌桌实例会被复用，又变成「各玩各的」（0.4.8-fix）
        from core.router import Router
        if Router.current is not None:
            Router.current.invalidate("/g/guandan/play")
        navigate("/g/guandan/play")

    def go(path: str):
        def _handler(_e):
            navigate(path)
        return _handler

    def go_history(_e):
        open_history(navigate)      # 丢掉缓存，进来看的是最新记录

    body = ft.Column(
        [
            ft.Text(t("guandan.choose_mode"), size=14,
                    color=T.TEXT_SECONDARY),
            ft.Container(height=8),
            # 第一行：开始游戏 + 快速记牌
            ft.Row(
                [
                    menu_card(
                        title=t("guandan.play"),
                        description=t("guandan.play_desc"),
                        icon="▶️",
                        available=True,
                        on_click=go_play,
                        ),
                    menu_card(
                        title=t("guandan.board"),
                        description=t("guandan.board_desc"),
                        icon="📝",
                        available=True,
                        on_click=go("/g/guandan/board"),
                    ),
                ],
                wrap=True,
                spacing=12,
                run_spacing=12,
            ),
            ft.Container(height=12),
            # 第二行：牌型速查 + 全模拟
            ft.Row(
                [
                    menu_card(
                        title=t("guandan.types"),
                        description=t("guandan.types_desc"),
                        icon="📖",
                        available=True,
                        on_click=go("/g/guandan/types"),
                    ),
                    menu_card(
                        title=t("guandan.simulator"),
                        description=t("guandan.simulator_desc"),
                        icon="🎬",
                        available=True,
                        on_click=go("/g/guandan/simulator"),
                    ),
                ],
                wrap=True,
                spacing=12,
                run_spacing=12,
            ),
            ft.Container(height=12),
            # 第三行：历史记录 + AI 建议（占位）
            ft.Row(
                [
                    menu_card(
                        title=t("guandan.history"),
                        description=t("guandan.history_desc"),
                        icon="🗂️",
                        available=True,
                        on_click=go_history,
                    ),
                    menu_card(
                        title=t("guandan.advisor"),
                        description=t("guandan.advisor_desc"),
                        icon="🤖",
                        available=False,
                    ),
                ],
                wrap=True,
                spacing=12,
                run_spacing=12,
            ),
        ],
        spacing=0,
    )

    return ft.Column(
        [
            app_bar(t("game.guandan.title"), on_back=go("/")),
            ft.Container(
                padding=ft.Padding.all(T.PADDING),
                content=body,
                expand=True,
            ),
        ],
        expand=True,
    )

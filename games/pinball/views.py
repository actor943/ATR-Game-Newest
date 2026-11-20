# -*- coding: utf-8 -*-
"""弹球机视图组装：子菜单 + 对局页入口（画面/输入/循环在子模块）。"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.ui_common import app_bar, grid_cards, menu_card, page_padding

from . import views_play
from .history_view import open_history


def build_home(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """子菜单：开始游戏 / 历史记录 / 操作说明。"""
    def _play(_e):
        from core.router import Router
        if Router.current is not None:
            Router.current.invalidate("/g/pinball/play")
        navigate("/g/pinball/play")

    def _history(_e):
        open_history(navigate)

    body = grid_cards(
        page,
        [
            menu_card(
                t("pinball.start", default="开始游戏"),
                t("pinball.start_desc",
                  default="蓄力发射、双挡板救球，撞保险杠 / 斜墙得分"),
                "🕹️", on_click=_play,
            ),
            menu_card(
                t("pinball.history", default="历史记录"),
                t("pinball.history_desc",
                  default="回看每局的分数与最高分（3 球用尽自动保存）"),
                "🕘", on_click=_history,
            ),
            menu_card(
                t("pinball.howto", default="操作说明"),
                t("pinball.howto_desc",
                  default="←/→ 或 A/D 打挡板，空格蓄力发射，P 暂停，R 重开"),
                "?", available=False,
            ),
        ],
        ideal_w=300, spacing=16, max_cols=4,
    )
    return ft.Column(
        [
            app_bar(t("route.pinball", default="弹球机"),
                    on_back=lambda _e: navigate("/")),
            page_padding(body),
        ],
        expand=True,
    )


def build_play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """对局页：交给 views_play 组装（返回可重建的 Control）。"""
    return views_play.build(page, navigate)

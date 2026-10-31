# -*- coding: utf-8 -*-
"""五子棋视图组装：子菜单 + 对局页（画面/交互在 views_board）。"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.ui_common import app_bar, grid_cards, menu_card, page_padding

from . import views_board
from .history_view import open_history


def build_home(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """子菜单：本地对局 / 历史记录 / 操作说明。"""
    def _play(_e):
        # 每次进对局都重建视图：重新判断是「本地双人」还是「房间联网」，
        # 并重新接管网络回调（否则会一直用缓存里的旧实例）。
        from core.router import Router
        if Router.current is not None:
            Router.current.invalidate("/g/gomoku/play")
        navigate("/g/gomoku/play")

    def _history(_e):
        open_history(navigate)

    body = grid_cards(
        page,
        [
            menu_card(
                t("gomoku.local", default="本地对局"),
                t("gomoku.local_desc",
                  default="两人轮流点格落子；联网时按房间席位自动分黑白"),
                "▶", on_click=_play,
            ),
            menu_card(
                t("gomoku.history", default="历史记录"),
                t("gomoku.history_desc",
                  default="回看以前下过的棋局（每局结束自动保存）"),
                "🕘", on_click=_history,
            ),
            menu_card(
                t("gomoku.howto", default="规则说明"),
                t("gomoku.howto_desc",
                  default="15×15，黑先；横/竖/斜连五即胜；无禁手"),
                "?", available=False,
            ),
        ],
        ideal_w=300, spacing=16, max_cols=4,
    )
    return ft.Column(
        [
            app_bar(t("route.gomoku", default="五子棋"),
                    on_back=lambda _e: navigate("/")),
            page_padding(body),
        ],
        expand=True,
    )


def build_play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """对局页：交给 views_board 组装。"""
    return views_board.build(page, navigate)
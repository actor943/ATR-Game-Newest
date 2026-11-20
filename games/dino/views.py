# -*- coding: utf-8 -*-
"""小恐龙视图组装：子菜单 + 对局页（画面/输入/循环在子模块）。"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, grid_cards, menu_card, page_padding

from . import views_play
from .history_view import open_history


def build_home(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """子菜单：开始游戏 / 历史记录 / 操作说明。"""
    def _play(_e):
        from core.router import Router
        if Router.current is not None:
            Router.current.invalidate("/g/dino/play")
        navigate("/g/dino/play")

    def _history(_e):
        open_history(navigate)

    body = grid_cards(
        page,
        [
            menu_card(
                t("dino.start", default="开始游戏"),
                t("dino.start_desc",
                  default="原生像素素材：跳过仙人掌、蹲过飞鸟，速度越来越快，还会天黑"),
                "🦖", on_click=_play,
            ),
            menu_card(
                t("dino.history", default="历史记录"),
                t("dino.history_desc",
                  default="回看以前跑出的最好成绩（每局结束自动保存）"),
                "🕘", on_click=_history,
            ),
            menu_card(
                t("dino.howto", default="操作说明"),
                t("dino.howto_desc",
                  default="空格/↑ 跳，↓ 蹲；手机点击跳、下滑蹲；P 暂停、R 重开"),
                "?", available=False,
            ),
        ],
        ideal_w=300, spacing=16, max_cols=4,
    )
    return ft.Column(
        [
            app_bar(t("route.dino", default="小恐龙"),
                    on_back=lambda _e: navigate("/")),
            page_padding(body),
        ],
        expand=True,
    )


def build_play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """对局页：交给 views_play 组装（返回可重建的 Control）。"""
    return views_play.build(page, navigate)

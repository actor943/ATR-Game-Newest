# -*- coding: utf-8 -*-
"""台球视图组装：子菜单 + 对局页（画面 / 交互在 views_play）。"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.ui_common import app_bar, menu_card, page_padding

from . import views_play
from .history_view import open_history


def build_home(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """子菜单：开始对局 / 历史记录 / 规则说明。"""

    def _play(_e):
        # 每次进对局都重建视图：重新判断是「本地双人」还是「房间联网」，
        # 并重新接管网络回调（否则会一直用缓存里的旧实例）。
        from core.router import Router
        if Router.current is not None:
            Router.current.invalidate("/g/billiards/play")
        navigate("/g/billiards/play")

    def _history(_e):
        open_history(navigate)

    body = ft.Row(
        [
            menu_card(
                t("billiards.local", default="开始对局"),
                t("billiards.local_desc",
                  default="拖白球拉弓击球；联网时按房间席位自动分 1 / 2 号"),
                "▶", on_click=_play,
            ),
            menu_card(
                t("billiards.history", default="历史记录"),
                t("billiards.history_desc",
                  default="回看以前下过的台球局（每局结束自动保存）"),
                "🕘", on_click=_history,
            ),
            menu_card(
                t("billiards.howto", default="规则说明"),
                t("billiards.howto_desc",
                  default="中式八球简化版：先定花色，清完自己的球再打 8 号"),
                "?", available=False,
            ),
        ],
        spacing=16, wrap=True,
    )
    return ft.Column(
        [
            app_bar(t("route.billiards", default="台球"),
                    on_back=lambda _e: navigate("/")),
            page_padding(body),
        ],
        expand=True,
    )


def build_play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """对局页：交给 views_play 组装。"""
    return views_play.build(page, navigate)

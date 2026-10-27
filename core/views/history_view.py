# -*- coding: utf-8 -*-
"""主菜单的「游玩记录」页：把**所有游戏**的历史记录汇到一张表里。

数据来源与各游戏的「历史记录」页一致（:mod:`core.history` 落盘到
``logs/<game_id>/``），区别只在于：列表里混着所有游戏的记录（每条前面
标出是哪个游戏），顶部还有一条筛选条可以只看某一款游戏。
"""

from __future__ import annotations

import flet as ft

from core import history
from core import registry
from core.history_view import HistoryPage, generic_summary
from core.i18n import t
from core.registry import NavigateFn
from core.theme import T

HISTORY_PATH = "/history"


def _game_label(game_id: str) -> str:
    """游戏 id -> 显示名（跟着界面语言走）。"""
    for item in registry.menu_items():
        if item.id == game_id:
            return item.label
    return game_id


def _chip(label: str, active: bool, on_click) -> ft.Control:
    """筛选条上的一个小按钮。"""
    return ft.Container(
        content=ft.Text(label, size=12,
                        color=T.TEXT_INVERT if active else T.TEXT_PRIMARY),
        bgcolor=T.PRIMARY if active else T.SURFACE,
        border=ft.Border.all(1, T.PRIMARY if active else T.BORDER),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        ink=True,
        on_click=on_click,
    )


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """构造「全部游玩记录」页。"""
    history_page = HistoryPage(
        page, navigate,
        game_id="",
        title=t("route.history", default="游玩记录"),
        back_route="/",
        summary_fn=generic_summary,
        list_height=260,
        all_games=True,
        game_label_fn=_game_label,
    )

    filter_host = ft.Row(spacing=6, wrap=True)

    def rebuild_chips() -> None:
        items = [("", t("history.filter_all", default="全部"))]
        items += [(gid, _game_label(gid)) for gid in history.game_ids()]
        controls = []
        for gid, label in items:
            active = (history_page.filter_game == gid)

            def _on_click(_e, g=gid):
                history_page.set_filter(g)
                rebuild_chips()
                page.update()

            controls.append(_chip(label, active, _on_click))
        filter_host.controls = controls

    rebuild_chips()
    history_page.header_controls = [
        ft.Text(t("history.filter_hint", default="按游戏筛选"),
                size=11, color=T.TEXT_MUTED),
        filter_host,
        ft.Container(height=8),
    ]
    return history_page.build()

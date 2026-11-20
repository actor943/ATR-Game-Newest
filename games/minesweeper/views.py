# -*- coding: utf-8 -*-
"""扫雷视图组装：子菜单（三档难度）+ 对局页入口。

子菜单点难度卡进对局时，会把难度暂存在模块级 ``_PENDING_LEVEL``：
路由是精确匹配的字符串，没法带 ``?level=...`` 参数；跳转前先
``invalidate`` 掉对局页缓存，保证每次开局都按新难度重建。
"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.ui_common import app_bar, grid_cards, menu_card, page_padding

from . import views_board
from .history_view import open_history

# 子菜单 → 对局页的「一次性」难度参数
_PENDING_LEVEL = "easy"


def _start(navigate: NavigateFn, level: str) -> None:
    """记下难度、丢掉旧对局缓存，再进对局页。"""
    global _PENDING_LEVEL
    _PENDING_LEVEL = level
    from core.router import Router
    if Router.current is not None:
        Router.current.invalidate("/g/minesweeper/play")
    navigate("/g/minesweeper/play")


def take_level() -> str:
    """对局页取走难度参数（取完恢复默认初级）。"""
    global _PENDING_LEVEL
    level, _PENDING_LEVEL = _PENDING_LEVEL, "easy"
    return level


def build_home(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """子菜单：初级 / 中级 / 高级 / 历史记录 / 操作说明。"""
    def _history(_e):
        open_history(navigate)

    cards = []
    for level, key, icon, fallback in (
        ("easy", "minesweeper.easy", "🌱", "初级 · 9×9 / 10 雷"),
        ("medium", "minesweeper.medium", "🌲", "中级 · 16×16 / 40 雷"),
        ("hard", "minesweeper.hard", "🔥", "高级 · 16×30 / 99 雷"),
    ):
        cards.append(menu_card(
            t(key, default=fallback.split(" · ")[0]),
            t(key + "_desc", default=fallback),
            icon, on_click=lambda _e, lv=level: _start(navigate, lv),
        ))
    cards.append(menu_card(
        t("minesweeper.history", default="历史记录"),
        t("minesweeper.history_desc",
          default="回看每局的成绩与用时（胜 / 负自动保存）"),
        "🕘", on_click=_history,
    ))
    cards.append(menu_card(
        t("minesweeper.howto", default="操作说明"),
        t("minesweeper.howto_desc",
          default="左键翻开、右键插旗；手机长按或开「插旗模式」；R 重开"),
        "?", available=False,
    ))
    body = grid_cards(page, cards, ideal_w=300, spacing=16, max_cols=4)
    return ft.Column(
        [
            app_bar(t("route.minesweeper", default="扫雷"),
                    on_back=lambda _e: navigate("/")),
            page_padding(body),
        ],
        expand=True,
    )


def build_play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """对局页：交给 views_board 组装（返回可重建的 Control）。"""
    return views_board.build(page, navigate, take_level())

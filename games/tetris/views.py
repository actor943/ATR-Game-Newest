# -*- coding: utf-8 -*-
"""俄罗斯方块视图组装：子菜单 + 对局页（画面/输入/循环在子模块）。"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, menu_card, page_padding

from . import views_play
from .history_view import open_history


def build_home(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """子菜单：开始游戏 / 历史记录 / 操作说明。"""
    def _play(_e):
        # 每次都重建对局页：上一局退出时重力循环已经被取消，
        # 用路由缓存里的旧实例会「进得去但不再下落」。
        from core.router import Router
        if Router.current is not None:
            Router.current.invalidate("/g/tetris/play")
        navigate("/g/tetris/play")

    def _history(_e):
        open_history(navigate)

    body = ft.Row(
        [
            menu_card(
                t("tetris.start", default="开始游戏"),
                t("tetris.start_desc",
                  default="单人无限模式：消行计分，等级越高越快"),
                "▶", on_click=_play,
            ),
            menu_card(
                t("tetris.history", default="历史记录"),
                t("tetris.history_desc",
                  default="回看以前的成绩（每局结束自动保存）"),
                "🕘", on_click=_history,
            ),
            menu_card(
                t("tetris.howto", default="操作说明"),
                t("tetris.howto_desc",
                  default="← → 移动 / ↑ 旋转 / ↓ 软降 / 空格硬降 / C 暂存"),
                "?", available=False,
            ),
        ],
        spacing=16, wrap=True,
    )
    return ft.Column(
        [
            app_bar(t("route.tetris", default="俄罗斯方块"),
                    on_back=lambda _e: navigate("/")),
            page_padding(body),
        ],
        expand=True,
    )


def build_play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """对局页：交给 views_play 组装（返回可重建的 Control）。"""
    return views_play.build(page, navigate)
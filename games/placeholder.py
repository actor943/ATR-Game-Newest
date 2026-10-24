# -*- coding: utf-8 -*-
"""占位视图：尚未实现的子游戏共用的「敬请期待」页面。

主菜单里 ``available=False`` 的游戏（Splendor / Chess / Chinese Chess）
点击后会跳到各自的占位路由，由本模块统一渲染。
"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, page_padding, status_pill


def build_stub(page: ft.Page, navigate: NavigateFn, title: str,
               note: str) -> ft.Control:
    """构建占位视图：顶栏 + 标题 + 说明 + 返回按钮。

    Args:
        page: 当前 Page（占位页暂不直接操作，预留）。
        navigate: 路由钩子，「返回」后回主菜单。
        title: 游戏名，同时显示在顶栏与正文标题。
        note: 一句话说明这里将来会放什么。
    """

    def _go_home(_e):
        navigate("/")

    body = ft.Column(
        [
            ft.Row(
                [
                    ft.Text(title, size=22, weight=ft.FontWeight.BOLD,
                            color=T.TEXT_PRIMARY),
                    ft.Container(width=10),
                    status_pill(t("common.coming_soon"), T.TEXT_MUTED),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(height=12),
            ft.Text(note, size=14, color=T.TEXT_SECONDARY),
            ft.Container(height=24),
            ft.Button(
                content=ft.Text(t("common.back")),
                icon=ft.Icons.ARROW_BACK,
                height=40,
                bgcolor=T.PRIMARY,
                color=T.TEXT_INVERT,
                on_click=_go_home,
            ),
        ],
        spacing=0,
    )

    return ft.Column(
        [
            app_bar(title, on_back=_go_home),
            page_padding(body),
        ],
        expand=True,
    )

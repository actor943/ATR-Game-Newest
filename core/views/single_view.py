# -*- coding: utf-8 -*-
"""单人游戏：所有已注册的游戏都收在这一页里（陪 AI 玩 / 单机工具）。

0.4.7 起主菜单不再把游戏图标直接摊在首页 —— 游戏变多了首页也不会变成图标墙。
界面风格由 :mod:`core.ui_theme` 分发（默认材料风 / 暗黑2 石砖风 / 社区包）。
"""

from __future__ import annotations

import flet as ft

from core import registry
from core import ui_theme as ui
from core.i18n import t
from core.registry import NavigateFn
from core.ui_common import grid_cards


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    items = registry.menu_items()

    def go(path: str):
        def _handler(_e):
            navigate(path)
        return _handler

    cards: list[ft.Control] = []
    for item in items:
        # .label / .desc 会按当前语言翻译（游戏插件登记了 title_key/desc_key）
        cards.append(
            ui.card(item.label, item.desc, item.icon,
                    go(item.home_path), available=item.available)
        )
    cards.append(
        ui.card(t("single.more"), t("single.more_desc"),
                "🎴", available=False)
    )

    # 铺满宽度：宽屏多列、窄屏自动退化为单列（不再挤在左边一列）
    grid = grid_cards(page, cards, ideal_w=300, spacing=12, max_cols=4)

    body = ft.Column(
        [
            ui.text(t("single.title"), 22, "", ft.FontWeight.BOLD),
            ft.Container(height=4),
            ui.text(t("single.subtitle"), 13, "secondary"),
            ft.Container(height=20),
            grid,
            ft.Container(expand=True),
        ],
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.START,
    )

    return ui.page(t("single.title"), body, on_back=lambda _e: navigate("/"))

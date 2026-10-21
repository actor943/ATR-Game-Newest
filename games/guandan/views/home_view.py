# -*- coding: utf-8 -*-
"""掼蛋子菜单。"""

from __future__ import annotations

import flet as ft

from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, menu_card
from games.guandan.views.history_view import open_history


def build(_page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """掼蛋子菜单：开始游戏 / 记牌 / 模拟 / 历史记录 / 牌型速查。"""

    def go(path: str):
        def _handler(_e):
            navigate(path)
        return _handler

    def go_history(_e):
        open_history(navigate)      # 丢掉缓存，进来看的是最新记录

    body = ft.Column(
        [
            ft.Text("选择一个模式", size=14, color=T.TEXT_SECONDARY),
            ft.Container(height=8),
            # 第一行：开始游戏 + 快速记牌
            ft.Row(
                [
                    menu_card(
                        title="开始游戏",
                        description="用上次的房间与座位配置直接开局：单人 / 三人机。",
                        icon="▶️",
                        available=True,
                        on_click=go("/g/guandan/play"),
                    ),
                    menu_card(
                        title="快速记牌",
                        description="记录出牌，按四家视角计算炸弹概率。",
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
                        title="牌型速查",
                        description="常见牌型与大小关系速记。",
                        icon="📖",
                        available=True,
                        on_click=go("/g/guandan/types"),
                    ),
                    menu_card(
                        title="全模拟",
                        description="AI 自动互玩整场，图形化观战（真牌图）。",
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
                        title="历史记录",
                        description="查看往期出牌记录（每整场结束自动保存）。",
                        icon="🗂️",
                        available=True,
                        on_click=go_history,
                    ),
                    menu_card(
                        title="AI 建议",
                        description="输入自己手牌，让算法给出推荐出牌。",
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
            app_bar("掼蛋", on_back=go("/")),
            ft.Container(
                padding=ft.Padding.all(T.PADDING),
                content=body,
                expand=True,
            ),
        ],
        expand=True,
    )

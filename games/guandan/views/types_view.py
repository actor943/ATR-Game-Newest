# -*- coding: utf-8 -*-
"""牌型速查视图。"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, page_padding


@dataclass(frozen=True)
class CardType:
    name: str        # 牌型名
    example: str     # 例：A♠ A♥ A♣ A♦
    desc: str        # 简短说明
    rank: int        # 同级别内的比较优先级（数字越大越大）


CARD_TYPES: list[CardType] = [
    CardType("单张", "A♠", "任意一张牌", 0),
    CardType("对子", "A♠ A♥", "两张同点数", 1),
    CardType("三张", "A♠ A♥ A♣", "三张同点数", 2),
    CardType("三带二", "A♠ A♥ A♣ + 8♦ 9♥", "三张同点数 + 一对", 3),
    CardType("顺子", "3-4-5-6-7", "5 张或更多连续点数（2 不参与，级牌可作任意牌）", 4),
    CardType("同花顺", "♠ 3-4-5-6-7", "同一花色的顺子（掼蛋中最大的普通牌型）", 5),
    CardType("钢板", "A-A-A + K-K-K", "两组连续三张", 6),
    CardType("炸弹（4 张）", "A×4", "4 张同点数 > 上面所有牌型", 7),
    CardType("炸弹（5 张）", "A×5", "5 张同点数 > 4 张炸弹", 8),
    CardType("炸弹（6 张）", "A×6", "6 张同点数 > 5 张炸弹", 9),
    CardType("炸弹（7+ 张）", "A×7 …", "越多越大", 10),
    CardType("天王炸", "4 张王", "两副牌里的所有王（4 张），最大牌型", 11),
]


def _type_row(t: CardType) -> ft.Container:
    rank_colors = {
        7: T.ACCENT, 8: T.ACCENT, 9: T.ACCENT, 10: T.ACCENT, 11: T.DANGER,
    }
    name_color = rank_colors.get(t.rank, T.TEXT_PRIMARY)

    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        border=ft.Border.only(
            bottom=ft.BorderSide(1, T.DIVIDER)),
        content=ft.Row(
            [
                ft.Container(
                    content=ft.Text(t.name, size=14, weight=ft.FontWeight.BOLD,
                                    color=name_color),
                    width=120,
                ),
                ft.Container(
                    content=ft.Text(t.example, size=12, color=T.TEXT_SECONDARY),
                    width=140,
                ),
                ft.Container(
                    content=ft.Text(t.desc, size=12, color=T.TEXT_SECONDARY),
                    expand=True,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def build(_page: ft.Page, navigate: NavigateFn) -> ft.Control:
    def go_back(_e):
        navigate("/g/guandan")

    body = ft.Column(
        [
            ft.Text(
                "以下为掼蛋中常见牌型。炸弹及天王炸在比较时无视牌型，"
                "只看张数；同张数时再比点数（2 最小，A 最大）。",
                size=12, color=T.TEXT_SECONDARY,
            ),
            ft.Container(height=12),
            ft.Container(
                border=ft.Border.all(1, T.BORDER),
                border_radius=8,
                content=ft.Column(
                    [_type_row(t) for t in CARD_TYPES], spacing=0,
                ),
            ),
            ft.Container(height=12),
            ft.Text(
                "提示：本工具目前仅计算 4 张及以上同点数的炸弹（含赖子），"
                "同花顺与其它牌型留到 0.5 引入。",
                size=11, color=T.TEXT_MUTED, italic=True,
            ),
        ],
        spacing=0,
    )

    return ft.Column(
        [
            app_bar("牌型速查", on_back=go_back),
            page_padding(ft.Container(content=body, expand=True)),
        ],
        expand=True,
    )

# -*- coding: utf-8 -*-
"""掼蛋牌面图片资源管理。

把内部 :class:`~games.guandan.cards.Card` 映射到顶层 ``assets/cards/`` 下的
PNG 文件。文件名采用「英文 + 小写 + 空格」的常见风格：

* 普通牌：``"{rank} of {suit}.png"``，例如 ``"10 of hearts.png"``、``"ace of spades.png"``
* 大小王：``"red joker.png"``（大王）、``"black joker.png"``（小王）

路径约定（重要）：返回的是**相对于 assets 目录根**的路径，不带 ``assets/``
前缀 —— 这是 Flet 的资源寻址方式：开发时由 ``ft.run(assets_dir=...)`` 指定
assets 根目录，``flet build`` 打包后同样按这个规则解析（见 flet 文档
"Assets"）。早期版本返回模块旁的绝对路径，打包后会找不到图，已改掉。
"""

from __future__ import annotations

import flet as ft

from .cards import Card

# assets 目录根下的子目录（打包内外一致）
_CARDS_SUBDIR = "cards"

# 内部花色 → 文件名用的英文花色
_SUIT_TO_NAME = {
    "♠": "spades",
    "♥": "hearts",
    "♣": "clubs",
    "♦": "diamonds",
}
# 内部 rank → 文件名用的英文 rank
_RANK_TO_NAME = {
    "J": "jack",
    "Q": "queen",
    "K": "king",
    "A": "ace",
}
# 大小王对应文件名
_JOKER_FILE = {
    "大王": "red joker.png",     # 大王 = 红王（最大）
    "小王": "black joker.png",   # 小王 = 黑王
}


def card_file_name(card: Card) -> str:
    """牌对应的文件名（不含目录）。"""
    if card.is_joker:
        return _JOKER_FILE[card.rank]
    return (f"{_RANK_TO_NAME.get(card.rank, card.rank)} of "
            f"{_SUIT_TO_NAME[card.suit]}.png")


def card_image_src(card: Card) -> str:
    """返回 ``Card`` 对应的图片**资源路径**（相对 assets 根目录）。"""
    return f"{_CARDS_SUBDIR}/{card_file_name(card)}"


def make_card_image(card: Card, *, width: int = 36, height: int = 50,
                    wild: bool = False, opacity: float = 1.0) -> ft.Control:
    """生成一张牌的可视控件。野牌（逢人配）外加 2px 红框。"""
    img = ft.Image(
        src=card_image_src(card),
        width=width,
        height=height,
        fit=ft.BoxFit.CONTAIN,
        tooltip=str(card),
    )
    if not wild and opacity >= 1.0:
        return img
    return ft.Container(
        content=img,
        border=ft.Border.all(2, "#FF4D4F") if wild else None,
        border_radius=4,
        opacity=opacity,
    )


def card_back_image(*, width: int = 36, height: int = 50) -> ft.Image:
    """没有专属牌背资源时，用大王图片当通用牌背占位。"""
    return ft.Image(
        src=card_image_src(Card("大王", "")),
        width=width,
        height=height,
        fit=ft.BoxFit.CONTAIN,
        opacity=0.35,
    )

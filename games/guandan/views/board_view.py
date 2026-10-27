# -*- coding: utf-8 -*-
"""掼蛋快速记牌视图。

由 0.3 整段 main() 函数迁移而来，逻辑等价：

* 先选择出牌人（我 / 下家 / 对家 / 上家）
* 点击牌面记录该家出的牌，再次点击可撤销
* 后台按四家视角计算三家对手的炸弹概率

模块划分
--------
* :mod:`games.guandan.views.board_widgets` —— 牌面按钮组件（普通牌 / 王）
* 本文件 —— 页面本身（选人、选级牌、点牌、算概率）
"""

from __future__ import annotations

import flet as ft

from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar

from ..analyzer import (
    JOKERS,
    PLAYER_NAMES,
    RANKS,
    SUITS,
    TOTAL_CARDS,
    TOTAL_PER_RANK,
    GdAnalyzer,
)
from .board_widgets import SUIT_COLORS, SUIT_NAMES, CardButton, JokerButton

def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """快速记牌视图构建器。每次调用返回一个新的闭包，状态随闭包保留。"""

    analyzer = GdAnalyzer()
    current_player = 0

    card_buttons: dict[tuple[str, str, int], CardButton] = {}
    joker_buttons: list[JokerButton] = []
    level_btns: dict[str, ft.Container] = {}
    level_btn_texts: dict[str, ft.Text] = {}
    rem_labels: dict[str, ft.Text] = {}
    player_chip_boxes: list[ft.Container] = []
    player_chip_texts: list[ft.Text] = []

    # ======== 顶部状态 ========
    remaining_text = ft.Text(
        f"剩余: {TOTAL_CARDS} / {TOTAL_CARDS} 张",
        size=20, weight=ft.FontWeight.BOLD, color=T.PRIMARY)

    level_info_text = ft.Text(
        "级牌: 未设置",
        size=14, weight=ft.FontWeight.BOLD, color=T.LEVEL_INFO)

    bomb_text = ft.Text("", size=12, color=T.TEXT_PRIMARY)
    threat_text = ft.Text("", size=12, color=T.TEXT_SECONDARY, italic=True)

    # ---------- 页面状态与刷新 ----------
    def refresh_status():

        """刷新顶部状态文字（当前玩家 / 级牌 / 剩余张数）。"""
        rem = analyzer.remaining_cards()
        remaining_text.value = f"剩余: {rem} / {TOTAL_CARDS} 张"
        remaining_text.color = (
            T.DANGER if rem < 27 else
            T.WARNING if rem < 54 else
            T.SUCCESS
        )

        if analyzer.level_rank:
            level_info_text.value = (
                f"级牌: {analyzer.level_rank} | "
                f"赖子 ♥{analyzer.level_rank} 剩余: {analyzer.wild_remaining()} 张")
        else:
            level_info_text.value = "级牌: 未设置"

        for idx, (box, text) in enumerate(zip(player_chip_boxes, player_chip_texts)):
            text.value = f"{PLAYER_NAMES[idx]} {analyzer.hand_size(idx)}"
            is_active = (idx == current_player)
            box.bgcolor = T.PRIMARY if is_active else T.SURFACE_ALT
            text.color = T.TEXT_INVERT if is_active else T.TEXT_SECONDARY

        summary = analyzer.bomb_summary()
        if summary:
            bomb_text.value = "炸弹威胁(三家至少一家): " + "  |  ".join(
                f"{label} {prob:.0%}" for label, prob in list(summary.items())[:8])
            top_label = next(iter(summary))
            detail = "  ".join(
                f"{PLAYER_NAMES[p]} {prob:.0%}"
                for p, prob in analyzer.bomb_detail(top_label))
            threat_text.value = f"最危险: {top_label} → {detail}"
        else:
            bomb_text.value = ""
            threat_text.value = ""

        page.update()

    def refresh_level_ui():

        """刷新级牌选择区（可选 2~A）。"""
        level = analyzer.level_rank
        for rank, btn in level_btns.items():
            is_active = (level == rank)
            btn.bgcolor = T.LEVEL_ACTIVE_BG if is_active else T.SURFACE_ALT
            text = level_btn_texts[rank]
            text.color = T.LEVEL_ACTIVE_TEXT if is_active else T.TEXT_MUTED
            text.value = "✓级" if is_active else "设级"
            text.size = 9 if is_active else 8
        for (rank, suit, _ci), btn in card_buttons.items():
            btn.set_wild(rank == level and suit == "♥")
        refresh_status()

    def refresh_all():

        """状态 + 级牌区一起刷新。"""
        for (rank, suit, ci), btn in card_buttons.items():
            btn.update_state(analyzer.is_played(rank, suit, ci))
        for btn in joker_buttons:
            btn.update_state(analyzer.is_joker_played(btn.name, btn.copy_index))
        for rank, label in rem_labels.items():
            label.value = f"×{analyzer.remaining_by_rank(rank)}"
        refresh_level_ui()

    def select_player(idx: int):

        """切换当前查看的玩家。"""
        nonlocal current_player
        current_player = idx
        refresh_status()

    # ======== 出牌人选择 ========
    player_selector = ft.Row(
        spacing=6, wrap=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    player_selector.controls.append(
        ft.Text("出牌人:", size=14, weight=ft.FontWeight.BOLD,
                color=T.TEXT_PRIMARY))
    for idx in range(len(PLAYER_NAMES)):
        text = ft.Text(f"{PLAYER_NAMES[idx]} 27", size=12,
                       weight=ft.FontWeight.BOLD,
                       color=T.TEXT_SECONDARY)
        box = ft.Container(
            width=96, height=34,
            bgcolor=T.SURFACE_ALT,
            border_radius=6,
            alignment=ft.alignment.Alignment.CENTER,
            on_click=lambda e, i=idx: select_player(i),
            content=text,
        )
        player_chip_boxes.append(box)
        player_chip_texts.append(text)
        player_selector.controls.append(box)
    player_selector.controls.append(
        ft.Text("先选人再点牌；再点一次可撤销",
                size=11, color=T.TEXT_MUTED))

    # ======== 级牌 ========
    def on_set_level(rank: str):

        """设置当前级牌点数。"""
        if analyzer.level_rank == rank:
            analyzer.set_level_rank(None)
        else:
            analyzer.set_level_rank(rank)
        refresh_level_ui()

    # ======== 顶部操作 ========
    def on_undo(_e):

        """撤销上一步标记。"""
        analyzer.undo_last()
        refresh_all()

    def on_reset(_e):

        """清空当前玩家的全部标记。"""
        analyzer.reset()
        refresh_all()

    top_bar = ft.Row([
        ft.Column([
            ft.Row([remaining_text, level_info_text], spacing=16),
        ], spacing=2),
        ft.Row([
            ft.Button(content=ft.Text("撤销"), icon=ft.Icons.UNDO,
                      on_click=on_undo, height=36),
            ft.Button(content=ft.Text("重置"), icon=ft.Icons.REFRESH,
                      on_click=on_reset, height=36,
                      bgcolor=T.DANGER_SOFT, color=T.DANGER),
        ], spacing=8),
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True)

    # ======== 卡牌区 ========
    card_grid = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)

    def on_card_toggle(btn: CardButton):

        """普通牌被点了 → 转发给内部处理。"""
        analyzer.toggle_card(current_player, btn.rank, btn.suit, btn.copy_index)
        refresh_all()

    def on_joker_toggle(btn: JokerButton):

        """王牌被点了 → 转发给内部处理。"""
        analyzer.toggle_joker(current_player, btn.name, btn.copy_index)
        refresh_all()

    # ---------- 牌面排布 ----------
    def build_cards():

        """按当前级牌把 108 张牌排好并生成按钮。"""
        card_grid.controls.clear()
        card_buttons.clear()
        joker_buttons.clear()

        # 花色表头
        suit_header_row = ft.Row([
            ft.Container(width=32),
            ft.Container(width=28),
        ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        for i, suit in enumerate(SUITS):
            color = SUIT_COLORS[suit]
            header_width = 80 if i == len(SUITS) - 1 else 86
            suit_header = ft.Container(
                width=header_width,
                alignment=ft.alignment.Alignment.CENTER,
                content=ft.Text(
                    f"{suit} {SUIT_NAMES[suit]}",
                    size=12, color=color, weight=ft.FontWeight.BOLD,
                ),
            )
            suit_header_row.controls.append(suit_header)
        suit_header_row.controls.append(ft.Container(width=36))
        card_grid.controls.append(suit_header_row)
        card_grid.controls.append(ft.Divider(height=1, color=T.DIVIDER))

        for rank in RANKS:
            is_active = (analyzer.level_rank == rank)
            level_text = ft.Text(
                "✓级" if is_active else "设级",
                size=9 if is_active else 8,
                weight=ft.FontWeight.BOLD,
                color=T.LEVEL_ACTIVE_TEXT if is_active else T.TEXT_MUTED,
            )
            level_btn = ft.Container(
                width=32, height=24,
                bgcolor=T.LEVEL_ACTIVE_BG if is_active else T.SURFACE_ALT,
                border_radius=4,
                alignment=ft.alignment.Alignment(0, 0),
                on_click=lambda e, r=rank: on_set_level(r),
                content=level_text,
            )
            level_btns[rank] = level_btn
            level_btn_texts[rank] = level_text

            rank_label = ft.Container(
                content=ft.Text(rank, size=14, weight=ft.FontWeight.BOLD,
                                color=T.TEXT_PRIMARY),
                width=28, alignment=ft.alignment.Alignment.CENTER_RIGHT,
            )

            suit_cards: list[ft.Control] = []
            is_wild_suit = (rank == analyzer.level_rank)
            for suit in SUITS:
                for ci in range(2):
                    btn = CardButton(rank, suit, ci,
                                     on_toggle=on_card_toggle,
                                     is_wild=(is_wild_suit and suit == "♥"))
                    card_buttons[(rank, suit, ci)] = btn
                    suit_cards.append(btn)
                suit_cards.append(ft.Container(width=6))
            if suit_cards:
                suit_cards.pop()

            rem_label = ft.Text(
                f"×{TOTAL_PER_RANK}", size=13,
                color=T.TEXT_SECONDARY, width=30,
                text_align=ft.TextAlign.CENTER,
            )
            rem_labels[rank] = rem_label

            row = ft.Row(
                [level_btn, rank_label] + suit_cards + [rem_label],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            card_grid.controls.append(row)

        card_grid.controls.append(ft.Divider(height=1, color=T.DIVIDER))

        # 王牌
        joker_row = ft.Row([
            ft.Text("王牌", size=14, weight=ft.FontWeight.BOLD,
                    color=T.TEXT_PRIMARY),
        ], spacing=6)
        for name in JOKERS:
            for ci in range(2):
                btn = JokerButton(name, ci, on_toggle=on_joker_toggle)
                joker_buttons.append(btn)
                joker_row.controls.append(btn)
            joker_row.controls.append(ft.Container(width=10))
        if joker_row.controls and isinstance(joker_row.controls[-1], ft.Container):
            joker_row.controls.pop()
        card_grid.controls.append(joker_row)

        # 图例
        card_grid.controls.append(ft.Divider(height=1, color=T.DIVIDER))
        legend = ft.Column([
            ft.Row([
                ft.Text("点击", size=12, color=T.TEXT_MUTED),
                ft.Container(width=20, height=20, bgcolor=T.CARD_BG,
                             border=ft.Border.all(1, color=T.CARD_BORDER),
                             border_radius=4, content=ft.Text("A", size=10)),
                ft.Text("=未出", size=12, color=T.TEXT_MUTED),
                ft.Container(width=8),
                ft.Container(width=20, height=20, bgcolor=T.CARD_PLAYED,
                             border=ft.Border.all(1, color=T.CARD_BORDER),
                             border_radius=4,
                             content=ft.Text("♥", size=10, color="#E53935")),
                ft.Text("=已出", size=12, color=T.TEXT_MUTED),
                ft.Container(width=8),
                ft.Container(width=20, height=20, bgcolor=T.WILD_BG,
                             border=ft.Border.all(2, color=T.WILD_BORDER),
                             border_radius=4,
                             content=ft.Text("♥A", size=8, color="#E53935")),
                ft.Text("=红桃级牌(赖子)", size=12, color=T.TEXT_MUTED),
                ft.Container(width=8),
                ft.Text("再次点击可撤销", size=12, color=T.TEXT_MUTED),
            ], spacing=4),
        ])
        card_grid.controls.append(legend)

    shortcuts = ft.Text(
        "提示: 先选出牌人 → 点击牌面记录该家出的牌（含自己）| "
        "设级按钮设置级牌 | 红桃级牌为赖子可配任意炸弹 | 撤销/重置",
        size=11, color=T.TEXT_MUTED,
        text_align=ft.TextAlign.CENTER,
    )

    build_cards()

    inner = ft.Column(
        [
            top_bar,
            player_selector,
            bomb_text,
            threat_text,
            ft.Divider(height=1),
            card_grid,
            shortcuts,
        ],
        spacing=8, expand=True,
    )

    def go_back(_e):

        """返回掼蛋子菜单。"""
        navigate("/g/guandan")

    return ft.Column(
        [
            app_bar("快速记牌", on_back=go_back),
            ft.Container(
                padding=ft.Padding.all(T.PADDING),
                content=inner,
                expand=True,
            ),
        ],
        expand=True,
    )

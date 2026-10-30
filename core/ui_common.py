# -*- coding: utf-8 -*-
"""通用 UI 组件。

0.4.7 起这里的组件**转发到界面包**（:mod:`core.ui_theme`）：
默认材料风 / 暗黑2 石砖风 / 以后的社区包，设置页切换后全应用换皮。
签名保持不变，老调用点一行都不用改。
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from . import ui_theme as _ui
from .theme import T


def menu_card(
    title: str,
    description: str,
    icon: str,
    *,
    available: bool = True,
    on_click=None,
    width: Optional[int] = None,
) -> ft.Container:
    """主菜单与子菜单上的大卡片。

    0.4.10：默认 ``expand=True``（不再写死 260px），放在 ``Row(wrap=True)``
    里时会自动平分、铺满整行 —— 解决宽屏「卡片全堆在左边一列、右边一片空白」。
    仍可用 ``width=`` 强制固定宽度（如需要窄卡片时）。
    """
    bg = T.SURFACE
    border = T.BORDER
    title_color = T.TEXT_PRIMARY if available else T.TEXT_MUTED
    desc_color = T.TEXT_SECONDARY if available else T.TEXT_MUTED
    icon_color = T.PRIMARY if available else T.TEXT_MUTED
    badge: Optional[ft.Container] = None
    if not available:
        badge = ft.Container(
            content=ft.Text("敬请期待", size=10, color=T.TEXT_INVERT,
                            weight=ft.FontWeight.BOLD),
            bgcolor=T.TEXT_MUTED,
            border_radius=4,
            padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        )

    def _on_click(_e):
        if available and on_click is not None:
            on_click(_e)

    return ft.Container(
        width=width,
        expand=(width is None),
        padding=ft.Padding.all(16),
        bgcolor=bg,
        border=ft.Border.all(1, border),
        border_radius=10,
        ink=True if available else False,
        on_click=_on_click,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(icon, size=28, color=icon_color),
                        ft.Container(expand=True),
                        *( [badge] if badge is not None else [] ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=10),
                ft.Text(title, size=16, weight=ft.FontWeight.BOLD,
                        color=title_color),
                ft.Container(height=4),
                ft.Text(description, size=12, color=desc_color),
            ],
            spacing=0,
        ),
    )
def app_bar(
    title: str,
    *,
    on_back: Optional[Callable] = None,
    actions: Optional[list[ft.Control]] = None,
) -> ft.Container:
    """通用顶栏：左侧返回（可选）+ 中间标题 + 右侧动作区。

    外观由当前界面包决定（默认=平面描边，石砖包=暗金火把线）。
    """
    return _ui.bar(title, on_back=on_back, actions=actions)





def status_pill(text: str, color: Optional[str] = None) -> ft.Container:
    # color 不能在默认参数里取 T.PRIMARY：默认值在导入时求值，切换主题后不会变
    color = color or T.PRIMARY
    return ft.Container(
        content=ft.Text(text, size=11, color=T.TEXT_INVERT, weight=ft.FontWeight.BOLD),
        bgcolor=color,
        border_radius=10,
        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
    )


def divider(height: int = 1, color: Optional[str] = None) -> ft.Container:
    color = color or T.DIVIDER
    return ft.Container(height=height, bgcolor=color)


def page_padding(content: ft.Control) -> ft.Container:
    return ft.Container(
        padding=ft.Padding.all(T.PADDING),
        content=content,
    )


# ============================================================
# 窄屏适配（手机竖屏 / 旋转后手牌不能被切掉）
# ============================================================

def page_width(page: ft.Page, fallback: float = 420.0) -> float:
    """当前页面宽度：优先 ``page.width``，退到窗口宽度，再退到 ``fallback``。

    手机端屏幕只有 360～430 逻辑像素，手牌一排 27 张必然放不下；
    所有按宽度自适应的地方都从这里取宽度。
    """
    try:
        w = getattr(page, "width", None)
        if w:
            return float(w)
        w = getattr(getattr(page, "window", None), "width", None)
        if w:
            return float(w)
    except Exception:  # noqa: BLE001 — 取不到就按窄屏兜底
        pass
    return fallback


def fit_card_row(
    avail: float,
    count: int,
    card_w: int,
    card_h: int,
    spacing: int,
    *,
    min_step: int = 24,
    max_rows: int = 3,
    min_card_w: int = 26,
) -> tuple[int, int, int, int, int]:
    """把 ``count`` 张牌排进 ``avail`` 宽的区域，返回牌面与排布参数。

    返回 ``(牌宽, 牌高, 负间距, 每行张数, 行数)``，直接喂给
    ``ft.Row(..., spacing=负间距, wrap=True, run_spacing=4)`` 即可。

    两级收缩，保证**一张牌都不会被挤出屏幕**：

    1. 先按 ``spacing`` 加大重叠（每张至少露出 ``min_step`` 像素才认得出）；
    2. 重叠到极限仍超过 ``max_rows`` 行，就整体缩小牌面（等比缩，
       下限 ``min_card_w``），宽屏则完全用原始尺寸，观感不变。
    """
    count = max(int(count), 0)
    if count == 0:
        return card_w, card_h, spacing, 0, 0

    w = int(card_w)
    while True:
        step = w + int(spacing)
        if step < min_step:
            step = min(min_step, w)     # 至少露 min_step，但不能超过整张牌宽
        per_row = 1 if avail <= w else int((avail - w) // max(step, 1)) + 1
        rows = -(-count // max(per_row, 1))     # ceil
        if rows <= max_rows or w <= min_card_w:
            break
        w -= 2
        if w < min_card_w:
            w = min_card_w
    h = max(24, round(w * card_h / card_w))
    return w, h, int(step - w), per_row, rows


def grid_cards(
    page: ft.Page,
    cards: list[ft.Control],
    *,
    ideal_w: int = 320,
    spacing: int = 14,
    max_cols: int = 4,
    min_w: int = 220,
) -> ft.Control:
    """把一组卡片**铺满可用宽度**，而不是挤在左边一列。

    0.4.10 之前：菜单 / 子菜单的卡片用固定宽度 ``Row(wrap=True)``，
    宽屏上三张 300px 卡片全堆在左边，右边一大片空白。

    现在按页面宽度算出能放几列，每张卡片等宽铺开到屏幕左右边缘
    （列数 = ⌊(可用宽+间距) / (理想宽+间距)⌋，封顶 ``max_cols``）；
    卡片不足一行时左对齐，多出的行各自铺满。窄屏自动退化为单列。

    注意：``cards`` 里每个控件会被就地改掉 ``width``（``ui.card`` 默认 300），
    其内部文字列带 ``expand``，会跟着撑开。
    """
    avail = page_width(page) - 2 * T.PADDING
    if avail <= 0:
        avail = 800                       # 取不到宽度时的兜底（约等于窄桌面）
    cols = max(1, min(max_cols,
                     int((avail + spacing) // (ideal_w + spacing))))
    cw = (avail - (cols - 1) * spacing) / cols
    cw = max(min_w, cw)
    rows: list[ft.Control] = []
    for i in range(0, len(cards), cols):
        chunk = cards[i:i + cols]
        for c in chunk:
            c.width = int(cw)
        rows.append(ft.Row(list(chunk), spacing=spacing))
    return ft.Column(rows, spacing=spacing)

# -*- coding: utf-8 -*-
"""通用 UI 组件。

0.4.7 起这里的组件**转发到界面包**（:mod:`core.ui_theme`）：
默认材料风 / 暗黑2 石砖风 / 以后的社区包，设置页切换后全应用换皮。
签名保持不变，老调用点一行都不用改。
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from . import responsive
from . import ui_theme as _ui
from .theme import T


def menu_card(
    title: str,
    description: str,
    icon: str,
    *,
    available: bool = True,
    on_click=None,
    width: int = 260,
) -> ft.Container:
    """主菜单与子菜单上的大卡片。

    注意：**不要**给这个卡片设 ``expand=True``！它在各游戏子菜单里是放在
    ``Row(wrap=True)``（Flutter 的 Wrap 控件）里的，而 Flutter 规定
    ``Expanded`` 只能存在于 ``Flex``（Row/Column）里，**放进 Wrap 会直接抛断言、
    整页白屏**。要铺满宽度请用 :func:`grid_cards`，它会给每张卡算好显式宽度。
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
    """页面内容区：整屏铺开，而不是缩到内容固有宽度。

    两个关键点：
    * 外层 Container 给 ``alignment`` —— Flutter 的 Container 在有对齐且
      父级宽度有界时会撑满父级宽度（顶栏底色、边框才不会只画一小条）；
    * 内容若是普通（非滚动）Column，把它的交叉轴改成 STRETCH，里面的
      设置面板 / 卡片列才会跟着铺满；带滚动的手机排版保持原样，避免把
      固定尺寸的舞台 / 棋盘硬拉宽。
    """
    try:
        if (isinstance(content, ft.Column)
                and content.scroll is None
                and content.horizontal_alignment
                in (ft.CrossAxisAlignment.START, ft.CrossAxisAlignment.CENTER)):
            content.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    except Exception:                           # noqa: BLE001 — 控件类型变了就算了
        pass
    return ft.Container(
        padding=ft.Padding.all(T.PADDING),
        alignment=ft.Alignment.TOP_LEFT,
        content=content,
    )


# ============================================================
# 窄屏适配（手机竖屏 / 旋转后手牌不能被切掉）
# ============================================================

def page_width(page: ft.Page, fallback: float = 420.0) -> float:
    """当前页面宽度：走 :mod:`core.responsive` 的「尺寸真相」。

    旧实现只读一次 ``page.width``，首帧拿不到就兜底 420（手机宽），于是
    宽屏也会被画成窄屏。现在优先取最近一次 resize 事件的宽高，能实时反映
    窗口最大化 / 从窗口模式切回全屏的变化。
    """
    return responsive.page_width(page, fallback)


def page_height(page: ft.Page, fallback: float = 720.0) -> float:
    """当前页面高度（游戏画面按宽高一起缩放时用它）。"""
    return responsive.page_height(page, fallback)


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
    """把一组卡片**铺满可用宽度**，并且会跟着窗口变化自动伸缩。

    0.4.10 之前：固定宽度 ``Row(wrap=True)``，宽屏上三张 300px 卡片全堆在
    左边；0.4.10 改成按页面宽度算显式 ``c.width``，仍是「构建时写死一次」，
    且列数按 ``max_cols`` 算、最后一行不足列数时右侧会空 1/4~1/2 屏。

    现在：按当前宽度算列数，每张卡片放进普通 ``Row`` 的 ``expand`` 格里
    （**不是** ``wrap=True`` 的 Wrap —— Expanded 放进 Wrap 会直接白屏），
    末尾补齐透明占位格，保证所有行等宽铺满。宽度由 Flutter 约束实时决定，
    窗口拉伸时不需要重建页面；只有「列数」变化才由 Router.reflow 重建。
    """
    if not cards:
        return ft.Column([], spacing=spacing)
    avail = page_width(page, fallback=responsive.FALLBACK_WIDTH) - 2 * T.PADDING
    if avail <= 0:
        avail = responsive.FALLBACK_WIDTH - 2 * T.PADDING
    cols = max(1, min(max_cols,
                     int((avail + spacing) // (ideal_w + spacing))))
    # 一行塞不下 min_w 的卡片就退化成单列（窄屏 / 手机竖屏）
    if (avail - (cols - 1) * spacing) / cols < min_w:
        cols = 1
    rows: list[ft.Control] = []
    for i in range(0, len(cards), cols):
        chunk = cards[i:i + cols]
        cells: list[ft.Control] = []
        for c in chunk:
            # 清掉 ui.card / menu_card 的写死宽度，交给 Expanded 的紧约束决定
            try:
                c.width = None
            except Exception:                   # noqa: BLE001
                pass
            cells.append(ft.Container(content=c, expand=True))
        # 最后一行不足 cols 张时补占位，卡片不会被拉成畸形的大宽块
        for _ in range(cols - len(chunk)):
            cells.append(ft.Container(expand=True))
        rows.append(ft.Row(cells, spacing=spacing))
    return ft.Column(rows, spacing=spacing)


def tap_button(
    text: str,
    on_click=None,
    *,
    icon=None,
    size: int = 14,
    width: Optional[int] = None,
    height: int = 38,
    primary: bool = False,
    text_color=None,
) -> ft.Control:
    """鼠标 / 触控专用按钮（**不可获得键盘焦点**）。

    与 ``ft.Button`` 不同，它用 :class:`ft.GestureDetector` 实现，Flutter 不会
    给它建 ``FocusNode``，于是：

    * 方向键**不会**把焦点高亮移到它上面（不会「方向键移动光标」）；
    * 空格 / 回车**不会**触发它（不会误按按钮）。

    专门给「用方向键操作的游戏」（俄罗斯方块 / 贪吃蛇）的对局页用：
    这样方向键只会被游戏自己吃掉，不会在按钮之间乱跳、也不会误触按钮。
    点击 / 触摸照常可用（仍是鼠标触控交互）。
    """
    label_color = text_color or T.TEXT_PRIMARY
    if icon is not None:
        content = ft.Row(
            [icon, ft.Text(text, size=size, color=label_color)],
            spacing=4, tight=True,
        )
    else:
        content = ft.Text(text, size=size, color=label_color)
    box = ft.Container(
        width=width, height=height,
        bgcolor=T.PRIMARY if primary else T.SURFACE_ALT,
        border=ft.Border.all(1, T.BORDER),
        border_radius=8,
        alignment=ft.Alignment.CENTER,
        padding=ft.Padding.symmetric(horizontal=12, vertical=4),
        content=content,
    )

    def _tap(_e):
        if on_click is not None:
            on_click(_e)

    return ft.GestureDetector(content=box, on_tap=_tap)

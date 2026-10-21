# -*- coding: utf-8 -*-
"""「暗黑2 + Minecraft」风味的界面零件（只给联机 / 房间用）。

为什么单独一份配色
-------------------
房间是个「地下城大厅」：石质面板、金线描边、火把色的高光。它跟主界面的配色
（浅色卡片 / Material）走的不是一套语言，混在一起会显得很脏，所以这里用一组
固定的深色石头 + 暗金，不跟主题切换走 —— 主题再怎么换，地下城还是暗的。

怎么做出「斜面」的感觉
----------------------
flet 的 Container 只有一个 ``border``，但我们可以给四条边分别上色：

* 上、左两条边用**亮色**（火把照到的那一侧）
* 下、右两条边用**暗色**（背光的那一侧）

视觉上就是一块凸出来的石砖；反过来上左暗、下右亮，就变成凹进去的槽。
这就是 Minecraft 按钮的那种立体感，不需要贴图就能做出来。
"""

from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

# ------------------------------------------------------------------
# 配色（固定深色，不随明暗主题切换）
# ------------------------------------------------------------------

INK = "#0B0906"             # 最底：地牢黑
STONE = "#1C1712"           # 石板背景
STONE_PANEL = "#26201A"     # 面板
STONE_LIGHT = "#3A2F25"     # 面板高光一层
GOLD = "#D9A441"            # 暗金（主强调色）
GOLD_LIGHT = "#F0C46A"      # 火把打在金子上的颜色
GOLD_DARK = "#6E5A3C"       # 描边的暗侧
BLOOD = "#8B2E2E"           # 警告 / 拒绝
RUNE = "#C9B28A"            # 正文口语色（羊皮纸感）
RUNE_DIM = "#8C7C62"        # 次要文字
SLOT_EMPTY = "#241D16"


# ------------------------------------------------------------------
# 基础零件
# ------------------------------------------------------------------

def text(value: str, size: int = 13, color: str = RUNE,
         weight: Optional[ft.FontWeight] = None,
         spacing: float = 0.0) -> ft.Text:
    """一行规定风格的文字（surrounding 徽标：size / 色 / 字距）。"""
    return ft.Text(
        value, size=size, color=color, weight=weight,
        style=ft.TextStyle(letter_spacing=spacing) if spacing else None,
        selectable=True,
    )


# 内部也统一走这个（历史写法保留别名，避免改动牵连太多处）
_text = text


def title(value: str, size: int = 20) -> ft.Column:
    """带装饰线的金色标题：``◆ 标题 ◆``。"""
    line = ft.Container(height=1, bgcolor=GOLD_DARK, expand=True)
    return ft.Column(
        [
            ft.Row([line, _text("◆", 12, GOLD_LIGHT), line],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(height=2),
            ft.Row([_text(value, size, GOLD_LIGHT, ft.FontWeight.BOLD, 2.0)],
                   alignment=ft.MainAxisAlignment.CENTER),
        ],
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )


def bevel(width: int = 2, *, raised: bool = True) -> ft.Border:
    """斜面边框：凸起 / 凹陷。

    ``raised=True``：上左亮下右暗（凸出来的石砖）；
    ``raised=False``：反过来（凹进去的槽，比如聊天输入框）。
    """
    lo, hi = (GOLD_DARK, STONE_LIGHT) if raised else (STONE_LIGHT, GOLD_DARK)
    top, left = (hi, hi) if raised else (lo, lo)
    bottom, right = (lo, lo) if raised else (hi, hi)
    return ft.Border.only(
        top=ft.BorderSide(width, top),
        left=ft.BorderSide(width, left),
        bottom=ft.BorderSide(width, bottom),
        right=ft.BorderSide(width, right),
    )


def panel(content: ft.Control, *, padding: int = 12,
          bgcolor: str = STONE_PANEL, raised: bool = True,
          width: Optional[int] = None,
          expand: Optional[bool] = None) -> ft.Container:
    """石质面板：房间里的所有区块都包一层。"""
    return ft.Container(
        content=content,
        padding=ft.Padding.all(padding),
        bgcolor=bgcolor,
        border=bevel(raised=raised),
        border_radius=2,
        width=width,
        expand=expand,
    )


def button(
    text: str,
    icon: Optional[str] = None,
    on_click: Optional[Callable] = None,
    *,
    primary: bool = True,
    enabled: bool = True,
    width: Optional[int] = None,
    height: int = 44,
) -> ft.Container:
    """石砖按钮：按下不退、四周带斜面，禁用时压暗。

    用 emoji 当图标（比 Icon 更有 MC 味，也不用纠结图标字体）。
    """
    bg = STONE_LIGHT if primary else STONE
    fg = GOLD_LIGHT if (primary and enabled) else RUNE_DIM
    kids: List[ft.Control] = []
    if icon:
        kids.append(ft.Text(icon, size=16, color=fg))
        kids.append(ft.Container(width=8))
    kids.append(_text(text, 14, fg, ft.FontWeight.BOLD, 1.0))

    if not enabled:
        return ft.Container(
            content=ft.Row(kids, alignment=ft.MainAxisAlignment.CENTER),
            width=width, height=height, bgcolor=STONE, opacity=0.45,
            border=bevel(raised=False), border_radius=2,
            alignment=ft.Alignment(0, 0), padding=ft.Padding.symmetric(
                horizontal=14, vertical=8),
        )
    return ft.Container(
        content=ft.Row(kids, alignment=ft.MainAxisAlignment.CENTER),
        width=width, height=height, bgcolor=bg, ink=True,
        on_click=on_click, border=bevel(), border_radius=2,
        alignment=ft.Alignment(0, 0),
        padding=ft.Padding.symmetric(horizontal=14, vertical=8),
    )


def field(label: str, value: str = "", *, hint: str = "",
          on_submit=None, expand: bool = True,
          max_length: Optional[int] = None,
          password: bool = False,
          ref: Optional[ft.Ref] = None) -> ft.Column:
    """凹进去的输入框 + 上面一行小标签。

    ``expand`` 只让**这一栏**在 Row 里等宽分地盘；输入框本身**不 expand** ——
    在 Column 里 expand 会把输入框拉高，页面就出现一块说不清来历的空白。
    """
    return ft.Column(
        [
            _text(label, 11, RUNE_DIM, spacing=1.0),
            ft.Container(height=4),
            ft.Container(
                content=ft.TextField(
                    value=value, hint_text=hint, on_submit=on_submit,
                    border=ft.InputBorder.NONE, text_size=14, color=RUNE,
                    hint_style=ft.TextStyle(color=RUNE_DIM, size=13),
                    content_padding=ft.Padding.symmetric(
                        horizontal=10, vertical=8),
                    bgcolor=INK, max_length=max_length, password=password,
                    ref=ref,
                ),
                bgcolor=INK, border=bevel(raised=False), border_radius=2,
            ),
        ],
        spacing=0,
        expand=expand,
    )


def pill(text: str, *, color: str = GOLD_DARK,
         fg: str = INK) -> ft.Container:
    """小标签：房间码、人数这类短信息。"""
    return ft.Container(
        content=_text(text, 11, fg, ft.FontWeight.BOLD, 1.0),
        bgcolor=color, border_radius=2,
        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
    )


def hint_line(text: str, color: str = RUNE_DIM) -> ft.Text:
    return _text(text, 12, color)


def scroll_box(content: ft.Control, *, height: Optional[int] = None,
               expand: bool = False) -> ft.Container:
    """聊天/日志用的滚动框（深色凹槽）。"""
    inner = ft.Column([content], spacing=0, scroll=ft.ScrollMode.AUTO,
                      auto_scroll=True, expand=expand)
    return ft.Container(
        content=inner if not height else ft.Container(content=inner,
                                                      height=height),
        bgcolor=INK, border=bevel(raised=False), border_radius=2,
        padding=ft.Padding.all(8),
        expand=expand,
    )


def empty_slot(label: str = "空位", *, on_click=None,
               width: int = 150, height: int = 76) -> ft.Container:
    """房间里的一个空位（虚线感的凹槽，点一下可以坐过去）。"""
    inner = ft.Column(
        [
            ft.Text("✚", size=16, color=RUNE_DIM),
            _text(label, 12, RUNE_DIM),
        ],
        spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        alignment=ft.MainAxisAlignment.CENTER,
    )
    return ft.Container(
        content=inner, width=width, height=height, bgcolor=SLOT_EMPTY,
        border=ft.Border.all(1, GOLD_DARK), border_radius=2,
        alignment=ft.Alignment(0, 0), ink=on_click is not None,
        on_click=on_click,
    )


def taken_slot(nick: str, *, host: bool = False, talking: bool = False,
               muted: bool = False, width: int = 150,
               height: int = 76) -> ft.Container:
    """有人的席位：边框在说话时会亮起来（语音反馈）。"""
    border_color = GOLD if talking else (GOLD_DARK if not muted else "#4A3A2A")
    mic = "🔇" if muted else ("🗣" if talking else "🎤")
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(mic, size=13, color=GOLD_LIGHT),
                        ft.Text("♛" if host else "", size=12,
                                color=GOLD_LIGHT),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER, spacing=4,
                ),
                _text(nick, 13, RUNE, ft.FontWeight.BOLD),
            ],
            spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        width=width, height=height,
        bgcolor=STONE_LIGHT if talking else STONE_PANEL,
        border=ft.Border.all(2, border_color), border_radius=2,
        alignment=ft.Alignment(0, 0),
    )


def chat_row(nick: str, text: str, *, own: bool = False,
             system: bool = False) -> ft.Control:
    """聊天记录里的一行。"""
    if system:
        return ft.Container(
            padding=ft.Padding.symmetric(vertical=3),
            content=_text(f"» {text}", 11, RUNE_DIM),
        )
    name_color = GOLD_LIGHT if own else "#9BC1D9"
    body = ft.Row(
        [
            _text(f"{nick}：", 12, name_color, ft.FontWeight.BOLD),
            _text(text, 12, RUNE),
        ],
        spacing=0, wrap=True,
    )
    return ft.Container(padding=ft.Padding.symmetric(vertical=3), content=body)


def level_bar(level: float, width: int = 90) -> ft.Container:
    """麦克风电平条（一格一格的，像 MC 的经验条）。"""
    blocks = 10
    lit = int(max(0.0, min(1.0, level)) * blocks)
    kids: List[ft.Control] = []
    for i in range(blocks):
        kids.append(ft.Container(
            width=6, height=10,
            bgcolor=(GOLD_LIGHT if i < lit else STONE_LIGHT),
            border_radius=1,
        ))
    return ft.Container(
        content=ft.Row(kids, spacing=2, tight=True), width=width,
        alignment=ft.Alignment(-1, 0),
    )


def torch_divider() -> ft.Container:
    """火把分割线：``——— ◆ ———``。"""
    line = ft.Container(height=1, bgcolor=GOLD_DARK, expand=True)
    return ft.Container(
        padding=ft.Padding.symmetric(vertical=10),
        content=ft.Row([line, _text("◆", 10, GOLD_DARK), line],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER,
                       spacing=6),
    )


def page(title_text: str, body: ft.Control, *, on_back=None,
         actions: Optional[List[ft.Control]] = None) -> ft.Column:
    """一整页：暗色底 + 石顶栏（沿用通用 app_bar 的结构，换成暗色）。

    顶栏用 ember 风格的手动实现，因为 app_bar 取的是主题色。
    """
    left: List[ft.Control] = []
    if on_back is not None:
        left.append(
            ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color=GOLD_LIGHT,
                          on_click=on_back, tooltip="返回")
        )
    bar = ft.Container(
        height=56, bgcolor=STONE_PANEL,
        border=ft.Border.only(bottom=ft.BorderSide(2, GOLD_DARK)),
        padding=ft.Padding.symmetric(horizontal=12),
        content=ft.Row(
            [*left, ft.Container(expand=True,
                                 content=_text(title_text, 18, GOLD_LIGHT,
                                               ft.FontWeight.BOLD, 2.0)),
             *(actions or [])],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
    return ft.Column(
        [
            bar,
            ft.Container(padding=ft.Padding.all(16), content=body, expand=True),
        ],
        expand=True,
    )


def wrap_page(control: ft.Control) -> ft.Container:
    """给暗色页面加个深色背景（顶层 Container）。"""
    return ft.Container(content=control, bgcolor=STONE, expand=True)

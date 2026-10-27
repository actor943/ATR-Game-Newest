# -*- coding: utf-8 -*-
"""暗黑2 + Minecraft 风界面包（联机与房间的默认皮，0.4.7 引入）。

风格怎么来的
------------
* **暗黑2**：暗色石底 + 暗金描边、火把分割线（◆）、衬线感的重标题；
* **Minecraft**：按钮/输入框用**四边分色**做出斜面（上左亮、下右暗就是凸起，
  反过来就是凹陷），不需要贴图就是一块石砖。

所有颜色走 :class:`~core.ui_packs.base.ColorTokens`，语气（gold / dim /
danger…）由基类翻译，所以设置页切换到别的包时这里不需要任何改动。
"""

from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from core.i18n import t

from .base import BasePack, ColorTokens, PackMeta

INK = "#0B0906"             # 最底：地牢黑
STONE = "#1C1712"           # 石板背景
STONE_PANEL = "#26201A"     # 面板
STONE_LIGHT = "#3A2F25"     # 面板高光一层
GOLD = "#D9A441"            # 暗金（主强调色）
GOLD_LIGHT = "#F0C46A"      # 火把打在金子上的颜色
GOLD_DARK = "#6E5A3C"       # 描边的暗侧
BLOOD = "#8B2E2E"           # 警告 / 拒绝
RUNE = "#C9B28A"            # 正文（羊皮纸感）
RUNE_DIM = "#8C7C62"        # 次要文字
SLOT_EMPTY = "#241D16"

RUSTIC_TOKENS = ColorTokens(
    bg=STONE, surface=STONE_PANEL, surface_alt=STONE_LIGHT,
    border=GOLD_DARK, divider=GOLD_DARK,
    text=RUNE, text_secondary=RUNE_DIM, text_muted=RUNE_DIM,
    primary=GOLD, on_primary=INK, accent=GOLD_LIGHT,
    danger=BLOOD, success="#7A9A4E",
    gold=GOLD, gold_light=GOLD_LIGHT,
    ink=INK, slot_empty=SLOT_EMPTY,
)

# 语气 → 本包里的实际颜色（覆盖基类的默认映射）
TONE_MAP = {
    "": RUNE,
    "dim": RUNE_DIM,
    "secondary": RUNE_DIM,
    "primary": GOLD_LIGHT,
    "accent": GOLD_LIGHT,
    "gold": GOLD_LIGHT,
    "danger": "#D97070",
    "ok": "#9DC36B",
    "on_primary": INK,
}


class RusticPack(BasePack):
    """石砖风：凸/凹全靠四边分色，图标用 emoji（剑、火把、砖块）。"""

    def __init__(self) -> None:

        """准备石砖风自己的颜色与字体。"""
        super().__init__(
            meta=PackMeta(
                id="rustic",
                name="暗黑2 / MC（石砖）",
                description="地下城大厅风：石砖斜面、暗金描边、火把分割线。",
            ),
            colors=RUSTIC_TOKENS,
            radius=2,
            padding=16,
        )

    # ---------------- 颜色 ----------------

    def tone(self, name: str) -> str:

        """取某种语气（gold / dim / danger）的颜色。"""
        return TONE_MAP.get(name, RUNE)

    # ---------------- 文字 / 装饰 ----------------

    def title(self, value: str, size: int = 20) -> ft.Control:

        """带火把纹样的标题。"""
        line = ft.Container(height=1, bgcolor=GOLD_DARK, expand=True)
        return ft.Column(
            [
                ft.Row([line, self.text("◆", 12, "gold"), line],
                       vertical_alignment=ft.CrossAxisAlignment.CENTER,
                       spacing=6),
                ft.Container(height=2),
                ft.Row([self.text(value, size, "gold", ft.FontWeight.BOLD, 2.0)],
                       alignment=ft.MainAxisAlignment.CENTER),
            ],
            spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def divider(self) -> ft.Control:

        """石砖风的分隔线。"""
        line = ft.Container(height=1, bgcolor=GOLD_DARK, expand=True)
        return ft.Container(
            padding=ft.Padding.symmetric(vertical=10),
            content=ft.Row([line, self.text("◆", 10, "gold"), line],
                           vertical_alignment=ft.CrossAxisAlignment.CENTER,
                           spacing=6),
        )

    def pill(self, value: str, *, tone: str = "gold") -> ft.Control:

        """圆角小标签。"""
        bg = self.tone(tone)
        return ft.Container(
            content=self.text(value, 11, "on_primary", ft.FontWeight.BOLD, 1.0),
            bgcolor=bg, border_radius=2,
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
        )

    # ---------------- 容器 ----------------

    def bevel(self, width: int = 2, *, raised: bool = True) -> ft.Border:
        """斜面边框：凸起（火把侧亮）/ 凹陷（背光侧暗）。"""
        lo, hi = (GOLD_DARK, STONE_LIGHT) if raised else (STONE_LIGHT, GOLD_DARK)
        return ft.Border.only(
            top=ft.BorderSide(width, hi if raised else lo),
            left=ft.BorderSide(width, hi if raised else lo),
            bottom=ft.BorderSide(width, lo if raised else hi),
            right=ft.BorderSide(width, lo if raised else hi),
        )

    def panel(self, content: ft.Control, *, padding: int = 12,
              expand: Optional[bool] = None,
              bgcolor: Optional[str] = None) -> ft.Control:

        """带斜角的面板。"""
        return ft.Container(
            content=content,
            padding=ft.Padding.all(padding),
            bgcolor=bgcolor or STONE_PANEL,
            border=self.bevel(), border_radius=2,
            expand=expand,
        )

    def scroll_box(self, content: ft.Control, *, height: Optional[int] = None,
                   expand: bool = False) -> ft.Control:

        """固定高度、可滚动的区域。"""
        inner = ft.Column([content], spacing=0, scroll=ft.ScrollMode.AUTO,
                          auto_scroll=True, expand=expand)
        body = ft.Container(content=inner, height=height) if height else inner
        return ft.Container(
            content=body, bgcolor=INK, border=self.bevel(raised=False),
            border_radius=2, padding=ft.Padding.all(8), expand=expand,
        )

    # ---------------- 控件 ----------------

    def button(self, text: str, icon: Optional[str] = None,
               on_click: Optional[Callable] = None, *, primary: bool = True,
               enabled: bool = True, width: Optional[int] = None,
               height: int = 44) -> ft.Control:

        """石砖风按钮。"""
        bg = STONE_LIGHT if primary else STONE
        fg = GOLD_LIGHT if (primary and enabled) else RUNE_DIM
        kids: List[ft.Control] = []
        if icon:
            kids.append(ft.Text(icon, size=16, color=fg))
            kids.append(ft.Container(width=8))
        kids.append(self.text(text, 14, "", ft.FontWeight.BOLD, 1.0))
        kids[0].color = fg if icon else None          # type: ignore[union-attr]
        if not icon:
            kids[0].color = fg                        # type: ignore[union-attr]

        if not enabled:
            return ft.Container(
                content=ft.Row(kids, alignment=ft.MainAxisAlignment.CENTER),
                width=width, height=height, bgcolor=STONE, opacity=0.45,
                border=self.bevel(raised=False), border_radius=2,
                alignment=ft.Alignment(0, 0),
                padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            )
        return ft.Container(
            content=ft.Row(kids, alignment=ft.MainAxisAlignment.CENTER),
            width=width, height=height, bgcolor=bg, ink=True,
            on_click=on_click, border=self.bevel(), border_radius=2,
            alignment=ft.Alignment(0, 0),
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        )

    def icon_button(self, icon: str, on_click: Optional[Callable] = None,
                    *, tooltip: str = "") -> ft.Control:

        """只有图标的小按钮。"""
        return ft.IconButton(icon=icon, icon_color=GOLD_LIGHT,
                             on_click=on_click, tooltip=tooltip)

    def chip(self, label: str, *, active: bool,
             on_click: Optional[Callable] = None) -> ft.Control:

        """胶囊标签。"""
        return ft.Container(
            content=self.text(label, 12, "gold" if active else "dim",
                              ft.FontWeight.BOLD),
            bgcolor=STONE_LIGHT if active else STONE,
            border=self.bevel(raised=active), border_radius=2,
            padding=ft.Padding.symmetric(horizontal=12, vertical=7),
            ink=True, on_click=on_click,
        )

    def field(self, label: str, value: str = "", *, hint: str = "",
              on_submit: Optional[Callable] = None, expand: bool = True,
              max_length: Optional[int] = None,
              ref: Optional[ft.Ref] = None) -> ft.Control:
        # 输入框本身**不 expand**：在 Column 里 expand 会把它拉高，
        # 页面就多出一块来历不明的空白（0.4.7 修掉的诡异窗口之一）
        """一行「标签 + 输入框」。"""
        return ft.Column(
            [
                self.text(label, 11, "dim", spacing=1.0),
                ft.Container(height=4),
                ft.Container(
                    content=ft.TextField(
                        value=value, hint_text=hint, on_submit=on_submit,
                        border=ft.InputBorder.NONE, text_size=14, color=RUNE,
                        hint_style=ft.TextStyle(color=RUNE_DIM, size=13),
                        content_padding=ft.Padding.symmetric(
                            horizontal=10, vertical=8),
                        bgcolor=INK, max_length=max_length, ref=ref,
                    ),
                    bgcolor=INK, border=self.bevel(raised=False),
                    border_radius=2,
                ),
            ],
            spacing=0, expand=expand,
        )

    def card(self, title: str, description: str, icon: str,
             on_click: Optional[Callable] = None, *, available: bool = True,
             width: Optional[int] = None) -> ft.Control:

        """主菜单 / 子菜单上的大卡片。"""
        return ft.Container(
            width=width or 300,
            bgcolor=STONE_PANEL, border=self.bevel(), border_radius=2,
            padding=ft.Padding.all(14),
            ink=available and on_click is not None,
            on_click=on_click if available else None,
            # opacity 只在不可用时给值：传 None 会被 flet 拒绝
            **({} if available else {"opacity": 0.55}),
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(icon, size=28),
                        width=48, height=48, bgcolor=STONE,
                        border=self.bevel(raised=False), border_radius=2,
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Container(width=12),
                    ft.Column(
                        [
                            self.text(title, 16, "gold", ft.FontWeight.BOLD,
                                      1.0),
                            ft.Container(height=2),
                            self.text(description, 12, "dim"),
                        ],
                        spacing=0, expand=True,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    # ---------------- 页面骨架 ----------------

    def bar(self, title_text: str, on_back: Optional[Callable] = None,
            actions: Optional[List[ft.Control]] = None) -> ft.Control:

        """页面顶栏。"""
        left: List[ft.Control] = []
        if on_back is not None:
            left.append(self.icon_button(ft.Icons.ARROW_BACK, on_back,
                                         tooltip=t("common.back")))
        return ft.Container(
            height=56, bgcolor=STONE_PANEL,
            border=ft.Border.only(bottom=ft.BorderSide(2, GOLD_DARK)),
            padding=ft.Padding.symmetric(horizontal=12),
            content=ft.Row(
                [*left,
                 ft.Container(expand=True,
                              content=self.text(title_text, 18, "gold",
                                                ft.FontWeight.BOLD, 2.0)),
                 *(actions or [])],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def page(self, title_text: str, content: ft.Control,
             on_back: Optional[Callable] = None,
             actions: Optional[List[ft.Control]] = None) -> ft.Control:

        """整页骨架：顶栏 + 内容。"""
        return ft.Column(
            [
                self.bar(title_text, on_back, actions),
                ft.Container(padding=ft.Padding.all(self.padding),
                             content=content, expand=True),
            ],
            expand=True,
        )

    def wrap(self, control: ft.Control) -> ft.Control:

        """把控件套进石砖风底色里。"""
        return ft.Container(content=control, bgcolor=STONE, expand=True)

    # ---------------- 联机专用件 ----------------

    def slot(self, label: str = "空位", *, on_click=None,
             width: int = 150, height: int = 76) -> ft.Control:

        """房间里的空位。"""
        return ft.Container(
            content=ft.Column(
                [ft.Text("✚", size=16, color=RUNE_DIM),
                 self.text(label, 12, "dim")],
                spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            width=width, height=height, bgcolor=SLOT_EMPTY,
            border=ft.Border.all(1, GOLD_DARK), border_radius=2,
            alignment=ft.Alignment(0, 0),
            ink=on_click is not None, on_click=on_click,
        )

    def taken_slot(self, nick: str, *, host: bool = False,
                   talking: bool = False, muted: bool = False,
                   width: int = 150, height: int = 76) -> ft.Control:

        """房间里已坐人的位子。"""
        border_color = GOLD if talking else (GOLD_DARK if not muted
                                             else "#4A3A2A")
        mic = "🔇" if muted else ("🗣" if talking else "🎤")
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [ft.Text(mic, size=13, color=GOLD_LIGHT),
                         ft.Text("♛" if host else "", size=12,
                                 color=GOLD_LIGHT)],
                        alignment=ft.MainAxisAlignment.CENTER, spacing=4,
                    ),
                    self.text(nick, 13, "", ft.FontWeight.BOLD),
                ],
                spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            width=width, height=height,
            bgcolor=STONE_LIGHT if talking else STONE_PANEL,
            border=ft.Border.all(2, border_color), border_radius=2,
            alignment=ft.Alignment(0, 0),
        )

    def chat_row(self, nick: str, text: str, *, own: bool = False,
                 system: bool = False) -> ft.Control:

        """聊天区的一行。"""
        if system:
            return ft.Container(
                padding=ft.Padding.symmetric(vertical=3),
                content=self.text(f"» {text}", 11, "dim"),
            )
        return ft.Container(
            padding=ft.Padding.symmetric(vertical=3),
            content=ft.Row(
                [self.text(f"{nick}：", 12, "gold" if own else "accent",
                           ft.FontWeight.BOLD),
                 self.text(text, 12)],
                spacing=0, wrap=True,
            ),
        )

    def level_bar(self, level: float, width: int = 90) -> ft.Control:

        """麦克风电平条。"""
        blocks = 10
        lit = int(max(0.0, min(1.0, level)) * blocks)
        kids = [
            ft.Container(
                width=6, height=10, border_radius=1,
                bgcolor=GOLD_LIGHT if i < lit else STONE_LIGHT,
            )
            for i in range(blocks)
        ]
        return ft.Container(
            content=ft.Row(kids, spacing=2, tight=True), width=width,
            alignment=ft.Alignment(-1, 0),
        )


from .registry import register as _register           # noqa: E402

_register(RusticPack())

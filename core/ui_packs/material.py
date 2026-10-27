# -*- coding: utf-8 -*-
"""默认界面包：干净的材料风（就是 0.4.6 及以前的样子）。

这一套是所有界面的**默认皮**：亮/暗由 ``core/theme.py`` 的明暗开关决定，
颜色令牌跟着明暗一起换。游戏界面（掼蛋牌桌等）也是靠覆写 ``theme.T``
落到这一套令牌上的 —— 所以切换界面风格时，游戏内部不用改一行代码。
"""

from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from core import theme
from core.i18n import t

from .base import BasePack, ColorTokens, PackMeta


def _tokens(dark: bool) -> ColorTokens:
    """按明暗取令牌（与 theme.T 的默认值保持一致）。"""
    if dark:
        return ColorTokens(
            bg="#12161C", surface="#1A2028", surface_alt="#232B36",
            border="#2E3846", divider="#2A323D",
            text="#E8EDF4", text_secondary="#AAB6C6", text_muted="#7C8899",
            primary="#3B82F6", on_primary="#FFFFFF", accent="#F59E0B",
            danger="#EF4444", success="#22C55E",
            gold="#E3B341", gold_light="#F2CE6B",
            ink="#0F141A", slot_empty="#1E252F",
        )
    return ColorTokens(
        bg="#F6F7F9", surface="#FFFFFF", surface_alt="#EEF1F5",
        border="#D8DEE6", divider="#E5E9EF",
        text="#1B2430", text_secondary="#5A6675", text_muted="#8A94A3",
        primary="#2563EB", on_primary="#FFFFFF", accent="#F59E0B",
        danger="#DC2626", success="#16A34A",
        gold="#B8860B", gold_light="#8A6508",
        ink="#FFFFFF", slot_empty="#F1F4F8",
    )


class MaterialPack(BasePack):
    """默认包：用 flet 原生控件拼，圆角 + 轻描边。"""

    def __init__(self) -> None:

        """准备两套配色（明 / 暗），并记住当前用哪套。"""
        dark = theme.mode() == "dark"
        super().__init__(
            meta=PackMeta(
                id="default",
                name="默认（材料）",
                description="干净的材料风界面，跟随明暗主题；游戏界面也用它。",
            ),
            colors=_tokens(dark),
            radius=8,
            padding=16,
        )

    # 明暗切换后要重新取一次令牌
    def resync(self) -> None:

        """重新读一遍明暗开关，把颜色令牌换成对应的。"""
        self.colors = _tokens(theme.mode() == "dark")

    # ---------------- 文字 / 装饰 ----------------

    def title(self, value: str, size: int = 20) -> ft.Control:

        """标题文字。"""
        return self.text(value, size, "text", ft.FontWeight.BOLD)

    def divider(self) -> ft.Control:

        """一条细分隔线。"""
        return ft.Divider(height=1, color=self.colors.divider)

    # ---------------- 容器 ----------------

    def panel(self, content: ft.Control, *, padding: int = 12,
              expand: Optional[bool] = None,
              bgcolor: Optional[str] = None) -> ft.Control:

        """带底色和圆角的面板。"""
        return ft.Container(
            content=content,
            padding=ft.Padding.all(padding),
            bgcolor=bgcolor or self.colors.surface,
            border=ft.Border.all(1, self.colors.border),
            border_radius=self.radius,
            expand=expand,
        )

    def scroll_box(self, content: ft.Control, *, height: Optional[int] = None,
                   expand: bool = False) -> ft.Control:

        """固定高度、可以滚动的区域。"""
        inner = ft.Column([content], spacing=0, scroll=ft.ScrollMode.AUTO,
                          auto_scroll=True, expand=expand)
        body = ft.Container(content=inner, height=height) if height else inner
        return ft.Container(
            content=body,
            bgcolor=self.colors.surface_alt,
            border=ft.Border.all(1, self.colors.border),
            border_radius=self.radius,
            padding=ft.Padding.all(8),
            expand=expand,
        )

    # ---------------- 控件 ----------------

    def button(self, text: str, icon: Optional[str] = None,
               on_click: Optional[Callable] = None, *, primary: bool = True,
               enabled: bool = True, width: Optional[int] = None,
               height: int = 44) -> ft.Control:

        """主按钮。"""
        label = f"{icon}  {text}" if icon else text
        return ft.Button(
            content=ft.Text(label, size=14),
            bgcolor=self.colors.primary if primary else self.colors.surface_alt,
            color=self.colors.on_primary if primary else self.colors.text,
            width=width, height=height,
            disabled=not enabled,
            on_click=on_click,
        )

    def icon_button(self, icon: str, on_click: Optional[Callable] = None,
                    *, tooltip: str = "") -> ft.Control:

        """只有图标的小按钮。"""
        return ft.IconButton(icon=icon, icon_color=self.colors.text,
                             on_click=on_click, tooltip=tooltip)

    def chip(self, label: str, *, active: bool,
             on_click: Optional[Callable] = None) -> ft.Control:

        """胶囊标签（可高亮，表示「选中」）。"""
        return ft.Container(
            content=self.text(label, 12, "on_primary" if active else "dim",
                              ft.FontWeight.BOLD),
            bgcolor=self.colors.primary if active else self.colors.surface_alt,
            border=ft.Border.all(1, self.colors.primary if active
                                 else self.colors.border),
            border_radius=20,
            padding=ft.Padding.symmetric(horizontal=14, vertical=7),
            ink=True, on_click=on_click,
        )

    def field(self, label: str, value: str = "", *, hint: str = "",
              on_submit: Optional[Callable] = None, expand: bool = True,
              max_length: Optional[int] = None,
              ref: Optional[ft.Ref] = None) -> ft.Control:

        """一行「标签 + 输入框」。"""
        return ft.Column(
            [
                self.text(label, 11, "dim"),
                ft.Container(height=4),
                ft.TextField(
                    value=value, hint_text=hint, on_submit=on_submit,
                    border=ft.InputBorder.OUTLINE, text_size=14,
                    color=self.colors.text, bgcolor=self.colors.ink,
                    hint_style=ft.TextStyle(color=self.colors.text_muted,
                                            size=13),
                    content_padding=ft.Padding.symmetric(horizontal=10,
                                                         vertical=8),
                    max_length=max_length, ref=ref,
                ),
            ],
            spacing=0, expand=expand,
        )

    def card(self, title: str, description: str, icon: str,
             on_click: Optional[Callable] = None, *, available: bool = True,
             width: Optional[int] = None) -> ft.Control:
        # opacity 只在不可用时给值：传 None 会被 flet 拒绝
        """主菜单 / 子菜单上的大卡片。"""
        dim = {} if available else {"opacity": 0.55}
        return ft.Container(
            width=width or 300,
            bgcolor=self.colors.surface,
            border=ft.Border.all(1, self.colors.border),
            border_radius=12,
            padding=ft.Padding.all(16),
            ink=available and on_click is not None,
            on_click=on_click if available else None,
            **dim,
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Text(icon, size=30),
                        width=52, height=52, bgcolor=self.colors.surface_alt,
                        border_radius=10, alignment=ft.Alignment(0, 0),
                    ),
                    ft.Container(width=12),
                    ft.Column(
                        [
                            self.text(title, 16, "primary", ft.FontWeight.BOLD),
                            ft.Container(height=2),
                            self.text(description, 12, "secondary"),
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

        """页面顶栏：左侧返回 + 中间标题 + 右侧动作区。"""
        left: List[ft.Control] = []
        if on_back is not None:
            left.append(ft.IconButton(icon=ft.Icons.ARROW_BACK,
                                      icon_color=self.colors.text,
                                      on_click=on_back,
                                      tooltip=t("common.back")))
        return ft.Container(
            height=56, bgcolor=self.colors.surface,
            border=ft.Border.only(bottom=ft.BorderSide(1, self.colors.border)),
            padding=ft.Padding.symmetric(horizontal=8),
            content=ft.Row(
                [*left, self.text(title_text, 18, "text", ft.FontWeight.BOLD),
                 *(actions or [])],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
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

        """把控件套进当前界面的统一底色里。"""
        return ft.Container(content=control, bgcolor=self.colors.bg,
                            expand=True)

    # ---------------- 联机专用件 ----------------

    def slot(self, label: str = "空位", *, on_click=None,
             width: int = 150, height: int = 76) -> ft.Control:

        """房间里的空位。"""
        return ft.Container(
            content=ft.Column(
                [ft.Text("＋", size=15, color=self.colors.text_muted),
                 self.text(label, 12, "dim")],
                spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            width=width, height=height, bgcolor=self.colors.slot_empty,
            border=ft.Border.all(1, self.colors.border), border_radius=8,
            alignment=ft.Alignment(0, 0),
            ink=on_click is not None, on_click=on_click,
        )

    def taken_slot(self, nick: str, *, host: bool = False,
                   talking: bool = False, muted: bool = False,
                   width: int = 150, height: int = 76) -> ft.Control:

        """房间里已坐人的位子（房主 / 正在说话 / 已静音都有区别）。"""
        mic = "🔇" if muted else ("🗣" if talking else "🎤")
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(f"{mic} {'👑' if host else ''}", size=13,
                            color=self.colors.text_secondary),
                    self.text(nick, 13, "text", ft.FontWeight.BOLD),
                ],
                spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            width=width, height=height,
            bgcolor=self.colors.primary if talking else self.colors.surface,
            border=ft.Border.all(2, self.colors.primary if talking
                                 else self.colors.border),
            border_radius=8, alignment=ft.Alignment(0, 0),
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
                [self.text(f"{nick}：", 12,
                           "primary" if own else "accent", ft.FontWeight.BOLD),
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
                width=6, height=10, border_radius=2,
                bgcolor=self.colors.primary if i < lit
                else self.colors.surface_alt,
            )
            for i in range(blocks)
        ]
        return ft.Container(
            content=ft.Row(kids, spacing=2, tight=True), width=width,
            alignment=ft.Alignment(-1, 0),
        )


# import 即注册
from .registry import register as _register           # noqa: E402

_register(MaterialPack())

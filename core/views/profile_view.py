# -*- coding: utf-8 -*-
"""我的（Profile）：改名字的地方。

进房间时别人看到的就是这里的名字。第一次进多人游戏时如果还没起过名，
系统会随机给你一个（见 :func:`core.profile.Profile.ensure_nick`），
随时可以回到这一页改成自己想要的。

0.4.7 的 Profile 只做**命名**这一件事（后续版本再加战绩、头像之类的）。
"""

from __future__ import annotations

import flet as ft

from core import ui_theme as ui
from core.i18n import t
from core.profile import Profile, random_nick
from core.registry import NavigateFn


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:

    """个人资料页：查看昵称与设备号，可改名、可随机生成。"""
    profile = Profile.load()
    had_nick = profile.named
    nick = profile.ensure_nick()          # 没起过就先随机一个，保证有名字可用

    name_ref = ft.Ref[ft.TextField]()
    tip = ui.hint("")

    def save(_e=None) -> None:
        box = name_ref.current
        value = (box.value if box else "").strip()
        if not value:
            tip.value = t("profile.empty_error")
            tip.color = ui.tone("danger")
            page.update()
            return
        if len(value) > 16:
            tip.value = t("profile.too_long")
            tip.color = ui.tone("danger")
            page.update()
            return
        profile.set_nick(value)
        tip.value = t("profile.saved", nick=profile.nick)
        tip.color = ui.tone("ok")
        page.update()

    def roll(_e=None) -> None:
        suggestion = random_nick()
        if name_ref.current is not None:
            name_ref.current.value = suggestion
        tip.value = t("profile.rolled", nick=suggestion)
        tip.color = ui.tone("secondary")
        page.update()

    def row(label: str, value: str) -> ft.Control:
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
            border=ft.Border.only(bottom=ft.BorderSide(1, ui.colors().divider)),
            content=ft.Row(
                [
                    ui.text(label, 13, "secondary"),
                    ft.Container(expand=True),
                    ui.text(value, 13, ""),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    body = ft.Column(
        [
            ui.text(t("profile.title"), 22, "", ft.FontWeight.BOLD),
            ft.Container(height=4),
            ui.text(t("profile.subtitle"), 13, "secondary"),
            ft.Container(height=18),
            ui.panel(
                ft.Column(
                    [
                        row(t("profile.current_nick"), nick),
                        row(t("profile.nick_source"), t("profile.nick_self")
                            if had_nick else t("profile.nick_random")),
                    ],
                    spacing=0,
                )
            ),
            ft.Container(height=18),
            ui.text(t("profile.change_nick"), 12, "secondary",
                    ft.FontWeight.BOLD),
            ft.Container(height=6),
            # 这一行**不 wrap**：wrap 的 Row 里放 expand 输入框会被 flet
            # 撑成一块灰色巨墙（0.4.7 修掉的「没有底的诡异窗口」）
            ft.Row(
                [
                    ft.Container(
                        content=ft.TextField(
                            ref=name_ref, value=nick, max_length=16,
                            border=ft.InputBorder.OUTLINE, text_size=14,
                            color=ui.colors().text, bgcolor=ui.colors().ink,
                            on_submit=save,
                        ),
                        border=ft.Border.all(1, ui.colors().border),
                        border_radius=8, expand=True,
                        padding=ft.Padding.symmetric(horizontal=10),
                    ),
                    ft.Container(width=10),
                    ui.button(t("profile.random"), None, roll, primary=False,
                              height=44),
                    ft.Container(width=10),
                    ui.button(t("profile.save"), None, save, height=44),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(height=12),
            tip,
            ft.Container(height=20),
            ui.text(t("profile.tip"), 11, "dim"),
            ft.Container(expand=True),
        ],
        spacing=0, scroll=ft.ScrollMode.AUTO, expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.START,
    )

    return ui.page(t("profile.title"), body, on_back=lambda _e: navigate("/"))

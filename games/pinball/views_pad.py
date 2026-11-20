# -*- coding: utf-8 -*-
"""手机端操作键：左挡板（按住）/ 蓄力发射（按住，松手弹射）/ 右挡板 / 暂停。

和键盘走同一个 ``_act()``。挡板按下时给一个 3 秒的「按住」时限，
即便手指滑出按钮、``on_tap_up`` 丢了，挡板也会自己落下，不会一直抬着；
``on_tap_cancel`` 同样按松开处理。
"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.theme import T


def _key(label: str, *, on_down=None, on_up=None, on_tap=None,
         big: bool = True, bg=None, color=None) -> ft.GestureDetector:
    box = ft.Container(
        width=94.0 if big else 62.0,
        height=76.0 if big else 62.0,
        bgcolor=bg or T.SURFACE_ALT,
        border=ft.Border.all(1, T.BORDER),
        border_radius=12,
        alignment=ft.Alignment.CENTER,
        content=ft.Text(label, size=14 if big else 12,
                        weight=ft.FontWeight.BOLD,
                        color=color or T.TEXT_PRIMARY),
    )
    return ft.GestureDetector(
        content=box,
        on_tap_down=on_down,
        on_tap_up=on_up,
        on_tap_cancel=on_up,
        on_tap=on_tap,
    )


class TouchPad:
    """一排触控键；动作通过 ``act`` 回调抛给对局页。"""

    def __init__(self, page: ft.Page, act):
        self.page = page
        self.act = act
        self.left_btn = _key(
            t("pinball.left", default="左挡板"),
            on_down=lambda _e: act("left_down"),
            on_up=lambda _e: act("left_up"),
        )
        self.plunge_btn = _key(
            t("pinball.plunge", default="发射"),
            on_down=lambda _e: act("plunge_down"),
            on_up=lambda _e: act("plunge_up"),
            bg=T.PRIMARY, color=T.TEXT_INVERT,
        )
        self.right_btn = _key(
            t("pinball.right", default="右挡板"),
            on_down=lambda _e: act("right_down"),
            on_up=lambda _e: act("right_up"),
        )
        self.pause_btn = _key(
            t("pinball.pause", default="暂停"),
            on_tap=lambda _e: act("pause"), big=False,
        )

    def build(self) -> ft.Control:
        return ft.Row(
            [self.left_btn, self.plunge_btn, self.right_btn, self.pause_btn],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            wrap=True,
            run_spacing=8,
        )

    def detach(self) -> None:
        """离开页面：兜底放下两片挡板（不触发发射）。"""
        try:
            self.act("left_up")
            self.act("right_up")
        except Exception:                       # noqa: BLE001
            pass

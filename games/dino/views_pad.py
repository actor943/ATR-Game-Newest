# -*- coding: utf-8 -*-
"""手机端操作键：跳（点按）、蹲（按住）、暂停（点按）。

走和键盘同一个 ``act()``：跳 = jump，蹲 = duck（按住时循环刷新下蹲计时，
松开即停；即便松开事件丢失，引擎里 0.5s 计时也会自动解除下蹲）。
"""

from __future__ import annotations

import asyncio
from typing import Optional

import flet as ft

from core.i18n import t
from core.theme import T


def _key(label: str, on_down=None, on_up=None, on_tap=None,
         bg=None, big: bool = True) -> ft.GestureDetector:
    box = ft.Container(
        width=92 if big else 64,
        height=92 if big else 64,
        bgcolor=bg or T.SURFACE_ALT,
        border=ft.Border.all(1, T.BORDER),
        border_radius=12,
        alignment=ft.Alignment.CENTER,
        content=ft.Text(label, size=18, weight=ft.FontWeight.BOLD,
                       color=T.TEXT_PRIMARY),
    )
    return ft.GestureDetector(
        content=box,
        on_tap_down=on_down,
        on_tap_up=on_up,
        on_tap=on_tap,
    )


class TouchPad:
    def __init__(self, page: ft.Page, act):
        self.page = page
        self.act = act
        self._duck_task: Optional[asyncio.Task] = None

        self.duck_btn = _key(t("dino.duck", default="蹲"),
                             on_down=lambda _e: self._start_duck(),
                             on_up=lambda _e: self._stop_duck())
        self.jump_btn = _key(t("dino.jump", default="跳"),
                            on_down=lambda _e: self.act("jump"),
                            bg=T.PRIMARY)
        self.pause_btn = _key(t("dino.pause", default="暂停"),
                             on_tap=lambda _e: self.act("pause"),
                             big=False)

    # ---------- 蹲：按住连发（刷新下蹲计时） ----------
    def _start_duck(self):
        self._stop_duck()
        self.act("duck")

        async def _repeat():
            try:
                while True:
                    self.act("duck")
                    await asyncio.sleep(0.15)
            except asyncio.CancelledError:
                pass

        try:
            self._duck_task = self.page.run_task(_repeat)
        except Exception:                   # noqa: BLE001
            self._duck_task = None

    def _stop_duck(self):
        if self._duck_task is not None:
            try:
                self._duck_task.cancel()
            except Exception:               # noqa: BLE001
                pass
            self._duck_task = None
        self.act("duck_release")

    # ---------- 对外 ----------
    def build(self) -> ft.Control:
        return ft.Row(
            [self.duck_btn, self.jump_btn, self.pause_btn],
            spacing=14,
            alignment=ft.MainAxisAlignment.CENTER,
        )

    def detach(self):
        self._stop_duck()

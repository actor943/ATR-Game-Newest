# -*- coding: utf-8 -*-
"""触屏操作键（手机端没有键盘，棋盘下面要有一排按键）。

键位
----
``←`` ``→`` ``↑`` ``↓``  转向（按住连发，持续保持该方向）
``慢``  速度 −1      ``快``  速度 +1（按住可快速连调，变速功能的触屏入口）
``暂停``  暂停 / 继续（单击，不连发）

按住不放会**连发**：先等 0.26 秒，之后每 0.10 秒触发一次 —— 转向和调速
都不用一直点。暂停键不连发，避免反复横跳。

实现用 ``ft.GestureDetector`` 的 ``on_tap_down`` / ``on_tap_up``：
``ft.Button`` 只有 ``on_click``，既不知道手指什么时候松开，也没法连发。
"""

from __future__ import annotations

import asyncio
from typing import Callable, Dict, Optional

import flet as ft

from core.i18n import t
from core.theme import T

REPEAT_DELAY = 0.26     # 按住多久开始连发（秒）
REPEAT_INTERVAL = 0.10  # 连发间隔（秒）

# (图标, 文案, 动作名, 是否连发)
KEYS = (
    (ft.Icons.ARROW_LEFT, "", "left", True),
    (ft.Icons.ARROW_UPWARD, "", "up", True),
    (ft.Icons.ARROW_DOWNWARD, "", "down", True),
    (ft.Icons.ARROW_RIGHT, "", "right", True),
    (ft.Icons.REMOVE, t("snake.slower", default="慢"), "speed_down", True),
    (ft.Icons.ADD, t("snake.faster", default="快"), "speed_up", True),
)
PAUSE_KEY = (ft.Icons.PAUSE, t("snake.pause", default="暂停"), "pause", False)


class TouchPad:
    """一排触屏操作键；动作通过 ``on_action`` 回调抛给对局页。"""

    def __init__(self, page: ft.Page, on_action: Callable[[str], None]):
        self.page = page
        self.on_action = on_action
        self._tasks: Dict[str, asyncio.Task] = {}

    # ---------- 动作 ----------

    def _fire(self, action: str) -> None:
        try:
            self.on_action(action)
        except Exception:                   # noqa: BLE001 — 按键不能把页面搞崩
            pass

    async def _repeat(self, action: str) -> None:
        try:
            await asyncio.sleep(REPEAT_DELAY)
            while True:
                await asyncio.sleep(REPEAT_INTERVAL)
                self._fire(action)
        except asyncio.CancelledError:
            raise
        except Exception:                   # noqa: BLE001
            return

    def _stop(self, action: str) -> None:
        task = self._tasks.pop(action, None)
        if task is not None:
            try:
                task.cancel()
            except Exception:               # noqa: BLE001
                pass

    def detach(self) -> None:
        for action in list(self._tasks):
            self._stop(action)

    # ---------- 界面 ----------

    def _key(self, icon, label: str, action: str, size: float,
             repeat: bool) -> ft.Control:
        def _down(_e):
            self._fire(action)
            if repeat:
                self._stop(action)
                try:
                    self._tasks[action] = self.page.run_task(
                        self._repeat(action))
                except Exception:           # noqa: BLE001
                    pass

        def _up(_e):
            self._stop(action)

        def _cancel(_e):
            self._stop(action)

        box = ft.Container(
            width=size, height=size,
            bgcolor=T.SURFACE_ALT,
            border=ft.Border.all(1, T.BORDER),
            border_radius=10,
            alignment=ft.Alignment.CENTER,
            content=(ft.Text(label, size=13, color=T.TEXT_PRIMARY)
                     if label
                     else ft.Icon(icon, size=int(size * 0.46),
                                  color=T.TEXT_PRIMARY)),
        )
        return ft.GestureDetector(
            content=box,
            on_tap_down=_down,
            on_tap_up=_up,
            on_tap_cancel=_cancel,
        )

    def build(self) -> ft.Control:
        size = 52.0
        keys = [self._key(icon, label, action, size, repeat)
                for icon, label, action, repeat in KEYS]
        keys.append(self._key(PAUSE_KEY[0], PAUSE_KEY[1], PAUSE_KEY[2],
                              62.0, PAUSE_KEY[3]))
        return ft.Row(
            keys,
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            wrap=True,
            run_spacing=8,
        )

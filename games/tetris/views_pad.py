# -*- coding: utf-8 -*-
"""触屏操作键（手机端没有键盘，棋盘下面要有一排按键）。

键位
----
``←`` ``→``  左右移动      ``↻``  顺时针旋转
``↓``        软降一格      ``⤓``  硬降到底
``HOLD``     暂存当前方块

按住不放会**连发**：先等 0.28 秒，之后每 0.11 秒触发一次 —— 快速横移
不用一直点。

实现用 ``ft.GestureDetector`` 的 ``on_tap_down`` / ``on_tap_up``：
``ft.Button`` 只有 ``on_click``，既不知道手指什么时候松开，也没法连发。
"""

from __future__ import annotations

import asyncio
from typing import Callable, Dict

import flet as ft

from core.i18n import t
from core.theme import T

REPEAT_DELAY = 0.28     # 按住多久开始连发（秒）
REPEAT_INTERVAL = 0.11  # 连发间隔（秒）

# (图标, 文案, 动作名)
KEYS = (
    (ft.Icons.ARROW_LEFT, "", "left"),
    (ft.Icons.ARROW_RIGHT, "", "right"),
    (ft.Icons.ROTATE_RIGHT, "", "rotate"),
    (ft.Icons.ARROW_DOWNWARD, "", "down"),
    (ft.Icons.ARROW_DROP_DOWN, "", "drop"),
)


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
        """按住不放时的连发。"""
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
        """离开页面时把所有连发任务停掉。"""
        for action in list(self._tasks):
            self._stop(action)

    # ---------- 界面 ----------

    def _key(self, icon, label: str, action: str, size: float) -> ft.Control:
        """一个可长按连发的键。"""
        def _down(_e):
            self._fire(action)
            self._stop(action)
            try:
                self._tasks[action] = self.page.run_task(self._repeat(action))
            except Exception:               # noqa: BLE001
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
        """搭出整排操作键（左右移动 + 旋转 + 下落 + 暂存）。"""
        size = 52.0
        keys = [self._key(icon, label, action, size)
                for icon, label, action in KEYS]
        keys.append(self._key(None, t("tetris.hold", default="暂存"),
                              "hold", 62.0))
        return ft.Row(
            keys,
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            wrap=True,
            run_spacing=8,
        )

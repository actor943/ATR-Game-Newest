# -*- coding: utf-8 -*-
"""台球对局页的「外接控制器」：角度转盘 + 力度条（牛顿）。

为什么要有这两个东西
--------------------
手机端最大的痛点是「手指戳不准白球」—— 白球直径才二十几像素，触控
点又粗，经常抓空。点空白处的话，原有的「拉弓」手势又得先按在母球上。

所以这里给出一套**不依赖触摸白球**的控制器：

* **角度转盘（轮盘）**：手指在圆盘上指哪，击球方向就朝哪；
* **力度条**：从下往上拖，0 → 75 牛（现实世界球杆出力区间）；
* **击球按钮**：按当前角度 + 力度出杆。

这两个控件摆在对局页下方的空位，桌面端和手机端都能用；原有「拖白球
拉弓」的手势依然保留，两套互不冲突。

坐标说明：屏幕 y 轴向下，所以角度用 ``math.atan2(dy, dx)`` 直接就是
游戏内的方向向量 ``(cos a, sin a)``，不需要任何翻转。
"""

from __future__ import annotations

import math

import flet as ft

from core.theme import T


# 控件配色（独立于界面包，保证在台球页上足够显眼）
_DIAL_RING = T.BORDER
_DIAL_BG = T.SURFACE
_NEEDLE = T.ACCENT
_HANDLE = T.ACCENT
_TRACK = T.SURFACE
_TRACK_BORDER = T.BORDER
_FILL = T.ACCENT


class AngleDial:
    """角度转盘：在圆盘上指方向。``on_change(angle_rad)`` 回报当前角度。"""

    def __init__(self, size: float = 130.0, on_change=None):
        self.size = float(size)
        self.r = self.size / 2.0
        self.angle = 0.0                      # 弧度，y 轴向下
        self.on_change = on_change
        self._build()

    def _build(self) -> None:
        c = self.r
        L = self.r - 10.0
        self._needle = ft.Container(
            width=L, height=5, bgcolor=_NEEDLE, border_radius=2.5,
            left=c - L / 2.0, top=c - 2.5,
            rotate=ft.Rotate(0.0, alignment=ft.Alignment(0, 0)),
        )
        self._handle = ft.Container(
            width=18, height=18, bgcolor=_HANDLE, border_radius=9,
            border=ft.Border.all(2, T.SURFACE),
            left=c + (self.r - 14) - 9, top=c - 9,
        )
        # 中心点
        self._hub = ft.Container(
            width=10, height=10, bgcolor=_NEEDLE, border_radius=5,
            left=c - 5, top=c - 5,
        )
        ring = ft.Container(
            width=self.size, height=self.size, bgcolor=_DIAL_BG,
            border=ft.Border.all(2, _DIAL_RING), border_radius=self.r,
        )
        self._stack = ft.Stack(
            [ring, self._needle, self._handle, self._hub],
            width=self.size, height=self.size,
        )
        self.control = ft.GestureDetector(
            content=self._stack,
            on_pan_start=self._drag, on_pan_update=self._drag,
        )
        self._place()

    def _drag(self, e) -> None:
        pos = getattr(e, "local_position", None)
        if pos is None:
            return
        try:
            x = float(pos.x) - self.r
            y = float(pos.y) - self.r
        except Exception:                     # noqa: BLE001
            return
        if math.hypot(x, y) < 1e-6:
            return
        self.angle = math.atan2(y, x)
        self._place()
        if self.on_change is not None:
            try:
                self.on_change(self.angle)
            except Exception:                 # noqa: BLE001
                pass

    def _place(self) -> None:
        self._needle.rotate.angle = self.angle
        rr = self.r - 14.0
        self._handle.left = self.r + math.cos(self.angle) * rr - 9
        self._handle.top = self.r + math.sin(self.angle) * rr - 9

    def set_angle(self, angle: float) -> None:
        """外部（比如白球位置变了）直接设定角度并刷新指针。"""
        self.angle = float(angle)
        self._place()


class PowerBar:
    """竖直力度条：从下往上拖，0 → ``max_n`` 牛。

    ``on_change(force_n)`` 回报当前力度（牛顿）。
    """

    def __init__(self, width: float = 46.0, height: float = 170.0,
                 max_n: float = 75.0, on_change=None):
        self.w = float(width)
        self.h = float(height)
        self.max_n = float(max_n)
        self.frac = 0.4                        # 0~1
        self.on_change = on_change
        self._build()

    def _build(self) -> None:
        self._fill = ft.Container(
            width=self.w - 6, height=0, left=3, top=0,
            bgcolor=_FILL, border_radius=ft.BorderRadius(6, 6, 0, 0),
        )
        self._handle = ft.Container(
            width=self.w, height=10, left=0, top=0,
            bgcolor=T.TEXT_PRIMARY, border_radius=5,
            border=ft.Border.all(2, T.SURFACE),
        )
        track = ft.Container(
            width=self.w, height=self.h, bgcolor=_TRACK,
            border=ft.Border.all(2, _TRACK_BORDER), border_radius=8,
            content=ft.Stack([self._fill, self._handle],
                             width=self.w, height=self.h),
        )
        self.control = ft.GestureDetector(
            content=track, on_pan_start=self._drag, on_pan_update=self._drag,
        )
        self._place()

    def _drag(self, e) -> None:
        pos = getattr(e, "local_position", None)
        if pos is None:
            return
        try:
            y = float(pos.y)
        except Exception:                     # noqa: BLE001
            return
        f = 1.0 - (y / self.h)
        f = max(0.0, min(1.0, f))
        if abs(f - self.frac) < 1e-4:
            return
        self.frac = f
        self._place()
        if self.on_change is not None:
            try:
                self.on_change(self.frac * self.max_n)
            except Exception:                 # noqa: BLE001
                pass

    def _place(self) -> None:
        fh = self.frac * self.h
        self._fill.height = fh
        self._fill.top = self.h - fh
        self._handle.top = self.h - fh - 5

    def set_force(self, force_n: float) -> None:
        """外部直接设定力度（牛顿）并刷新。"""
        self.frac = max(0.0, min(1.0, float(force_n) / self.max_n))
        self._place()

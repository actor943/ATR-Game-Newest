# -*- coding: utf-8 -*-
"""台球对局页的「外接控制器」：角度转盘 + 力度条 + 击球点圆盘。

为什么要有这三个东西
--------------------
手机端最大的痛点是「手指戳不准白球」—— 白球直径才二十几像素，触控
点又粗，经常抓空。点空白处的话，原有的「拉弓」手势又得先按在母球上。

所以这里给出一套**不依赖触摸白球**的控制器：

* **角度转盘（轮盘）**：手指在圆盘上指哪，击球方向就朝哪；
* **力度条**：从下往上拖，0 → 200 牛（对局页另有数值输入框，可直接
  敲一个精确力度；两者双向同步）；
* **击球点圆盘**：在这颗放大的白球上拖红点选杆法 —— 上=高杆（跟进）、
  下=低杆（回缩）、左/右=加塞；红点离中心越远，旋转越强；
* **击球按钮**：按当前角度 + 力度 + 击球点出杆。

这几个控件摆在对局页下方的空位，桌面端和手机端都能用；原有「拖白球
拉弓」的手势依然保留，两套互不冲突（拉弓同样吃当前选好的杆法）。

坐标说明：屏幕 y 轴向下，所以角度用 ``math.atan2(dy, dx)`` 直接就是
游戏内的方向向量 ``(cos a, sin a)``，不需要任何翻转。击球点圆盘相反：
圆盘上方是「高杆」，所以要取 ``-(y - r)`` 把屏幕 y 翻过来。
"""

from __future__ import annotations

import math

import flet as ft

from core.theme import T

from .physics import FORCE_MAX_N, clamp_tip


# 控件配色（独立于界面包，保证在台球页上足够显眼）
_DIAL_RING = T.BORDER
_DIAL_BG = T.SURFACE
_NEEDLE = T.ACCENT
_HANDLE = T.ACCENT
_TRACK = T.SURFACE
_TRACK_BORDER = T.BORDER
_FILL = T.ACCENT
# 击球点圆盘：白球 + 十字 + 红色杆头印
_TIP_BALL = "#F5F2E8"
_TIP_CROSS = "#A8ADB5"
_TIP_DOT = "#D64545"


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
                 max_n: float = FORCE_MAX_N, on_change=None):
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


class SpinDial:
    """击球点圆盘：拖红点选「高低杆 + 加塞」。

    ``on_change(top, side)`` 回报杆法；``top`` 上正下负（高杆 / 低杆），
    ``side`` 右正左负（右塞 / 左塞），两者被限制在单位圆盘内
    （:func:`physics.clamp_tip`），斜着打满时等比缩放，不会滑杆。

    圆盘是「站在母球后面看过去」的球杆接触面：上方=高杆、下方=低杆，
    屏幕 y 向下，所以换算时要取负号。
    """

    def __init__(self, size: float = 110.0, on_change=None):
        self.size = float(size)
        self.r = self.size / 2.0
        self.rr = self.r - 11.0            # 红点可达半径
        self.top = 0.0
        self.side = 0.0
        self.on_change = on_change
        self._build()

    def _build(self) -> None:
        c = self.r
        ball = ft.Container(
            width=self.size, height=self.size, bgcolor=_TIP_BALL,
            border=ft.Border.all(2, _DIAL_RING), border_radius=self.r,
        )
        cross_h = ft.Container(width=self.size - 20, height=1,
                               bgcolor=_TIP_CROSS, left=10, top=c - 0.5)
        cross_v = ft.Container(width=1, height=self.size - 20,
                               bgcolor=_TIP_CROSS, left=c - 0.5, top=10)
        hub = ft.Container(width=6, height=6, bgcolor=_TIP_CROSS,
                           border_radius=3, left=c - 3, top=c - 3)
        self._dot = ft.Container(
            width=15, height=15, bgcolor=_TIP_DOT, border_radius=7.5,
            border=ft.Border.all(2, "#FFFFFF"), left=c - 7.5, top=c - 7.5,
        )
        self._stack = ft.Stack(
            [ball, cross_h, cross_v, hub, self._dot],
            width=self.size, height=self.size,
        )
        self.control = ft.GestureDetector(
            content=self._stack,
            on_tap_down=self._drag,
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
        # 屏幕 y 向下，圆盘上方才是高杆
        a, s = clamp_tip(-y / self.rr, x / self.rr)
        if abs(a - self.top) < 1e-4 and abs(s - self.side) < 1e-4:
            return
        self.top, self.side = a, s
        self._place()
        if self.on_change is not None:
            try:
                self.on_change(self.top, self.side)
            except Exception:                 # noqa: BLE001
                pass

    def _place(self) -> None:
        self._dot.left = self.r + self.side * self.rr - 7.5
        self._dot.top = self.r - self.top * self.rr - 7.5

    def set_spin(self, top: float, side: float) -> None:
        """外部（预设按钮 / 出杆后归中）直接设定杆法并刷新，不触发回调。"""
        self.top, self.side = clamp_tip(top, side)
        self._place()

    def reset(self) -> None:
        """回到中杆。"""
        self.set_spin(0.0, 0.0)

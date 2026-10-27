# -*- coding: utf-8 -*-
"""球桌画面：球桌贴图、球、瞄准线，以及拖拽手势。

为什么用绝对定位的 ``Container``
--------------------------------
台球的球是**连续坐标**，不是网格 —— 球要在两个格子之间。所以这里不用
方格布局，而是把每颗球画成一个 ``left/top`` 定位的图片控件，每帧只改
``left/top`` 两个数字。

贴图与物理坐标怎么对上
----------------------
物理坐标只覆盖球桌贴图里的**绿色台面区**（1087×565，见
:mod:`games.billiards.assets`）。这里把整张贴图按比例缩放，再往左上角
挪一个台面区的偏移，于是「球心坐标」和「贴图像素」是同一套坐标 ——
球进袋的时候，看起来就是掉进贴图上那个黑袋口里。

为什么用 ``GestureDetector``
----------------------------
flet 1.0 的 ``Container`` 没有 ``on_pan_*``，拖拽手势统一走
``ft.GestureDetector``（``on_pan_start`` / ``on_pan_update`` / ``on_pan_end``），
事件的 ``local_position`` 就是相对这个手势层左上角的坐标 —— 正好等于
物理坐标系，一一对应，不用任何换算。

本文件只管「画」和「把手势转出去」，不碰规则。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import flet as ft

from .assets import (
    TABLE_GREEN, TABLE_IMAGE, TABLE_IMAGE_SIZE, ball_image_src,
)
from .engine import BilliardsEngine
from .physics import Ball

# ============================================================
# 配色
# ============================================================

FELT_EDGE = "#2E8B57"     # 开球线
GUIDE = "#FFFFFF"         # 瞄准线
CUE_MARK = "#FFFFFF99"    # 母球标记点

MAX_AIM_DOTS = 22         # 瞄准线最多几个点


def _xy(event) -> Tuple[float, float]:
    """从手势事件里取出相对坐标（容错：拿不到就当 0,0）。"""
    pos = getattr(event, "local_position", None)
    if pos is None:
        return (0.0, 0.0)
    try:
        return (float(pos.x), float(pos.y))
    except Exception:       # noqa: BLE001 — 事件结构变了就当没拖
        return (0.0, 0.0)


class TableView:
    """把引擎里的球画到屏幕上，并把拖拽手势转发给对局页。"""

    def __init__(self, engine: BilliardsEngine,
                 on_pan_start: Callable[[float, float], None],
                 on_pan_update: Callable[[float, float], None],
                 on_pan_end: Callable[[float, float], None]):
        self.engine = engine
        self._cb_start = on_pan_start
        self._cb_update = on_pan_update
        self._cb_end = on_pan_end
        self._balls: Dict[int, ft.Container] = {}
        self._aim_dots: List[ft.Container] = []
        self._stack: Optional[ft.Stack] = None
        self._pending: List[ft.Container] = []   # 球桌还没建好时先攒着

    # ============================================================
    # 组装
    # ============================================================

    def build(self) -> ft.Control:
        """搭出整张球桌（贴图 + 开球线 + 球 + 瞄准线）。"""
        t = self.engine.table
        # 贴图像素 → 本机像素
        art = t.width / TABLE_GREEN[2]
        img_w = TABLE_IMAGE_SIZE[0] * art
        img_h = TABLE_IMAGE_SIZE[1] * art
        off_x = TABLE_GREEN[0] * art
        off_y = TABLE_GREEN[1] * art

        layers: List[ft.Control] = []
        # 球桌贴图（比台面大一圈，往左上角挪回台面区）
        layers.append(ft.Image(
            src=TABLE_IMAGE, width=img_w, height=img_h,
            left=-off_x, top=-off_y, fit=ft.BoxFit.FILL,
        ))
        # 开球线 + 母球标记点（台面 1/4 处）
        layers.append(ft.Container(left=t.head_x - 0.5, top=0, width=1,
                                   height=t.height, bgcolor=FELT_EDGE))
        layers.append(ft.Container(left=t.head_x - 3, top=t.head_y - 3,
                                   width=6, height=6, bgcolor=CUE_MARK,
                                   border_radius=3))

        self._stack = ft.Stack(controls=layers, width=t.width,
                               height=t.height,
                               clip_behavior=ft.ClipBehavior.NONE)
        # 球桌建好之前就画好的球（如果有）补进来
        if self._pending:
            self._stack.controls.extend(self._pending)
            self._pending = []

        # 瞄准线用的点（预先建好，按力度显示几个）
        for _ in range(MAX_AIM_DOTS):
            dot = ft.Container(width=5, height=5, bgcolor=GUIDE,
                               border_radius=2.5, visible=False)
            self._aim_dots.append(dot)
            self._stack.controls.append(dot)

        detector = ft.GestureDetector(
            content=self._stack,
            on_pan_start=self._pan_start,
            on_pan_update=self._pan_update,
            on_pan_end=self._pan_end,
        )
        # 外面留一圈木头库边的位置（贴图自己会画出来，这里只占位）
        pad_l = TABLE_GREEN[0] * art
        pad_t = TABLE_GREEN[1] * art
        pad_r = (TABLE_IMAGE_SIZE[0] - TABLE_GREEN[0] - TABLE_GREEN[2]) * art
        pad_b = (TABLE_IMAGE_SIZE[1] - TABLE_GREEN[1] - TABLE_GREEN[3]) * art
        return ft.Container(
            padding=ft.Padding.only(left=pad_l, top=pad_t,
                                    right=pad_r, bottom=pad_b),
            content=detector,
        )

    # ============================================================
    # 手势
    # ============================================================

    def _pan_start(self, e):
        x, y = _xy(e)
        self._cb_start(x, y)

    def _pan_update(self, e):
        x, y = _xy(e)
        self._cb_update(x, y)

    def _pan_end(self, e):
        x, y = _xy(e)
        self._cb_end(x, y)

    # ============================================================
    # 画面刷新
    # ============================================================

    def sync(self) -> None:
        """按引擎里的球刷新画面（球的位置 / 出现 / 消失）。"""
        for ball in self.engine.balls:
            ctrl = self._balls.get(ball.number)
            if ctrl is None:
                ctrl = self._make_ball(ball)
                self._balls[ball.number] = ctrl
                if self._stack is not None:
                    self._stack.controls.append(ctrl)
                else:
                    self._pending.append(ctrl)
            ctrl.left = ball.x - ball.radius
            ctrl.top = ball.y - ball.radius
            ctrl.visible = ball.active
        self._sync_aim()

    def _make_ball(self, ball: Ball) -> ft.Container:
        """画一颗球（用 assets 里的球贴图）。"""
        d = ball.radius * 2
        img = ft.Image(src=ball_image_src(ball.number), width=d, height=d,
                       fit=ft.BoxFit.CONTAIN)
        return ft.Container(width=d, height=d, content=img)

    # ============================================================
    # 瞄准线
    # ============================================================

    def set_aim(self, cx: float, cy: float, dx: float, dy: float,
                power: float) -> None:
        """显示瞄准线：从母球沿击球方向点一串点，长度随力度变。"""
        step = max(10.0, self.engine.table.ball_radius * 1.5)
        count = int(min(MAX_AIM_DOTS, max(1, round(power * MAX_AIM_DOTS))))
        for i, dot in enumerate(self._aim_dots):
            if i < count:
                d = step * (i + 1)
                dot.left = cx + dx * d - 2.5
                dot.top = cy + dy * d - 2.5
                dot.visible = True
                dot.opacity = max(0.25, 1.0 - i / (count + 2))
            else:
                dot.visible = False

    def clear_aim(self) -> None:
        """收起瞄准线。"""
        for dot in self._aim_dots:
            dot.visible = False

    def _sync_aim(self) -> None:
        """球动了以后把瞄准线一起挪走（保持贴着母球）。"""
        for dot in self._aim_dots:
            if dot.visible and dot.left is None:
                dot.visible = False

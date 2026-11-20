# -*- coding: utf-8 -*-
"""弹球台画面：``ft.Stack`` 绝对定位的静态装饰 + 动态球 / 挡板。

为什么用绝对定位的 Container
----------------------------
球是连续坐标，不是网格，所以跟台球一样用 ``left/top`` 定位；每帧只改
两个数字，不重建控件树。挡板是一条会转动的线段，Flet 的旋转控件定位
比较绕，这里把每片挡板离散成 7 个圆点，按角度插值摆位 —— 视觉上就是
一根圆头胶囊，碰撞判定仍用引擎里的**线段**，两者完全对得上。

缩放
----
物理世界固定 ``400×640``，渲染层统一乘 ``scale``。窗口尺寸变化时不碰
引擎，只调 ``rebuild(scale)`` 重画静态装饰并更新动态控件的尺寸。
"""

from __future__ import annotations

from typing import Dict, List

import flet as ft

from core.i18n import t
from core.theme import T

from .engine import (
    BALL_R, BUMPER_SPEC, CHANNEL_X, FLIPPER_HALF_W, GATE_Y, OVER,
    SLING_SPEC, WALL, WORLD_H, WORLD_W, PinballEngine,
)

# ---------- 复古霓虹配色（台面固定深色，与明暗主题无关） ----------
BG = "#0B1020"
WALL_COLOR = "#263859"
GUIDE = "#4FC3F7"
BUMPER_COLORS = ("#FF5252", "#FFC107", "#40C4FF", "#69F0AE", "#E040FB")
BUMPER_EDGE = "#FFFFFF"
FLIPPER_COLOR = "#FFB300"
SLING_COLOR = "#7C4DFF"
BALL_COLOR = "#FAFAFA"
DRAIN_COLOR = "#161B2E"
# 发射道单向门：青色 = 开着（球可经导轨进入主区），橙色 = 已关闭
GATE_OPEN = GUIDE
GATE_CLOSED = "#FF7043"

FLIPPER_DOTS = 7
POWER_H = 140.0             # 蓄力条最大高度（世界坐标）


class TableView:
    """把引擎状态画到台面上；``sync()`` 每帧调用，``rebuild()`` 缩放时调用。"""

    def __init__(self, engine: PinballEngine):
        self.engine = engine
        self.scale = 1.0
        self.stack = ft.Stack(clip_behavior=ft.ClipBehavior.HARD_EDGE)
        self.stage = ft.Container(
            bgcolor=BG,
            border=ft.Border.all(2, WALL_COLOR),
            border_radius=8,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=self.stack,
        )
        self.ball_ctrl: ft.Container | None = None
        self._flip_dots: Dict[str, List[ft.Container]] = {}
        self.power_fill: ft.Container | None = None
        self.overlay: ft.Container | None = None
        self.overlay_text: ft.Text | None = None
        self.gate_ctrl: ft.Container | None = None
        self.gate_text: ft.Text | None = None

    # ---------- 静态零件 ----------

    def _dot(self, x: float, y: float, radius: float,
             color: str, s: float) -> ft.Container:
        return ft.Container(
            left=(x - radius) * s, top=(y - radius) * s,
            width=2 * radius * s, height=2 * radius * s,
            border_radius=radius * s, bgcolor=color,
        )

    def _segment_dots(self, ax: float, ay: float, bx: float, by: float,
                      radius: float, color: str, count: int,
                      s: float) -> List[ft.Container]:
        """用一串小圆点画一条斜线（避开 Flet 旋转控件的定位问题）。"""
        return [self._dot(ax + (bx - ax) * i / (count - 1),
                          ay + (by - ay) * i / (count - 1),
                          radius, color, s)
                for i in range(count)]

    def rebuild(self, scale: float) -> ft.Control:
        """按新缩放重画整张台面（返回可放进页面的 stage）。"""
        s = self.scale = max(0.4, float(scale))
        w, h = WORLD_W * s, WORLD_H * s
        self.stage.width = w
        self.stage.height = h
        self.stack.width = w
        self.stack.height = h

        layers: List[ft.Control] = [
            ft.Container(width=w, height=h, bgcolor=BG),
            # 底部漏球区
            ft.Container(left=0, top=(WORLD_H - 28) * s, width=w,
                         height=28 * s, bgcolor=DRAIN_COLOR),
            # 顶部 / 左右外墙
            ft.Container(left=0, top=0, width=w, height=WALL * s,
                         bgcolor=WALL_COLOR),
            ft.Container(left=0, top=0, width=WALL * s, height=h,
                         bgcolor=WALL_COLOR),
            ft.Container(left=(WORLD_W - WALL) * s, top=0,
                         width=WALL * s, height=h, bgcolor=WALL_COLOR),
            # 发射通道隔墙：全高有效，只在导轨口留一道缺口给单向活门
            ft.Container(left=(CHANNEL_X - 2) * s, top=0,
                         width=4 * s, height=(GATE_Y - 14) * s,
                         bgcolor=WALL_COLOR),
            ft.Container(left=(CHANNEL_X - 2) * s, top=GATE_Y * s,
                         width=4 * s, height=(WORLD_H - GATE_Y) * s,
                         bgcolor=WALL_COLOR),
            # 顶部单向导轨的提示线
            ft.Container(left=(CHANNEL_X - 46) * s, top=(GATE_Y - 6) * s,
                         width=46 * s, height=3 * s, bgcolor=GUIDE),
            ft.Container(left=CHANNEL_X * s, top=(GATE_Y - 6) * s,
                         width=(WORLD_W - WALL - CHANNEL_X) * s,
                         height=3 * s, bgcolor=GUIDE),
            # 台面铭牌
            ft.Container(
                left=0, top=(GATE_Y + 16) * s, width=w, height=28 * s,
                alignment=ft.Alignment.CENTER,
                content=ft.Text("A T R   P I N B A L L", size=max(9.0, 13 * s),
                                color="#38507A", weight=ft.FontWeight.BOLD),
            ),
        ]

        # 单向活门：球经导轨进入主区后立刻「关门」（引擎 in_play 决定颜色）
        self.gate_text = ft.Text("←", size=max(9.0, 11 * s), color=BG,
                                 weight=ft.FontWeight.BOLD,
                                 text_align=ft.TextAlign.CENTER)
        self.gate_ctrl = ft.Container(
            left=(CHANNEL_X - 22) * s, top=(GATE_Y - 15) * s,
            width=24 * s, height=12 * s,
            border_radius=2 * s, bgcolor=GATE_OPEN,
            alignment=ft.Alignment.CENTER, content=self.gate_text,
        )
        layers.append(self.gate_ctrl)

        # 保险杠 / 小目标
        for i, (x, y, r, _pts, _kick) in enumerate(BUMPER_SPEC):
            layers.append(ft.Container(
                left=(x - r) * s, top=(y - r) * s,
                width=2 * r * s, height=2 * r * s,
                border_radius=r * s,
                bgcolor=BUMPER_COLORS[i % len(BUMPER_COLORS)],
                border=ft.Border.all(max(1.0, 2 * s), BUMPER_EDGE),
                alignment=ft.Alignment.CENTER,
                content=ft.Text("★" if r > 20 else "",
                                size=max(8.0, r * s * 0.8),
                                color=BG, weight=ft.FontWeight.BOLD),
            ))
        # 两侧斜墙
        for ax, ay, bx, by in SLING_SPEC:
            layers.extend(self._segment_dots(
                ax, ay, bx, by, 5.0, SLING_COLOR, 9, s))

        # ---- 动态控件 ----
        self.ball_ctrl = ft.Container(
            width=2 * BALL_R * s, height=2 * BALL_R * s,
            border_radius=BALL_R * s, bgcolor=BALL_COLOR,
            border=ft.Border.all(max(1.0, 1.5 * s), "#90A4AE"),
        )
        layers.append(self.ball_ctrl)

        self._flip_dots = {}
        for f in self.engine.flippers:
            dots = [self._dot(0.0, 0.0, FLIPPER_HALF_W, FLIPPER_COLOR, s)
                    for _ in range(FLIPPER_DOTS)]
            self._flip_dots[f.side] = dots
            layers.extend(dots)

        power_x = (WORLD_W - WALL - 7) * s
        layers.append(ft.Container(
            left=power_x, top=(WORLD_H - 30 - POWER_H) * s,
            width=5 * s, height=POWER_H * s,
            border_radius=3 * s, bgcolor="#263859",
        ))
        self.power_fill = ft.Container(
            left=power_x, top=(WORLD_H - 30) * s,
            width=5 * s, height=0.0,
            border_radius=3 * s, bgcolor=T.ACCENT,
        )
        layers.append(self.power_fill)

        self.overlay_text = ft.Text(
            "", size=max(12.0, 17 * s), color="#FFFFFF",
            weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER,
        )
        self.overlay = ft.Container(
            left=0, top=0, width=w, height=h,
            bgcolor=ft.Colors.with_opacity(0.62, "#000000"),
            alignment=ft.Alignment.CENTER,
            content=self.overlay_text, visible=False,
        )
        layers.append(self.overlay)

        self.stack.controls = layers
        return self.stage

    # ---------- 每帧刷新 ----------

    def sync(self) -> None:
        """把球 / 挡板 / 蓄力条 / 提示层刷到最新（只改属性，不重建控件）。"""
        if self.ball_ctrl is None or self.overlay is None:
            return
        e = self.engine
        s = self.scale
        b = e.ball
        self.ball_ctrl.left = (b.x - b.r) * s
        self.ball_ctrl.top = (b.y - b.r) * s

        for f in e.flippers:
            dots = self._flip_dots.get(f.side, [])
            tx, ty = f.tip()
            for i, dot in enumerate(dots):
                u = i / (len(dots) - 1)
                px = f.px + (tx - f.px) * u
                py = f.py + (ty - f.py) * u
                dot.left = (px - FLIPPER_HALF_W) * s
                dot.top = (py - FLIPPER_HALF_W) * s

        power = max(0.0, min(1.0, e.state.power))
        if self.power_fill is not None:
            self.power_fill.height = POWER_H * power * s
            self.power_fill.top = (WORLD_H - 30 - POWER_H * power) * s

        st = e.state
        if self.gate_ctrl is not None and self.gate_text is not None:
            closed = st.in_play
            self.gate_ctrl.bgcolor = GATE_CLOSED if closed else GATE_OPEN
            self.gate_text.color = "#FFFFFF" if closed else BG
            self.gate_text.value = "×" if closed else "←"
        if st.status == OVER:
            text = (t("pinball.over", default="游戏结束")
                    + f"\n{t('pinball.score', default='分数')} {st.score}"
                    + f"\n{t('pinball.restart_hint', default='R / 重开 再来一局')}")
        elif st.paused:
            text = t("pinball.paused", default="已暂停")
        elif st.waiting:
            text = (t("pinball.charging", default="蓄力中…")
                    if st.charging else
                    t("pinball.launch_hint",
                      default="按住「发射」蓄力，松手弹射\n空格键按下即自动蓄力发射"))
        else:
            text = ""
        self.overlay.visible = bool(text)
        self.overlay_text.value = text

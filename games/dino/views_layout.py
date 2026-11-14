# -*- coding: utf-8 -*-
"""页面组装：宽屏 / 窄屏两套排版 + 自适应缩放（手机端兼容）。"""

from __future__ import annotations

import flet as ft

from core import responsive
from core.i18n import t
from core.theme import T
from core.ui_common import app_bar, page_padding, tap_button

from .engine import WORLD_H, WORLD_W

NARROW_W = 620         # 小于这个宽度按「手机竖屏」处理


class LayoutMixin:
    """页面组装：舞台、信息栏、操作键怎么摆。"""

    # ---------- 自适应缩放 ----------

    def _layout(self) -> None:
        """按宽高一起算舞台缩放（宽屏放大、窄屏缩小，且不出屏幕）。"""
        w, h = responsive.size(self.page)
        plat = str(getattr(self.page, "platform", "") or "").lower()
        self._touch = (w < NARROW_W) or plat in ("android", "ios")
        if self._touch:
            # 手机竖屏：扣掉标题栏、信息条、操作键和留白
            avail_w = w - 32.0
            avail_h = h - 56.0 - 64.0 - 150.0 - 40.0
        else:
            # 宽屏：舞台占剩余宽度（减去右侧信息栏约 220 + 留白）
            avail_w = (w - 260.0) - 40.0
            avail_h = h - 56.0 - 40.0
        scale = min(avail_w / WORLD_W, avail_h / WORLD_H)
        self.scale = max(2.0, min(scale, 18.0))
        self._apply_stage_size()

    # ---------- 控件小工具 ----------

    def _build_side(self) -> ft.Control:
        """宽屏：右侧信息栏。"""
        return ft.Column(
            [ft.Text(t("dino.title", default="小恐龙"),
                     size=16, weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY),
             ft.Container(height=8),
             ft.Column([ft.Text(t("dino.score", default="分数"), size=11,
                               color=T.TEXT_MUTED), self.score_text], spacing=0),
             ft.Container(height=6),
             ft.Column([ft.Text(t("dino.best", default="最高"), size=11,
                               color=T.TEXT_MUTED), self.best_text], spacing=0),
             ft.Container(height=6),
             ft.Column([ft.Text(t("dino.speed", default="速度"), size=11,
                               color=T.TEXT_MUTED), self.speed_text], spacing=0),
             ft.Container(height=6),
             self.status_text,
             ft.Container(height=6),
             self.pause_btn,
             tap_button(t("dino.restart", default="重开"),
                        lambda _e: self._restart())],
            spacing=4, width=200,
        )

    def _build_strip(self) -> ft.Control:
        """窄屏：顶部一条信息 + 暂停 / 重开。"""
        score_col = ft.Column([ft.Text(t("dino.score", default="分数"), size=10,
                                      color=T.TEXT_MUTED), self.score_text],
                             spacing=0)
        best_col = ft.Column([ft.Text(t("dino.best", default="最高"), size=10,
                                     color=T.TEXT_MUTED), self.best_text],
                            spacing=0)
        speed_col = ft.Column([ft.Text(t("dino.speed", default="速度"), size=10,
                                      color=T.TEXT_MUTED), self.speed_text],
                            spacing=0)
        return ft.Row(
            [score_col, best_col, speed_col, self.status_text,
             self.pause_btn,
             tap_button(t("dino.restart", default="重开"),
                        lambda _e: self._restart())],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
            run_spacing=6,
        )

    # ---------- 组装整页 ----------

    def build(self) -> ft.Control:
        self._layout()
        self._render()
        self._attach()

        # 舞台外层包一层手势：点击跳，下滑蹲。
        # on_tap 是点击跳跃的兜底（on_tap_up 在手势竞争时可能不触发），
        # on_tap_cancel 负责清理拖动状态；_PlayPage 内部做了同次点击去重。
        stage_touch = ft.GestureDetector(
            content=self.stage,
            on_tap=self._on_stage_tap,
            on_tap_down=self._swipe_start,
            on_tap_up=self._swipe_end,
            on_tap_cancel=self._swipe_cancel,
        )

        if self._touch:
            body = ft.Column(
                [self._build_strip(), ft.Container(height=6), stage_touch,
                 ft.Container(height=10), self.pad.build(),
                 ft.Text(t("dino.touch_hint",
                           default="点击/轻滑跳，下滑蹲；下方按键可连发"),
                         size=10, color=T.TEXT_MUTED)],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
            )
        else:
            body = ft.Row(
                [stage_touch, ft.Container(width=20), self._build_side()],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )

        def _back(_e):
            self._detach()
            self.navigate("/g/dino")

        return ft.Column(
            [app_bar(t("route.dino.play", default="小恐龙 · 对局"),
                     on_back=_back),
             page_padding(body)],
            expand=True,
        )

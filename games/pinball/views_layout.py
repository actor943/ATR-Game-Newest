# -*- coding: utf-8 -*-
"""弹球机对局页的「组装」那一半：宽屏 / 窄屏两套排版 + 台面缩放。

拆成 mixin 是为了守住「单文件不超过 500 行」的规矩（见 CODE_INDEX.md）：

* :mod:`games.pinball.views_board` —— 台面画面（静态装饰 + 动态控件）
* :mod:`games.pinball.views_pad` —— 手机端操作键
* :mod:`games.pinball.views_play` —— 引擎、输入、主循环、落盘
* 本文件 —— 把台面、信息栏、操作键拼成页面
"""

from __future__ import annotations

import flet as ft

from core import responsive
from core.i18n import t
from core.theme import T
from core.ui_common import app_bar, page_padding, tap_button

from .engine import WORLD_H, WORLD_W

NARROW_W = 620         # 小于这个宽度按「手机竖屏」处理


class LayoutMixin:
    """页面组装：台面、信息栏、操作键怎么摆。"""

    # ---------- 自适应缩放 ----------

    def _layout(self) -> None:
        """按宽高一起算台面缩放（宽屏放大、窄屏缩小，且不出屏幕）。"""
        w, h = responsive.size(self.page)
        plat = str(getattr(self.page, "platform", "") or "").lower()
        self._touch = (w < NARROW_W) or plat in ("android", "ios")
        if self._touch:
            # 手机竖屏：扣掉顶栏、信息条、底部操作键与留白
            avail_w = w - 32.0
            avail_h = h - 56.0 - 64.0 - 150.0 - 24.0
        else:
            # 宽屏：台面 + 右侧信息栏
            avail_w = w - 32.0 - 16.0 - 210.0
            avail_h = h - 56.0 - 40.0
        scale = min(avail_w / WORLD_W, avail_h / WORLD_H)
        self.scale = max(0.45, min(1.6, scale))

    # ---------- 控件小工具 ----------

    def _restart_button(self) -> ft.Control:
        return tap_button(t("pinball.restart", default="重开"),
                          lambda _e: self._act("restart"),
                          size=13, width=76, height=34)

    def _info_col(self, label: str, value: ft.Text) -> ft.Control:
        return ft.Column(
            [ft.Text(label, size=11, color=T.TEXT_MUTED), value],
            spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # ---------- 宽屏：右侧信息栏 ----------

    def _build_side(self) -> ft.Control:
        return ft.Column(
            [
                ft.Text(t("route.pinball", default="弹球机"), size=16,
                        weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY),
                ft.Container(height=10),
                ft.Text(t("pinball.score", default="分数"), size=12,
                        color=T.TEXT_MUTED),
                self.score_text,
                ft.Container(height=8),
                ft.Text(t("pinball.best", default="最高分"), size=12,
                        color=T.TEXT_MUTED),
                self.best_text,
                ft.Container(height=8),
                ft.Text(t("pinball.balls", default="剩余球"), size=12,
                        color=T.TEXT_MUTED),
                self.balls_text,
                ft.Container(height=10),
                self.status_text,
                self.message_text,
                ft.Container(height=10),
                ft.Row([self.pause_btn, ft.Container(width=6),
                        self._restart_button()],
                       spacing=4, wrap=True, run_spacing=6),
                ft.Container(height=10),
                ft.Text(t("pinball.keyboard_hint",
                          default="←/→ 或 A/D 拍挡板，空格蓄力发射"),
                        size=11, color=T.TEXT_MUTED),
                ft.Text(t("pinball.touch_hint",
                          default="P 暂停 · R 重开 · 手机用底部按键"),
                        size=11, color=T.TEXT_MUTED),
            ],
            spacing=2, width=200,
        )

    # ---------- 窄屏：顶部信息条 ----------

    def _build_strip(self) -> ft.Control:
        return ft.Row(
            [self._info_col(t("pinball.score", default="分数"),
                            self.score_text),
             self._info_col(t("pinball.best", default="最高"),
                            self.best_text),
             self._info_col(t("pinball.balls", default="球"),
                            self.balls_text),
             self.status_text,
             self.pause_btn,
             self._restart_button()],
            spacing=10, wrap=True, run_spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # ---------- 整页 ----------

    def build(self) -> ft.Control:
        self._layout()
        stage = self.table.rebuild(self.scale)
        self._refresh()
        self._attach()

        if self._touch:
            body = ft.Column(
                [self._build_strip(), ft.Container(height=6), stage,
                 ft.Container(height=10), self.pad.build(),
                 self.message_text,
                 ft.Text(t("pinball.touch_hint",
                           default="P 暂停 · R 重开 · 手机用底部按键"),
                         size=10, color=T.TEXT_MUTED)],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
            )
        else:
            body = ft.Row(
                [stage, ft.Container(width=18), self._build_side()],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )

        def _back(_e):
            self._detach()
            self.navigate("/g/pinball")

        return ft.Column(
            [app_bar(t("route.pinball.play", default="弹球机 · 对局"),
                     on_back=_back),
             page_padding(body)],
            expand=True,
        )

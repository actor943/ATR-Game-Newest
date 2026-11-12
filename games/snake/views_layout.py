# -*- coding: utf-8 -*-
"""贪吃蛇对局页的「组装」那一半：宽屏 / 窄屏两套排版。

拆成 mixin 是为了守住「单文件不超过 500 行」的规矩（见 CODE_INDEX.md）：

* :mod:`games.snake.views_play` —— 引擎、渲染、输入、主循环
* :mod:`games.snake.views_pad` —— 触屏操作键
* 本文件 —— 把上面那些拼成页面（宽屏：棋盘 + 右侧信息栏；
  窄屏：顶部信息条 + 棋盘 + 底部操作键）
"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.theme import T
from core.ui_common import app_bar, page_padding, tap_button


class LayoutMixin:
    """页面组装：棋盘、信息栏、操作键怎么摆。"""

    # ---------- 控件小工具 ----------

    def _speed_control(self) -> ft.Control:
        """速度 − / 数字 / +（变速功能的手动入口）。

        减 / 加快捷键用 ``tap_button``（不可获焦）：方向键只给游戏，不跳按钮。
        """
        minus = tap_button("－", lambda _e: self._set_speed(-1),
                           size=16, width=40, height=34,
                           text_color=T.TEXT_PRIMARY)
        plus = tap_button("＋", lambda _e: self._set_speed(+1),
                          size=16, width=40, height=34,
                          text_color=T.TEXT_PRIMARY)
        return ft.Row(
            [minus, self.speed_text, plus],
            spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # ---------- 组装 ----------

    def _build_board(self) -> ft.Control:
        """棋盘（黑底 + 暗绿网格 + 滑动手势）。"""
        board = ft.Container(
            bgcolor="#000000",
            border=ft.Border.all(2, COLOR_BOARD_BORDER),
            padding=ft.Padding.all(2),
            content=ft.GestureDetector(
                content=self.board_host,
                on_pan_start=self._swipe_start,
                on_pan_end=self._swipe_end,
            ),
        )
        return board

    def _build_side(self) -> ft.Control:
        """宽屏右侧的信息栏。"""
        return ft.Column(
            [
                ft.Text(t("snake.score", default="分数"), size=12,
                        color=T.TEXT_MUTED),
                self.score_text,
                ft.Container(height=8),
                ft.Text(t("snake.best", default="最高分"), size=12,
                        color=T.TEXT_MUTED),
                self.best_text,
                ft.Container(height=8),
                ft.Text(t("snake.speed", default="速度（1~10）"), size=12,
                        color=T.TEXT_MUTED),
                self._speed_control(),
                ft.Container(height=8),
                self.status_text,
                ft.Container(height=6),
                self.pause_btn,
                tap_button(t("snake.restart", default="重开"),
                           lambda _e: self._restart()),
                ft.Container(height=6),
                ft.Text(t("snake.keyboard_hint",
                          default="方向键 / WASD 转向，空格或 P 暂停，R 重开"),
                        size=11, color=T.TEXT_MUTED),
                ft.Text(t("snake.speed_hint",
                          default="吃食物会自然加速，也可手动 ± 调速"),
                        size=11, color=T.TEXT_MUTED),
            ],
            spacing=2,
        )

    def _build_strip(self) -> ft.Control:
        """窄屏顶部的一条信息（分数 / 最高分 / 速度 / 暂停 / 重开）。"""
        score_col = ft.Column([
            ft.Text(t("snake.score", default="分数"), size=11,
                    color=T.TEXT_MUTED),
            self.score_text,
        ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        best_col = ft.Column([
            ft.Text(t("snake.best", default="最高分"), size=11,
                    color=T.TEXT_MUTED),
            self.best_text,
        ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        speed_col = ft.Column([
            ft.Text(t("snake.speed", default="速度"), size=11,
                    color=T.TEXT_MUTED),
            self.speed_text,
        ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        return ft.Row(
            [score_col, best_col, speed_col,
             self.pause_btn,
             tap_button(t("snake.restart", default="重开"),
                        lambda _e: self._restart())],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
            run_spacing=6,
        )

    def build(self) -> ft.Control:
        """搭出整页。"""
        self._layout()
        self._build_grid()
        self._refresh()
        self._attach()

        board = self._build_board()
        if self._touch:
            # 手机：信息压成顶部一条，操作键放底部
            body = ft.Column(
                [self._build_strip(), ft.Container(height=6), board,
                 ft.Container(height=10), self.pad.build(),
                 ft.Text(t("snake.touch_hint",
                           default="滑动棋盘也能转向；下方按键可连发"),
                         size=10, color=T.TEXT_MUTED)],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
            )
        else:
            body = ft.Row(
                [board, ft.Container(width=18), self._build_side()],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )

        def _back(_e):
            self._detach()
            self.navigate("/g/snake")

        return ft.Column(
            [app_bar(t("route.snake.play", default="贪吃蛇 · 对局"),
                     on_back=_back),
             page_padding(body)],
            expand=True,
        )


# 棋盘外框颜色（与渲染层棋盘黑底呼应）
COLOR_BOARD_BORDER = "#1B5E20"

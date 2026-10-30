# -*- coding: utf-8 -*-
"""俄罗斯方块对局页的「组装」那一半：宽屏 / 窄屏两套排版。

拆成 mixin 是为了守住「单文件不超过 500 行」的规矩（见 CODE_INDEX.md）：

* :mod:`games.tetris.views_play` —— 引擎、渲染、输入、主循环
* :mod:`games.tetris.views_pad` —— 触屏操作键
* 本文件 —— 把上面那些拼成页面（宽屏：棋盘 + 右侧信息栏；
  窄屏：顶部信息条 + 棋盘 + 底部操作键）
"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.theme import T
from core.ui_common import app_bar, page_padding


class LayoutMixin:
    """页面组装：棋盘、信息栏、操作键怎么摆。"""

    # ---------- 组装 ----------

    def _build_board(self) -> ft.Control:
        """棋盘（带滑动手势）。"""
        board = ft.Container(
            bgcolor=T.SURFACE,
            border=ft.Border.all(1, T.BORDER),
            padding=ft.Padding.all(4),
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
                ft.Text(t("tetris.next", default="下一块"), size=12,
                        color=T.TEXT_MUTED),
                ft.Column(self._mini_next_widgets, spacing=6),
                ft.Container(height=10),
                ft.Text(t("tetris.hold", default="暂存"), size=12,
                        color=T.TEXT_MUTED),
                self._mini_hold_widget,
                ft.Container(height=10),
                ft.Text(t("tetris.score", default="分数"), size=12,
                        color=T.TEXT_MUTED),
                self.score_text,
                ft.Row([
                    ft.Text(t("tetris.level", default="等级"), size=11),
                    self.level_text,
                    ft.Text(t("tetris.lines", default="消行"), size=11),
                    self.lines_text,
                ], spacing=6),
                ft.Container(height=8),
                self.status_text,
                ft.Button(
                    content=ft.Text(t("tetris.restart", default="重开")),
                    on_click=lambda _e: self._restart(),
                ),
                ft.Container(height=6),
                ft.Text(t("tetris.keyboard_hint",
                          default="方向键移动 / 旋转，空格硬降，C 暂存"),
                        size=11, color=T.TEXT_MUTED),
            ],
            spacing=4,
        )

    def _build_strip(self) -> ft.Control:
        """窄屏顶部的一条信息（下一块 / 暂存 / 分数 / 重开）。"""
        next_col = ft.Column([
            ft.Text(t("tetris.next", default="下一块"), size=11,
                    color=T.TEXT_MUTED),
            self._mini_next_widgets[0],
        ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        hold_col = ft.Column([
            ft.Text(t("tetris.hold", default="暂存"), size=11,
                    color=T.TEXT_MUTED),
            self._mini_hold_widget,
        ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        score_col = ft.Column([
            ft.Row([
                ft.Text(t("tetris.score", default="分数"), size=11),
                self.score_text,
            ], spacing=4),
            ft.Row([
                ft.Text(t("tetris.level", default="等级"), size=11),
                self.level_text,
                ft.Text(t("tetris.lines", default="消行"), size=11),
                self.lines_text,
            ], spacing=4),
        ], spacing=2)
        return ft.Row(
            [next_col, hold_col, score_col,
             ft.Button(content=ft.Text(t("tetris.restart", default="重开")),
                       on_click=lambda _e: self._restart())],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
            run_spacing=6,
        )

    def build(self) -> ft.Control:
        """搭出整页。"""
        self._layout()
        self._build_grid()
        self._mini_next_widgets = []
        self._mini_next = []
        for _ in range(2):
            widget, grid = self._new_mini()
            self._mini_next_widgets.append(widget)
            self._mini_next.append(grid)
        self._mini_hold_widget, self._mini_hold = self._new_mini()
        self._refresh()
        self._attach()

        board = self._build_board()
        if self._touch:
            # 手机：信息压成顶部一条，操作键放底部
            body = ft.Column(
                [self._build_strip(), ft.Container(height=6), board,
                 ft.Container(height=10), self.pad.build(),
                 ft.Text(t("tetris.touch_hint",
                           default="按住下面的键可以连发，滑动棋盘也能操作"),
                         size=10, color=T.TEXT_MUTED)],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
            )
        else:
            body = ft.Row(
                [board, ft.Container(width=16), self._build_side()],
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )

        def _back(_e):
            self._detach()
            self.navigate("/g/tetris")

        return ft.Column(
            [app_bar(t("route.tetris.play", default="俄罗斯方块 · 对局"),
                     on_back=_back),
             page_padding(body)],
            expand=True,
        )

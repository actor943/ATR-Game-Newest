# -*- coding: utf-8 -*-
"""扫雷对局页的「组装」那一半：宽屏 / 窄屏两套排版。

拆成 mixin 是为了守住「单文件不超过 500 行」的规矩（见 CODE_INDEX.md）：

* :mod:`games.minesweeper.views_board` —— 引擎、格子、输入、计时、落盘；
* 本文件 —— 把棋盘、信息栏、难度 / 插旗按钮拼成页面
  （宽屏：棋盘 + 右侧信息栏；窄屏：顶部信息条 + 棋盘 + 底部按钮）。
"""

from __future__ import annotations

import flet as ft

from core.i18n import t
from core.theme import T
from core.ui_common import app_bar, page_padding, tap_button


class LayoutMixin:
    """页面组装：棋盘、信息栏、按钮怎么摆。"""

    # ---------- 控件小工具 ----------

    def _level_buttons(self) -> ft.Control:
        """三档难度（键盘 1 / 2 / 3 同效）。"""
        keys = (
            ("easy", t("minesweeper.easy", default="初级")),
            ("medium", t("minesweeper.medium", default="中级")),
            ("hard", t("minesweeper.hard", default="高级")),
        )
        return ft.Row(
            [tap_button(label, lambda _e, lv=lv: self._act("level:" + lv),
                        size=12, width=62, height=32)
             for lv, label in keys],
            spacing=6, wrap=True, run_spacing=6,
        )

    def _restart_button(self) -> ft.Control:
        return tap_button(t("minesweeper.restart", default="重开"),
                          lambda _e: self._act("restart"),
                          size=13, width=76, height=34)

    def _info_col(self, label: str, value: ft.Text) -> ft.Control:
        return ft.Column(
            [ft.Text(label, size=11, color=T.TEXT_MUTED), value],
            spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # ---------- 棋盘 ----------

    def _build_board(self) -> ft.Control:
        """棋盘外框；高级 30 列在手机上放不下时，外层 Row 可横向滚动。"""
        board = ft.Container(
            bgcolor="#90A4AE",
            border=ft.Border.all(2, "#90A4AE"),
            padding=ft.Padding.all(2),
            content=self.board_host,
        )
        return ft.Row([board], spacing=0, scroll=ft.ScrollMode.AUTO,
                      vertical_alignment=ft.CrossAxisAlignment.START)

    # ---------- 宽屏：右侧信息栏 ----------

    def _build_side(self) -> ft.Control:
        return ft.Column(
            [
                ft.Text(t("route.minesweeper", default="扫雷"), size=16,
                        weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY),
                self.level_text,
                ft.Container(height=10),
                ft.Text(t("minesweeper.remaining", default="剩余雷数"),
                        size=12, color=T.TEXT_MUTED),
                self.mine_text,
                ft.Container(height=8),
                ft.Text(t("minesweeper.time", default="用时"),
                        size=12, color=T.TEXT_MUTED),
                self.time_text,
                ft.Container(height=8),
                self.status_text,
                ft.Container(height=10),
                ft.Text(t("minesweeper.level", default="难度"),
                        size=12, color=T.TEXT_MUTED),
                self._level_buttons(),
                ft.Container(height=10),
                self.flag_btn,
                ft.Container(height=6),
                self._restart_button(),
                ft.Container(height=10),
                ft.Text(t("minesweeper.keyboard_hint",
                          default="左键翻开 / 右键插旗 · R 重开 · F 插旗 · 1/2/3 换难度"),
                        size=11, color=T.TEXT_MUTED),
                ft.Text(t("minesweeper.howto_desc",
                          default="左键翻开、右键插旗；手机长按或开「插旗模式」；R 重开"),
                        size=11, color=T.TEXT_MUTED),
            ],
            spacing=2, width=200,
        )

    # ---------- 窄屏：顶部信息条 ----------

    def _build_strip(self) -> ft.Control:
        return ft.Column(
            [
                ft.Row(
                    [self._info_col(t("minesweeper.remaining", default="剩余雷数"),
                                    self.mine_text),
                     self._info_col(t("minesweeper.time", default="用时"),
                                    self.time_text),
                     self.level_text,
                     self.status_text],
                    spacing=14, wrap=True, run_spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [self.flag_btn, self._restart_button()],
                    spacing=8, wrap=True, run_spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self._level_buttons(),
            ],
            spacing=6,
        )

    # ---------- 整页 ----------

    def build(self) -> ft.Control:
        self._layout()
        self._build_grid()
        self._refresh()
        self._attach()

        board = self._build_board()
        if self._touch:
            body = ft.Column(
                [self._build_strip(), ft.Container(height=8), board,
                 ft.Text(t("minesweeper.touch_hint",
                           default="长按格子插旗；高级盘可左右滑动查看"),
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
            self.navigate("/g/minesweeper")

        return ft.Column(
            [app_bar(t("route.minesweeper.play", default="扫雷 · 对局"),
                     on_back=_back),
             page_padding(body)],
            expand=True,
        )

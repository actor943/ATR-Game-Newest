# -*- coding: utf-8 -*-
"""对局页：棋盘画面 + 键盘输入 + 主循环（重力/锁定）。

为避免内存泄漏，离开页面时必须 `_detach()`：
* 取消 asyncio 任务；
* 还原 `page.on_keyboard_event`。
"""

from __future__ import annotations

import asyncio
from typing import Optional

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar, page_padding

from .engine import COLS, ROWS, SHAPES, TetrisEngine

CELL = 26          # 单元格边长（像素）


class _PlayPage:
    """一页对局：持有引擎、控件、循环任务。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self.engine = TetrisEngine()
        self._task: Optional[asyncio.Task] = None
        self._prev_keyboard = None
        self._log_saved = False          # 这一局是否已经落过盘

        # 画布：用 Container 网格画（flet 1.0 的 Canvas 交互不便，方格更稳）
        self.board_host = ft.Column(spacing=0)
        self.score_text = ft.Text("0", size=18, weight=ft.FontWeight.BOLD,
                                  color=T.TEXT_PRIMARY)
        self.level_text = ft.Text("1", size=14, color=T.TEXT_SECONDARY)
        self.lines_text = ft.Text("0", size=14, color=T.TEXT_SECONDARY)
        self.next_host = ft.Column(spacing=0)
        self.hold_host = ft.Column(spacing=0)
        self.status_text = ft.Text("", size=12, color=T.DANGER)

    # ---------- 画面 ----------

    def _cell_box(self, color: Optional[str]) -> ft.Container:
        return ft.Container(
            width=CELL, height=CELL,
            bgcolor=color or T.SURFACE_ALT,
            border=ft.Border.all(0.5, T.DIVIDER),
        )

    def _render_board(self):
        """把棋盘 + 活动方块 + 幽灵块画成网格。"""
        board = self.engine.visible_board()          # 去掉隐藏行
        grid = [row[:] for row in board]

        # 幽灵块先画（浅色描边）——用浅色填充近似
        for (r, c) in self.engine.ghost_cells():
            rr = r - 2
            if 0 <= rr < ROWS and grid[rr][c] is None:
                grid[rr][c] = "#CCCCCC"

        # 活动方块覆盖
        piece = self.engine.state.piece
        if piece is not None:
            color = SHAPES[piece.kind][0]
            for (r, c) in piece.cells():
                rr = r - 2
                if 0 <= rr < ROWS:
                    grid[rr][c] = color

        self.board_host.controls = [
            ft.Row([self._cell_box(cell) for cell in row], spacing=0)
            for row in grid
        ]

    def _render_side(self):
        """右侧：下一块、Hold、分数。"""
        def _mini(kind: Optional[str]) -> ft.Control:
            if not kind:
                return ft.Container(height=CELL * 2)
            color = SHAPES[kind][0]
            cells = set(SHAPES[kind][1])
            rows = []
            for r in range(2):
                rows.append(ft.Row(
                    [self._cell_box(color if (r, c) in cells else None)
                     for c in range(4)],
                    spacing=0,
                ))
            return ft.Column(rows, spacing=0)

        q = self.engine.state.next_queue
        self.next_host.controls = [_mini(k) for k in q[:2]]
        self.hold_host.controls = [_mini(self.engine.state.hold)]

        s = self.engine.state
        self.score_text.value = str(s.score)
        self.level_text.value = str(s.level)
        self.lines_text.value = str(s.lines)
        self.status_text.value = t("tetris.over", default="游戏结束") \
            if s.game_over else ""

    def _refresh(self):
        self._render_board()
        self._render_side()
        self.page.update()

    # ---------- 输入 ----------

    # flet 1.0 的按键名是 "ArrowLeft"/"ArrowDown"（驼峰、无空格），
    # 老版本是 "arrow left"（带空格）。两种写法都认，
    # 否则方向键在新版 flet 上完全没反应。
    _KEY_ALIAS = {
        "arrowleft": "left", "arrowright": "right",
        "arrowup": "up", "arrowdown": "down",
        "a": "left", "d": "right", "w": "up", "s": "down",
        " ": "drop", "space": "drop",
        "c": "hold",
    }

    def _on_key(self, e: ft.KeyboardEvent):
        raw = (e.key or "")
        key = raw.lower().replace(" ", "")
        action = self._KEY_ALIAS.get(key)
        over = self.engine.state.game_over
        if action == "left":
            self.engine.move(-1)
        elif action == "right":
            self.engine.move(1)
        elif action == "up":
            self.engine.rotate(1)
        elif action == "down":
            if not over:
                self.engine.tick()
        elif action == "drop":
            if not over:
                self.engine.hard_drop()
        elif action == "hold":
            if not over:
                self.engine.hold_piece()
        else:
            return
        self._refresh()
        if self.engine.state.game_over:
            self._save_match_log()

    # ---------- 主循环 ----------

    async def _loop(self):
        """按等级决定下落间隔；锁定时给一点点缓冲。"""
        try:
            while True:
                s = self.engine.state
                interval = max(0.05, 0.8 - (s.level - 1) * 0.07)
                await asyncio.sleep(interval)
                if s.game_over:
                    self._refresh()
                    self._save_match_log()
                    return
                self.engine.tick()
                self._refresh()
        except asyncio.CancelledError:
            raise
        except Exception:                   # noqa: BLE001 — 页面没了就收工
            return

    # ---------- 生命周期 ----------

    def _attach(self):
        self._prev_keyboard = self.page.on_keyboard_event
        self.page.on_keyboard_event = self._on_key
        # 用 page.run_task 起重力循环（和其它游戏一致）：
        # 它跑在 flet 自己的事件循环上，直接 asyncio.ensure_future
        # 在没有运行中事件循环的线程里会 RuntimeError。
        try:
            self._task = self.page.run_task(self._loop)
        except Exception:                   # noqa: BLE001
            self._task = None

    def _detach(self):
        if self._task is not None:
            try:
                self._task.cancel()
            except Exception:               # noqa: BLE001
                pass
            self._task = None
        try:
            self.page.on_keyboard_event = self._prev_keyboard
        except Exception:  # noqa: BLE001 — 页面已销毁
            pass

    def _restart(self):
        self.engine = TetrisEngine()
        self._log_saved = False           # 新的一局，重新允许落盘
        self._refresh()

    # ---------- 历史记录 ----------

    def _save_match_log(self) -> None:
        """一局结束（方块堆到顶）时把成绩落盘。

        写到应用数据目录的 ``logs/tetris/``（见 :mod:`core.history`）；
        主菜单的「游玩记录」页会把它和别的游戏的记录汇总在一起。
        """
        if self._log_saved:
            return
        s = self.engine.state
        if s.score <= 0:
            return                       # 一分没得就没必要留记录
        self._log_saved = True
        meta = {
            "状态": "游戏结束",
            "分数": str(s.score),
            "等级": str(s.level),
            "消行": str(s.lines),
            "模式": "单人",
        }
        lines = [
            f"分数：{s.score}",
            f"等级：{s.level}",
            f"消行：{s.lines}",
        ]
        try:
            from core import history
            history.save_match_log("tetris", lines, meta)
        except Exception as exc:          # noqa: BLE001
            print(f"[tetris] 保存历史记录失败：{exc!r}")

    # ---------- 组装 ----------

    def build(self) -> ft.Control:
        self._refresh()
        self._attach()

        board_panel = ft.Container(
            bgcolor=T.SURFACE,
            border=ft.Border.all(1, T.BORDER),
            padding=ft.Padding.all(4),
            content=self.board_host,
        )

        side = ft.Column(
            [
                ft.Text(t("tetris.next", default="下一块"), size=12,
                        color=T.TEXT_MUTED),
                self.next_host,
                ft.Container(height=10),
                ft.Text(t("tetris.hold", default="暂存"), size=12,
                        color=T.TEXT_MUTED),
                self.hold_host,
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
            ],
            spacing=4,
        )

        body = ft.Row(
            [board_panel, ft.Container(width=16), side],
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


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """入口：新建一页对局并返回控件树。"""
    return _PlayPage(page, navigate).build()
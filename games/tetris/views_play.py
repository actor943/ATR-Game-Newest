# -*- coding: utf-8 -*-
"""对局页：棋盘画面 + 键盘/触屏输入 + 主循环（重力/锁定）。

手机端怎么玩
------------
手机上**没有键盘**，所以这一页同时提供两套操作，走同一个 ``_act()``：

* **键盘（桌面）**：方向键移动 / 旋转 / 软降，空格硬降，C 暂存；
* **触屏（手机）**：棋盘下方一排操作键（:mod:`games.tetris.views_pad`），
  按住能连发；棋盘上直接滑动也行（左滑右移、下滑软降、上滑旋转）。

窄屏适配
--------
手机竖屏只有 360~430 逻辑像素，10×20 的棋盘再加右侧信息栏必然放不下。
所以按 :func:`core.ui_common.page_width` 判断宽度：

* **宽屏**：棋盘在左，信息栏在右（和以前一样）；
* **窄屏**：信息压成顶部一条，棋盘居中，操作键在下面；格子边长按屏幕
  宽高**自动缩放**，保证整盘都留在屏幕里。

性能
----
棋盘格子**只建一次**，之后每帧只改 ``bgcolor``。以前每帧重建 200 个
容器，手机上会明显卡。

为避免内存泄漏，离开页面时必须 ``_detach()``：
* 取消 asyncio 任务；
* 还原 ``page.on_keyboard_event`` 与 ``page.on_resize``；
* 停掉触屏按键的连发任务。
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import flet as ft

from core.i18n import t
from core.registry import NavigateFn
from core.theme import T
from core.ui_common import page_width

from .engine import COLS, HIDDEN_ROWS, ROWS, SHAPES, TetrisEngine
from .views_layout import LayoutMixin
from .views_pad import TouchPad

CELL_MAX = 26          # 格子最大边长（宽屏）
CELL_MIN = 12          # 格子最小边长（手机）
NARROW_W = 620         # 小于这个宽度按「手机竖屏」处理
GHOST = "#5A6472"      # 幽灵块颜色


class _PlayPage(LayoutMixin):
    """一页对局：持有引擎、控件、循环任务。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self.engine = TetrisEngine()
        self._task: Optional[asyncio.Task] = None
        self._prev_keyboard = None
        self._prev_resize = None
        self._log_saved = False          # 这一局是否已经落过盘
        self.cell = CELL_MAX             # 棋盘格子边长
        self.mini = CELL_MAX             # 预览小方块边长
        self._touch = False              # 是否手机布局（带操作键）
        self._grid: List[List[ft.Container]] = []
        self._mini_next: List[List[List[ft.Container]]] = []
        self._mini_next_widgets: List[ft.Control] = []
        self._mini_hold: List[List[ft.Container]] = []
        self._mini_hold_widget: Optional[ft.Control] = None
        self._drag_from: Optional[tuple] = None

        # 画布：用 Container 网格画（flet 1.0 的 Canvas 交互不便，方格更稳）
        self.board_host = ft.Column(spacing=0)
        self.score_text = ft.Text("0", size=18, weight=ft.FontWeight.BOLD,
                                  color=T.TEXT_PRIMARY)
        self.level_text = ft.Text("1", size=14, color=T.TEXT_SECONDARY)
        self.lines_text = ft.Text("0", size=14, color=T.TEXT_SECONDARY)
        self.status_text = ft.Text("", size=12, color=T.DANGER)
        self.pad = TouchPad(page, self._act)

    # ---------- 布局 ----------

    def _layout(self) -> None:
        """按屏幕宽高决定格子大小和布局形态。"""
        w = page_width(self.page, fallback=420.0)
        try:
            h = float(getattr(self.page, "height", None) or 720.0)
        except Exception:                   # noqa: BLE001
            h = 720.0
        plat = str(getattr(self.page, "platform", "") or "").lower()
        self._touch = (w < NARROW_W) or plat in ("android", "ios")
        if self._touch:
            # 手机竖屏：扣掉标题栏、信息条、操作键和留白
            avail_w = w - 40.0
            avail_h = h - 56.0 - 60.0 - 150.0 - 24.0
            cell = min(avail_w / COLS, avail_h / ROWS)
            self.cell = max(CELL_MIN, min(CELL_MAX, cell))
            self.mini = max(10.0, self.cell * 0.6)
        else:
            self.cell = CELL_MAX
            self.mini = CELL_MAX

    def _apply_cell_size(self) -> None:
        """格子边长变了就同步到所有格子控件上。"""
        for row in self._grid:
            for cell in row:
                cell.width = self.cell
                cell.height = self.cell
        for grid in list(self._mini_next) + [self._mini_hold]:
            for row in grid:
                for cell in row:
                    cell.width = self.mini
                    cell.height = self.mini

    # ---------- 画面 ----------

    def _cell_box(self, color: Optional[str]) -> ft.Container:
        return ft.Container(
            width=self.cell, height=self.cell,
            bgcolor=color or T.SURFACE_ALT,
            border=ft.Border.all(0.5, T.DIVIDER),
        )

    def _build_grid(self) -> None:
        """把棋盘格子建出来（只建一次，之后只改颜色）。"""
        self._grid = []
        rows = []
        for _ in range(ROWS):
            row = [self._cell_box(None) for _ in range(COLS)]
            self._grid.append(row)
            rows.append(ft.Row(row, spacing=0))
        self.board_host.controls = rows

    def _new_mini(self):
        """一个 4×2 的小方块预览，返回（控件, 格子列表）。"""
        grid = []
        rows = []
        for _ in range(2):
            row = [ft.Container(width=self.mini, height=self.mini,
                               bgcolor=T.SURFACE_ALT) for _ in range(4)]
            grid.append(row)
            rows.append(ft.Row(row, spacing=0))
        return ft.Column(rows, spacing=0), grid

    def _render_board(self):
        """把棋盘 + 活动方块 + 幽灵块刷到格子上。"""
        board = self.engine.visible_board()          # 去掉隐藏行
        for r, row in enumerate(self._grid):
            for c, cell in enumerate(row):
                cell.bgcolor = board[r][c] or T.SURFACE_ALT

        # 幽灵块先画（浅色）
        for (r, c) in self.engine.ghost_cells():
            rr = r - HIDDEN_ROWS
            if 0 <= rr < ROWS and board[rr][c] is None:
                self._grid[rr][c].bgcolor = GHOST

        # 活动方块覆盖
        piece = self.engine.state.piece
        if piece is not None:
            color = SHAPES[piece.kind][0]
            for (r, c) in piece.cells():
                rr = r - HIDDEN_ROWS
                if 0 <= rr < ROWS:
                    self._grid[rr][c].bgcolor = color

    def _paint_mini(self, grid: List[List[ft.Container]],
                    kind: Optional[str]) -> None:
        """给一个 4×2 的小预览上色。"""
        cells = set(SHAPES[kind][1]) if kind else set()
        color = SHAPES[kind][0] if kind else None
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                cell.bgcolor = color if (r, c) in cells else T.SURFACE_ALT

    def _render_side(self):
        """下一块、Hold、分数。"""
        q = self.engine.state.next_queue
        for i, kind in enumerate(q[:2]):
            self._paint_mini(self._mini_next[i], kind)
        self._paint_mini(self._mini_hold, self.engine.state.hold)

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
        "arrowup": "rotate", "arrowdown": "down",
        "a": "left", "d": "right", "w": "rotate", "s": "down",
        ":": "rotate", " ": "drop", "space": "drop",
        "c": "hold",
    }

    def _act(self, action: str) -> None:
        """所有输入（键盘 / 触屏按键 / 滑动）都走这里。"""
        e = self.engine
        over = e.state.game_over
        if action == "left":
            e.move(-1)
        elif action == "right":
            e.move(1)
        elif action == "rotate":
            e.rotate(1)
        elif action == "down":
            if not over:
                e.tick()
        elif action == "drop":
            if not over:
                e.hard_drop()
        elif action == "hold":
            if not over:
                e.hold_piece()
        else:
            return
        self._refresh()
        if e.state.game_over:
            self._save_match_log()

    def _on_key(self, e: ft.KeyboardEvent):
        raw = (e.key or "")
        key = raw.lower().replace(" ", "")
        action = self._KEY_ALIAS.get(key)
        if action:
            self._act(action)

    # ---------- 棋盘上手势（手机） ----------

    def _swipe_start(self, e):
        pos = getattr(e, "local_position", None)
        if pos is None:
            return
        self._drag_from = (float(pos.x), float(pos.y))

    def _swipe_end(self, e):
        pos = getattr(e, "local_position", None)
        start = self._drag_from
        self._drag_from = None
        if pos is None or start is None:
            return
        dx = float(pos.x) - start[0]
        dy = float(pos.y) - start[1]
        step = max(1.0, self.cell)
        if abs(dx) >= abs(dy):
            # 左右滑动：一次移动几格
            n = int(round(abs(dx) / step)) or 1
            for _ in range(min(n, 4)):
                self._act("right" if dx > 0 else "left")
        elif dy > 0:
            # 下滑：软降
            n = int(round(dy / step)) or 1
            for _ in range(min(n, 6)):
                self._act("down")
        else:
            # 上滑：旋转
            self._act("rotate")

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
        try:
            self._prev_resize = self.page.on_resize
            self.page.on_resize = self._on_resize
        except Exception:                   # noqa: BLE001
            self._prev_resize = None
        # 用 page.run_task 起重力循环（和其它游戏一致）：
        # 它跑在 flet 自己的事件循环上，直接 asyncio.ensure_future
        # 在没有运行中事件循环的线程里会 RuntimeError。
        try:
            self._task = self.page.run_task(self._loop)
        except Exception:                   # noqa: BLE001
            self._task = None

    def _on_resize(self, e):
        """屏幕尺寸变了：重算格子边长，整盘留在屏幕里。"""
        self._layout()
        self._apply_cell_size()
        self._refresh()

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
        try:
            self.page.on_resize = self._prev_resize
        except Exception:                   # noqa: BLE001
            pass
        self.pad.detach()

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


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """入口：新建一页对局并返回控件树。"""
    return _PlayPage(page, navigate).build()

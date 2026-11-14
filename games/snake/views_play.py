# -*- coding: utf-8 -*-
"""对局页：棋盘画面 + 键盘/触屏输入 + 主循环（变速驱动）。

手机端怎么玩
------------
手机上**没有键盘**，所以这一页同时提供两套操作，走同一个 ``_act()``：

* **键盘（桌面）**：方向键 / WASD 转向，空格或 P 暂停，R 重开；
* **触屏（手机）**：棋盘下方一排操作键（:mod:`games.snake.views_pad`），
  按住能连发；棋盘上直接滑动也能转向（上滑/下滑/左滑/右滑）。

窄屏适配
--------
手机竖屏只有 360~430 逻辑像素，20×20 的棋盘必须自适应：
按 :func:`core.ui_common.page_width` 判断宽度，格子边长**自动缩放**，
保证整盘都留在屏幕里；窄屏下信息压成顶部一条，操作键放底部。

性能
----
棋盘格子**只建一次**，之后每帧只改 ``bgcolor``。

变速
----
主循环每帧重读 ``engine.interval()``，速度等级（1~10）改变后**立刻生效**；
吃食物会自然加速，玩家也能随时 ``−`` / ``+`` 手动调速。

为避免内存泄漏，离开页面时必须 ``_detach()``：
* 取消 asyncio 任务；
* 还原 ``page.on_keyboard_event`` 与 ``page.on_resize``；
* 停掉触屏按键的连发任务。
"""

from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

import flet as ft

from core import responsive
from core.i18n import t
from core.registry import NavigateFn
from core.theme import T

from .engine import (
    COLOR_BODY, COLOR_BOARD, COLOR_FOOD, COLOR_GRID, COLOR_HEAD,
    COLS, ROWS, SnakeEngine,
)
from .views_layout import LayoutMixin
from .views_pad import TouchPad

CELL_MAX = 22          # 窄屏（手机竖屏）格子边长上限
CELL_WIDE_MAX = 36     # 宽屏放大上限：20×20 棋盘最大 720×720
CELL_MIN = 11          # 格子最小边长（手机）
NARROW_W = 620         # 小于这个宽度按「手机竖屏」处理

# 方向动作 → (dr, dc)
_DIRS = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}


class _PlayPage(LayoutMixin):
    """一页对局：持有引擎、控件、循环任务。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self._best = 0
        self.engine = SnakeEngine(best=self._best)
        self._task: Optional[asyncio.Task] = None
        self._prev_keyboard = None
        self._prev_resize = None
        self._log_saved = False
        self.cell = CELL_MAX
        self._touch = False
        self._grid: List[List[ft.Container]] = []
        self._drag_from: Optional[Tuple[float, float]] = None

        # 画布
        self.board_host = ft.Column(spacing=0)
        self.score_text = ft.Text("0", size=18, weight=ft.FontWeight.BOLD,
                                  color=T.TEXT_PRIMARY)
        self.best_text = ft.Text("0", size=14, color=T.TEXT_SECONDARY)
        self.speed_text = ft.Text(str(self.engine.state.speed), size=14,
                                  color=T.ACCENT, weight=ft.FontWeight.BOLD)
        self.status_text = ft.Text("", size=12, color=T.DANGER)
        self.pause_label = ft.Text(t("snake.pause", default="暂停"),
                                   size=13, color=T.TEXT_PRIMARY)
        _pause_box = ft.Container(
            bgcolor=T.SURFACE_ALT, border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            alignment=ft.Alignment.CENTER,
            content=ft.Row(
                [ft.Icon(ft.Icons.PAUSE, size=16, color=T.TEXT_PRIMARY),
                 self.pause_label],
                spacing=4, tight=True,
            ),
        )
        # 用 GestureDetector 而非 ft.Button：不可获得键盘焦点，方向键不会在
        # 按钮间跳、也不会误触按钮（只保留鼠标 / 触控与键盘 on_keyboard_event）
        self.pause_btn = ft.GestureDetector(
            content=_pause_box, on_tap=lambda _e: self._toggle_pause())
        self.pad = TouchPad(page, self._act)

    # ---------- 布局 ----------

    def _layout(self) -> None:
        """按屏幕宽高决定格子大小（宽屏放大、窄屏缩小）。"""
        w, h = responsive.size(self.page)
        plat = str(getattr(self.page, "platform", "") or "").lower()
        self._touch = (w < NARROW_W) or plat in ("android", "ios")
        if self._touch:
            # 手机竖屏：扣掉标题栏、信息条、操作键和留白
            avail_w = w - 32.0
            avail_h = h - 56.0 - 64.0 - 150.0 - 24.0
        else:
            # 宽屏：棋盘 + 右侧信息栏，按剩余宽高一起算
            avail_w = w - 32.0 - 16.0 - 200.0
            avail_h = h - 56.0 - 32.0 - 20.0
        cell = min(avail_w / COLS, avail_h / ROWS)
        cap = CELL_MAX if self._touch else CELL_WIDE_MAX
        self.cell = max(CELL_MIN, min(cap, cell))

    def _apply_cell_size(self) -> None:
        for row in self._grid:
            for cell in row:
                cell.width = self.cell
                cell.height = self.cell

    # ---------- 画面 ----------

    def _cell_box(self) -> ft.Container:
        return ft.Container(
            width=self.cell, height=self.cell,
            bgcolor=COLOR_BOARD,
            border=ft.Border.all(0.5, COLOR_GRID),
        )

    def _build_grid(self) -> None:
        self._grid = []
        rows = []
        for _ in range(ROWS):
            row = [self._cell_box() for _ in range(COLS)]
            self._grid.append(row)
            rows.append(ft.Row(row, spacing=0))
        self.board_host.controls = rows

    def _render_board(self):
        grid = self.engine.render_grid()
        for r, row in enumerate(self._grid):
            for c, cell in enumerate(row):
                v = grid[r][c]
                if v == 2:
                    cell.bgcolor = COLOR_HEAD
                elif v == 1:
                    cell.bgcolor = COLOR_BODY
                elif v == 3:
                    cell.bgcolor = COLOR_FOOD
                else:
                    cell.bgcolor = COLOR_BOARD

    def _render_side(self):
        s = self.engine.state
        self.score_text.value = str(s.score)
        self.best_text.value = str(s.best)
        self.speed_text.value = str(s.speed)
        if s.game_over:
            self.status_text.value = (t("snake.win", default="通关！")
                                      if s.won
                                      else t("snake.over", default="游戏结束"))
            self.status_text.color = T.SUCCESS if s.won else T.DANGER
        elif s.paused:
            self.status_text.value = t("snake.paused", default="已暂停")
            self.status_text.color = T.WARNING
        else:
            self.status_text.value = ""
        # 暂停键文案跟着状态变
        self.pause_label.value = (t("snake.resume", default="继续")
                                  if s.paused else t("snake.pause", default="暂停"))

    def _refresh(self):
        self._render_board()
        self._render_side()
        self.page.update()

    # ---------- 输入 ----------

    _KEY_ALIAS = {
        "arrowleft": "left", "arrowright": "right",
        "arrowup": "up", "arrowdown": "down",
        "a": "left", "d": "right", "w": "up", "s": "down",
        "space": "pause", "p": "pause",
        "r": "restart",
    }

    def _act(self, action: str) -> None:
        e = self.engine
        if action in _DIRS:
            dr, dc = _DIRS[action]
            e.set_direction(dr, dc)
        elif action == "speed_up":
            e.change_speed(+1)
        elif action == "speed_down":
            e.change_speed(-1)
        elif action == "pause":
            e.toggle_pause()
        elif action == "restart":
            self._restart()
            return
        else:
            return
        self._refresh()
        if e.state.game_over:
            self._save_match_log()

    def _on_key(self, e: ft.KeyboardEvent):
        # flet 把空格上报为 " "，strip 后变空串，这里归一为 "space"，
        # 否则空格键（暂停）映射会落空。
        raw = (e.key or "").strip().lower()
        if raw == "" or raw == "spacebar":
            raw = "space"
        action = self._KEY_ALIAS.get(raw)
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
        if abs(dx) >= abs(dy):
            self._act("right" if dx > 0 else "left")
        elif dy > 0:
            self._act("down")
        else:
            self._act("up")

    # ---------- 主循环（变速驱动） ----------

    async def _loop(self):
        try:
            while True:
                if self.engine.state.game_over:
                    self._refresh()
                    self._save_match_log()
                    return
                # 每帧重读间隔：变速即时生效
                interval = self.engine.interval()
                await asyncio.sleep(interval)
                if self.engine.state.game_over:
                    self._refresh()
                    self._save_match_log()
                    return
                self.engine.step()
                self._refresh()
        except asyncio.CancelledError:
            raise
        except Exception:                   # noqa: BLE001 — 页面没了就收工
            return

    # ---------- 生命周期 ----------

    def _attach(self):
        self._prev_keyboard = self.page.on_keyboard_event
        self.page.on_keyboard_event = self._on_key
        # 走全局 resize 分发器，不覆盖框架 / 其它页面的回调
        responsive.subscribe(self.page, "snake.play", self._on_resize)
        try:
            self._task = self.page.run_task(self._loop)
        except Exception:                   # noqa: BLE001
            self._task = None

    def _on_resize(self, *_args):
        """屏幕尺寸变了：重算格子边长（兼容事件对象与 (w, h) 两种签名）。"""
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
        except Exception:  # noqa: BLE001
            pass
        responsive.unsubscribe(self.page, "snake.play", self._on_resize)
        self.pad.detach()

    def _restart(self):
        self._best = max(self._best, self.engine.state.best)
        self.engine = SnakeEngine(best=self._best)
        self._log_saved = False
        self._refresh()

    def _toggle_pause(self):
        self.engine.toggle_pause()
        self._refresh()

    def _set_speed(self, delta: int):
        self.engine.change_speed(delta)
        self._refresh()

    # ---------- 历史记录 ----------

    def _save_match_log(self) -> None:
        if self._log_saved:
            return
        s = self.engine.state
        if s.score <= 0:
            return
        self._log_saved = True
        self._best = max(self._best, s.best)
        meta = {
            "状态": "通关" if s.won else "游戏结束",
            "分数": str(s.score),
            "最高分": str(s.best),
            "速度": str(s.speed),
            "步数": str(s.steps),
            "模式": "单人",
        }
        lines = [
            f"分数：{s.score}",
            f"最高分：{s.best}",
            f"最终速度：{s.speed}",
            f"步数：{s.steps}",
            "结果：" + ("通关" if s.won else "游戏结束"),
        ]
        try:
            from core import history
            history.save_match_log("snake", lines, meta)
        except Exception as exc:          # noqa: BLE001
            print(f"[snake] 保存历史记录失败：{exc!r}")


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    return _PlayPage(page, navigate).build()

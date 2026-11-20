# -*- coding: utf-8 -*-
"""扫雷对局页：棋盘画面 + 鼠标 / 触屏输入 + 计时循环 + 落盘。

操作
----
* **桌面**：左键翻开（已翻开的数字格再点 = chord）、右键插旗；
  ``1/2/3`` 换难度、``F`` 切换插旗模式、``R`` 重开；
* **手机**：点格翻开、**长按**插旗；手指不方便长按时打开「插旗模式」，
  之后所有点击都变成插旗；高级 30 列盘可以横向滚动看全。

长按与右击都会抑制紧随其后的一次 ``on_tap``（Flutter 的手势竞争里，
偶尔会补发一次 tap），否则「插旗」会立刻被「翻开」覆盖掉。

性能
----
格子控件只建一次，之后每次操作只改 ``bgcolor`` 与 ``Text.value``；
计时循环每 0.2 秒只刷新文字，不重画整张棋盘。离开页面必须 ``_detach()``：
取消计时任务、还原键盘回调、注销 resize 订阅。
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Optional

import flet as ft

from core import responsive
from core.i18n import t
from core.registry import NavigateFn
from core.theme import T

from .engine import LOST, PLAYING, READY, WON, MinesweeperEngine
from .views_layout import LayoutMixin

# ---------- 棋盘配色（固定浅色底，明暗主题下数字都看得清） ----------
COLOR_HIDDEN = "#CFD8DC"
COLOR_OPEN = "#ECEFF1"
COLOR_FLAG = "#FFE082"
COLOR_BOOM = "#EF5350"
COLOR_BORDER = "#90A4AE"
NUM_COLORS = ("", "#1565C0", "#2E7D32", "#C62828", "#4527A0",
              "#AD1457", "#00838F", "#37474F", "#212121")

CELL_MIN = 14          # 高级盘在手机上的最小格子
CELL_MAX = 34          # 宽屏放大上限
NARROW_W = 620         # 小于这个宽度按「手机竖屏」处理

_LEVEL_NAMES = {"easy": "初级", "medium": "中级", "hard": "高级"}


def fmt_time(seconds: float) -> str:
    """秒 → ``mm:ss``（历史记录与计时条共用）。"""
    n = max(0, int(seconds))
    return f"{n // 60:02d}:{n % 60:02d}"


class _PlayPage(LayoutMixin):
    """一页对局：持有引擎、格子控件、计时任务。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn, level: str):
        self.page = page
        self.navigate = navigate
        self.engine = MinesweeperEngine(level)
        self._task: Optional[asyncio.Task] = None
        self._prev_keyboard = None
        self._log_saved = False
        self._flag_mode = False
        self._suppress_until = 0.0
        self.cell = 28.0
        self._touch = False
        self._boxes: List[List[ft.Container]] = []
        self._labels: List[List[ft.Text]] = []

        self.board_host = ft.Column(spacing=0)
        # ---- 信息文字 ----
        self.mine_text = ft.Text("0", size=18, weight=ft.FontWeight.BOLD,
                                 color=T.ACCENT)
        self.time_text = ft.Text("00:00", size=18, weight=ft.FontWeight.BOLD,
                                 color=T.TEXT_PRIMARY)
        self.level_text = ft.Text("", size=13, color=T.TEXT_SECONDARY)
        self.status_text = ft.Text("", size=12, color=T.TEXT_SECONDARY)

        # 插旗模式按钮：自己留着 box / label 引用，方便切换时改底色
        self.flag_label = ft.Text("", size=13, color=T.TEXT_PRIMARY)
        self.flag_box = ft.Container(
            bgcolor=T.SURFACE_ALT, border=ft.Border.all(1, T.BORDER),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            alignment=ft.Alignment.CENTER,
            content=self.flag_label,
        )
        self.flag_btn = ft.GestureDetector(
            content=self.flag_box,
            on_tap=lambda _e: self._act("flag_mode"),
        )

    # ---------- 布局 ----------

    def _layout(self) -> None:
        """按屏幕宽高决定格子边长；高级盘放不下时允许横向滚动。"""
        w, h = responsive.size(self.page)
        plat = str(getattr(self.page, "platform", "") or "").lower()
        self._touch = (w < NARROW_W) or plat in ("android", "ios")
        s = self.engine.state
        if self._touch:
            avail_w = w - 32.0
            avail_h = h - 56.0 - 96.0 - 110.0
        else:
            avail_w = w - 32.0 - 16.0 - 210.0
            avail_h = h - 56.0 - 40.0
        cell = min(avail_w / s.cols, avail_h / s.rows)
        self.cell = max(CELL_MIN, min(CELL_MAX, cell))

    def _apply_cell_size(self) -> None:
        """窗口变了：只改格子的宽高与字号，棋局状态不丢。"""
        for row in self._boxes:
            for box in row:
                box.width = self.cell
                box.height = self.cell
        for row in self._labels:
            for label in row:
                label.size = max(9.0, self.cell * 0.55)

    # ---------- 画面 ----------

    def _build_grid(self) -> None:
        """按当前难度重建整张格子控件表（换难度时行列数会变）。"""
        s = self.engine.state
        self._boxes = []
        self._labels = []
        rows: List[ft.Control] = []
        for r in range(s.rows):
            boxes: List[ft.Container] = []
            labels: List[ft.Text] = []
            cells: List[ft.Control] = []
            for c in range(s.cols):
                label = ft.Text("", size=max(9.0, self.cell * 0.55),
                                weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER,
                                color=NUM_COLORS[1])
                box = ft.Container(
                    width=self.cell, height=self.cell,
                    bgcolor=COLOR_HIDDEN,
                    border=ft.Border.all(0.5, COLOR_BORDER),
                    alignment=ft.Alignment.CENTER,
                    content=label,
                )
                cells.append(ft.GestureDetector(
                    content=box,
                    on_tap=lambda _e, rr=r, cc=c: self._tap(rr, cc),
                    on_secondary_tap=lambda _e, rr=r, cc=c: self._flag(rr, cc),
                    on_long_press=lambda _e, rr=r, cc=c: self._flag(rr, cc),
                ))
                boxes.append(box)
                labels.append(label)
            self._boxes.append(boxes)
            self._labels.append(labels)
            rows.append(ft.Row(cells, spacing=0))
        self.board_host.controls = rows

    def _render_grid(self) -> None:
        """把引擎状态刷到格子上（只改颜色 / 文字，不重建控件）。"""
        e = self.engine
        s = e.state
        for r, row in enumerate(self._boxes):
            for c, box in enumerate(row):
                label = self._labels[r][c]
                chars = e.cell_chars(r, c)
                label.value = chars
                if s.status == LOST and s.exploded == (r, c):
                    box.bgcolor = COLOR_BOOM
                    label.color = "#FFFFFF"
                elif s.flagged[r][c]:
                    box.bgcolor = COLOR_FLAG
                    label.color = "#212121"
                elif s.revealed[r][c]:
                    box.bgcolor = COLOR_OPEN
                    n = s.adj[r][c]
                    label.color = NUM_COLORS[n] if n else T.TEXT_PRIMARY
                elif s.status == LOST and (r, c) in s.mine_set:
                    box.bgcolor = COLOR_OPEN
                    label.color = "#212121"
                else:
                    box.bgcolor = COLOR_HIDDEN
                    label.color = T.TEXT_PRIMARY

    def _render_side(self) -> None:
        """信息栏：剩余雷 / 用时 / 难度 / 状态 / 插旗模式。"""
        s = self.engine.state
        self.mine_text.value = str(self.engine.remaining())
        self.time_text.value = fmt_time(s.elapsed)
        self.level_text.value = t("minesweeper.level_" + s.level,
                                  default=_LEVEL_NAMES.get(s.level, s.level))
        if s.status == READY:
            self.status_text.value = t("minesweeper.hint_start",
                                       default="点任意一格开始（首击必不踩雷）")
            self.status_text.color = T.TEXT_SECONDARY
        elif s.status == WON:
            self.status_text.value = t("minesweeper.win", default="扫雷成功！")
            self.status_text.color = T.SUCCESS
        elif s.status == LOST:
            self.status_text.value = t("minesweeper.over", default="踩雷了")
            self.status_text.color = T.DANGER
        else:
            self.status_text.value = ""
        on = self._flag_mode
        self.flag_label.value = t("minesweeper.flag_on", default="插旗模式：开") \
            if on else t("minesweeper.flag_off", default="插旗模式：关")
        self.flag_box.bgcolor = T.PRIMARY if on else T.SURFACE_ALT
        self.flag_label.color = T.TEXT_INVERT if on else T.TEXT_PRIMARY

    def _refresh(self) -> None:
        self._render_grid()
        self._render_side()
        self.page.update()

    # ---------- 输入 ----------

    _KEY_ALIAS = {
        "r": "restart",
        "1": "level:easy", "2": "level:medium", "3": "level:hard",
        "f": "flag_mode",
    }

    def _act(self, action: str) -> None:
        """键盘 / 按钮统一入口。"""
        if action == "restart":
            self._restart()
            return
        if action.startswith("level:"):
            self._restart(action.split(":", 1)[1])
            return
        if action == "flag_mode":
            self._flag_mode = not self._flag_mode
            self._refresh()
            return

    def _after_move(self) -> None:
        """一次操作之后刷新画面；结束时顺手落盘。"""
        self._refresh()
        if self.engine.is_over():
            self._save_match_log()

    def _tap(self, r: int, c: int) -> None:
        if time.monotonic() < self._suppress_until:
            return                       # 长按 / 右击补发的 tap，忽略
        if self._flag_mode:
            self.engine.toggle_flag(r, c)
        else:
            self.engine.reveal(r, c)     # 已翻开的数字格内部会走 chord
        self._after_move()

    def _flag(self, r: int, c: int) -> None:
        self._suppress_until = time.monotonic() + 0.6
        self.engine.toggle_flag(r, c)
        self._after_move()

    def _on_key(self, e: ft.KeyboardEvent):
        raw = (e.key or "").strip().lower()
        action = self._KEY_ALIAS.get(raw)
        if action:
            self._act(action)

    # ---------- 计时循环 ----------

    async def _loop(self) -> None:
        """0.2 秒一跳：只有进行中的局计时，文字刷新不重画棋盘。"""
        last = time.monotonic()
        try:
            while True:
                await asyncio.sleep(0.2)
                now = time.monotonic()
                dt = min(0.5, max(0.0, now - last))
                last = now
                if self.engine.state.status == PLAYING:
                    self.engine.tick(dt)
                    self.time_text.value = fmt_time(self.engine.state.elapsed)
                    self.page.update()
        except asyncio.CancelledError:
            raise
        except Exception:                   # noqa: BLE001 — 页面没了就收工
            return

    # ---------- 生命周期 ----------

    def _attach(self) -> None:
        self._prev_keyboard = self.page.on_keyboard_event
        self.page.on_keyboard_event = self._on_key
        responsive.subscribe(self.page, "minesweeper.play", self._on_resize)
        try:
            self._task = self.page.run_task(self._loop)
        except Exception:                   # noqa: BLE001
            self._task = None

    def _on_resize(self, *_args) -> None:
        """窗口变了：重算格子边长，原位改控件尺寸。"""
        self._layout()
        self._apply_cell_size()
        self._refresh()

    def _detach(self) -> None:
        if self._task is not None:
            try:
                self._task.cancel()
            except Exception:               # noqa: BLE001
                pass
            self._task = None
        try:
            self.page.on_keyboard_event = self._prev_keyboard
        except Exception:                   # noqa: BLE001
            pass
        responsive.unsubscribe(self.page, "minesweeper.play", self._on_resize)

    def _restart(self, level: Optional[str] = None) -> None:
        best = max(self.engine.best, self.engine.score())
        self.engine.restart(level, best=best)
        self._log_saved = False
        self._layout()
        self._build_grid()
        self._refresh()

    # ---------- 历史记录 ----------

    def _save_match_log(self) -> None:
        if self._log_saved or not self.engine.is_over():
            return
        self._log_saved = True
        s = self.engine.state
        won = s.status == WON
        score = self.engine.score()
        used = f"{int(s.elapsed)} 秒"
        meta = {
            "状态": "胜利" if won else "失败",
            "难度": _LEVEL_NAMES.get(s.level, s.level),
            "用时": used,
            "分数": str(score),
            "模式": "单人",
            "雷数": str(s.mines),
            "盘面": f"{s.rows}×{s.cols}",
        }
        lines = [
            f"结果：{'胜利' if won else '失败'}",
            f"难度：{_LEVEL_NAMES.get(s.level, s.level)}（{s.rows}×{s.cols} / {s.mines} 雷）",
            f"用时：{used}",
            f"分数：{score}",
            f"翻开格子：{s.opened}",
            f"最高分：{max(self.engine.best, score)}",
        ]
        try:
            from core import history
            history.save_match_log("minesweeper", lines, meta)
        except Exception as exc:            # noqa: BLE001
            print(f"[minesweeper] 保存历史记录失败：{exc!r}")


def build(page: ft.Page, navigate: NavigateFn, level: str = "easy") -> ft.Control:
    """入口：新建一页对局并返回控件树。"""
    return _PlayPage(page, navigate, level).build()

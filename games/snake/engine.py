# -*- coding: utf-8 -*-
"""贪吃蛇纯逻辑引擎（不依赖 flet，可命令行自检）。

坐标系：``(row, col)``，row=0 是顶部，col=0 是左边。蛇身用 ``deque`` 存，
索引 0 是蛇头。

变速功能
--------
* 速度等级 ``speed`` 取值 1~10（默认 5）；
* 每步间隔 ``interval`` = ``0.32 - (speed-1) * 0.028``，并夹在
  ``[0.05, 0.32]`` 秒之间；等级越高越快；
* **吃一个食物自动 +1 级**（经典加速），玩家也能随时用 ``−`` / ``+`` 手动改；
* 主循环每帧重新读 ``interval()``，改速度**立刻生效**，不用等下一局。

复古风
------
棋盘固定黑色底 + 暗绿网格，蛇身荧光绿、蛇头亮绿、食物红色，渲染层用这套
配色（与主题无关，营造老式掌机的味道）。
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

Cell = Tuple[int, int]

# ---------- 棋盘尺寸 ----------
COLS = 20
ROWS = 20
START_LEN = 3

# ---------- 复古配色（渲染层取用） ----------
COLOR_BOARD = "#000000"      # 棋盘黑底
COLOR_GRID = "#0C2A0C"       # 暗绿网格线
COLOR_BODY = "#00C853"       # 蛇身（荧光绿）
COLOR_HEAD = "#B2FF59"       # 蛇头（亮绿）
COLOR_FOOD = "#FF3B30"       # 食物（红）

# 渲染格类型
EMPTY = 0
BODY = 1
HEAD = 2
FOOD = 3

SPEED_MIN = 1
SPEED_MAX = 10
SPEED_DEFAULT = 5


def interval_for(speed: int) -> float:
    """速度等级 → 每步间隔（秒）。等级越高越快。"""
    s = max(SPEED_MIN, min(SPEED_MAX, speed))
    return max(0.05, 0.32 - (s - 1) * 0.028)


@dataclass
class SnakeState:
    """一局对战的完整状态。"""

    snake: Deque[Cell] = field(default_factory=deque)
    dir: Cell = (0, 1)               # 当前朝向（下一步会走这个方向）
    food: Optional[Cell] = None
    score: int = 0
    best: int = 0                    # 本次会话最高分（跨局保留）
    speed: int = SPEED_DEFAULT
    game_over: bool = False
    won: bool = False                # 棋盘填满 = 通关
    paused: bool = False
    steps: int = 0


class SnakeEngine:
    """门面：所有操作与查询都走这里。"""

    def __init__(self, seed: Optional[int] = None, best: int = 0):
        self.state = SnakeState()
        self.state.best = best
        self._rng = random.Random(
            seed if seed is not None else random.randrange(1 << 30))
        self._last_committed = (0, 1)     # 上一次「实际移动」的方向，防 180° 掉头
        self._reset()

    # ---------- 内部 ----------

    def _reset(self) -> None:
        s = self.state
        s.snake = deque()
        mid_r = ROWS // 2
        # 蛇头在最右，朝右；蛇身往左排
        for i in range(START_LEN):
            s.snake.append((mid_r, START_LEN - 1 - i))
        s.dir = (0, 1)
        s.food = None
        s.score = 0
        s.speed = SPEED_DEFAULT
        s.game_over = False
        s.won = False
        s.paused = False
        s.steps = 0
        self._last_committed = (0, 1)
        self._place_food()

    def _place_food(self) -> None:
        """在空位随机放食物；没空位 = 通关。"""
        s = self.state
        occupied = set(s.snake)
        free = [(r, c) for r in range(ROWS) for c in range(COLS)
                if (r, c) not in occupied]
        if not free:
            s.food = None
            s.game_over = True
            s.won = True
            return
        s.food = self._rng.choice(free)

    # ---------- 操作 ----------

    def set_direction(self, dr: int, dc: int) -> None:
        """改朝向；禁止 180° 掉头（相对「上一次实际移动」的方向）。"""
        s = self.state
        if s.game_over or s.paused:
            return
        if (dr, dc) == (-self._last_committed[0], -self._last_committed[1]):
            return                      # 反向 = 撞自己，直接忽略
        if (dr, dc) == s.dir:
            return
        s.dir = (dr, dc)

    def set_speed(self, level: int) -> None:
        s = self.state
        s.speed = max(SPEED_MIN, min(SPEED_MAX, level))

    def change_speed(self, delta: int) -> None:
        self.set_speed(self.state.speed + delta)

    def toggle_pause(self) -> None:
        s = self.state
        if s.game_over:
            return
        s.paused = not s.paused

    def restart(self, best: Optional[int] = None) -> None:
        if best is not None:
            self.state.best = best
        self._reset()

    def step(self) -> None:
        """时间驱动的一步：按当前方向前进一格。"""
        s = self.state
        if s.game_over or s.paused:
            return
        dr, dc = s.dir
        self._last_committed = (dr, dc)
        head = s.snake[0]
        nr, nc = head[0] + dr, head[1] + dc

        # 撞墙
        if nr < 0 or nr >= ROWS or nc < 0 or nc >= COLS:
            s.game_over = True
            return

        ate = (s.food is not None and (nr, nc) == s.food)

        # 撞自己：未吃食物时尾巴会腾出来，所以撞到当前尾巴不算死
        if (nr, nc) in s.snake:
            if not ate and (nr, nc) == s.snake[-1]:
                pass
            else:
                s.game_over = True
                return

        s.snake.appendleft((nr, nc))
        if ate:
            s.score += 10
            if s.score > s.best:
                s.best = s.score
            self.change_speed(+1)          # 吃食物后自然加速（变速核心）
            self._place_food()
        else:
            s.snake.pop()
        s.steps += 1

    # ---------- 查询 ----------

    def interval(self) -> float:
        """当前速度对应的每步间隔（秒）。"""
        return interval_for(self.state.speed)

    def render_grid(self) -> List[List[int]]:
        """返回 2D 网格：0 空 / 1 身 / 2 头 / 3 食物。"""
        grid = [[EMPTY] * COLS for _ in range(ROWS)]
        s = self.state
        for (r, c) in s.snake:
            if 0 <= r < ROWS and 0 <= c < COLS:
                grid[r][c] = BODY
        if s.snake:
            hr, hc = s.snake[0]
            if 0 <= hr < ROWS and 0 <= hc < COLS:
                grid[hr][hc] = HEAD
        if s.food is not None:
            fr, fc = s.food
            if 0 <= fr < ROWS and 0 <= fc < COLS:
                grid[fr][fc] = FOOD
        return grid

    def to_dict(self) -> dict:
        s = self.state
        return {
            "snake": list(s.snake),
            "dir": list(s.dir),
            "food": list(s.food) if s.food else None,
            "score": s.score, "best": s.best, "speed": s.speed,
            "game_over": s.game_over, "won": s.won,
            "paused": s.paused, "steps": s.steps,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SnakeEngine":
        eng = cls(seed=1, best=data.get("best", 0))
        s = eng.state
        s.snake = deque((r, c) for (r, c) in data.get("snake", []))
        d = data.get("dir", [0, 1])
        s.dir = (d[0], d[1])
        f = data.get("food")
        s.food = None if f is None else (f[0], f[1])
        s.score = data.get("score", 0)
        s.speed = data.get("speed", SPEED_DEFAULT)
        s.game_over = bool(data.get("game_over", False))
        s.won = bool(data.get("won", False))
        s.paused = bool(data.get("paused", False))
        s.steps = data.get("steps", 0)
        eng._last_committed = s.dir
        return eng

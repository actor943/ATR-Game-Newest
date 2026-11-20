# -*- coding: utf-8 -*-
"""扫雷纯逻辑引擎（不依赖 flet，可命令行自检）。

规则
----
* 三档难度：初级 9×9/10 雷、中级 16×16/40 雷、高级 16×30/99 雷；
* **首击安全**：第一次点开之后才布雷，且点击格与它的 8 邻域都不放雷；
* 点开数字 0 会向四周「洪泛」展开；在已翻开的数字格上再点一次，
  若周围旗数等于数字就自动翻开其余邻格（经典 chord）；
* 左键翻开、右键 / 长按插旗；踩雷即负，翻开全部非雷格即胜（自动补旗）；
* 计时由视图层每帧把 ``dt`` 喂给 :meth:`MinesweeperEngine.tick`，
  引擎本身不读系统时间，方便命令行自检。

坐标一律 ``(row, col)``，row=0 是顶行。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

Cell = Tuple[int, int]

# ---------- 难度 ----------
# 名称 → (行, 列, 雷数)。列数多的高级盘在手机上会缩小格子并允许横向滚动。
LEVELS: Dict[str, Tuple[int, int, int]] = {
    "easy": (9, 9, 10),
    "medium": (16, 16, 40),
    "hard": (16, 30, 99),
}
LEVEL_ORDER = ("easy", "medium", "hard")

# 胜利基础分（时间越久越少），供历史记录与「游玩记录」汇总用
LEVEL_BASE = {"easy": 300, "medium": 800, "hard": 1500}

# ---------- 状态 ----------
READY = "ready"
PLAYING = "playing"
WON = "won"
LOST = "lost"


@dataclass
class MineState:
    """一局扫雷的完整状态。"""

    level: str = "easy"
    rows: int = 9
    cols: int = 9
    mines: int = 10
    mine_set: Set[Cell] = field(default_factory=set)
    adj: List[List[int]] = field(default_factory=list)
    revealed: List[List[bool]] = field(default_factory=list)
    flagged: List[List[bool]] = field(default_factory=list)
    status: str = READY
    elapsed: float = 0.0
    flags: int = 0
    opened: int = 0
    exploded: Optional[Cell] = None
    last_action: str = ""       # "boom" / "win" / "flag" / "open" 等，给界面做反馈


class MinesweeperEngine:
    """门面：布雷、翻开、插旗、chord、计时、胜负与序列化都走这里。"""

    def __init__(self, level: str = "easy", seed: Optional[int] = None,
                 best: int = 0):
        self.best = best
        self.state = MineState()
        self._rng = random.Random(
            seed if seed is not None else random.randrange(1 << 30))
        self._planted = False
        self._reset(level)

    # ---------- 初始化 ----------

    def _reset(self, level: str) -> None:
        """按难度清空棋盘（雷要等首击才布）。"""
        if level not in LEVELS:
            level = "easy"
        rows, cols, mines = LEVELS[level]
        s = self.state
        s.level = level
        s.rows, s.cols, s.mines = rows, cols, min(mines, rows * cols - 1)
        s.mine_set = set()
        s.adj = [[0] * cols for _ in range(rows)]
        s.revealed = [[False] * cols for _ in range(rows)]
        s.flagged = [[False] * cols for _ in range(rows)]
        s.status = READY
        s.elapsed = 0.0
        s.flags = 0
        s.opened = 0
        s.exploded = None
        s.last_action = ""
        self._planted = False

    def restart(self, level: Optional[str] = None,
                best: Optional[int] = None) -> None:
        """重开一局；不给难度就沿用当前难度。"""
        if best is not None:
            self.best = best
        self._reset(level or self.state.level)

    # ---------- 小工具 ----------

    def _inside(self, r: int, c: int) -> bool:
        s = self.state
        return 0 <= r < s.rows and 0 <= c < s.cols

    def neighbors(self, r: int, c: int) -> List[Cell]:
        """返回 (r, c) 的 8 邻域（越界的不算）。"""
        out: List[Cell] = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if self._inside(nr, nc):
                    out.append((nr, nc))
        return out

    def is_over(self) -> bool:
        """这一局是否已经结束（胜 / 负）。"""
        return self.state.status in (WON, LOST)

    def remaining(self) -> int:
        """剩余雷数 = 总雷数 − 已插旗数（可以为负，跟经典扫雷一致）。"""
        return self.state.mines - self.state.flags

    # ---------- 布雷 ----------

    def _plant_mines(self, safe: Cell) -> None:
        """首击后布雷：安全区（点击格 + 8 邻域）里一颗雷都不放。"""
        s = self.state
        zone = {safe, *self.neighbors(*safe)}
        free = [(r, c) for r in range(s.rows) for c in range(s.cols)
                if (r, c) not in zone]
        # 盘面极小、安全区放不下所有雷时，缩小安全区，保证布雷数量不变
        if len(free) < s.mines:
            free = [(r, c) for r in range(s.rows) for c in range(s.cols)
                    if (r, c) != safe]
        s.mine_set = set(self._rng.sample(free, s.mines))
        for r, c in s.mine_set:
            for nr, nc in self.neighbors(r, c):
                s.adj[nr][nc] += 1
        self._planted = True
        s.status = PLAYING
        s.last_action = "start"

    # ---------- 操作 ----------

    def reveal(self, r: int, c: int) -> bool:
        """左键点一格：翻开 / 洪泛展开；已翻开的数字格改走 chord。"""
        s = self.state
        if not self._inside(r, c) or self.is_over():
            return False
        if s.revealed[r][c]:
            return self.chord(r, c)
        if s.flagged[r][c]:
            return False                       # 插旗格不能直接翻开
        if not self._planted:
            self._plant_mines((r, c))
        if (r, c) in s.mine_set:
            s.status = LOST
            s.exploded = (r, c)
            s.last_action = "boom"
            return True
        self._flood(r, c)
        s.last_action = "win" if s.status == WON else "open"
        return True

    def _flood(self, r: int, c: int) -> None:
        """从 (r, c) 洪泛展开；数字 0 继续向 8 邻域扩散。"""
        s = self.state
        queue: List[Cell] = [(r, c)]
        while queue:
            cr, cc = queue.pop()
            if s.revealed[cr][cc] or s.flagged[cr][cc]:
                continue
            if (cr, cc) in s.mine_set:
                continue
            s.revealed[cr][cc] = True
            s.opened += 1
            if s.adj[cr][cc] == 0:
                queue.extend(self.neighbors(cr, cc))
        self._check_win()

    def _check_win(self) -> None:
        """非雷格全翻开 = 胜利，并把剩下的雷自动补上旗。"""
        s = self.state
        if s.status in (WON, LOST):
            return
        if s.opened < s.rows * s.cols - s.mines:
            return
        s.status = WON
        for cell in s.mine_set:
            r, c = cell
            if not s.flagged[r][c]:
                s.flagged[r][c] = True
                s.flags += 1
        s.last_action = "win"
        self.best = max(self.best, self.score())

    def toggle_flag(self, r: int, c: int) -> bool:
        """右键 / 长按 / 插旗模式：在没翻开的格子上切换旗子。"""
        s = self.state
        if not self._inside(r, c) or self.is_over():
            return False
        if s.revealed[r][c]:
            return False
        s.flagged[r][c] = not s.flagged[r][c]
        s.flags += 1 if s.flagged[r][c] else -1
        s.last_action = "flag"
        return True

    def chord(self, r: int, c: int) -> bool:
        """已翻开的数字格：周围旗数够数时，自动翻开其余邻格。"""
        s = self.state
        if not self._inside(r, c) or self.is_over():
            return False
        if not s.revealed[r][c] or s.adj[r][c] <= 0:
            return False
        around = self.neighbors(r, c)
        if sum(1 for (nr, nc) in around if s.flagged[nr][nc]) != s.adj[r][c]:
            return False
        changed = False
        for nr, nc in around:
            if s.revealed[nr][nc] or s.flagged[nr][nc]:
                continue
            if (nr, nc) in s.mine_set:       # 旗插错了：照样踩雷
                s.status = LOST
                s.exploded = (nr, nc)
                s.last_action = "boom"
                return True
            self._flood(nr, nc)
            changed = True
        if changed and not self.is_over():
            s.last_action = "open"
        return changed

    def tick(self, dt: float) -> None:
        """时间推进（只有进行中的局才计时）。"""
        if self.state.status == PLAYING and dt > 0:
            self.state.elapsed += float(dt)

    # ---------- 查询 ----------

    def score(self) -> int:
        """胜利分数 = 难度基础分 − 用时惩罚；失败为 0。"""
        s = self.state
        if s.status != WON:
            return 0
        base = LEVEL_BASE.get(s.level, 300)
        return max(10, base - int(s.elapsed) * 3)

    def cell_chars(self, r: int, c: int) -> str:
        """这一格该显示什么：旗 / 雷 / 数字 / 空（未翻开返回 ""）。"""
        s = self.state
        if s.flagged[r][c]:
            if s.status == LOST and (r, c) not in s.mine_set:
                return "❌"                    # 插错的旗
            return "🚩"
        if s.status == LOST and (r, c) in s.mine_set:
            return "💥" if s.exploded == (r, c) else "💣"
        if not s.revealed[r][c]:
            return ""
        n = s.adj[r][c]
        return str(n) if n else ""

    def to_dict(self) -> dict:
        """整局快照（自检往返用；联机暂未开放）。"""
        s = self.state
        return {
            "level": s.level, "rows": s.rows, "cols": s.cols,
            "mines": s.mines, "mine_set": sorted(s.mine_set),
            "revealed": s.revealed, "flagged": s.flagged,
            "status": s.status, "elapsed": s.elapsed,
            "flags": s.flags, "opened": s.opened,
            "exploded": list(s.exploded) if s.exploded else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MinesweeperEngine":
        """从快照还原（雷表已定，之后不再布雷）。"""
        eng = cls(level=data.get("level", "easy"), seed=1)
        s = eng.state
        s.mine_set = {(r, c) for (r, c) in data.get("mine_set", [])}
        for r, c in s.mine_set:
            for nr, nc in eng.neighbors(r, c):
                s.adj[nr][nc] += 1
        s.revealed = data.get("revealed", s.revealed)
        s.flagged = data.get("flagged", s.flagged)
        s.status = data.get("status", READY)
        s.elapsed = float(data.get("elapsed", 0.0))
        s.flags = int(data.get("flags", 0))
        s.opened = int(data.get("opened", 0))
        ex = data.get("exploded")
        s.exploded = (ex[0], ex[1]) if ex else None
        eng._planted = True
        return eng

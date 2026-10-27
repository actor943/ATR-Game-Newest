# -*- coding: utf-8 -*-
"""俄罗斯方块纯逻辑引擎（不依赖 flet，可命令行自检）。

坐标系：``(row, col)``，row=0 是顶部，col=0 是左边。
每个方块用「单元格相对偏移」的集合表示；旋转用矩阵变换 + 简单墙踢。

对外只有一个门面类 :class:`TetrisEngine`，视图只管调它的方法、读它的属性。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

Cell = Tuple[int, int]        # (row, col)

# ---------- 棋盘尺寸 ----------
COLS = 10
ROWS = 20
HIDDEN_ROWS = 2               # 顶部缓冲行（出生时方块可能越界，不渲染）


# ---------- 七种方块 ----------
# 每种给「旋转态 0」的单元格；其余旋转由 _rotate_cells 生成。
# 用字母做 id，方便序列化与日志。
SHAPES: Dict[str, Tuple[str, List[Cell]]] = {
    "I": ("#00BCD4", [(1, 0), (1, 1), (1, 2), (1, 3)]),
    "O": ("#FFC107", [(0, 0), (0, 1), (1, 0), (1, 1)]),
    "T": ("#9C27B0", [(0, 0), (0, 1), (0, 2), (1, 1)]),
    "S": ("#4CAF50", [(0, 1), (0, 2), (1, 0), (1, 1)]),
    "Z": ("#F44336", [(0, 0), (0, 1), (1, 1), (1, 2)]),
    "J": ("#3F51B5", [(0, 0), (1, 0), (1, 1), (1, 2)]),
    "L": ("#FF9800", [(0, 2), (1, 0), (1, 1), (1, 2)]),
}
PIECE_IDS = tuple(SHAPES.keys())


def _rotate_cells(cells: List[Cell], turns: int) -> List[Cell]:
    """把一组单元格顺时针转 ``turns`` 次（以包围盒左上角为轴）。"""
    for _ in range(turns % 4):
        cells = [(c, -r) for (r, c) in cells]
        min_r = min(r for r, _ in cells)
        min_c = min(c for _, c in cells)
        cells = [(r - min_r, c - min_c) for (r, c) in cells]
    return cells


# 预生成 7 种 × 4 旋转态
ROTATIONS: Dict[str, List[List[Cell]]] = {
    pid: [_rotate_cells(cells, t) for t in range(4)]
    for pid, (_color, cells) in SHAPES.items()
}


# ---------- SRS 风格墙踢表（够用版，按旋转态索引） ----------
# 正数向右/向下，单位格。简化版：只做「左右各试 0~2 格 + 上顶 1 格」。
KICKS: List[Tuple[int, int]] = [
    (0, 0), (0, -1), (0, 1), (0, -2), (0, 2), (-1, 0), (-1, -1), (-1, 1),
]


@dataclass
class Piece:
    """活动方块：种类、旋转态、左上角位置。"""

    kind: str
    rot: int = 0
    row: int = 0
    col: int = 3

    def cells(self) -> List[Cell]:
        """当前旋转态下的绝对坐标。"""
        return [(self.row + r, self.col + c)
                for (r, c) in ROTATIONS[self.kind][self.rot % 4]]


@dataclass
class TetrisState:
    """一局对战的完整状态（可直接序列化）。"""

    board: List[List[Optional[str]]] = field(
        default_factory=lambda: [[None] * COLS for _ in range(ROWS + HIDDEN_ROWS)])
    piece: Optional[Piece] = None
    next_queue: List[str] = field(default_factory=list)
    hold: Optional[str] = None
    hold_used: bool = False
    score: int = 0
    lines: int = 0
    level: int = 1
    combo: int = -1
    game_over: bool = False
    bag: List[str] = field(default_factory=list)     # 7-bag 剩余
    rng_seed: int = 0


class TetrisEngine:
    """门面：所有操作与查询都走这里。

    对局是**确定性**的（给定 seed + 操作序列），方便联机复现与回放。
    """

    def __init__(self, seed: Optional[int] = None):
        self.state = TetrisState()
        self.state.rng_seed = seed if seed is not None else random.randrange(1 << 30)
        self._rng = random.Random(self.state.rng_seed)
        self._refill_bag()
        self._spawn()

    # ---------- 内部 ----------

    def _refill_bag(self):
        """7-bag：把七种打乱后追加，保证不会长时间缺某种。"""
        bag = list(PIECE_IDS)
        self._rng.shuffle(bag)
        self.state.bag.extend(bag)

    def _take_next(self) -> str:
        if not self.state.bag:
            self._refill_bag()
        return self.state.bag.pop(0)

    def _spawn(self):
        """从队列取一个方块放到顶部中央；放不下就 game over。"""
        if not self.state.next_queue:
            self.state.next_queue = [self._take_next() for _ in range(3)]
        kind = self.state.next_queue.pop(0)
        self.state.next_queue.append(self._take_next())
        piece = Piece(kind, 0, HIDDEN_ROWS - 1, (COLS - 4) // 2)
        # 出生位置若非法，往上顶一格再试
        if not self._fits(piece):
            piece.row -= 1
        if not self._fits(piece):
            self.state.game_over = True
            self.state.piece = None
            return
        self.state.piece = piece
        self.state.hold_used = False

    def _fits(self, piece: Piece) -> bool:
        for (r, c) in piece.cells():
            if c < 0 or c >= COLS or r >= ROWS + HIDDEN_ROWS:
                return False
            if r < 0:
                continue                 # 顶部允许悬空
            if self.state.board[r][c] is not None:
                return False
        return True

    def _lock(self):
        """把活动方块落到棋盘，消行，生成新方块。"""
        piece = self.state.piece
        if piece is None:
            return
        for (r, c) in piece.cells():
            if 0 <= r < ROWS + HIDDEN_ROWS:
                self.state.board[r][c] = SHAPES[piece.kind][0]
        self.state.piece = None
        self._clear_lines()
        self._spawn()

    def _clear_lines(self):
        """消整行，更新分数 / 等级 / combo。"""
        board = self.state.board
        kept = [row for row in board if any(cell is None for cell in row)]
        cleared = len(board) - len(kept)
        if cleared:
            for _ in range(cleared):
                kept.insert(0, [None] * COLS)
            self.state.board = kept
            # 经典计分：1/2/3/4 行 → 100/300/500/800 × level
            base = {1: 100, 2: 300, 3: 500, 4: 800}.get(cleared, 0)
            self.state.score += base * self.state.level
            self.state.lines += cleared
            self.state.combo += 1
            if self.state.combo > 0:
                self.state.score += 50 * self.state.combo * self.state.level
            new_level = self.state.lines // 10 + 1
            if new_level != self.state.level:
                self.state.level = new_level
        else:
            self.state.combo = -1

    # ---------- 公开操作 ----------

    def move(self, dcol: int) -> bool:
        """左右移动一格；返回是否成功。"""
        piece = self.state.piece
        if piece is None or self.state.game_over:
            return False
        test = Piece(piece.kind, piece.rot, piece.row, piece.col + dcol)
        if self._fits(test):
            piece.col += dcol
            return True
        return False

    def rotate(self, turns: int = 1) -> bool:
        """旋转（带墙踢）；返回是否成功。"""
        piece = self.state.piece
        if piece is None or self.state.game_over:
            return False
        new_rot = (piece.rot + turns) % 4
        for dr, dc in KICKS:
            test = Piece(piece.kind, new_rot, piece.row + dr, piece.col + dc)
            if self._fits(test):
                piece.rot = new_rot
                piece.row += dr
                piece.col += dc
                return True
        return False

    def soft_drop(self) -> bool:
        """下移一格；返回是否成功。失败说明该锁定了。"""
        piece = self.state.piece
        if piece is None or self.state.game_over:
            return False
        test = Piece(piece.kind, piece.rot, piece.row + 1, piece.col)
        if self._fits(test):
            piece.row += 1
            return True
        return False

    def hard_drop(self):
        """硬降：落到底并立即锁定。"""
        piece = self.state.piece
        if piece is None or self.state.game_over:
            return
        while self.soft_drop():
            pass
        self._lock()

    def tick(self):
        """时间驱动的一步：若下不去就锁定。"""
        if self.state.game_over:
            return
        if not self.soft_drop():
            self._lock()

    def hold_piece(self):
        """Hold：把当前方块暂存，下次再按时换回来（每方块一次）。"""
        if self.state.hold_used or self.state.piece is None:
            return
        cur = self.state.piece.kind
        if self.state.hold is None:
            self.state.hold = cur
            self._spawn()
        else:
            self.state.hold, self.state.piece = (
                cur, Piece(self.state.hold, 0, HIDDEN_ROWS - 1, (COLS - 4) // 2))
        self.state.hold_used = True

    # ---------- 查询 ----------

    def ghost_cells(self) -> List[Cell]:
        """幽灵块（落点预览）的绝对坐标。"""
        piece = self.state.piece
        if piece is None:
            return []
        test = Piece(piece.kind, piece.rot, piece.row, piece.col)
        while True:
            nxt = Piece(test.kind, test.rot, test.row + 1, test.col)
            if not self._fits(nxt):
                return test.cells()
            test = nxt

    def visible_board(self) -> List[List[Optional[str]]]:
        """去掉顶部 HIDDEN_ROWS 的可渲染棋盘。"""
        return self.state.board[HIDDEN_ROWS:]

    # ---------- 序列化（联机 / 回放用） ----------

    def to_dict(self) -> dict:
        s = self.state
        return {
            "board": s.board,
            "piece": (None if s.piece is None
                      else [s.piece.kind, s.piece.rot, s.piece.row, s.piece.col]),
            "next": list(s.next_queue),
            "hold": s.hold,
            "hold_used": s.hold_used,
            "score": s.score, "lines": s.lines, "level": s.level,
            "combo": s.combo, "game_over": s.game_over,
            "bag": list(s.bag), "seed": s.rng_seed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TetrisEngine":
        """从快照恢复（不重放操作，直接还原状态）。"""
        eng = cls(seed=data.get("seed"))
        s = eng.state
        s.board = data["board"]
        p = data.get("piece")
        s.piece = None if p is None else Piece(p[0], p[1], p[2], p[3])
        s.next_queue = list(data.get("next", []))
        s.hold = data.get("hold")
        s.hold_used = bool(data.get("hold_used"))
        s.score = data.get("score", 0)
        s.lines = data.get("lines", 0)
        s.level = data.get("level", 1)
        s.combo = data.get("combo", -1)
        s.game_over = bool(data.get("game_over"))
        s.bag = list(data.get("bag", []))
        return eng
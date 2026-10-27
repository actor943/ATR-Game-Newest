# -*- coding: utf-8 -*-
"""五子棋纯逻辑引擎（不依赖 flet，可命令行自检）。

* 棋盘 15×15，坐标 ``(row, col)``，row=0 顶部，col=0 左边。
* 黑白轮流；黑先。**没有禁手**（自由规则），够两个人下。
* 胜负：任一方向连续 5 子（含 6 子以上）即胜。
* 平局：棋盘下满无人五连。

对外只暴露 :class:`GomokuEngine`，视图只调它的方法 / 读它的属性。
状态是确定性的，且 :meth:`to_dict` / :meth:`from_dict` 可完整往返——
联机时房主生成快照、客人还原即可。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

SIZE = 15                       # 15 路棋盘
EMPTY = 0
BLACK = 1                       # 黑先手
WHITE = 2

# 胜负结果常量
ONGOING = 0
BLACK_WIN = 1
WHITE_WIN = 2
DRAW = 3

Cell = Tuple[int, int]          # (row, col)

# 四个方向：横 / 竖 / 主对角 / 副对角
_DIRS = ((0, 1), (1, 0), (1, 1), (1, -1))


@dataclass
class Move:
    """一步棋：位置 + 落子方（方便悔棋与回放）。"""

    row: int
    col: int
    stone: int                   # BLACK / WHITE


@dataclass
class GomokuState:
    """一局完整状态（可直接序列化）。"""

    board: List[List[int]] = field(
        default_factory=lambda: [[EMPTY] * SIZE for _ in range(SIZE)])
    moves: List[Move] = field(default_factory=list)
    turn: int = BLACK            # 轮到谁
    result: int = ONGOING
    win_line: List[Cell] = field(default_factory=list)   # 获胜五子，画高亮用

    def empty(self, row: int, col: int) -> bool:
        return self.board[row][col] == EMPTY


class GomokuEngine:
    """门面：落子 / 悔棋 / 查询 / 序列化。"""

    def __init__(self):
        self.state = GomokuState()

    # ---------- 内部 ----------

    def _in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < SIZE and 0 <= c < SIZE

    def _five_from(self, r: int, c: int, stone: int) -> List[Cell]:
        """从 (r,c) 出发沿四方向数同色连子；返回任一条 ≥5 的线，否则空。"""
        board = self.state.board
        for dr, dc in _DIRS:
            line: List[Cell] = [(r, c)]
            # 正向
            rr, cc = r + dr, c + dc
            while self._in_bounds(rr, cc) and board[rr][cc] == stone:
                line.append((rr, cc))
                rr += dr
                cc += dc
            # 反向
            rr, cc = r - dr, c - dc
            while self._in_bounds(rr, cc) and board[rr][cc] == stone:
                line.insert(0, (rr, cc))
                rr -= dr
                cc -= dc
            if len(line) >= 5:
                return line
        return []

    # ---------- 公开操作 ----------

    def play(self, row: int, col: int) -> bool:
        """在 (row,col) 落子；返回是否合法并成功。

        合法性：在界内 / 该格为空 / 对局未结束。
        """
        s = self.state
        if s.result != ONGOING:
            return False
        if not self._in_bounds(row, col) or not s.empty(row, col):
            return False
        stone = s.turn
        s.board[row][col] = stone
        s.moves.append(Move(row, col, stone))

        win = self._five_from(row, col, stone)
        if win:
            s.result = BLACK_WIN if stone == BLACK else WHITE_WIN
            s.win_line = win
            return True

        if len(s.moves) >= SIZE * SIZE:
            s.result = DRAW
            return True

        s.turn = WHITE if stone == BLACK else BLACK
        return True

    def undo(self) -> bool:
        """悔一步（对局结束后也允许，方便复盘）。"""
        s = self.state
        if not s.moves:
            return False
        last = s.moves.pop()
        s.board[last.row][last.col] = EMPTY
        s.result = ONGOING
        s.win_line = []
        s.turn = last.stone
        return True

    def reset(self):
        """开新局。"""
        self.state = GomokuState()

    # ---------- 查询 ----------

    def last_move(self) -> Optional[Move]:
        return self.state.moves[-1] if self.state.moves else None

    def winner(self) -> int:
        return self.state.result

    def is_over(self) -> bool:
        return self.state.result != ONGOING

    def legal(self, row: int, col: int) -> bool:
        s = self.state
        return (s.result == ONGOING and self._in_bounds(row, col)
                and s.empty(row, col))

    # ---------- 序列化（联机 / 回放） ----------

    def to_dict(self) -> dict:
        s = self.state
        return {
            "board": s.board,
            "moves": [[m.row, m.col, m.stone] for m in s.moves],
            "turn": s.turn,
            "result": s.result,
            "win_line": [list(p) for p in s.win_line],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GomokuEngine":
        """直接从快照还原（不重放，保证与房主完全一致）。"""
        eng = cls()
        s = eng.state
        s.board = [list(row) for row in data["board"]]
        s.moves = [Move(int(r), int(c), int(st))
                   for r, c, st in data.get("moves", [])]
        s.turn = int(data.get("turn", BLACK))
        s.result = int(data.get("result", ONGOING))
        s.win_line = [(int(r), int(c)) for r, c in data.get("win_line", [])]
        return eng
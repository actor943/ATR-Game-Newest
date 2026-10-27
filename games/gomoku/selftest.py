# -*- coding: utf-8 -*-
"""五子棋引擎自检：python -m games.gomoku.selftest"""
from __future__ import annotations

from .engine import (
    BLACK, BLACK_WIN, DRAW, SIZE, WHITE, WHITE_WIN, GomokuEngine,
)


def _run() -> int:
    # 1) 黑先，落子合法
    eng = GomokuEngine()
    assert eng.state.turn == BLACK
    assert eng.play(7, 7)
    assert eng.state.turn == WHITE
    assert not eng.play(7, 7)               # 同格不能落

    # 2) 横向五连
    eng = GomokuEngine()
    for i in range(4):
        eng.play(7, 3 + i)                  # 黑
        eng.play(8, 3 + i)                  # 白
    assert eng.play(7, 7)                   # 黑第五子
    assert eng.state.result == BLACK_WIN
    assert len(eng.state.win_line) >= 5

    # 3) 斜向五连
    eng = GomokuEngine()
    for i in range(4):
        eng.play(3 + i, 3 + i)
        eng.play(0, 0 + i)
    assert eng.play(7, 7)
    assert eng.state.result == BLACK_WIN

    # 4) 悔棋回退
    eng = GomokuEngine()
    eng.play(7, 7)
    assert eng.undo()
    assert eng.state.board[7][7] == 0
    assert eng.state.turn == BLACK

    # 5) 序列化往返
    eng = GomokuEngine()
    eng.play(7, 7); eng.play(7, 8)
    snap = eng.to_dict()
    eng2 = GomokuEngine.from_dict(snap)
    assert eng2.to_dict() == snap

    print("gomoku selftest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
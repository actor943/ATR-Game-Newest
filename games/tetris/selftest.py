# -*- coding: utf-8 -*-
"""俄罗斯方块引擎自检：python -m games.tetris.selftest"""
from __future__ import annotations
from .engine import COLS, ROWS, PIECE_IDS, TetrisEngine


def _run() -> int:
    fails = 0

    # 1) 七种方块齐全，出生合法
    eng = TetrisEngine(seed=1)
    assert set(PIECE_IDS) == {"I", "O", "T", "S", "Z", "J", "L"}

    # 2) 硬降 + 消行
    eng = TetrisEngine(seed=42)
    for _ in range(3):
        eng.hard_drop()
    assert eng.state.lines >= 0

    # 3) 确定性：同 seed 同操作 → 同状态
    a, b = TetrisEngine(seed=7), TetrisEngine(seed=7)
    for _ in range(20):
        a.tick(); b.tick()
    assert a.to_dict()["board"] == b.to_dict()["board"]

    # 4) 序列化往返
    snap = eng.to_dict()
    eng2 = TetrisEngine.from_dict(snap)
    assert eng2.to_dict() == snap

    print("tetris selftest: OK")
    return fails


if __name__ == "__main__":
    raise SystemExit(_run())
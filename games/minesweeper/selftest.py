# -*- coding: utf-8 -*-
"""扫雷引擎自检：``python -m games.minesweeper.selftest``。"""
from __future__ import annotations

from .engine import (
    LEVELS, LOST, PLAYING, READY, WON, MinesweeperEngine,
)


def _run() -> int:
    # 1) 三档难度合法：雷数一定少于格子数
    for level, (rows, cols, mines) in LEVELS.items():
        assert rows > 0 and cols > 0 and 0 < mines < rows * cols, level

    # 2) 首击前不布雷；首击安全区（自身 + 8 邻域）一颗雷都没有
    eng = MinesweeperEngine("easy", seed=1)
    assert eng.state.status == READY and not eng.state.mine_set
    eng.reveal(4, 4)
    s = eng.state
    assert s.status == PLAYING and len(s.mine_set) == 10
    safe = {(4, 4), *eng.neighbors(4, 4)}
    assert all(cell not in safe for cell in s.mine_set)
    assert s.opened >= 9                        # 安全区至少展开 3×3

    # 3) 邻域数字与实际雷数一致
    for r in range(s.rows):
        for c in range(s.cols):
            want = sum(1 for p in eng.neighbors(r, c) if p in s.mine_set)
            assert s.adj[r][c] == want, (r, c)

    # 4) 插旗：切换两次回到原状，旗数 / 剩余雷数跟着变
    hidden = next((r, c) for r in range(s.rows) for c in range(s.cols)
                  if not s.revealed[r][c])
    before = eng.remaining()
    assert eng.toggle_flag(*hidden)
    assert s.flagged[hidden[0]][hidden[1]] and eng.remaining() == before - 1
    assert eng.toggle_flag(*hidden)
    assert not s.flagged[hidden[0]][hidden[1]] and eng.remaining() == before
    assert not eng.toggle_flag(4, 4)            # 已翻开的格子不能插旗

    # 5) 踩雷判负，胜负后任何操作都无效
    eng2 = MinesweeperEngine("easy", seed=2)
    eng2.reveal(0, 0)
    mine = next(iter(eng2.state.mine_set))
    assert eng2.reveal(*mine)
    assert eng2.state.status == LOST and eng2.state.exploded == mine
    assert not eng2.toggle_flag(0, 0) and not eng2.reveal(0, 0)

    # 6) chord：数字格周围旗数够了，自动翻开其余邻格
    eng3 = MinesweeperEngine("easy", seed=3)
    s3 = eng3.state
    eng3._planted = True
    s3.status = PLAYING
    s3.mine_set = {(0, 0)}
    for nr, nc in eng3.neighbors(0, 0):
        s3.adj[nr][nc] += 1
    s3.revealed[0][1] = True
    s3.opened = 1
    assert eng3.toggle_flag(0, 0)
    assert eng3.chord(0, 1)                     # 旗数 == 数字 1，应能展开
    assert s3.revealed[1][0] and s3.revealed[1][1]

    # 7) 翻开所有非雷格判胜，剩余雷自动补旗
    eng4 = MinesweeperEngine("easy", seed=4)
    eng4.reveal(4, 4)
    for r in range(eng4.state.rows):
        for c in range(eng4.state.cols):
            if (r, c) not in eng4.state.mine_set and not eng4.state.revealed[r][c]:
                eng4.reveal(r, c)
    assert eng4.state.status == WON
    assert eng4.state.flags == 10 and eng4.remaining() == 0
    assert eng4.score() > 0 and eng4.best == eng4.score()

    # 8) 计时只在进行中累加
    eng4.tick(3.0)
    assert eng4.state.elapsed == 0.0
    eng5 = MinesweeperEngine("medium", seed=5)
    eng5.reveal(8, 8)
    eng5.tick(0.2)
    eng5.tick(0.3)
    assert abs(eng5.state.elapsed - 0.5) < 1e-6
    assert eng5.state.rows == 16 and eng5.state.mines == 40

    # 9) 序列化往返
    eng5.toggle_flag(0, 0)
    snap = eng5.to_dict()
    restored = MinesweeperEngine.from_dict(snap)
    assert restored.to_dict() == snap
    assert restored.neighbors(0, 0) == eng5.neighbors(0, 0)

    print("minesweeper selftest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())

# -*- coding: utf-8 -*-
"""贪吃蛇引擎自检：python -m games.snake.selftest"""
from __future__ import annotations

from .engine import COLS, ROWS, SnakeEngine, interval_for


def _run() -> int:
    # 1) 棋盘尺寸合理
    assert COLS == 20 and ROWS == 20

    # 2) 初始蛇合法、有食物
    eng = SnakeEngine(seed=1)
    assert len(eng.state.snake) == 3
    assert eng.state.food is not None
    assert eng.state.food not in eng.state.snake

    # 3) 防 180° 掉头：初始朝右，(0,-1) 应被忽略
    eng.set_direction(0, -1)
    assert eng.state.dir == (0, 1)

    # 4) 限速：speed 夹在 1~10
    eng.set_speed(99)
    assert eng.state.speed == 10
    eng.set_speed(-5)
    assert eng.state.speed == 1

    # 5) 间隔随速度单调下降
    assert interval_for(10) < interval_for(1)
    assert interval_for(5) <= 0.32 and interval_for(10) >= 0.05

    # 6) 自动加速：吃食物后 speed 上升
    eng2 = SnakeEngine(seed=2)
    eng2.state.food = (eng2.state.snake[0][0], eng2.state.snake[0][1] + 1)
    before = eng2.state.speed
    eng2.step()
    assert eng2.state.score == 10
    assert eng2.state.speed == before + 1

    # 7) 撞墙即结束
    eng3 = SnakeEngine(seed=3)
    eng3.set_direction(0, -1)     # 朝左，但当前朝右不能瞬间反；先下一帧
    # 让蛇朝左：先向下再向左（合法 90°）
    eng3.set_direction(1, 0)
    eng3.step()
    eng3.set_direction(0, -1)
    # 一路往左直到撞墙
    for _ in range(ROWS + 5):
        eng3.step()
        if eng3.state.game_over:
            break
    assert eng3.state.game_over

    # 8) 序列化往返
    snap = eng2.to_dict()
    eng4 = SnakeEngine.from_dict(snap)
    assert eng4.to_dict() == snap

    print("snake selftest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())

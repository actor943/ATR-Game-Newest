# -*- coding: utf-8 -*-
"""弹球机引擎自检：``python -m games.pinball.selftest``。"""
from __future__ import annotations

import math

from .engine import (
    BALL_R, BUMPER_SPEC, CHANNEL_X, GATE_Y, OVER, PLAYING, WALL, WORLD_H,
    WORLD_W, PinballEngine,
)


def _in_play(eng: PinballEngine) -> None:
    """把引擎摆成「球已在主区跑」的状态（跳过发射等待、单向门已关）。"""
    eng.state.status = PLAYING
    eng.state.waiting = False
    eng.state.in_play = True


def _run() -> int:
    # 1) 几何：保险杠在台面内、两片挡板之间留得下球
    assert WORLD_W > CHANNEL_X > 0 and 0 < GATE_Y < WORLD_H
    for x, y, r, *_ in BUMPER_SPEC:
        assert WALL + r < x < CHANNEL_X - r and WALL + r < y < WORLD_H
    eng0 = PinballEngine()
    left, right = eng0.flippers
    gap = right.tip()[0] - left.tip()[0]
    assert gap > 2 * BALL_R, gap

    # 2) 初始状态：3 条命、球在发射位
    assert eng0.state.balls == 3 and eng0.state.waiting
    assert eng0.state.status != OVER and eng0.ball.vy == 0

    # 3) 蓄力满自动发射；升到顶部导轨后折进主区（不丢命）
    eng = PinballEngine()
    eng.start_charge()
    for _ in range(30):
        eng.advance(0.04)
        if not eng.state.waiting:
            break                    # 蓄满那一帧刚发射，球还没开始上升
    assert not eng.state.waiting and eng.ball.vy < 0
    entered = False
    for _ in range(240):
        eng.advance(1 / 60)
        if eng.ball.x < CHANNEL_X and eng.ball.y < GATE_Y + 40:
            entered = True
            break
    assert entered, (eng.ball.x, eng.ball.y, eng.state.balls)
    assert eng.state.balls == 3

    # 4) 连续模拟 5 秒：球始终不出左右墙 / 顶墙，速度不爆表
    eng2 = PinballEngine()
    eng2.release_plunge()
    for _ in range(300):
        eng2.advance(1 / 60)
        b = eng2.ball
        assert WALL + b.r - 1.0 <= b.x <= WORLD_W - WALL - b.r + 1.0
        assert b.y >= WALL + b.r - 1.0
        assert math.hypot(b.vx, b.vy) <= 1501.0

    # 5) 保险杠：命中加分 + 主动把球弹回去
    eng3 = PinballEngine()
    _in_play(eng3)
    bx, by, br, points, _kick = BUMPER_SPEC[0]
    eng3.ball.x, eng3.ball.y = bx, by - br - BALL_R - 2.0
    eng3.ball.vx, eng3.ball.vy = 0.0, 180.0
    eng3.advance(0.02)
    assert eng3.state.score >= points and eng3.state.bumper_hits >= 1
    assert eng3.ball.vy < 0, eng3.ball.vy

    # 6) 挡板：抬起状态下落上来的球会被拍回上方并计分
    eng4 = PinballEngine()
    _in_play(eng4)
    f = eng4.flippers[0]
    f.up = True
    f.angle = f.up_angle
    tx, ty = f.tip()
    mx, my = (f.px + tx) / 2.0, (f.py + ty) / 2.0
    eng4.ball.x, eng4.ball.y = mx, my - BALL_R - 7.0 - 2.0
    eng4.ball.vx, eng4.ball.vy = 0.0, 120.0
    eng4.advance(0.02)
    assert eng4.state.flipper_hits >= 1
    assert eng4.ball.vy < 0, eng4.ball.vy

    # 7) 丢球：主区底部漏出扣一条命，3 次后结束；发射通道回落不扣命
    eng5 = PinballEngine()
    for left_balls in (2, 1, 0):
        _in_play(eng5)
        eng5.ball.x, eng5.ball.y = 200.0, WORLD_H + 40.0
        eng5.ball.vx, eng5.ball.vy = 0.0, 120.0
        eng5.advance(0.02)
        assert eng5.state.balls == left_balls
    assert eng5.is_over() and eng5.state.status == OVER
    eng6 = PinballEngine()
    eng6.release_plunge()
    eng6.ball.x = CHANNEL_X + 20.0
    eng6.ball.y = WORLD_H - 30.0
    eng6.ball.vy = 120.0
    eng6.advance(0.02)
    assert eng6.state.balls == 3 and eng6.state.waiting

    # 8) 暂停时物理不推进
    eng7 = PinballEngine()
    eng7.release_plunge()
    eng7.toggle_pause()
    before = (eng7.ball.x, eng7.ball.y, eng7.state.elapsed)
    eng7.advance(0.04)
    assert (eng7.ball.x, eng7.ball.y, eng7.state.elapsed) == before

    # 9) 单向门：进主区后球被锁在分隔墙左侧，任何角度都回不到发射道
    eng8 = PinballEngine()
    eng8.release_plunge()
    for _ in range(240):
        eng8.advance(1 / 60)
        if eng8.state.in_play:
            break
    assert eng8.state.in_play, (eng8.ball.x, eng8.ball.y)
    # 人为把球放到通道上方、给一个朝右上冲的高速，看墙是否全高生效
    eng8.state.status = PLAYING
    eng8.state.waiting = False
    eng8.ball.x, eng8.ball.y = CHANNEL_X + 18.0, 40.0
    eng8.ball.vx, eng8.ball.vy = 1200.0, -600.0
    eng8._walls()
    assert eng8.ball.x <= CHANNEL_X - BALL_R + 1e-6
    assert eng8.ball.vx < 0                     # 被弹回台面，没钻进通道
    b0 = eng8.state.balls
    for _ in range(120):
        if eng8.state.waiting:
            assert eng8.state.balls < b0        # 只可能是正常从底部漏球
            break
        eng8.advance(1 / 60)
        assert eng8.ball.x <= CHANNEL_X - BALL_R + 0.5
        assert eng8.state.in_play

    # 10) 序列化往返
    snap = eng3.to_dict()
    restored = PinballEngine.from_dict(snap)
    assert restored.to_dict() == snap
    assert restored.bumpers[0].armed == eng3.bumpers[0].armed

    print("pinball selftest: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())

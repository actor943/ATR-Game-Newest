# -*- coding: utf-8 -*-
"""台球自检：python -m games.billiards.selftest

物理与规则分开验：

* 物理：摆球不重叠、球会互相撞、摩擦会让球停下、撞库不出台、
  球能进袋、高速球不会穿透；
* 规则：空杆 / 白球落袋 / 打进对方球会犯规换手，进自己的球继续，
  提前打进 8 号球判负，清完组再打进 8 号球获胜；
* 序列化：整局快照能原样往返。
"""

from __future__ import annotations

import math

from .engine import (
    BilliardsEngine, FOUL_EIGHT_EARLY, FOUL_NO_CONTACT, FOUL_SCRATCH,
    FOUL_WRONG_BALL, GROUP_SOLID, GROUP_STRIPE, PHASE_OVER,
)
from .physics import (
    BASE_H, BASE_W, KIND_CUE, KIND_EIGHT, KIND_SOLID, KIND_STRIPE, Ball,
    all_stopped, ball_color, kind_of, legal_spot, step,
)


# ============================================================
# 物理
# ============================================================


def _test_rack() -> None:
    """摆球：15 颗目标球 + 1 颗白球，互不重叠。"""
    eng = BilliardsEngine()
    assert len(eng.balls) == 16, f"应该有 16 颗球，实际 {len(eng.balls)}"
    numbers = sorted(b.number for b in eng.balls)
    assert numbers == list(range(0, 16)), numbers
    cue = eng.cue
    assert cue is not None and cue.active
    assert abs(cue.x - eng.table.head_x) < 1e-6
    for i, a in enumerate(eng.balls):
        for b in eng.balls[i + 1:]:
            d = math.hypot(a.x - b.x, a.y - b.y)
            assert d >= (a.radius + b.radius) * 0.98, \
                f"{a.number} 与 {b.number} 重叠了（距离 {d:.2f}）"
    eight = eng.ball(8)
    assert eight is not None and eight.kind == KIND_EIGHT


def _test_kind_and_color() -> None:
    """球号 → 种类 / 颜色。"""
    assert kind_of(0) == KIND_CUE
    assert kind_of(3) == KIND_SOLID
    assert kind_of(11) == KIND_STRIPE
    assert kind_of(8) == KIND_EIGHT
    assert ball_color(0) != ball_color(1)
    assert ball_color(9) == ball_color(1)      # 同色花色球
    assert ball_color(8) != ball_color(1)


def _test_collision() -> None:
    """白球撞球：法向分量交换（等质量弹性碰撞）。"""
    eng = BilliardsEngine()
    for b in eng.balls:
        b.active = False
    t = eng.table
    a = Ball(x=200.0, y=t.height / 2, radius=t.ball_radius, number=0)
    c = Ball(x=260.0, y=t.height / 2, radius=t.ball_radius, number=1,
             kind=KIND_SOLID)
    eng.balls = [a, c]
    a.vx = 300.0
    for _ in range(40):
        step(eng.balls, t, 1 / 60)
        if c.vx > 0:
            break
    assert c.vx > 100, f"被撞的球应该动起来，实际 vx={c.vx:.1f}"
    assert a.vx < 150, f"撞完以后白球应该慢下来，实际 vx={a.vx:.1f}"


def _test_friction_stops() -> None:
    """摩擦：球最终会停下来。"""
    eng = BilliardsEngine()
    for b in eng.balls:
        b.active = False
    t = eng.table
    b = Ball(x=t.width / 2, y=t.height / 2, radius=t.ball_radius, number=1)
    eng.balls = [b]
    b.vx = 400.0
    steps = 0
    while not all_stopped(eng.balls) and steps < 60 * 30:
        step(eng.balls, t, 1 / 60)
        steps += 1
    assert all_stopped(eng.balls), "球应该停下来"
    assert steps < 60 * 30


def _test_cushion() -> None:
    """撞库：球不会跑出台面。"""
    eng = BilliardsEngine()
    for b in eng.balls:
        b.active = False
    t = eng.table
    b = Ball(x=t.width / 2, y=t.height / 2, radius=t.ball_radius, number=1)
    eng.balls = [b]
    b.vx = -900.0
    b.vy = 600.0
    for _ in range(600):
        step(eng.balls, t, 1 / 60)
        for ball in eng.balls:
            assert 0 <= ball.x <= t.width, ball.x
            assert 0 <= ball.y <= t.height, ball.y


def _test_pocket() -> None:
    """进袋：球心进了袋口范围就算落袋。"""
    eng = BilliardsEngine()
    for b in eng.balls:
        b.active = False
    t = eng.table
    b = Ball(x=60.0, y=60.0, radius=t.ball_radius, number=1)
    eng.balls = [b]
    b.vx = -300.0
    b.vy = -300.0
    potted = []
    for _ in range(120):
        ev = step(eng.balls, t, 1 / 60)
        potted.extend(ev["potted"])
        if potted:
            break
    assert potted == [1], f"球应该落袋，实际 {potted}"
    assert not b.active


def _test_no_tunneling() -> None:
    """高速球不会穿透另一颗球（子步进）。"""
    eng = BilliardsEngine()
    for b in eng.balls:
        b.active = False
    t = eng.table
    a = Ball(x=100.0, y=t.height / 2, radius=t.ball_radius, number=0)
    c = Ball(x=160.0, y=t.height / 2, radius=t.ball_radius, number=1,
             kind=KIND_SOLID)
    eng.balls = [a, c]
    a.vx = t.max_speed          # 满力，一帧能走十几像素
    hit = False
    for _ in range(120):
        ev = step(eng.balls, t, 1 / 60)
        if ev["hits"]:
            hit = True
            break
    assert hit, "高速白球应该撞到前面的球（没有穿透）"


def _test_legal_spot() -> None:
    """摆球位置合法性。"""
    eng = BilliardsEngine()
    t = eng.table
    assert not legal_spot(eng.balls, t, -5.0, t.height / 2)
    assert not legal_spot(eng.balls, t, t.width + 5.0, t.height / 2)
    assert not legal_spot(eng.balls, t, t.width / 2, -5.0)


# ============================================================
# 规则
# ============================================================


def _bare_engine(group0=None, group1=None, keep=False) -> BilliardsEngine:
    """一张干净的桌子（只有白球），方便单测规则。

    ``keep=True`` 时保留目标球在台面上（用来测「组还没清完」的情形）。
    """
    eng = BilliardsEngine()
    if not keep:
        for b in eng.balls:
            b.active = False
    cue = eng.cue
    assert cue is not None
    cue.active = True
    cue.x, cue.y = eng.table.head_x, eng.table.head_y
    eng.groups = [group0, group1]
    return eng


def _test_fouls() -> None:
    """犯规：空杆 / 白球落袋 / 打进对方球 → 换手 + 对方自由球。"""
    # 1) 空杆
    eng = _bare_engine()
    out = eng.judge([], None)
    assert FOUL_NO_CONTACT in out["fouls"], out
    assert eng.turn == 1, "犯规后应该换手"
    assert eng.ball_in_hand is True, "对方应该拿到自由球"

    # 2) 白球落袋
    eng = _bare_engine()
    out = eng.judge([0], 1)
    assert FOUL_SCRATCH in out["fouls"], out
    assert eng.turn == 1
    cue = eng.cue
    assert cue is not None and cue.active, "白球应该被重新摆回台面"

    # 3) 打进对方组的球
    eng = _bare_engine(GROUP_SOLID, GROUP_STRIPE)
    out = eng.judge([11], 11)
    assert FOUL_WRONG_BALL in out["fouls"], out
    assert eng.turn == 1


def _test_continue_and_groups() -> None:
    """打进自己的球继续打；第一杆决定花色。"""
    # 打进自己的球 → 继续
    eng = _bare_engine(GROUP_SOLID, GROUP_STRIPE)
    eng.judge([3], 3)
    assert eng.turn == 0, "进自己的球应该继续"
    assert eng.groups[0] == GROUP_SOLID

    # 还没定花色时，第一杆进什么球就归什么组
    eng = _bare_engine()
    eng.judge([12], 12)
    assert eng.groups[0] == GROUP_STRIPE, eng.groups

    # 没进自己的球 → 换手
    eng = _bare_engine(GROUP_SOLID, GROUP_STRIPE)
    eng.judge([], 3)
    assert eng.turn == 1, "没进球应该换手"


def _test_eight_ball() -> None:
    """8 号球：提前打进判负，清完组再打进获胜。"""
    # 1) 提前打进 8 号 → 直接判负（自己的球还在台面上）
    eng = _bare_engine(GROUP_SOLID, GROUP_STRIPE, keep=True)
    out = eng.judge([8], 3)
    assert FOUL_EIGHT_EARLY in out["fouls"], out
    assert eng.result == 1, "提前打进 8 号球应该判负"
    assert eng.phase == PHASE_OVER

    # 2) 清完组再打进 8 号 → 获胜
    eng = _bare_engine(GROUP_SOLID, GROUP_STRIPE)
    for b in eng.balls:
        if b.kind == GROUP_SOLID:
            b.active = False        # 实色球都进袋了
    eng.judge([8], 3)
    assert eng.result == 0, "打进 8 号球应该获胜"
    assert eng.phase == PHASE_OVER


def _test_ball_in_hand() -> None:
    """自由球：能放在合法位置，非法位置不行。"""
    eng = _bare_engine()
    eng.judge([], None)             # 空杆 → 对方自由球
    assert eng.ball_in_hand is True
    t = eng.table
    assert eng.can_place_cue(t.width / 2, t.height / 2)
    assert not eng.can_place_cue(-10, t.height / 2)
    assert eng.place_cue(t.width / 2, t.height / 2)
    assert eng.ball_in_hand is False
    cue = eng.cue
    assert cue is not None
    assert abs(cue.x - t.width / 2) < 1e-6


# ============================================================
# 序列化
# ============================================================


def _test_serialize() -> None:
    """整局快照往返。"""
    eng = BilliardsEngine()
    eng.groups = [GROUP_SOLID, GROUP_STRIPE]
    eng.turn = 1
    eng.judge([3], 3)
    snap = eng.to_dict()
    eng2 = BilliardsEngine.from_dict(snap)
    assert eng2.to_dict() == snap

    # 不同尺寸的球桌：坐标按比例换算
    small = BilliardsEngine.from_dict(snap, size=(BASE_W / 2, BASE_H / 2))
    cue = small.cue
    assert cue is not None
    orig = eng.cue
    assert orig is not None
    assert abs(cue.x - orig.x / 2) < 0.5
    assert small.turn == eng.turn
    assert small.groups == [GROUP_SOLID, GROUP_STRIPE]


def _test_reset() -> None:
    """重开一局：球位、花色、轮次全部复位。"""
    eng = BilliardsEngine()
    eng.judge([3], 3)
    eng.reset()
    assert eng.turn == 0
    assert eng.groups == [None, None]
    assert eng.potted == []
    assert eng.result is None
    assert len(eng.balls) == 16
    assert all(b.active for b in eng.balls)


# ============================================================
# 入口
# ============================================================


def _run() -> int:
    cases = [
        _test_rack, _test_kind_and_color, _test_collision,
        _test_friction_stops, _test_cushion, _test_pocket,
        _test_no_tunneling, _test_legal_spot,
        _test_fouls, _test_continue_and_groups, _test_eight_ball,
        _test_ball_in_hand,
        _test_serialize, _test_reset,
    ]
    for case in cases:
        case()
    print(f"billiards selftest: OK（{len(cases)} 组用例）")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())

# -*- coding: utf-8 -*-
"""弹球机纯物理 / 规则引擎（不依赖 flet，可命令行自检）。

世界坐标固定 ``400 × 640``，y 轴向下；渲染层只负责乘一个缩放系数，
所以窗口怎么拉伸都不影响手感。

台面结构
--------
* 右侧是**发射通道**（``x > CHANNEL_X``），球在这里蓄力弹射；
* 球升到 ``GATE_Y`` 时经「顶部单向导轨」折进主区，随后**单向门立即关闭**
  （成熟弹球机的 shooter-lane one-way gate）：分隔墙从此在**整个高度**
  都有效，主区里的球无论什么角度都回不到发射通道，只可能从底部挡板
  之间正常漏球 —— 不会出现「弹回出生点 / 白丢一球」；
* 主区有 3 个大保险杠（+100）和 2 个小目标（+50），撞上会被主动弹开；
* 底部两片**挡板**绕枢轴旋转，抬起时能把球打回台面；两侧斜墙
  （slingshot）也会弹球并加分；
* 球从挡板中间漏到底部就丢一条命，3 条命用尽即结束；只有**发射力度
  不够、球还没过导轨**时才会落回发射通道，这种不算丢命，重新发射即可。

物理
----
``advance(dt)`` 按 2 个子步积分：重力、空气阻尼、库边反弹、圆 / 线段
碰撞（点到线段最近点），碰撞后主动加一记冲量，速度有上限防穿透。
蓄力、暂停、丢球、计分、序列化都在这个模块里，视图层只管画和收输入。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

# ---------- 台面几何（世界坐标） ----------
WORLD_W = 400.0
WORLD_H = 640.0
BALL_R = 9.0
WALL = 10.0                       # 外墙厚度（视觉）
CHANNEL_X = WORLD_W - 44.0        # 发射通道与主区的分隔墙
GATE_Y = 112.0                    # 顶部导轨高度
LAUNCH_X = (CHANNEL_X + WORLD_W - WALL) / 2.0
LAUNCH_Y = WORLD_H - 40.0

GRAVITY = 760.0
RESTITUTION = 0.86                # 库边弹性
MAX_SPEED = 1500.0
AIR_DRAG = 0.02                   # 每秒速度衰减比例
CHARGE_SECONDS = 0.8              # 蓄满需要多久

FLIPPER_LEN = 70.0
FLIPPER_HALF_W = 7.0
FLIPPER_Y = WORLD_H - 92.0
FLIPPER_REST = 0.48               # 弧度，正角 = 朝右下
FLIPPER_UP = -0.48
ANG_SPEED = 10.0                  # 挡板角速度（弧度 / 秒）
FLIP_KICK = 300.0                 # 抬起过程中拍球的冲量
FLIP_KICK_IDLE = 140.0            # 已经抬起、球自然落上来时的冲量

# 保险杠 / 小目标：(x, y, 半径, 分数, 弹开冲量)
BUMPER_SPEC = (
    (108.0, 218.0, 23.0, 100, 250.0),
    (252.0, 196.0, 23.0, 100, 250.0),
    (180.0, 312.0, 25.0, 100, 265.0),
    (58.0, 352.0, 12.0, 50, 160.0),
    (296.0, 338.0, 12.0, 50, 160.0),
)

# 底部两侧斜墙（slingshot）：(ax, ay, bx, by)
SLING_SPEC = (
    (WALL, 456.0, 86.0, 528.0),
    (CHANNEL_X, 456.0, 268.0, 528.0),
)
SLING_KICK = 190.0
SLING_POINTS = 50

READY = "ready"
PLAYING = "playing"
OVER = "over"


# ---------- 数据结构 ----------

@dataclass
class Ball:
    x: float = LAUNCH_X
    y: float = LAUNCH_Y
    vx: float = 0.0
    vy: float = 0.0
    r: float = BALL_R


@dataclass
class Flipper:
    side: str
    px: float
    py: float
    rest_angle: float
    up_angle: float
    angle: float = 0.0
    up: bool = False
    omega: float = 0.0            # 本步角速度（判断是否正在拍）
    cooldown: float = 0.0         # 防止一次接触反复加分

    def tip(self) -> Tuple[float, float]:
        """挡板自由端的坐标。"""
        return (self.px + math.cos(self.angle) * FLIPPER_LEN,
                self.py + math.sin(self.angle) * FLIPPER_LEN)


@dataclass
class Bumper:
    x: float
    y: float
    r: float
    points: int
    kick: float
    armed: bool = True            # 球离开之后才能再次计分


@dataclass
class PinballState:
    """一局弹球的完整状态。"""

    score: int = 0
    best: int = 0
    balls: int = 3                # 剩余球数
    bumper_hits: int = 0
    flipper_hits: int = 0
    elapsed: float = 0.0
    status: str = READY
    paused: bool = False
    waiting: bool = True          # 球在发射位，等待弹射
    in_play: bool = False         # 球已过单向门进入主区（门已关闭）
    charging: bool = False
    power: float = 0.0            # 0~1，蓄力条
    message: str = ""             # 短暂提示："+100" / "丢球" 等
    message_ttl: float = 0.0


def closest_on_segment(px: float, py: float,
                       ax: float, ay: float, bx: float,
                       by: float) -> Tuple[float, float]:
    """点 (px, py) 到线段 AB 的最近点。"""
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 < 1e-9:
        return ax, ay
    u = ((px - ax) * dx + (py - ay) * dy) / length2
    u = max(0.0, min(1.0, u))
    return ax + u * dx, ay + u * dy


class PinballEngine:
    """门面：物理推进、蓄力发射、挡板、计分、丢球与序列化。"""

    def __init__(self, best: int = 0):
        self.state = PinballState(best=best)
        self.ball = Ball()
        self.flippers = (
            Flipper("left", 105.0, FLIPPER_Y, FLIPPER_REST, FLIPPER_UP,
                    angle=FLIPPER_REST),
            Flipper("right", 255.0, FLIPPER_Y,
                    math.pi - FLIPPER_REST, math.pi - FLIPPER_UP,
                    angle=math.pi - FLIPPER_REST),
        )
        self.bumpers = [Bumper(*spec) for spec in BUMPER_SPEC]
        self._sling_cd = [0.0] * len(SLING_SPEC)
        self._reset_ball()

    # ---------- 生命周期 ----------

    def _reset_ball(self, message: str = "") -> None:
        self.ball = Ball()
        self.state.waiting = True
        self.state.in_play = False        # 新球重新开门
        self.state.charging = False
        self.state.power = 0.0
        self.state.status = READY
        if message:
            self._message(message)

    def restart(self, best: Optional[int] = None) -> None:
        """重开一局（最高分跨局保留）。"""
        if best is not None:
            self.state.best = best
        s = self.state
        s.score = 0
        s.balls = 3
        s.bumper_hits = 0
        s.flipper_hits = 0
        s.elapsed = 0.0
        s.paused = False
        s.message = ""
        s.message_ttl = 0.0
        for f in self.flippers:
            f.up = False
            f.angle = f.rest_angle
            f.omega = 0.0
            f.cooldown = 0.0
        for b in self.bumpers:
            b.armed = True
        self._sling_cd = [0.0] * len(SLING_SPEC)
        self._reset_ball()

    def toggle_pause(self) -> None:
        if self.state.status != OVER:
            self.state.paused = not self.state.paused

    # ---------- 输入 ----------

    def set_flipper(self, side: str, up: bool) -> None:
        """抬起 / 放下某侧挡板。"""
        for f in self.flippers:
            if f.side == side:
                f.up = bool(up)

    def start_charge(self) -> None:
        """开始蓄力（球必须在发射位）。"""
        s = self.state
        if s.status == OVER or not s.waiting or s.paused:
            return
        if not s.charging:
            s.charging = True
            s.power = 0.0

    def charge(self, dt: float) -> None:
        """蓄力推进；蓄满自动发射（按住不放也不会卡死）。"""
        s = self.state
        if not s.charging or s.paused:
            return
        s.power = min(1.0, s.power + float(dt) / CHARGE_SECONDS)
        if s.power >= 1.0:
            self.release_plunge()

    def release_plunge(self) -> bool:
        """松手发射：力度决定初速，最小力度也保证能越过顶部导轨。"""
        s = self.state
        if s.status == OVER or not s.waiting or s.paused:
            return False
        power = max(0.25, min(1.0, s.power if s.charging else 0.45))
        self.ball.vy = -(880.0 + 420.0 * power)
        self.ball.vx = -10.0
        s.waiting = False
        s.in_play = False             # 发射阶段：门还开着，等球过导轨再关
        s.charging = False
        s.power = 0.0
        s.status = PLAYING
        self._message("发射！")
        return True

    # ---------- 计分 / 提示 ----------

    def _message(self, text: str) -> None:
        self.state.message = text
        self.state.message_ttl = 1.1

    def _add_score(self, points: int, text: str) -> None:
        s = self.state
        s.score += points
        s.best = max(s.best, s.score)
        self._message(text)
        if points >= 100:
            s.bumper_hits += 1

    # ---------- 主循环 ----------

    def advance(self, dt: float) -> None:
        """推进一帧；暂停 / 结束 / 等待发射时都不跑物理。"""
        s = self.state
        if s.paused or s.status == OVER:
            return
        dt = max(0.001, min(0.04, float(dt)))
        self.charge(dt)
        if s.message_ttl > 0:
            s.message_ttl = max(0.0, s.message_ttl - dt)
        if s.waiting:
            return
        if s.status == PLAYING:
            s.elapsed += dt
        for _ in range(2):                  # 两个子步，防高速穿透
            self._step(dt / 2.0)

    def _step(self, h: float) -> None:
        """一个物理子步。"""
        s, b = self.state, self.ball
        self._step_flippers(h)
        for i in range(len(self._sling_cd)):
            self._sling_cd[i] = max(0.0, self._sling_cd[i] - h)

        b.vy += GRAVITY * h
        drag = max(0.0, 1.0 - AIR_DRAG * h)
        b.vx *= drag
        b.vy *= drag
        self._clamp_speed()
        b.x += b.vx * h
        b.y += b.vy * h

        self._gate()
        self._walls()
        self._hit_bumpers()
        self._hit_slings()
        self._hit_flippers()
        self._clamp_speed()
        self._drain()

    def _clamp_speed(self) -> None:
        b = self.ball
        speed = math.hypot(b.vx, b.vy)
        if speed > MAX_SPEED:
            k = MAX_SPEED / speed
            b.vx *= k
            b.vy *= k

    def _step_flippers(self, h: float) -> None:
        """挡板按角速度平滑转向目标角度。"""
        for f in self.flippers:
            f.cooldown = max(0.0, f.cooldown - h)
            target = f.up_angle if f.up else f.rest_angle
            delta = target - f.angle
            step = max(-ANG_SPEED * h, min(ANG_SPEED * h, delta))
            f.omega = step / h if h > 0 else 0.0
            f.angle += step

    # ---------- 碰撞：库边 / 导轨 ----------

    def _gate(self) -> None:
        """顶部单向导轨：球升到 GATE_Y 折进主区，随后单向门立即关闭。"""
        s, b = self.state, self.ball
        if s.in_play or b.x <= CHANNEL_X or b.y > GATE_Y or b.vy >= 0:
            return
        # 沿导轨滑进主区：落点离隔墙远一些、速度朝左下，进门不会贴墙
        b.x = CHANNEL_X - b.r - 30.0
        b.y = GATE_Y - b.r - 4.0
        b.vx = -170.0
        b.vy = 60.0
        s.in_play = True                  # 关门：之后主区与发射道完全隔离
        self._message("进入台面")

    def _walls(self) -> None:
        """外墙 + 发射道单向门：按 ``in_play`` 把球锁在对应分区。

        门关上后分隔墙**整个高度**都有效（原来只在 GATE_Y 以下有墙，
        球从主区顶部斜着飞过去就能落回发射道）；主区球最右只到
        ``CHANNEL_X - r``，任何角度撞过来都只会弹回台面，不会再回出生点。
        发射阶段相反：球被夹在通道里，唯一的出口就是顶部导轨。
        """
        b = self.ball
        top = WALL + b.r
        if self.state.in_play:
            left, right = WALL + b.r, CHANNEL_X - b.r
        else:
            left, right = CHANNEL_X + b.r, WORLD_W - WALL - b.r
        if b.x < left:
            b.x = left
            b.vx = abs(b.vx) * RESTITUTION
        elif b.x > right:
            b.x = right
            b.vx = -abs(b.vx) * RESTITUTION
        if b.y < top:
            b.y = top
            b.vy = abs(b.vy) * RESTITUTION

    def _reflect(self, nx: float, ny: float, e: float = RESTITUTION) -> None:
        """沿法线反射速度（只在球朝障碍物运动时生效）。"""
        b = self.ball
        vn = b.vx * nx + b.vy * ny
        if vn < 0:
            b.vx -= (1.0 + e) * vn * nx
            b.vy -= (1.0 + e) * vn * ny

    def _hit_bumpers(self) -> None:
        """圆形保险杠：把球推出表面、反射并主动弹开，命中加分。"""
        b = self.ball
        for bumper in self.bumpers:
            dx, dy = b.x - bumper.x, b.y - bumper.y
            dist = math.hypot(dx, dy)
            reach = b.r + bumper.r
            if dist > reach + 6.0:
                bumper.armed = True
                continue
            if dist < 1e-6:
                nx, ny = 0.0, -1.0
                dist = 0.0
            else:
                nx, ny = dx / dist, dy / dist
            if dist < reach:
                b.x = bumper.x + nx * (reach + 0.5)
                b.y = bumper.y + ny * (reach + 0.5)
                self._reflect(nx, ny, 0.92)
                if bumper.armed:
                    b.vx += nx * bumper.kick
                    b.vy += ny * bumper.kick
                    self._add_score(bumper.points, f"+{bumper.points}")
                    bumper.armed = False

    def _hit_slings(self) -> None:
        """两侧斜墙：反弹 + 一记冲量，把快要漏下去的球弹回台面。"""
        b = self.ball
        for i, (ax, ay, bx, by) in enumerate(SLING_SPEC):
            qx, qy = closest_on_segment(b.x, b.y, ax, ay, bx, by)
            dx, dy = b.x - qx, b.y - qy
            dist = math.hypot(dx, dy)
            reach = b.r + 4.0
            if dist >= reach:
                continue
            if dist < 1e-6:
                nx, ny = 0.0, -1.0
            else:
                nx, ny = dx / dist, dy / dist
            b.x = qx + nx * (reach + 0.5)
            b.y = qy + ny * (reach + 0.5)
            self._reflect(nx, ny, 0.9)
            if self._sling_cd[i] <= 0:
                b.vx += nx * SLING_KICK
                b.vy += ny * SLING_KICK
                self._add_score(SLING_POINTS, f"+{SLING_POINTS}")
                self._sling_cd[i] = 0.18

    def _hit_flippers(self) -> None:
        """挡板线段碰撞；抬起时给球一记向上的拍击。"""
        b = self.ball
        for f in self.flippers:
            ax, ay = f.px, f.py
            bx, by = f.tip()
            qx, qy = closest_on_segment(b.x, b.y, ax, ay, bx, by)
            dx, dy = b.x - qx, b.y - qy
            dist = math.hypot(dx, dy)
            reach = b.r + FLIPPER_HALF_W
            if dist >= reach:
                continue
            if dist < 1e-6:
                nx, ny = 0.0, -1.0
            else:
                nx, ny = dx / dist, dy / dist
            b.x = qx + nx * (reach + 0.5)
            b.y = qy + ny * (reach + 0.5)
            self._reflect(nx, ny, 0.72)
            moving = f.up and abs(f.omega) > 0.5
            kick = FLIP_KICK if moving else (FLIP_KICK_IDLE if f.up else 0.0)
            if kick and f.cooldown <= 0:
                b.vx += nx * kick
                b.vy += ny * kick - 30.0
                self.state.flipper_hits += 1
                self._add_score(25, "+25")
                f.cooldown = 0.14

    # ---------- 丢球 ----------

    def _drain(self) -> None:
        """发射没够到导轨而落回通道 = 重新发射；主区底部漏球 = 丢一条命。

        单向门关上后球已不可能出现在通道，所以第一条只会在发射阶段触发，
        也就不存在「进了台面又被判回出生点」的情况。
        """
        s, b = self.state, self.ball
        if (not s.in_play and b.x > CHANNEL_X
                and b.y >= LAUNCH_Y - 6.0 and b.vy >= 0):
            self._reset_ball("重新发射")
            return
        if b.y - b.r > WORLD_H + 8.0:
            s.balls -= 1
            if s.balls <= 0:
                s.balls = 0
                s.status = OVER
                s.charging = False
                s.power = 0.0
                self.ball.vx = self.ball.vy = 0.0
                self._message("游戏结束")
            else:
                self._reset_ball("丢球！")

    # ---------- 查询 ----------

    def is_over(self) -> bool:
        return self.state.status == OVER

    def to_dict(self) -> dict:
        """整局快照（自检往返用；联机暂未开放）。"""
        s, b = self.state, self.ball
        return {
            "ball": [b.x, b.y, b.vx, b.vy],
            "flippers": [[f.angle, f.up, f.cooldown] for f in self.flippers],
            "bumpers": [x.armed for x in self.bumpers],
            "score": s.score, "best": s.best, "balls": s.balls,
            "bumper_hits": s.bumper_hits, "flipper_hits": s.flipper_hits,
            "elapsed": s.elapsed, "status": s.status, "paused": s.paused,
            "waiting": s.waiting, "in_play": s.in_play,
            "charging": s.charging, "power": s.power,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PinballEngine":
        """从快照还原。"""
        eng = cls(best=data.get("best", 0))
        s = eng.state
        b = eng.ball
        b.x, b.y, b.vx, b.vy = data.get("ball", [LAUNCH_X, LAUNCH_Y, 0, 0])
        for f, (angle, up, cd) in zip(
                eng.flippers, data.get("flippers", [])):
            f.angle, f.up, f.cooldown = angle, bool(up), cd
        for bumper, armed in zip(eng.bumpers, data.get("bumpers", [])):
            bumper.armed = bool(armed)
        s.score = data.get("score", 0)
        s.balls = data.get("balls", 3)
        s.bumper_hits = data.get("bumper_hits", 0)
        s.flipper_hits = data.get("flipper_hits", 0)
        s.elapsed = data.get("elapsed", 0.0)
        s.status = data.get("status", READY)
        s.paused = bool(data.get("paused", False))
        s.waiting = bool(data.get("waiting", True))
        s.in_play = bool(data.get("in_play", False))
        s.charging = bool(data.get("charging", False))
        s.power = data.get("power", 0.0)
        return eng

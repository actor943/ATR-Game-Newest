# -*- coding: utf-8 -*-
"""台球物理内核：球、球桌、碰撞、摩擦（纯 Python，**不依赖 flet**）。

这个文件只回答一个问题：**球怎么动**。

坐标
----
台面坐标系：左上角为原点，x 向右、y 向下，单位是「像素」。

缩放
----
所有几何都以 760×395 的标准球桌为基准（比例与球桌贴图的绿色台面区
一致）。换个尺寸时整张桌**等比缩放**（球半径、袋口、最大速度、摩擦
一起缩放），所以手机上的小球和电脑上的大球手感完全一样 —— 这是联机
能玩的前提（双方各自用自己的桌面尺寸）。

防穿透
------
一帧里球最多移动 ``max_speed * dt`` 像素，球半径才 9 像素，直接算就会
「穿过去」。所以 :func:`step` 会按速度把一帧拆成若干**子步**，每个子步都
重新检测碰撞（见 :func:`_substep`）。

规则（谁赢、什么时候换手）在 :mod:`games.billiards.engine`，
这里不掺任何规则判断。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

# ============================================================
# 基准尺寸（与 assets/billiards/table.png 的绿色台面区同比例）
# ============================================================
#
# 贴图 1200×678，绿色台面区在 (56, 56) - (1143, 621)，即 1087×565。
# 下面这组基准就是「台面区」缩放到 760 宽时的样子（比例 760/1087）。

BASE_W = 760.0          # 台面宽（不含库边）
BASE_H = 395.0          # 台面高
BALL_R = 12.5           # 球半径

# 袋口位置：量自 table.png 的黑色袋口圆（贴图像素：x, y, 半径）
_POCKETS_SRC = (
    (58.6, 67.6, 31.0),     # 左上角袋
    (1130.1, 65.8, 31.0),   # 右上角袋
    (60.2, 613.1, 31.0),    # 左下角袋
    (1131.6, 611.5, 31.0),  # 右下角袋
    (592.9, 53.3, 27.0),    # 上中袋
    (592.9, 623.7, 27.0),   # 下中袋
)
# 绿色台面区在贴图里的左上角（贴图像素）
_GREEN_ORIGIN = (56.0, 56.0)
# 绿色台面区的宽（贴图像素）—— 用来把贴图像素换算成本机像素
_GREEN_W = 1087.0

POCKET_R = 21.0         # 角袋判定半径（按基准桌）
POCKET_R_SIDE = 19.0    # 中袋判定半径（按基准桌）

# ============================================================
# 物理参数（会随桌面尺寸一起缩放）
# ============================================================

RESTITUTION = 0.93      # 撞库边的反弹系数
ROLL_DECEL = 190.0      # 滚动摩擦造成的减速度（像素/秒²）
STOP_SPEED = 4.0        # 低于这个速度就当作静止
MAX_SPEED = 640.0       # 满力一杆的速度（像素/秒）
MAX_SUBSTEP = 12        # 一帧最多拆成多少个子步

# ============================================================
# 球的种类与颜色
# ============================================================

KIND_CUE = "cue"        # 白球
KIND_SOLID = "solid"    # 实色 1~7
KIND_STRIPE = "stripe"  # 花色 9~15
KIND_EIGHT = "eight"    # 8 号黑球

# 1~8 号球的球色（9~15 号是同色的花色球）
BALL_COLORS: Dict[int, str] = {
    1: "#F5C518",   # 黄
    2: "#1E5FBF",   # 蓝
    3: "#D2372C",   # 红
    4: "#6A2C91",   # 紫
    5: "#EF7C1A",   # 橙
    6: "#1E8E4E",   # 绿
    7: "#7B3F1D",   # 栗
    8: "#141414",   # 黑
}


def ball_color(number: int) -> str:
    """球色：花色球跟同号实色球同色，8 号是黑色。"""
    if number <= 0:
        return "#F7F4EC"          # 白球
    if number == 8:
        return BALL_COLORS[8]
    base = number - 8 if number > 8 else number
    return BALL_COLORS.get(base, "#888888")


def kind_of(number: int) -> str:
    """球号 → 球的种类。"""
    if number <= 0:
        return KIND_CUE
    if number == 8:
        return KIND_EIGHT
    if number <= 7:
        return KIND_SOLID
    return KIND_STRIPE


# ============================================================
# 数据结构
# ============================================================


@dataclass
class Ball:
    """一颗球：位置 + 速度 + 半径 + 号码。"""

    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    radius: float = BALL_R
    number: int = 0
    kind: str = KIND_CUE
    active: bool = True          # False = 已经落袋

    def speed(self) -> float:
        """当前速度大小。"""
        return math.hypot(self.vx, self.vy)

    def stop(self) -> None:
        """把速度清零（落袋 / 归位时用）。"""
        self.vx = 0.0
        self.vy = 0.0

    def to_dict(self) -> list:
        """序列化（联机快照用）：``[号码, x, y, 是否在台面]``。"""
        return [self.number, round(self.x, 2), round(self.y, 2),
                1 if self.active else 0]


class Table:
    """一张球桌：尺寸 + 由尺寸推出来的球半径、袋口位置。

    袋口共 6 个：四个角袋 + 两个中袋。判定进袋用的是「球心到袋心的
    距离 ≤ 袋口半径」，不是「球心到边的距离」，这样角袋才够大。
    """

    def __init__(self, width: float = BASE_W, height: float = BASE_H):
        self.width = float(width)
        self.height = float(height)
        # 缩放系数：所有长度与速度都跟着它走
        self.scale = self.width / BASE_W
        self.ball_radius = BALL_R * self.scale
        # 贴图像素 → 本机像素（袋口位置直接照着球桌贴图量）
        art = self.width / _GREEN_W
        self.pockets: List[Tuple[float, float, float]] = [
            ((px - _GREEN_ORIGIN[0]) * art, (py - _GREEN_ORIGIN[1]) * art,
             pr * art)
            for (px, py, pr) in _POCKETS_SRC
        ]
        self.max_speed = MAX_SPEED * self.scale
        self.roll_decel = ROLL_DECEL * self.scale

    # ---------- 几个关键位置 ----------

    @property
    def head_x(self) -> float:
        """开球线（白球默认摆放处的竖线）。"""
        return self.width * 0.25

    @property
    def head_y(self) -> float:
        return self.height * 0.5

    @property
    def foot_x(self) -> float:
        """底袋线（摆球区前沿）。"""
        return self.width * 0.75

    def to_dict(self) -> list:
        return [self.width, self.height]


# ============================================================
# 摆球
# ============================================================


def rack_numbers() -> List[int]:
    """标准八球摆球顺序（三角形里从上到下、每排从左到右）。

    第三排中间放 8 号，尾排两个角一实一花。
    """
    return [1, 2, 3, 4, 8, 5, 6, 9, 10, 12, 11, 13, 14, 15, 7]


def rack_balls(table: Table) -> List[Ball]:
    """按标准八球摆法摆 15 颗目标球（不含白球）。"""
    r = table.ball_radius
    # 三角形顶点在摆球区前沿，最尾一排离底袋留一点空隙
    apex_x = table.width - r * 9.2
    cy = table.height / 2.0
    balls: List[Ball] = []
    for i, number in enumerate(rack_numbers()):
        row = 0
        index = i
        # 先算出这个球在第几排、排内第几个
        for rr in range(5):
            if index < rr + 1:
                row = rr
                break
            index -= rr + 1
        x = apex_x + row * 1.732 * r          # 每排往后挪 1.732R
        y = cy + (index - row / 2.0) * 2.0 * r
        balls.append(Ball(x=x, y=y, radius=r, number=number,
                          kind=kind_of(number)))
    return balls


# ============================================================
# 物理
# ============================================================


def step(balls: Sequence[Ball], table: Table, dt: float) -> dict:
    """把台面上的球推进 ``dt`` 秒，返回这一段发生的事件。

    返回值::

        {"potted": [球号...],   # 落袋的球
         "first_contact": 球号 or None,  # 白球最先碰到的球
         "hits": 次数,          # 球与球碰撞次数
         "cushion": 次数}       # 撞库次数
    """
    ev: Dict[str, object] = {"potted": [], "first_contact": None,
                             "hits": 0, "cushion": 0}
    active = [b for b in balls if b.active]
    if not active or dt <= 0:
        return ev

    # 子步进：球跑得越快，拆得越细，保证不会互相穿透
    max_v = max(max(abs(b.vx), abs(b.vy)) for b in active)
    steps = 1
    if max_v > 0:
        steps = int(math.ceil(max_v * dt / (table.ball_radius * 0.5)))
        steps = max(1, min(steps, MAX_SUBSTEP))
    h = dt / steps
    for _ in range(steps):
        _substep(active, table, h, ev)
    return ev


def _substep(balls: List[Ball], table: Table, h: float, ev: dict) -> None:
    """一个小步：移动 → 撞库 → 球撞球 → 摩擦 → 判落袋。"""
    # 1) 位置积分
    for b in balls:
        if not b.active:
            continue            # 已经落袋的球不再参与
        b.x += b.vx * h
        b.y += b.vy * h

    # 2) 库边反弹（矩形台面，四条边各判一次）
    r = table.ball_radius
    for b in balls:
        if not b.active:
            continue
        if b.x < r:
            b.x = r
            b.vx = abs(b.vx) * RESTITUTION
            ev["cushion"] += 1
        elif b.x > table.width - r:
            b.x = table.width - r
            b.vx = -abs(b.vx) * RESTITUTION
            ev["cushion"] += 1
        if b.y < r:
            b.y = r
            b.vy = abs(b.vy) * RESTITUTION
            ev["cushion"] += 1
        elif b.y > table.height - r:
            b.y = table.height - r
            b.vy = -abs(b.vy) * RESTITUTION
            ev["cushion"] += 1

    # 3) 球与球碰撞（等质量弹性碰撞：法向分量交换，切向不变）
    for i in range(len(balls)):
        a = balls[i]
        if not a.active:
            continue
        for j in range(i + 1, len(balls)):
            c = balls[j]
            if not c.active:
                continue
            dx = c.x - a.x
            dy = c.y - a.y
            dist = math.hypot(dx, dy)
            min_r = a.radius + c.radius
            if dist <= 1e-9 or dist >= min_r:
                continue
            nx, ny = dx / dist, dy / dist
            # 相对速度（a 相对 c）在法线上的分量
            vn = (a.vx - c.vx) * nx + (a.vy - c.vy) * ny
            if vn <= 0:
                continue                     # 已经在分开，不用管
            a.vx -= vn * nx
            a.vy -= vn * ny
            c.vx += vn * nx
            c.vy += vn * ny
            # 把重叠的两颗球推开，免得下一帧又撞一次（能量白白掉光）
            overlap = (min_r - dist) / 2.0
            a.x -= nx * overlap
            a.y -= ny * overlap
            c.x += nx * overlap
            c.y += ny * overlap
            ev["hits"] += 1
            if ev["first_contact"] is None:
                if a.number == 0:
                    ev["first_contact"] = c.number
                elif c.number == 0:
                    ev["first_contact"] = a.number

    # 4) 滚动摩擦：速度按固定减速度变小（匀减速，比乘系数更接近真实）
    for b in balls:
        if not b.active:
            continue
        sp = b.speed()
        if sp <= 0:
            continue
        ns = sp - table.roll_decel * h
        if ns < STOP_SPEED:
            ns = 0.0
        k = ns / sp
        b.vx *= k
        b.vy *= k

    # 5) 落袋判定
    for b in balls:
        if not b.active:
            continue            # 已经进过袋的球不再重复计数
        for (px, py, pr) in table.pockets:
            if math.hypot(b.x - px, b.y - py) <= pr:
                b.active = False
                b.stop()
                ev["potted"].append(b.number)
                break


def all_stopped(balls: Sequence[Ball]) -> bool:
    """台面上所有球都停下来了？（一杆结束的判定）"""
    for b in balls:
        if b.active and b.speed() > 0:
            return False
    return True


# ============================================================
# 摆球位置辅助（白球归位 / 自由球）
# ============================================================


def legal_spot(balls: Sequence[Ball], table: Table, x: float, y: float,
               ignore: Optional[Ball] = None) -> bool:
    """这个位置能不能放球：不出台面、不与别的球重叠。"""
    r = table.ball_radius
    if not (r <= x <= table.width - r and r <= y <= table.height - r):
        return False
    for b in balls:
        if b is ignore or not b.active:
            continue
        if math.hypot(b.x - x, b.y - y) < (b.radius + r) * 0.98:
            return False
    return True


def find_spot(balls: Sequence[Ball], table: Table,
              prefer_x: float, prefer_y: float) -> Tuple[float, float]:
    """找一个能放球的位置：先试首选点，不行就在附近螺旋式找。"""
    if legal_spot(balls, table, prefer_x, prefer_y):
        return prefer_x, prefer_y
    r = table.ball_radius
    for ring in range(1, 14):
        for k in range(ring * 8):
            ang = k * (math.pi / 4.0)
            x = prefer_x + math.cos(ang) * ring * r
            y = prefer_y + math.sin(ang) * ring * r
            if legal_spot(balls, table, x, y):
                return x, y
    return prefer_x, prefer_y

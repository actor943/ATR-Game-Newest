# -*- coding: utf-8 -*-
"""Chrome 小恐龙（离线恐龙） —— 纯逻辑引擎，不依赖 flet。

玩法：小恐龙自动向前奔跑，地面不断左移；玩家：
    · 跳跃（空格 / ↑ / W / 点击）越过仙人掌；
    · 下蹲（↓ / S / 按住触屏键）钻过贴地飞鸟；
    · 速度随分数**自动**加快（这是 Chrome 恐龙的招牌机制，没有手动调速）。

坐标系：世界坐标，x 向右、y 向下为正。地面顶部在 GROUND_TOP，
恐龙站在 y = GROUND_TOP - DINO_STAND_H 处；跳跃时 dino_top 减小（往上）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

# ---------- 世界尺寸（逻辑单位，渲染时按屏幕缩放） ----------
WORLD_W = 120
WORLD_H = 40
GROUND_TOP = 30

# ---------- 恐龙 ----------
DINO_X = 18
DINO_W = 7
DINO_STAND_H = 9
DINO_DUCK_H = 5

# ---------- 物理 ----------
# 可玩性约束（用「枚举起跳时机」实测校准，见 selftest._assert_passable）：
# 恐龙跳一次的「离地安全窗口」必须长于「障碍横穿恐龙所需的 tick 数」。后者
# = (5 + 障碍宽) / 速度，**低速时最长**，所以参数按起始速度校准。原版
# JUMP_V=5.2 / GRAVITY=0.85 时，最高仙人掌与贴地飞鸟只有 0~1 tick 容错
# （33ms），h≥12 甚至物理上跳不过去 —— 属于必死局。
JUMP_V = 5.4          # 起跳初速度（向上为正，单位/ tick）
GRAVITY = 0.72        # 滞空约 14 tick；顶点 dino_top≈3.4，不会飞出画面顶部
BASE_SPEED = 1.6      # 起始水平速度（单位/ tick）
SPEED_GROWTH = 0.004  # 约 1~1.5 分钟达到顶速，让「越来越快」真正可感知
MAX_SPEED = 4.2

# ---------- 障碍 ----------
CACTUS_MIN_H = 6
CACTUS_MAX_H = 11     # 上限 11 时，最低速度下仍有 ≥4 tick 起跳容错
CACTUS_W = 4
BIRD_W = 7            # 飞鸟比仙人掌宽，过宽会让贴地飞鸟跳不过去
BIRD_H = 4
SPAWN_INSET = 6       # 在屏幕右侧外多远生成

# 相邻障碍至少间隔这么多个 tick，保证「落地 + 再起跳」来得及。
# 必须按速度线性放大：顶速下若仍按固定 30 单位，间隔只剩 ~7 tick，
# 比一次跳跃的滞空还短，连续两个需跳障碍会变成无解。
MIN_GAP_TICKS = 22

# 循环每 tick 约等于这么多秒（只用于下蹲计时，与 views_play 的 interval 对齐）
TICK_SECONDS = 0.03


@dataclass
class Obstacle:
    kind: str            # 'cactus' | 'bird'
    x: float             # 左边界（世界坐标）
    y: float             # 上边界（世界坐标，向下为正）
    w: float
    h: float


class Dino:
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self.best = 0
        self.reset()

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.score = 0.0
        self.alive = True
        self.started = False
        self.paused = False
        # 恐龙状态
        self.dino_top = GROUND_TOP - DINO_STAND_H
        self.vy = 0.0
        self.on_ground = True
        self.ducking = False
        self.duck_until = 0.0     # 下蹲保持到的累计时间（秒）
        self.speed = BASE_SPEED
        self.obstacles: list[Obstacle] = []
        self.spawn_countdown = 32.0
        self.tick = 0
        self.t = 0.0               # 累计时间（秒），用于下蹲计时

    # ------------------------- 动作接口 -------------------------
    def start(self) -> None:
        """开始奔跑（不跳跃）。

        专供「死后重开」：重开后应立刻进入跑动状态，而不是停在待开始界面
        让玩家再按一次空格——那样看起来就像「重开没反应」。
        """
        if self.alive:
            self.started = True

    def jump(self) -> None:
        """跳跃；若还没开始，则顺便开始游戏。"""
        if not self.alive:
            return
        if not self.started:
            self.started = True
        if self.paused:
            return
        if self.on_ground:
            self.vy = -JUMP_V
            self.on_ground = False

    def request_duck(self, duration: float = 0.5) -> None:
        """请求下蹲：保持 duration 秒（触屏/键盘每次按下都刷新，模拟“按住”）。"""
        if not self.alive or not self.started or self.paused:
            return
        self.duck_until = self.t + duration

    def release_duck(self) -> None:
        self.duck_until = 0.0

    def toggle_pause(self) -> None:
        if self.started and self.alive:
            self.paused = not self.paused

    def restart(self) -> None:
        prev_best = max(self.best, int(self.score)) if hasattr(self, "score") else self.best
        self.reset()
        self.best = prev_best

    # ------------------------- 内部 -------------------------
    def _spawn(self) -> None:
        r = self.rng.random()
        if r < 0.28 and self.score > 60:   # 一定分数后才出现飞鸟
            if self.rng.random() < 0.5:
                # 高处飞鸟：占「站立恐龙头顶」那 4 格，站立会撞、下蹲（或跳高）可过
                y = GROUND_TOP - DINO_STAND_H
            else:
                # 贴地飞鸟：占地面那 4 格，站立 / 下蹲都撞，必须跳起
                y = GROUND_TOP - BIRD_H
            self.obstacles.append(Obstacle("bird", WORLD_W + SPAWN_INSET, y, BIRD_W, BIRD_H))
        else:
            h = self.rng.uniform(CACTUS_MIN_H, CACTUS_MAX_H)
            self.obstacles.append(
                Obstacle("cactus", WORLD_W + SPAWN_INSET, GROUND_TOP - h, CACTUS_W, h)
            )

    # ------------------------- 主步进 -------------------------
    def step(self, dt_ticks: float = 1.0) -> None:
        if not self.started or self.paused or not self.alive:
            return
        self.t += dt_ticks * TICK_SECONDS
        self.tick += 1

        # 难度：随分数加速（招牌机制）
        self.speed = min(BASE_SPEED + self.score * SPEED_GROWTH, MAX_SPEED)

        # 下蹲只在地面生效。若空中也算「变矮」，恐龙底部会凭空上移
        # DINO_STAND_H - DINO_DUCK_H，出现悬空变矮 / 更容易蹭过障碍的物理
        # 不一致；空中一律用站立碰撞盒，落地后下一帧才切换成下蹲。
        self.ducking = (self.duck_until > self.t) and self.on_ground

        # 物理：跳跃 / 重力
        if not self.on_ground:
            self.vy += GRAVITY
            self.dino_top += self.vy
            rest_top = GROUND_TOP - (DINO_DUCK_H if self.ducking else DINO_STAND_H)
            if self.dino_top >= rest_top:
                self.dino_top = rest_top
                self.vy = 0.0
                self.on_ground = True
        else:
            self.dino_top = GROUND_TOP - (DINO_DUCK_H if self.ducking else DINO_STAND_H)

        # 移动障碍
        for o in self.obstacles:
            o.x -= self.speed * dt_ticks
        self.obstacles = [o for o in self.obstacles if o.x + o.w > -2]

        # 计分（按奔跑距离）
        self.score += self.speed * dt_ticks * 0.1

        # 生成新障碍（间隔随速度变大，保证可通过）
        self.spawn_countdown -= self.speed * dt_ticks
        if self.spawn_countdown <= 0:
            self._spawn()
            gap = (max(32.0, self.speed * MIN_GAP_TICKS)
                   + self.rng.uniform(0, 26))
            self.spawn_countdown = gap

        # 碰撞检测（AABB，留 1 单位宽容度）
        dh = DINO_DUCK_H if self.ducking else DINO_STAND_H
        dx0, dx1 = DINO_X, DINO_X + DINO_W
        dy0, dy1 = self.dino_top, self.dino_top + dh
        inset = 1.0
        for o in self.obstacles:
            ox0, ox1 = o.x, o.x + o.w
            oy0, oy1 = o.y, o.y + o.h
            if (ox1 - inset > dx0) and (ox0 + inset < dx1) and \
               (oy1 - inset > dy0) and (oy0 + inset < dy1):
                self.alive = False
                break

        if not self.alive:
            self.best = max(self.best, int(self.score))

    # ------------------------- 序列化 -------------------------
    def serialize(self) -> dict:
        return {
            "score": self.score,
            "speed": self.speed,
            "alive": self.alive,
            "started": self.started,
            "paused": self.paused,
            "dino_top": self.dino_top,
            "on_ground": self.on_ground,
            "ducking": self.ducking,
            "obstacles": [
                {"kind": o.kind, "x": o.x, "y": o.y, "w": o.w, "h": o.h}
                for o in self.obstacles
            ],
        }

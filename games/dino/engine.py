# -*- coding: utf-8 -*-
"""Chrome 小恐龙（离线恐龙） —— 纯逻辑引擎，不依赖 flet。

玩法：小恐龙自动向前奔跑，地面不断左移；玩家：
    · 跳跃（空格 / ↑ / W / 点击）越过仙人掌；
    · 下蹲（↓ / S / 按住触屏键）钻过高空飞鸟；
    · 速度随分数**自动**加快（这是 Chrome 恐龙的招牌机制，没有手动调速）；
    · 每跑过一段分数切换昼夜（招牌的「天黑了」），云层与地面持续视差滚动。

坐标系：世界坐标，x 向右、y 向下为正。地面顶部在 GROUND_TOP，
恐龙站在 y = GROUND_TOP - DINO_STAND_H 处；跳跃时 dino_top 减小（往上）。

素材与坐标的换算：``assets/Dino_assets/`` 的 PNG 按 ``PPU = 10``
（10 像素 = 1 世界单位）折算，仙人掌的宽高直接取 6 张素材的原生比例，
所以「看到的」和「撞到的」是同一个框。这个文件只存素材 key（字符串），
不 import 贴图模块，保持纯逻辑、可被命令行自检直接调用。
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
# = (5 + 障碍宽) / 速度，**低速时最长**，所以参数按起始速度校准。
# 0.4.10 接入原生素材后，三株仙人掌宽达 10.5 单位；沿用旧的
# JUMP_V=5.4 / GRAVITY=0.72 / BASE_SPEED=1.6 时它们只剩 2 tick（66ms）
# 容错，人类基本按不出来。这里把跳跃改成「同高度、更飘」（降低重力同时
# 降低初速，顶点仍是 dino_top≈3.1 不出画面），并把起始速度提到 2.0，
# 让最宽/最高的组合在起始速度下仍有 ≥5 tick 容错。
JUMP_V = 4.8          # 起跳初速度（向上为正，单位/ tick）
GRAVITY = 0.57        # 滞空约 16 tick；顶点 dino_top≈3.1，不会飞出画面顶部
BASE_SPEED = 2.0      # 起始水平速度（单位/ tick）
SPEED_GROWTH = 0.004  # 约 1 分钟达到顶速，让「越来越快」真正可感知
MAX_SPEED = 4.2

# ---------- 障碍 ----------
# 物理包络：自检按这两个高度枚举最坏情况，比实际素材还留了点余量。
CACTUS_MIN_H = 6
CACTUS_MAX_H = 11
CACTUS_W = 4
BIRD_W = 7            # 飞鸟比仙人掌宽，过宽会让贴地飞鸟跳不过去
BIRD_H = 4
SPAWN_INSET = 6       # 在屏幕右侧外多远生成

# 素材像素 → 世界单位。88×94 的恐龙 ≈ 8.8×9.4 单位，正好和 7×9 的碰撞框
# 同量级；2404×28 的地面 ≈ 240×2.8 单位。
PPU = 10.0

# 6 种仙人掌：(素材 key, 世界宽, 世界高)。宽高就是 PNG 原生尺寸 / PPU，
# 所以视图层按 o.w/o.h 摆贴图时几乎不用拉伸，像素画的形状完全保真。
# 注意最宽的 small3 (10.5) 也要能被一次跳跃越过，selftest 会逐个枚举验证。
CACTUS_VARIANTS: tuple[tuple[str, float, float], ...] = (
    ("small1", 4.0, 7.1),
    ("small2", 6.8, 7.1),
    ("small3", 10.5, 7.1),
    ("large1", 4.8, 9.5),
    ("large2", 9.9, 9.5),
    ("large3", 10.2, 9.5),
)

# ---------- 场景 ----------
TRACK_TILE_W = 240.0   # 一块地面贴图的宽度（世界单位），两块拼接无缝循环
TRACK_H = 2.8          # 地面贴图高度（世界单位）
CLOUD_W = 8.4          # 云贴图内容宽（84px / PPU）
CLOUD_H = 2.9          # 云贴图内容高（29px / PPU）
CLOUD_PARALLAX = 0.28  # 云比地面慢，做出景深
NIGHT_FIRST = 100.0    # 第一次天黑的分数
NIGHT_SPAN = (120.0, 220.0)   # 之后每段昼夜持续的分数区间

# 相邻障碍至少间隔这么多个 tick，保证「落地 + 再起跳」来得及。
# 必须按速度线性放大：顶速下若仍按固定 30 单位，间隔只剩 ~7 tick，
# 比一次跳跃的滞空还短，连续两个需跳障碍会变成无解。素材接入后滞空
# 变长（16 tick），这里同步放宽到 24 tick，保证「落地 + 再起跳」来得及。
MIN_GAP_TICKS = 24

# 循环每 tick 约等于这么多秒（只用于下蹲计时，与 views_play 的 interval 对齐）
TICK_SECONDS = 0.03


@dataclass
class Obstacle:
    kind: str            # 'cactus' | 'bird'
    x: float             # 左边界（世界坐标）
    y: float             # 上边界（世界坐标，向下为正）
    w: float
    h: float
    variant: str = "small1"   # 素材 key；飞鸟固定为 bird1/bird2 由帧数选


@dataclass
class Cloud:
    """背景云。只做视差，不参与碰撞。"""

    x: float
    y: float
    w: float = CLOUD_W


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
        # —— 场景（云 / 地面滚动 / 昼夜）——
        self.clouds: list[Cloud] = [
            Cloud(20.0, 6.0), Cloud(66.0, 10.0), Cloud(104.0, 4.5),
        ]
        self.cloud_countdown = 90.0
        self.track_offset = 0.0
        self.night = False
        self.night_at = NIGHT_FIRST
        self.milestone = 0         # 已经历的昼夜切换次数

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
            self.obstacles.append(Obstacle("bird", WORLD_W + SPAWN_INSET, y,
                                           BIRD_W, BIRD_H, "bird1"))
        else:
            # 从 6 张原生仙人掌素材里挑一张，碰撞框尺寸直接来自素材比例。
            # 分数低时只出单株 / 双株，跑远了才放三株，难度平滑上升。
            pool = (CACTUS_VARIANTS[:4] if self.score < 120 else CACTUS_VARIANTS)
            variant, w, h = pool[self.rng.randrange(len(pool))]
            self.obstacles.append(
                Obstacle("cactus", WORLD_W + SPAWN_INSET, GROUND_TOP - h,
                         w, h, variant)
            )

    def _step_scene(self, dt_ticks: float) -> None:
        """云层视差、地面滚动、昼夜切换（都不参与碰撞）。"""
        dx = self.speed * dt_ticks
        self.track_offset = (self.track_offset + dx) % TRACK_TILE_W

        cloud_dx = dx * CLOUD_PARALLAX
        for c in self.clouds:
            c.x -= cloud_dx
        self.clouds = [c for c in self.clouds if c.x + c.w > -CLOUD_W]
        self.cloud_countdown -= dx
        if self.cloud_countdown <= 0:
            self.clouds.append(Cloud(
                WORLD_W + self.rng.uniform(2, 24),
                self.rng.uniform(3.0, 12.0),
            ))
            self.cloud_countdown = self.rng.uniform(70, 170)

        if self.score >= self.night_at:
            self.night = not self.night
            self.milestone += 1
            self.night_at = self.score + self.rng.uniform(*NIGHT_SPAN)

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

        self._step_scene(dt_ticks)

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
            "night": self.night,
            "milestone": self.milestone,
            "track_offset": self.track_offset,
            "clouds": [{"x": c.x, "y": c.y, "w": c.w} for c in self.clouds],
            "obstacles": [
                {"kind": o.kind, "x": o.x, "y": o.y, "w": o.w, "h": o.h,
                 "variant": o.variant}
                for o in self.obstacles
            ],
        }

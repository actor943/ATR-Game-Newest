# -*- coding: utf-8 -*-
"""小恐龙引擎自检：python -m games.dino.selftest

除基础碰撞 / 物理外，最重要的是 ``_assert_passable()``：用**真实引擎**
枚举每种障碍的起跳 / 下蹲时机，确认在最低速度下也有足够宽的容错窗口。
这道断言专门防止「调参调出物理上跳不过去的必死局」（0.4.10 曾发生过：
最高仙人掌窗口 0 tick、h≥10 和贴地飞鸟仅 1 tick）。

接入原生 PNG 素材后，6 种仙人掌的碰撞框直接取素材比例（最宽 10.5 单位），
所以这里会**逐个素材形态**枚举窗口；另外检查素材齐全、云层 / 地面滚动 /
昼夜切换这些新增场景状态。
"""

from __future__ import annotations

from . import engine as eng
from .engine import (
    DINO_DUCK_H, DINO_STAND_H, DINO_X, GROUND_TOP, CACTUS_W, Obstacle, Dino,
)


def _fix_speed(speed: float):
    """把速度固定在给定值（引擎 step 每帧会按分数重算速度）。"""
    eng.BASE_SPEED = speed
    eng.SPEED_GROWTH = 0.0
    eng.MAX_SPEED = max(eng.MAX_SPEED, speed)


def _restore_constants(orig: dict) -> None:
    for k, v in orig.items():
        setattr(eng, k, v)


def _pass_window(kind, y, w, h, speed, action, K=22):
    """返回能安全通过该障碍的动作 tick 列表；长度 = 容错窗口宽度。

    障碍从 x0 = 24 + K*speed 出发，K tick 后左沿到达 x=24（碰撞窗口右界）。
    t=j 时执行动作，j 越小代表动作越早。
    """
    good = []
    x0 = 24 + K * speed
    for j in range(0, K + 12):
        e = Dino(seed=0)
        e.start()
        e.spawn_countdown = 1e9          # 关掉自然生成，只测这一个障碍
        e.obstacles = [Obstacle(kind, x0, y, w, h)]
        ok = True
        for t in range(0, K + 90):
            if t == j:
                if action == "jump":
                    e.jump()
                else:
                    e.request_duck(5.0)  # 覆盖整个通过窗口
            e.step(1.0)
            if not e.alive:
                ok = False
                break
            if not e.obstacles or e.obstacles[0].x + e.obstacles[0].w < 14:
                break
        if ok:
            good.append(j)
    return good


def _air_ticks() -> int:
    """一次跳跃的滞空 tick 数。"""
    e = Dino(seed=0)
    e.start()
    e.spawn_countdown = 1e9
    e.jump()
    n = 0
    while not e.on_ground and n < 100:
        e.step(1.0)
        n += 1
    return n


def _assert_passable() -> None:
    """每种障碍（含 6 种仙人掌素材）在起始速度 / 顶速下都要 ≥3 tick 窗口。"""
    keys = ("BASE_SPEED", "SPEED_GROWTH", "MAX_SPEED")
    orig = {k: getattr(eng, k) for k in keys}
    try:
        for speed in (orig["BASE_SPEED"], orig["MAX_SPEED"]):
            _fix_speed(speed)
            for h in (eng.CACTUS_MIN_H, 8, 10, eng.CACTUS_MAX_H):
                n = len(_pass_window("cactus", GROUND_TOP - h, CACTUS_W, h,
                                     speed, "jump"))
                assert n >= 3, (
                    "仙人掌 h=%s 在速度 %.2f 下仅 %d tick 容错，过于苛刻/无解"
                    % (h, speed, n))
            windows = []
            for key, w, h in eng.CACTUS_VARIANTS:
                n = len(_pass_window("cactus", GROUND_TOP - h, w, h,
                                     speed, "jump"))
                windows.append("%s=%d" % (key, n))
                assert n >= 3, (
                    "素材 %s (%.1f×%.1f) 在速度 %.2f 下仅 %d tick 容错"
                    % (key, w, h, speed, n))
            hi = len(_pass_window("bird", GROUND_TOP - DINO_STAND_H,
                                  eng.BIRD_W, eng.BIRD_H, speed, "duck"))
            lo = len(_pass_window("bird", GROUND_TOP - eng.BIRD_H,
                                  eng.BIRD_W, eng.BIRD_H, speed, "jump"))
            assert hi >= 3, "高空飞鸟在速度 %.2f 下下蹲窗口仅 %d tick" % (speed, hi)
            assert lo >= 3, "贴地飞鸟在速度 %.2f 下起跳窗口仅 %d tick" % (speed, lo)
            print("    速度 %.2f：%s 飞鸟(蹲)=%d 飞鸟(跳)=%d"
                  % (speed, " ".join(windows), hi, lo))
    finally:
        _restore_constants(orig)


def _run() -> None:
    # —— 1. 碰撞：正前方放一棵仙人掌，必死 ——
    e = Dino(seed=0)
    e.jump()                                   # 顺便开始
    e.obstacles = [Obstacle("cactus", DINO_X + 1.0, GROUND_TOP - 10,
                           CACTUS_W, 10)]
    e.spawn_countdown = 1e9
    e.step()
    assert not e.alive, "正前方仙人掌应当撞上"
    assert e.best >= 0

    # —— 2. 站立撞高空飞鸟；下蹲可过 ——
    bird_hi_y = GROUND_TOP - DINO_STAND_H
    e = Dino(seed=0)
    e.jump()
    e.on_ground = True
    e.vy = 0.0
    e.dino_top = GROUND_TOP - DINO_STAND_H
    e.duck_until = 0.0
    e.ducking = False
    e.obstacles = [Obstacle("bird", DINO_X + 1.0, bird_hi_y, eng.BIRD_W, 4)]
    e.spawn_countdown = 1e9
    e.step()
    assert not e.alive, "站立应当撞上高空飞鸟"

    e2 = Dino(seed=0)
    e2.jump()
    e2.on_ground = True
    e2.vy = 0.0
    e2.dino_top = GROUND_TOP - DINO_DUCK_H
    e2.duck_until = 1e9                          # 强制下蹲
    e2.ducking = True
    e2.obstacles = [Obstacle("bird", DINO_X + 1.0, bird_hi_y, eng.BIRD_W, 4)]
    e2.spawn_countdown = 1e9
    e2.step()
    assert e2.alive, "下蹲应当钻过高空飞鸟"

    # —— 3. 跳跃物理：起跳后离地、且不会飞出画面顶部 ——
    e3 = Dino(seed=0)
    e3.jump()
    before = e3.dino_top
    min_top = e3.dino_top
    for _ in range(20):
        e3.step()
        min_top = min(min_top, e3.dino_top)
        if e3.on_ground:
            break
    assert e3.dino_top < before or min_top < before, "起跳后应当上升"
    assert min_top > 0, "跳跃顶点不能飞出画面顶部（dino_top=%.2f）" % min_top

    # —— 4. 长跑 + 简单规避 AI：应当能跑出正分且不崩溃 ——
    e4 = Dino(seed=7)
    e4.jump()
    for _ in range(3000):
        nearest = None
        for o in e4.obstacles:
            if o.x + o.w > DINO_X and (nearest is None or o.x < nearest.x):
                nearest = o
        if nearest:
            eta = (nearest.x - (DINO_X + eng.DINO_W)) / max(0.01, e4.speed)
            if 0 < eta < 6 and e4.on_ground:
                if nearest.kind == "bird" and nearest.y < 24:
                    e4.request_duck(0.5)
                else:
                    e4.jump()
        e4.step()
        if not e4.alive:
            break
    assert e4.score > 60, "规避 AI 应当能跑出像样的分数（实得 %d）" % int(e4.score)
    assert isinstance(e4.serialize(), dict)

    # —— 5. 难度曲线：随分数加速、封顶，且 90 秒内明显可感知 ——
    e5 = Dino(seed=0)
    e5.start()
    e5.spawn_countdown = 1e9
    for _ in range(3000):                     # 90 秒
        e5.step(1.0)
    assert e5.speed <= eng.MAX_SPEED + 1e-9
    assert e5.speed >= eng.BASE_SPEED + (eng.MAX_SPEED - eng.BASE_SPEED) * 0.5, \
        "90 秒内速度应明显提升（实得 %.2f）" % e5.speed

    # —— 6. 障碍间隔必须够「落地 + 再起跳」，否则连续两个需跳障碍无解 ——
    air = _air_ticks()
    min_gap = max(32.0, eng.MAX_SPEED * eng.MIN_GAP_TICKS)
    gap_ticks = min_gap / eng.MAX_SPEED
    assert gap_ticks >= air + 5, (
        "顶速下最小障碍间隔 %.1f tick 不足以在滞空 %d tick 后再起跳"
        % (gap_ticks, air))

    # —— 7. 根本可行性：每种障碍都要有 ≥3 tick 容错窗口 ——
    print("  可玩性检查（枚举起跳窗口）:")
    _assert_passable()

    # —— 8. 素材：19 张 PNG 全在，路径不带 assets/ 前缀，尺寸与引擎比例一致 ——
    from . import assets
    assert assets.assets_available(), \
        "缺少素材：" + ", ".join(k for k, s in assets.SPRITES.items() if not s.exists())
    assert len(assets.SPRITES) == 19, "素材表数量与 assets/Dino_assets 不符"
    assert all(not s.src.startswith("assets/") for s in assets.SPRITES.values()), \
        "Flet 资源路径必须相对 assets 根，不能带 assets/ 前缀"
    for _key, w, h in eng.CACTUS_VARIANTS:
        sp = assets.sprite(_key)
        assert abs(sp.w / eng.PPU - w) < 0.15, "%s 素材宽度与碰撞框不符" % _key
        assert abs(sp.h / eng.PPU - h) < 0.15, "%s 素材高度与碰撞框不符" % _key
    assert "Dino_assets/" in assets.dino_src("run", 1)
    assert assets.dino_src("run", 0) != assets.dino_src("run", 1)
    assert assets.bird_src(0) != assets.bird_src(1)

    # —— 9. 场景：地面滚动有界、云层向左视差、到分数会天黑再天亮 ——
    e6 = Dino(seed=3)
    e6.start()
    e6.spawn_countdown = 1e9          # 只测场景，关掉自然障碍
    cloud_x0 = e6.clouds[0].x
    for _ in range(30):
        e6.step(1.0)
    assert e6.clouds[0].x < cloud_x0, "云应当向左飘"
    assert 0 <= e6.track_offset < eng.TRACK_TILE_W, "地面滚动偏移必须落在一个贴图周期内"
    e7 = Dino(seed=3)
    e7.start()
    e7.spawn_countdown = 1e9
    e7.score = eng.NIGHT_FIRST - 0.01
    assert not e7.night
    e7.step(1.0)
    assert e7.night and e7.milestone == 1, "跑过里程碑应当天黑"
    snap = e7.serialize()
    assert snap["night"] and snap["clouds"] and "track_offset" in snap

    # —— 10. 素材形态：实际跑一会应当 6 种仙人掌都可能出现且 variant 可序列化 ——
    seen = set()
    for seed in range(12):
        e8 = Dino(seed=seed)
        e8.start()
        e8.score = 300.0              # 解锁全部形态
        for _ in range(400):
            e8.step(1.0)
            for o in e8.obstacles:
                if o.kind == "cactus":
                    seen.add(o.variant)
            if not e8.alive:
                break
        for o in e8.serialize()["obstacles"]:
            assert "variant" in o
    assert seen, "跑动中应当生成过仙人掌"
    assert seen.issubset({v[0] for v in eng.CACTUS_VARIANTS}), \
        "出现了素材表里不存在的形态：" + str(seen)

    print("dino selftest: OK（含素材 / 场景 / 形态检查）")


if __name__ == "__main__":
    _run()

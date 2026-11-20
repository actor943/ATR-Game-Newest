# -*- coding: utf-8 -*-
"""小恐龙素材表：把 ``assets/Dino_assets/`` 里的 PNG 映射成 Flet 资源路径。

路径约定
--------
``main.py`` 起应用时把 ``assets_dir`` 指到项目根的 ``assets/``，所以这里
返回的路径是**相对 assets 根**的，不带 ``assets/`` 前缀，例如
``Dino_assets/Dino/DinoRun1.png``。``flet build`` 打包后也按同一规则解析
（与 ``games/chess/assets.py`` / ``games/billiards/assets.py`` 一致）。

尺寸从 PNG 本体量出，两个用途：

* ``w`` / ``h``：贴图原始像素尺寸，用来算宽高比，避免把像素画拉变形；
* ``visible_h``：素材里真正画了内容的高度（从顶部算，单位像素）。
  ``Cloud.png`` 是 84×101 但云只画在顶部 29px，``Reset.png`` 是 75×101
  但图标只占顶部 66px。直接把整张图压进一个小框里，云/图标会被挤成一条，
  所以视图层要用「裁剪容器」只露出顶部这段（见 ``views_play._clipped``）。

引擎里的世界坐标按 ``PPU = 10``（10 像素 = 1 世界单位）折算，因此
88×94 的站立恐龙 ≈ 8.8×9.4 世界单位，2404×28 的地面 ≈ 240×2.8。

素材缺失时不会白屏：``ft.Image(error_content=...)`` 会退回一块纯色矩形，
视图层统一传了兜底内容。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Final, Optional

SUBDIR: Final[str] = "Dino_assets"
ASSETS_ROOT: Final[Path] = (
    Path(__file__).resolve().parent.parent.parent / "assets" / SUBDIR
)

# 精灵原始色：除云之外都是 Chrome 恐龙的深灰 (#535353)，云是浅灰 (#DADADA)。
INK: Final[str] = "#535353"
INK_LIGHT: Final[str] = "#e8e8e8"


@dataclass(frozen=True)
class Sprite:
    """一张贴图。``visible_h`` 小于 ``h`` 时表示底部是透明留白，需要裁剪。"""

    path: str
    w: float
    h: float
    visible_h: Optional[float] = None

    @property
    def src(self) -> str:
        return f"{SUBDIR}/{self.path}"

    @property
    def ratio(self) -> float:
        """内容宽高比（用于按比例摆放，不被拉伸）。"""
        return self.w / (self.visible_h or self.h)

    def exists(self) -> bool:
        return (ASSETS_ROOT / self.path).is_file()


SPRITES: Final[Dict[str, Sprite]] = {
    # —— 恐龙 ——
    "dino_start": Sprite("Dino/DinoStart.png", 97, 101),
    "dino_run1": Sprite("Dino/DinoRun1.png", 87, 94),
    "dino_run2": Sprite("Dino/DinoRun2.png", 88, 94),
    "dino_jump": Sprite("Dino/DinoJump.png", 88, 94),
    "dino_duck1": Sprite("Dino/DinoDuck1.png", 118, 60),
    "dino_duck2": Sprite("Dino/DinoDuck2.png", 116, 60),
    "dino_dead": Sprite("Dino/DinoDead.png", 86, 101),
    # —— 仙人掌（key 与 engine.CACTUS_VARIANTS 一一对应）——
    "small1": Sprite("Cactus/SmallCactus1.png", 40, 71),
    "small2": Sprite("Cactus/SmallCactus2.png", 68, 71),
    "small3": Sprite("Cactus/SmallCactus3.png", 105, 71),
    "large1": Sprite("Cactus/LargeCactus1.png", 48, 95),
    "large2": Sprite("Cactus/LargeCactus2.png", 99, 95),
    "large3": Sprite("Cactus/LargeCactus3.png", 102, 95),
    # —— 飞鸟 ——
    "bird1": Sprite("Bird/Bird1.png", 97, 68),
    "bird2": Sprite("Bird/Bird2.png", 93, 62),
    # —— 场景 ——
    "cloud": Sprite("Other/Cloud.png", 84, 101, 29),
    "track": Sprite("Other/Track.png", 2404, 28, 26),
    "game_over": Sprite("Other/GameOver.png", 386, 40, 35),
    "reset": Sprite("Other/Reset.png", 75, 101, 66),
}


def sprite(key: str) -> Sprite:
    """按 key 取贴图；未知 key 退回站立恐龙，保证界面不会出现空图。"""
    return SPRITES.get(key) or SPRITES["dino_run1"]


def src(key: str) -> str:
    return sprite(key).src


def dino_src(state: str, frame: int = 0) -> str:
    """恐龙当前帧：``start / run / jump / duck / dead`` → 素材路径。"""
    if state == "start":
        return src("dino_start")
    if state == "dead":
        return src("dino_dead")
    if state == "jump":
        return src("dino_jump")
    if state == "duck":
        return src("dino_duck2" if frame % 2 else "dino_duck1")
    return src("dino_run2" if frame % 2 else "dino_run1")


def cactus_src(variant: str) -> str:
    return src(variant)


def bird_src(frame: int = 0) -> str:
    return src("bird2" if frame % 2 else "bird1")


def assets_available() -> bool:
    """素材是否齐全（自检 / 打包排错用）。"""
    return all(s.exists() for s in SPRITES.values())

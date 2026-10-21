# games/chess/assets.py
# -*- coding: utf-8 -*-
"""国际象棋资源管理。

素材按「主题」分目录存放于 ``assets/chess/<Theme>/`` 下，每个主题内含
12 张图片：``wK wQ wR wB wN wP`` 与 ``bK bQ bR bB bN bP``。

Flet 启动时的 ``assets_dir`` 指向项目根的 ``assets/``，因此棋子图片的
资源相对路径形如 ``chess/Cyborg/wK.png``。
"""

from __future__ import annotations

from pathlib import Path

# 可用的棋子皮肤主题（按 assets/chess 下的子目录）
AVAILABLE_THEMES: list[str] = [
    "Cyborg", "Anime", "Apollo", "Artemis", "Attack", "Clash",
    "Hades", "Halloween", "Hera", "Juno", "Jupiter", "Mars",
    "Minerva", "Stone", "Venus",
]

_DEFAULT_THEME = "Cyborg"

_PIECE_FILES = {
    'wK': 'wK.png', 'wQ': 'wQ.png', 'wR': 'wR.png', 'wB': 'wB.png',
    'wN': 'wN.png', 'wP': 'wP.png',
    'bK': 'bK.png', 'bQ': 'bQ.png', 'bR': 'bR.png', 'bB': 'bB.png',
    'bN': 'bN.png', 'bP': 'bP.png',
}

# 校验哪些主题目录真实存在（避免配置里多写导致空图）
_ASSETS_ROOT = Path(__file__).resolve().parent.parent.parent / "assets" / "chess"


def available_themes() -> list[str]:
    """返回实际可用的主题（目录存在才算）。"""
    out = []
    for t in AVAILABLE_THEMES:
        if (_ASSETS_ROOT / t).is_dir():
            out.append(t)
    if not out and (_ASSETS_ROOT / _DEFAULT_THEME).is_dir():
        out.append(_DEFAULT_THEME)
    return out


def piece_image_src(piece_code: str, theme: str = _DEFAULT_THEME) -> str:
    """返回 Flet 资源相对路径；``piece_code`` 为空时返回空串。"""
    if not piece_code:
        return ""
    fname = _PIECE_FILES.get(piece_code)
    if not fname:
        return ""
    return f"chess/{theme}/{fname}"

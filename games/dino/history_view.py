# -*- coding: utf-8 -*-
"""小恐龙历史记录：查看本地保存的单局成绩。

数据来源：游戏结束（撞到障碍）时自动落盘（见
:mod:`games.dino.views_play` 里的 ``_save_match_log``），写到应用数据
目录下的 ``logs/dino/``。

界面 / 交互逻辑与俄罗斯方块、贪吃蛇等共用 :mod:`core.history_view` 的底层
实现，本文件只按小恐龙的字段（分数 / 最高分 / 速度）定制一份列表摘要。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import flet as ft

from core import history_view as _hv
from core.i18n import t
from core.registry import NavigateFn

GAME_ID = "dino"
HISTORY_PATH = "/g/dino/history"

META_TIME = "生成时间"
META_SCORE = "分数"
META_BEST = "最高分"
META_SPEED = "速度"


def _summary(path: Path, meta: Dict[str, str]) -> str:
    """列表上一行摘要：时间 + 分数 + 最高分 + 速度。"""
    when = meta.get(META_TIME) or _hv._stamp_from_name(path)
    parts = [when]
    score = meta.get(META_SCORE, "")
    if score:
        parts.append(t("history.score_suffix", score=score))
    best = meta.get(META_BEST, "")
    if best:
        parts.append(t("dino.best_suffix", best=best))
    speed = meta.get(META_SPEED, "")
    if speed:
        parts.append(t("dino.speed_suffix", speed=speed))
    return " · ".join(parts)


def build(page, navigate: NavigateFn) -> ft.Control:
    """小恐龙历史记录页（委托给通用历史页）。"""
    return _hv.build_history(
        page, navigate, game_id=GAME_ID, title=t("dino.history"),
        back_route="/g/dino", summary_fn=_summary)


def open_history(navigate: NavigateFn) -> None:
    """从小恐龙子菜单 / 对局页跳到历史记录页。"""
    _hv.open_history(navigate, history_path=HISTORY_PATH)

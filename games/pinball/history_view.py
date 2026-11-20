# -*- coding: utf-8 -*-
"""弹球机历史记录：查看本地保存的每局成绩。

数据来源：3 球用尽时自动落盘（见 :mod:`games.pinball.views_play` 的
``_save_match_log``），写到应用数据目录下的 ``logs/pinball/``。
界面与交互复用 :mod:`core.history_view`，本文件只定制列表摘要。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import flet as ft

from core import history_view as _hv
from core.i18n import t
from core.registry import NavigateFn

GAME_ID = "pinball"
HISTORY_PATH = "/g/pinball/history"

# 落盘文件头部的键是中文（历史文件已经写成那样了，不跟着语言变）
META_TIME = "生成时间"
META_STATE = "状态"
META_SCORE = "分数"
META_BEST = "最高分"
META_HITS = "保险杠命中"


def _summary(path: Path, meta: Dict[str, str]) -> str:
    """列表上一行摘要：时间 + 分数 + 最高分 + 命中数。"""
    when = meta.get(META_TIME) or _hv._stamp_from_name(path)
    parts = [when]
    score = meta.get(META_SCORE, "")
    if score:
        parts.append(t("history.score_suffix", score=score))
    best = meta.get(META_BEST, "")
    if best:
        parts.append(t("pinball.best_suffix", best=best))
    hits = meta.get(META_HITS, "")
    if hits:
        parts.append(t("pinball.hits_suffix", hits=hits))
    return " · ".join(parts)


def build(page, navigate: NavigateFn) -> ft.Control:
    """弹球机历史记录页（委托给通用历史页）。"""
    return _hv.build_history(
        page, navigate, game_id=GAME_ID,
        title=t("pinball.history"), back_route="/g/pinball",
        summary_fn=_summary)


def open_history(navigate: NavigateFn) -> None:
    """从弹球机子菜单跳到历史记录页。"""
    _hv.open_history(navigate, history_path=HISTORY_PATH)

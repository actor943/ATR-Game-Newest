# -*- coding: utf-8 -*-
"""扫雷历史记录：查看本地保存的每局成绩。

数据来源：胜 / 负时自动落盘（见 :mod:`games.minesweeper.views_board` 的
``_save_match_log``），写到应用数据目录下的 ``logs/minesweeper/``。
界面与交互复用 :mod:`core.history_view`，本文件只定制列表摘要。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import flet as ft

from core import history_view as _hv
from core.i18n import t
from core.registry import NavigateFn

GAME_ID = "minesweeper"
HISTORY_PATH = "/g/minesweeper/history"

# 落盘文件头部的键是中文（历史文件已经写成那样了，不跟着语言变）
META_TIME = "生成时间"
META_STATE = "状态"
META_LEVEL = "难度"
META_TIME_USED = "用时"
META_SCORE = "分数"


def _summary(path: Path, meta: Dict[str, str]) -> str:
    """列表上一行摘要：时间 + 结果 + 难度 + 用时 + 分数。"""
    when = meta.get(META_TIME) or _hv._stamp_from_name(path)
    parts = [when]
    for key in (META_STATE, META_LEVEL):
        value = meta.get(key, "")
        if value:
            parts.append(value)
    used = meta.get(META_TIME_USED, "")
    if used:
        parts.append(t("minesweeper.time_suffix", time=used))
    score = meta.get(META_SCORE, "")
    if score and score != "0":
        parts.append(t("history.score_suffix", score=score))
    return " · ".join(parts)


def build(page, navigate: NavigateFn) -> ft.Control:
    """扫雷历史记录页（委托给通用历史页）。"""
    return _hv.build_history(
        page, navigate, game_id=GAME_ID,
        title=t("minesweeper.history"), back_route="/g/minesweeper",
        summary_fn=_summary)


def open_history(navigate: NavigateFn) -> None:
    """从扫雷子菜单跳到历史记录页。"""
    _hv.open_history(navigate, history_path=HISTORY_PATH)

# -*- coding: utf-8 -*-
"""俄罗斯方块历史记录：查看本地保存的单局成绩。

数据来源：方块堆到顶（游戏结束）时自动落盘（见
:mod:`games.tetris.views_play` 里的 ``_save_match_log``），写到应用数据
目录下的 ``logs/tetris/``（Mac：``~/Library/Application Support/ATR Game``）。

界面 / 交互逻辑与掼蛋、国际象棋、五子棋共用 :mod:`core.history_view` 的底层
实现，本文件只按俄罗斯方块的字段（分数 / 等级 / 消行）定制一份列表摘要。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import flet as ft

from core import history_view as _hv
from core.i18n import t
from core.registry import NavigateFn

GAME_ID = "tetris"
HISTORY_PATH = "/g/tetris/history"

# 落盘文件头部的键是中文（历史文件已经写成那样了，不跟着语言变）
META_TIME = "生成时间"
META_STATE = "状态"
META_SCORE = "分数"
META_LEVEL = "等级"
META_LINES = "消行"


def _summary(path: Path, meta: Dict[str, str]) -> str:
    """列表上一行摘要：时间 + 分数 + 等级 + 消行。"""
    when = meta.get(META_TIME) or _hv._stamp_from_name(path)
    parts = [when]
    score = meta.get(META_SCORE, "")
    if score:
        parts.append(t("history.score_suffix", score=score))
    level = meta.get(META_LEVEL, "")
    if level:
        parts.append(t("history.level_suffix", level=level))
    lines = meta.get(META_LINES, "")
    if lines:
        parts.append(t("history.lines_suffix", lines=lines))
    return " · ".join(parts)


def build(page, navigate: NavigateFn) -> ft.Control:
    """俄罗斯方块历史记录页（委托给通用历史页）。"""
    return _hv.build_history(
        page, navigate, game_id=GAME_ID, title=t("tetris.history"),
        back_route="/g/tetris", summary_fn=_summary)


def open_history(navigate: NavigateFn) -> None:
    """从俄罗斯方块子菜单 / 对局页跳到历史记录页。"""
    _hv.open_history(navigate, history_path=HISTORY_PATH)

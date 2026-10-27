# -*- coding: utf-8 -*-
"""五子棋历史记录：查看本地保存的对局着法。

数据来源：对局结束（或中途退出）时自动落盘（见
:mod:`games.gomoku.views_board` 里的 ``_save_match_log``），写到应用数据
目录下的 ``logs/gomoku/``（Mac：``~/Library/Application Support/ATR Game``）。

界面 / 交互逻辑与掼蛋、国际象棋共用 :mod:`core.history_view` 的底层实现，
本文件只按五子棋的字段定制一份列表摘要。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import flet as ft

from core import history_view as _hv
from core.i18n import t
from core.registry import NavigateFn

GAME_ID = "gomoku"
HISTORY_PATH = "/g/gomoku/history"

# 落盘文件头部的键是中文（历史文件已经写成那样了，不跟着语言变）
META_TIME = "生成时间"
META_STATE = "状态"
META_WIN = "胜方"
META_MODE = "模式"
META_MOVES = "步数"
META_NO_WIN = ("平局", "未分胜负")


def _summary(path: Path, meta: Dict[str, str]) -> str:
    """列表上一行摘要：时间 + 状态 + 胜负 + 模式 + 步数。"""
    when = meta.get(META_TIME) or _hv._stamp_from_name(path)
    state = meta.get(META_STATE, "")
    win = meta.get(META_WIN, "")
    mode = meta.get(META_MODE, "")
    moves = meta.get(META_MOVES, "")
    parts = [when]
    if state:
        parts.append(state)
    if win:
        # 「平局 / 未分胜负」后面不能跟「获胜」
        parts.append(win if win in META_NO_WIN
                     else t("history.win_suffix", win=win))
    if mode:
        parts.append(mode)
    if moves:
        parts.append(t("history.moves", n=moves))
    return " · ".join(parts)


def build(page, navigate: NavigateFn) -> ft.Control:
    """五子棋历史记录页（委托给通用历史页，按 gomoku 字段定制摘要）。"""
    return _hv.build_history(
        page, navigate, game_id=GAME_ID, title=t("gomoku.history"),
        back_route="/g/gomoku", summary_fn=_summary)


def open_history(navigate: NavigateFn) -> None:
    """从五子棋子菜单 / 对局页跳到历史记录页。"""
    _hv.open_history(navigate, history_path=HISTORY_PATH)

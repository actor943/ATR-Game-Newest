# -*- coding: utf-8 -*-
"""国际象棋历史记录：查看本地保存的对局着法。

数据来源：``开始对局`` 那盘棋在**每局结束时**自动落盘（见
:mod:`games.chess.views` 的 ``ChessPlayView._save_match_log``），写到应用数据
目录下的 ``logs/chess/``（Mac：``~/Library/Application Support/ATR Game``）。

界面 / 交互逻辑与掼蛋共用 :mod:`core.history_view` 的「底层逻辑」，本模块只按
象棋的字段（状态 / 胜方 / 模式）定制一份列表摘要。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from core import history_view as _hv
from core.i18n import t
from core.registry import NavigateFn

GAME_ID = "chess"
HISTORY_PATH = "/g/chess/history"

# 落盘文件头部的键是中文（历史文件已经写成那样了，不跟着语言变）
META_TIME = "生成时间"
META_STATE = "状态"
META_WIN = "胜方"
META_MODE = "模式"
META_NO_WIN = ("和棋", "未分胜负")


def _summary(path: Path, meta: Dict[str, str]) -> str:
    """列表上一行摘要：时间 + 状态 + 胜负 + 模式。"""
    when = meta.get(META_TIME) or _hv._stamp_from_name(path)
    state = meta.get(META_STATE, "")
    win = meta.get(META_WIN, "")
    mode = meta.get(META_MODE, "")
    parts = [when]
    if state:
        parts.append(state)
    if win:
        # 「和棋」「未分胜负」后面不能跟「获胜」
        parts.append(win if win in META_NO_WIN
                     else t("history.win_suffix", win=win))
    if mode:
        parts.append(mode)
    return " · ".join(parts)


def build(page, navigate: NavigateFn) -> ft.Control:
    """国际象棋历史记录页（委托给通用历史页，按 chess 字段定制摘要）。"""
    return _hv.build_history(
        page, navigate, game_id=GAME_ID, title=t("chess.home.history"),
        back_route="/g/chess", summary_fn=_summary)


def open_history(navigate: NavigateFn) -> None:
    """从国际象棋子菜单 / 对局页跳到历史记录页。"""
    _hv.open_history(navigate, history_path=HISTORY_PATH)

# -*- coding: utf-8 -*-
"""台球历史记录：查看本地保存的对局。

数据来源：对局结束（或中途退出）时自动落盘（见
:mod:`games.billiards.views_play` 里的 ``_save_match_log``），写到应用数据
目录下的 ``logs/billiards/``。

界面 / 交互逻辑与掼蛋、五子棋共用 :mod:`core.history_view` 的底层实现，
本文件只按台球的字段定制一份列表摘要。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import flet as ft

from core import history_view as _hv
from core.i18n import t
from core.registry import NavigateFn

GAME_ID = "billiards"
HISTORY_PATH = "/g/billiards/history"

# 落盘文件头部的键是中文（历史文件已经写成那样了，不跟着语言变）
META_TIME = "生成时间"
META_STATE = "状态"
META_RESULT = "结果"
META_MODE = "模式"
META_SHOTS = "杆数"
META_NO_WIN = ("未分胜负",)


def _summary(path: Path, meta: Dict[str, str]) -> str:
    """列表上一行摘要：时间 + 状态 + 结果 + 模式 + 杆数。"""
    when = meta.get(META_TIME) or _hv._stamp_from_name(path)
    state = meta.get(META_STATE, "")
    result = meta.get(META_RESULT, "")
    mode = meta.get(META_MODE, "")
    shots = meta.get(META_SHOTS, "")
    parts = [when]
    if state:
        parts.append(state)
    if result and result not in META_NO_WIN:
        parts.append(result)
    if mode:
        parts.append(mode)
    if shots:
        parts.append(f"{shots} 杆")
    return " · ".join(parts)


def build(page, navigate: NavigateFn) -> ft.Control:
    """台球历史记录页（委托给通用历史页，按台球字段定制摘要）。"""
    return _hv.build_history(
        page, navigate, game_id=GAME_ID, title=t("billiards.history"),
        back_route="/g/billiards", summary_fn=_summary)


def open_history(navigate: NavigateFn) -> None:
    """从台球子菜单 / 对局页跳到历史记录页。"""
    _hv.open_history(navigate, history_path=HISTORY_PATH)

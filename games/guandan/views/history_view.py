# -*- coding: utf-8 -*-
"""掼蛋历史记录：查看本地保存的出牌记录（界面与交互逻辑见 core/history_view）。

数据来源：``开始游戏`` 那张牌桌在**每整场结束时**自动落盘（见
:meth:`games.guandan.views.play_view.PlayView._save_match_log`），写到应用数据
目录下的 ``logs/guandan/``（Mac：``~/Library/Application Support/ATR Game``）。

本页把日志文件按时间倒序列出来，点一条看全文；只服务「开始游戏」，
「全模拟」（4 人 AI 观战）不落盘，所以这里也看不到它的记录。

历史页的界面 / 交互统一在 :mod:`core.history_view`（与象棋共用的「底层逻辑」），
本文件只是按掼蛋的字段定制一份摘要函数。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from core import history_view as _hv
from core.registry import NavigateFn

GAME_ID = "guandan"
HISTORY_PATH = "/g/guandan/history"


def _summary(path: Path, meta: Dict[str, str]) -> str:
    """列表上显示的一行摘要：时间 + 状态 + 谁赢 + 打了几局。"""
    when = meta.get("生成时间") or _hv._stamp_from_name(path)
    state = meta.get("状态", "")
    win = meta.get("胜方", "")
    hands = meta.get("局数", "")
    parts = [when]
    if state:
        parts.append(state)
    if win:
        # 「未分胜负」是中途退出的记录，后面不能再跟「获胜」
        parts.append(win if win == "未分胜负" else f"{win}获胜")
    if hands:
        parts.append(f"{hands} 局")
    return " · ".join(parts)


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """掼蛋历史记录页（委托给通用历史页，按 guandan 字段定制摘要）。"""
    return _hv.build_history(
        page, navigate, game_id=GAME_ID, title="历史记录",
        back_route="/g/guandan", summary_fn=_summary)


def open_history(navigate: NavigateFn) -> None:
    """从其它页面（对局顶栏、掼蛋子菜单）跳到历史记录页。"""
    _hv.open_history(navigate, history_path=HISTORY_PATH)

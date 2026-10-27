# -*- coding: utf-8 -*-
"""房间会话的「游戏数据透传」那一半：把玩法消息原样转给房间里跑的游戏。

被 core.net.session.RoomSession 以 mixin 的方式继承。
"""

from __future__ import annotations

from typing import Any, Dict

from . import GAME

class SessionGameMixin:
    """游戏数据透传那一半：把玩法消息原样转给房间里跑的游戏。"""

    # ---------------- 游戏数据透传（象棋走子等） ----------------

    def set_game_handler(self, fn) -> None:
        """房主 / 客人进到某个联机游戏里时，把处理玩法消息的回调挂上来。

        ``fn(msg)`` 收到的 ``msg`` 是整包（含 ``data`` 字段）。离开游戏时传
        ``None`` 摘掉即可。走的是直接回调，不经事件队列，因此即使房间界面的
        轮询还在跑也不会把玩法消息抢走。

        挂上回调时会先把暂存的玩法消息补发一遍（见 ``_game_backlog``）——
        「开始游戏」后视图重建有先后，先到消息的那一方不会丢。
        """
        with self._lock:
            self._game_handler = fn
            backlog, self._game_backlog = self._game_backlog, []
        if fn is None:
            return
        for msg in backlog:
            try:
                fn(msg)
            except Exception:                     # noqa: BLE001
                pass

    def send_game(self, data: Dict[str, Any]) -> None:
        """把一帧玩法数据可靠地发给房间里其他所有人（不含自己）。"""
        self._reliable({"t": GAME, "game": self.info.game_id, "data": data},
                       self._others())

    def send_game_to_host(self, data: Dict[str, Any]) -> None:
        """客人用：把一帧玩法数据可靠地**单播**给房主（动作请求走房主中转）。"""
        if self.is_host or not self.info.port:
            return
        self._reliable({"t": GAME, "game": self.info.game_id, "data": data},
                       [(self.info.ip, self.info.port)])

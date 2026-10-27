# -*- coding: utf-8 -*-
"""国际象棋的「联机对弈」那一半：算身份、同步局面、轮询席位。

由 :class:`games.chess.views.ChessPlayView` 以 mixin 的方式继承。
"""

from __future__ import annotations

import asyncio

import flet as ft


class ChessSyncMixin:
    """联机身份计算、局面同步、席位轮询。"""

    # ------------------------------------------------------------------
    # 联网对弈相关
    # ------------------------------------------------------------------
    def _toast(self, msg: str):

        """在棋盘上方弹一条小提示（几秒后自动消失）。"""
        try:
            self.page.pop_dialog()
        except Exception:
            pass
        try:
            self.page.show_dialog(
                ft.AlertDialog(
                    modal=False,
                    content=ft.Text(msg),
                    actions=[ft.TextButton(
                        "知道了",
                        on_click=lambda _e: self.page.pop_dialog())],
                )
            )
        except Exception:
            pass

    # ---------- 身份与在线状态 ----------
    def _compute_role(self):
        """根据房间席位表算出本机是白方 / 黑方 / 观战。

        规则：座位号最小的两个上场座位（< players）分别是白、黑；
        其余座位以及未入座的人都是观战。
        """
        if self.net is None:
            self.role = "local"
            return
        me = self.net.me
        white_mid = black_mid = None
        try:
            # roster() 返回的是 List[Member]（按座位排），不是字典——
            # 早前版本把它当字典调 .values()，联机象棋一进对局页就
            # AttributeError，手机端直接红屏。
            members = self.net.roster()
            seated = sorted((m for m in members if m.seat >= 0),
                            key=lambda m: m.seat)
            players = [m for m in seated if m.seat < self.players]
            white_mid = players[0].mid if len(players) > 0 else None
            black_mid = players[1].mid if len(players) > 1 else None
        except Exception as exc:            # 手机端红屏比"降级成观战"糟糕得多
            print(f"[chess] 算身份失败，先按观战处理：{exc!r}")
        self.white_mid = white_mid
        self.black_mid = black_mid
        if me.mid == white_mid:
            self.role = "w"
        elif me.mid == black_mid:
            self.role = "b"
        else:
            self.role = "spectator"

    def _evaluate_presence(self):
        """判断联网对手是否中途离场（在场方直接判胜）。

        仅在「本机是上场玩家且对面的玩家座位已空、对局尚未结束」时成立；
        观战方 / 双方都不在时不判胜（只负责显示谁离开了）。
        """
        if self.net is None or self.role not in ("w", "b"):
            self.opponent_left = False
            return
        opp_mid = self.black_mid if self.role == "w" else self.white_mid
        self.opponent_left = (opp_mid is None) and not self.game.is_game_over()

    def _refresh_net_text(self):

        """刷新顶栏上的联机状态文字。"""
        if self.net is None or self.page is None:
            return
        self._evaluate_presence()
        if self.opponent_left:
            self.net_text.value = "对方已离开，可重开新对局"
            # 判胜文案交给 _update_status 统一显示
            self._update_status()
            return
        if self.role == "local":
            self.net_text.value = ""
        elif self.role == "spectator":
            missing = []
            if self.white_mid is None:
                missing.append("白方")
            if self.black_mid is None:
                missing.append("黑方")
            if missing:
                self.net_text.value = "观战中 · " + "、".join(missing) + "已离开"
            else:
                self.net_text.value = "观战中 · 轮到" + (
                    "白方" if self.game.turn == "w" else "黑方")
        else:
            side = "白方" if self.role == "w" else "黑方"
            opp_mid = self.black_mid if self.role == "w" else self.white_mid
            if opp_mid is None:
                self.net_text.value = f"你是{side} · 对方已离开，等待新对手"
            elif self.role == self.game.turn:
                self.net_text.value = f"你是{side} · ▶ 轮到你走棋"
            else:
                self.net_text.value = f"你是{side} · ⏳ 等待对方"
        try:
            self.page.update()
        except Exception:
            pass

    # ---------- 网络消息 ----------
    def _on_net(self, msg):
        """收到房间里的玩法消息（来自其他设备）。"""
        if not self._is_active_view() or self.net is None:
            return
        data = msg.get("data") or {}
        k = data.get("k")
        if k == "mv":
            color = self.game.turn               # 走子方颜色（走之前）
            self.game.move(data["fr"], data["fc"], data["tr"], data["tc"],
                           promotion=data.get("p") or None)
            self._record_ply(color, data["fr"], data["fc"],
                             data["tr"], data["tc"], data.get("p") or None)
            self.selected_pos = None
            self._render_board()
            self._update_status()
            self._maybe_save_on_end()
        elif k == "reset":
            self.game.reset()
            self.selected_pos = None
            self._render_board()
            self._update_status()
            # 重开 = 新的一局，记录从头再来
            self._log_lines = []
            self._log_saved = False
            self._ply = 0
            self._log_lines.append(f"对局开始：{self._mode_label()}")
        elif k == "undo":
            self.game.undo()
            self.selected_pos = None
            self._render_board()
            self._update_status()
        elif k == "req_state":
            if self.net.is_host:
                self.net.send_game({"k": "state", "s": self.game.serialize()})
        elif k == "state":
            state = data.get("s")
            if state:
                self._state_synced = True
                self.game.load_state(state)
                # 迟到者从中途局面加入，只记录后续着法
                if not self._log_lines:
                    self._log_lines.append("（从中途局面开始记录）")
                self.selected_pos = None
                self._render_board()
                self._update_status()
        # 任何网络事件后都重算身份（可能有人入座 / 离座）
        self._compute_role()
        self._refresh_net_text()

    async def _sync_wait(self):
        """没拿到房主局面就周期性重问（房主的视图可能比我们晚建好）。"""
        for _ in range(40):                     # 最多等 20 秒
            if self._state_synced or not self._is_active_view():
                return
            self.net.send_game({"k": "req_state"})
            await asyncio.sleep(0.5)

    async def _net_poll(self):
        """后台轮询席位变化，让「等待对方入座 / 对方离开」等状态及时刷新。"""
        while True:
            if not self._is_active_view() or self.net is None:
                return
            try:
                self._compute_role()
                self._refresh_net_text()
            except Exception:
                pass
            await asyncio.sleep(0.6)

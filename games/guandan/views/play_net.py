# -*- coding: utf-8 -*-
"""掼蛋牌桌的「联机同步」那一半：房主权威、整局快照、重推。

协议要点
--------
从房间「开始」进来的对局，**房主是唯一权威**：只有房主洗牌发牌，之后每有
一个动作（出牌 / 过牌 / 进贡 / 发下一手）房主就把整场局面连同新的事件日志
重推一次快照；所有人按 ``seq`` 只采用更新的快照，乱序 / 重传的旧包直接丢弃。
客人不本地洗牌、不本地跑 AI、不本地写日志 —— 全部等房主快照。

由 :class:`games.guandan.views.play_view._Play` 以 mixin 的方式继承。
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any, Dict

from games.guandan.config import SEAT_AI, SEAT_HUMAN
from games.guandan.engine import (
    IllegalMove,
    card_from_json,
    cards_from_json,
    load_match,
    result_from_json,
    serialize_match,
)
from games.guandan.views.play_const import (
    FG,
    MUTED,
    NAMES,
    WIN_COLOR,
    _LOG_COLOR_KEYS,
    _LOG_COLORS,
    _is_bomb,
    _is_seat,
)

class PlayNetMixin:
    """联机同步：房主权威 + 整局快照。"""

    # ---------- 席位与身份 ----------
    def _setup_net_seats(self) -> None:
        """按房间席位表排座：房间 0~3 号座 = 牌桌 甲~丁，空位给电脑。

        房间 4 号位起（或还没入座）的人只围观，不看任何一手牌。
        """
        members = self.net.roster()
        by_seat = {m.seat: m for m in members if m.seat >= 0}
        # 我坐哪一号：以席位表里**我自己那条**为准（self.net.me.seat 是本地
        # 缓存，可能还没同步到；拿不到就宁可当旁观者，也别猜 0 号座 ——
        # 猜错就会把别人的手牌当成自己的显示出来）。
        mine = next((m for m in members if m.mid == self.net.me.mid), None)
        my_room_seat = mine.seat if mine is not None else self.net.me.seat
        seats = list(self.cfg.seats)
        for i in range(4):
            seats[i] = SEAT_HUMAN if i in by_seat else SEAT_AI
        if all(s == SEAT_AI for s in seats):        # 兜底：不能全电脑
            seats[0] = SEAT_HUMAN
        if 0 <= my_room_seat < 4:
            self.my_seat = my_room_seat
            self.spectator = False
        else:
            self.my_seat = 0
            self.spectator = True
        self.remote_nicks = {
            i: by_seat[i].nick for i in range(4)
            if i in by_seat and by_seat[i].mid != self.net.me.mid
        }
        self.cfg = replace(self.cfg, seats=tuple(seats),
                           local_seat=self.my_seat)

    def _is_local(self, seat: int) -> bool:
        """这个座位是不是由本机玩家亲手操作（旁观者谁都不操作）。"""
        return not self.spectator and seat == self.my_seat

    def _is_auto(self, seat: int) -> bool:
        """这个座位是否由电脑代打：本机玩家与远端真人之外的座位。

        联机时远端真人的座位**不**交给电脑 —— 他的着法会随房主快照到达。
        """
        if self._is_local(seat):
            return False
        if seat in self.remote_nicks:
            return False
        return True

    def _controller(self, seat: int) -> str:
        """界面上的控制器标签：你 / 远端昵称 / 电脑。"""
        if self._is_local(seat):
            return self.cfg.local_nick or "你"
        if seat in self.remote_nicks:
            return self.remote_nicks[seat]
        return "电脑"

    def _seat_summary(self) -> str:
        """座位一览（写进日志 / 落盘元信息）。"""
        if self.net is None:
            return self.cfg.summary()
        return "  ".join(f"{NAMES[p]}·{self._controller(p)}"
                         for p in range(4))

    def _notify_host(self, data: Dict[str, Any]) -> None:
        """客人：把本地这一步动作单播给房主（房主应用后重推快照）。"""
        if self.net is not None and not self.is_host:
            self.net.send_game_to_host(data)

    def _publish_if_host(self) -> None:
        """房主：自己动手之后把新快照推给所有人。

        0.4.8-fix：以前只有「客人」这一路会把动作告诉房主，房主自己的出牌 /
        过牌 / 进贡**从不广播** —— 客人的牌桌就停在发牌那一刻不动
        （看着像两边手牌一样，其实是一边根本没收到任何后续）。
        """
        if self.net is not None and self.is_host:
            self._push_state()

    def _detach_net(self) -> None:
        """离开牌桌：摘掉网络回调，别让旧实例继续收玩法消息。"""
        if self.net is not None:
            self.net.set_game_handler(None)
        self._clear_current_play()

    # ---------- 房主权威的整局快照 ----------
    def _push_state(self) -> None:
        """房主：把整场局面 + 新的事件日志广播给房间里其他所有人。"""
        if self.net is None or not self.is_host:
            return
        self._seq += 1
        lines = self._log_lines
        start = min(self._log_sent, len(lines))
        delta = [[text, _LOG_COLOR_KEYS.get(color, "fg"), bool(bold)]
                 for text, (color, bold) in zip(
                     list(lines)[start:], list(self._log_meta)[start:])]
        self._log_sent = len(lines)
        self.net.send_game({"k": "state", "seq": self._seq,
                            "log_from": start, "log": delta,
                            "s": serialize_match(self.match, self.hand,
                                                 self.result)})

    def _on_net(self, msg):
        """收到房间里的玩法消息。

        房主是权威：只处理客人的动作请求（mv / pass / tribute / next）与
        req_state；客人只接受房主的 state 快照（按 seq 只采用更新的）。
        """
        if not self._is_current_play() or not self.alive or self.net is None:
            return
        data = msg.get("data") or {}
        k = data.get("k")
        try:
            if k == "req_state":
                if self.net.is_host:
                    self._push_state()
            elif k == "state":
                if not self.net.is_host:
                    self._apply_state(data)
            elif k == "mv":
                if self.net.is_host:
                    self._host_apply_play(data)
            elif k == "pass":
                if self.net.is_host:
                    self._host_apply_pass(data)
            elif k == "tribute":
                if self.net.is_host:
                    self._host_apply_tribute(data)
            elif k == "next":
                if self.net.is_host:
                    self._host_next_hand()
        except Exception:                     # noqa: BLE001
            # 网络线程里不能炸；坏包忽略即可
            pass

    def _apply_state(self, data: Dict[str, Any]) -> None:
        """采用房主推来的整局快照（乱序 / 重传的旧包直接丢弃）。"""
        try:
            seq = int(data.get("seq", 0))
        except (TypeError, ValueError):
            return
        if seq <= self._last_seq:
            return
        hand = load_match(self.match, data.get("s") or {})
        if hand is None:
            return
        self.hand = hand
        self._last_seq = seq
        # ---- 事件日志增量（漏过的开头补一句说明，后续按条数对齐）----
        try:
            log_from = int(data.get("log_from", 0) or 0)
        except (TypeError, ValueError):
            log_from = self._log_have
        if log_from > self._log_have:
            self._append_log(f"……（漏过 {log_from - self._log_have} 条事件）",
                             MUTED, False)
            self._log_have = log_from
        for entry in (data.get("log") or []):
            try:
                text = str(entry[0])
                color = _LOG_COLORS.get(str(entry[1]), FG)
                bold = bool(entry[2])
            except (IndexError, TypeError, ValueError):
                continue
            self._append_log(text, color, bold)
            self._log_have += 1
        # ---- 局面 ----
        # 结算面板：一手可能由任意一家（含房主上的电脑）走完，客人不本地推导，
        # 直接用快照里房主的结算结果（0.4.8-fix）。房主发了下一手（res 为空、
        # 牌局未结束）就清掉面板 —— 不能靠 hand_no 判断：settle 时它已经 +1 了，
        # 发新手不会再变（0.4.8-fix2：客人会卡在上一手的结算面板上）。
        if self.hand.ended:
            res = result_from_json(data.get("res"))
            if res is not None:
                self.result = res
                self._result_hand_no = self.match.hand_no
        else:
            self.result = None
        self.selected.clear()
        self.tribute_sel.clear()
        tr = self.hand.tribute
        if tr is None or tr.done:
            # 进贡得来的牌：走完才标（中途不标，牌还没换过来）
            self.gift_marks = (set(tr.received_gifts(self.my_seat))
                               if tr is not None else set())
        if not self._synced:
            self._synced = True
            self._start_ai()
        # 整场结束由房主的快照确认，客人在这一刻才落盘（日志已齐）
        if self.match.winner is not None and not self._log_saved:
            self._save_match_log()
        self._refresh()

    # ---------------- 房主：应用客人的动作 ----------------

    # ---------- 房主执行客人请求 ----------
    def _host_apply_play(self, data: Dict[str, Any]) -> None:

        """房主：执行客人请求的出牌。"""
        seat = data.get("p")
        cards = cards_from_json(data.get("c"))
        if not _is_seat(seat) or cards is None:
            return
        if self.hand.ended or self.hand.turn != seat:
            return
        try:
            combo = self.hand.play(seat, cards)
        except IllegalMove:
            return                          # 客人的局面过期 → 忽略，快照会纠正
        self._log_play(seat, combo, _is_bomb(combo))
        if seat in self.hand.out_order:
            self._log(f"★ {NAMES[seat]} 出完（{len(self.hand.out_order)}游）",
                      WIN_COLOR, bold=True)
        self._after_action()
        self._push_state()

    def _host_apply_pass(self, data: Dict[str, Any]) -> None:

        """房主：执行客人请求的过牌。"""
        seat = data.get("p")
        if not _is_seat(seat):
            return
        if self.hand.ended or self.hand.turn != seat:
            return
        try:
            self.hand.pass_turn(seat)
        except IllegalMove:
            return
        self._log(f"{NAMES[seat]} 过", MUTED)
        self._after_action()
        self._push_state()

    def _host_apply_tribute(self, data: Dict[str, Any]) -> None:

        """房主：执行客人请求的进贡。"""
        tr = self.hand.tribute
        if tr is None or tr.done:
            return
        card = card_from_json(data.get("card"))
        if card is None or not tr.choose(card):
            return
        self._tribute_after_step(tr)
        self._refresh()
        self._push_state()

    def _host_next_hand(self) -> None:

        """房主：结算完一手后发下一手牌并广播。"""
        r = self.result
        if r is None or r.match_over:
            return
        self._deal_next_hand()

    # ---------------- 客人：要牌 / 席位变化 ----------------

    async def _sync_wait(self) -> None:
        """没拿到房主快照就周期性重问（房主的视图可能比我们晚建好）。"""
        for _ in range(40):                     # 最多 20 秒
            if not self.alive or self._synced or not self._is_current_play():
                return
            self.net.send_game_to_host({"k": "req_state"})
            await asyncio.sleep(0.5)

    async def _net_poll(self) -> None:
        """联机时周期性按席位表刷新控制器标注（有人入座 / 离开）。"""
        while self.alive and self._is_current_play() and self.net is not None:
            try:
                self._refresh_seats_from_room()
            except Exception:                 # noqa: BLE001
                pass
            await asyncio.sleep(1.0)

    def _refresh_seats_from_room(self) -> None:
        """席位表变了 → 重算远端真人；离开的座位交给电脑代打（房主接管）。"""
        if self.net is None:
            return
        members = self.net.roster()
        by_seat = {m.seat: m for m in members if m.seat >= 0}
        remote = {i: by_seat[i].nick for i in range(4)
                  if i in by_seat and by_seat[i].mid != self.net.me.mid}
        if remote != self.remote_nicks:
            gone = [n for s, n in self.remote_nicks.items() if s not in remote]
            self.remote_nicks = remote
            if gone and self._synced:
                self._log(f"（联机）{'、'.join(gone)} 离开了牌桌，"
                          f"空位由电脑代打", MUTED)
            if self._synced:
                self._refresh()

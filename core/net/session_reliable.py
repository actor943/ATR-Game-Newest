# -*- coding: utf-8 -*-
"""房间会话的「可靠传输」那一半：收发包、ACK、重传、心跳。

被 core.net.session.RoomSession 以 mixin 的方式继承，
所以里面的方法可以直接用 self.xxx。
"""

from __future__ import annotations

import socket
from typing import Any, Dict, List, Tuple

from ..i18n import t
from . import (
    ACK,
    BYE,
    CHAT,
    GAME,
    HELLO,
    PING,
    REJECT,
    ROSTER,
    START,
    WELCOME,
    code_hash,
    decode,
    encode,
    new_mid,
    now,
)
from .session_const import (
    HEARTBEAT_TIMEOUT,
    MAX_RETRY,
    RETRY_INTERVAL,
    ROSTER_INTERVAL,
    TICK,
)

class SessionReliableMixin:
    """可靠传输那一半：收发包、ACK、重传、心跳、席位表广播。"""

    # ================================================================
    # 内部：收发
    # ================================================================

    # ---------- 最基础的收发 ----------
    def _others(self) -> List[Tuple[str, int]]:

        """除自己以外的所有成员地址（发广播时用）。"""
        return [(m.ip, m.ctrl_port) for m in self.members.values()
                if m.mid != self.me.mid and m.ctrl_port]

    def _send(self, msg: Dict[str, Any], addr: Tuple[str, int]) -> None:

        """把一个包发出去（不做重传，只是单纯 sendto）。"""
        try:
            self.sock.sendto(encode(msg), addr)
        except OSError:
            pass

    # ---------- 可靠发送（带序号 + 重传） ----------
    def _reliable(self, msg: Dict[str, Any],
                  targets: List[Tuple[str, int]]) -> None:
        """发给多人的「不可丢」消息：登记待确认，超时由 tick 重发。"""
        mid = msg.setdefault("mid_seq", new_mid())
        msg["need_ack"] = True
        with self._lock:
            self._pending[mid] = {"addr": targets, "msg": msg,
                                  "next": now() + RETRY_INTERVAL, "tries": 0}
        if targets:
            for addr in targets:
                self._send(msg, addr)
        else:
            with self._lock:
                self._pending.pop(mid, None)

    def _ack(self, seq: str, addr: Tuple[str, int]) -> None:

        """收到确认包：把对应的待确认项从表里去掉。"""
        self._send({"t": ACK, "ack": seq}, addr)

    def _say_hello(self) -> None:

        """客人上线：广播一句 hello，请房主分配席位。"""
        self._single_target = (self.info.ip, self.info.port)
        with self._lock:
            self._pending["join"] = {
                "addr": [self._single_target],
                "msg": {"t": HELLO, "mid": self.me.mid, "nick": self.me.nick,
                        "code": self.code,          # 单播给房主，房主明文比对
                        "code_check": self._code_proof(),
                        "vp": self.voice.bound_port},
                "next": now() + RETRY_INTERVAL, "tries": 0, "hello": True,
            }
            self._send(self._pending["join"]["msg"], self._single_target)

    def _code_proof(self) -> Dict[str, str]:
        """向房主证明「我知道房间码」，但不把房间码发出去。

        把房间码散列时用房主广播出来的盐，房主本地算一遍比对即可。
        """
        return {"hash": code_hash(self.code, getattr(self.info, "salt", "")),
                "mid": self.me.mid}

    def _goodbye(self) -> None:

        """离开时广播一句 bye，告诉房主把我划掉。"""
        msg = {"t": BYE, "mid": self.me.mid, "nick": self.me.nick}
        targets = self._others()
        if not self.is_host and self.info.port:
            targets = [(self.info.ip, self.info.port)]
        for addr in targets:
            self._send(msg, addr)

    # ---------------- 接收循环 ----------------

    # ---------- 接收循环 ----------
    def _rx_loop(self) -> None:

        """收包线程：不停地从 socket 读包，按类型分发给各个 _on_xxx。"""
        while not self._stop.is_set():
            try:
                raw, addr = self.sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                break
            msg = decode(raw)
            if not msg:
                continue
            kind = str(msg.get("t", ""))
            if msg.get("need_ack"):
                self._ack(str(msg.get("mid_seq", "")), addr)
            # 去重：可靠消息（need_ack）没收到 ACK 会被重传，同一个 mid_seq
            # 只处理一次 —— 否则「开始」重传会让房间页重复跳一次对局页，
            # 把客人正在看的那张牌桌顶掉。
            mid_seq = str(msg.get("mid_seq", "") or "")
            if mid_seq:
                with self._lock:
                    if mid_seq in self._seen_seq:
                        continue
                    self._seen_seq.add(mid_seq)
                    if len(self._seen_seq) > 512:
                        self._seen_seq = set(list(self._seen_seq)[-256:])
            if kind == ACK:
                seq = str(msg.get("ack", ""))
                with self._lock:
                    self._pending.pop(seq, None)
                continue
            if kind == HELLO:
                self._on_hello(msg, addr)
            elif kind == WELCOME:
                self._on_welcome(msg)
            elif kind == REJECT:
                self._on_reject(msg)
            elif kind == ROSTER:
                self._on_roster(msg)
            elif kind == PING:
                self._on_ping(msg, addr)
            elif kind == BYE:
                self._on_bye(msg)
            elif kind == CHAT:
                self._on_chat(msg)
            elif kind == START:
                self._on_start(msg)
            elif kind == GAME:
                self._on_game(msg)
    # ---------------- 心跳 / 重传 / 席位表 ----------------

    # ---------- 心跳与席位表广播 ----------
    def _tick_loop(self) -> None:

        """心跳线程：定时调用 _tick_once。"""
        while not self._stop.is_set():
            try:
                self._tick_once()
            except Exception:                 # noqa: BLE001 — 后台线程不能死
                pass
            self._stop.wait(TICK)

    def _tick_once(self) -> None:

        """一次心跳：超时重传、该 ping 就 ping、该广播席位表就广播。"""
        ts = now()
        # 1) 客人：心跳（顺带把语音端口、想要的座位带过去）
        if not self.is_host and self.joined.is_set():
            if ts - self._last_ping >= 1.0:
                self._last_ping = ts
                self._send({"t": PING, "mid": self.me.mid, "nick": self.me.nick,
                            "vp": self.voice.bound_port,
                            "mic": self.me.mic_on},
                           (self.info.ip, self.info.port))
                with self._lock:
                    me = self.members.get(self.me.mid)
                    if me is not None:
                        me.voice_port = self.voice.bound_port
        # 2) 房主：踢掉没心跳的、定期广播席位表
        if self.is_host:
            drop = [mid for mid, m in self.members.items()
                    if not m.host and ts - m.last_seen > HEARTBEAT_TIMEOUT]
            for mid in drop:
                member = self.members.pop(mid, None)
                if member is not None:
                    self._emit(("system", t("net.dropped",
                                            nick=member.nick)))
            if drop:
                self._push_roster()
                self._refresh_voice_peers()
            self.info.taken = len(self.members)
            if ts - self._last_roster >= ROSTER_INTERVAL:
                self._push_roster()
        # 3) 重传没有 ACK 的可靠消息
        with self._lock:
            expired = []
            for seq, item in self._pending.items():
                if ts < item["next"]:
                    continue
                if item["tries"] >= MAX_RETRY:
                    expired.append(seq)
                    if item.get("hello"):
                        self.join_error = t("net.no_response")
                        self._emit(("join_failed", self.join_error))
                    continue
                item["tries"] += 1
                item["next"] = ts + RETRY_INTERVAL
                for addr in item["addr"]:
                    self._send(item["msg"], addr)
            for seq in expired:
                self._pending.pop(seq, None)

    def _push_roster(self) -> None:

        """广播席位表（房主权威，所有人照它显示）。"""
        self._last_roster = now()
        targets = self._others()
        if not targets:
            return
        self._reliable({"t": ROSTER,
                        "members": [m.to_dict() for m in self.members.values()],
                        "seats": self.info.seats,
                        "game_id": self.info.game_id,
                        "game_title": self.info.game_title}, targets)
        self._emit(("roster", self.roster()))

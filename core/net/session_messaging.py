# -*- coding: utf-8 -*-
"""房间会话的「消息处理」那一半：收到各种包之后干什么。

被 core.net.session.RoomSession 以 mixin 的方式继承。
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from ..i18n import t
from . import REJECT, WELCOME, check_code, now, same_code
from .member import Member
from .session_const import GAME_BACKLOG

class SessionMessagingMixin:
    """消息处理那一半：收到各类包之后干什么。"""

    # ---------------- 各类消息的处理 ----------------

    # ---------- 握手（客人上线 / 房主回应） ----------
    def _on_hello(self, msg: Dict[str, Any], addr: Tuple[str, int]) -> None:

        """收到客人的「hello」：校验房间码，通过就回一个 welcome 并登记席位。"""
        if not self.is_host:
            return
        nick = str(msg.get("nick", t("net.anon")))[:16]
        proof = msg.get("code_check") or {}
        ip = addr[0]
        # 1) 房间码对不对：明文兜底，散列兜actoring（两端版本不一致时也能进）
        code_ok = (same_code(msg.get("code"), self.code)
                   or check_code(str(msg.get("code") or self.code),
                                 self.info.salt, str(proof.get("hash", ""))))
        if not code_ok:
            self._send({"t": REJECT, "reason": t("net.wrong_code"),
                        "mid": "0"}, addr)
            self._emit(("system", t("net.wrong_code_sys", ip=ip)))
            return
        mid = str(msg.get("mid", ""))
        if not mid:
            return
        # 2) 老成员重连（同一 id）→ 直接刷新
        member = self.members.get(mid)
        if member is None:
            if self.started or len(self.members) >= self.info.seats:
                self._send({"t": REJECT,
                            "reason": (t("net.already_started")
                                       if self.started
                                       else t("net.room_full")),
                            "mid": mid}, addr)
                return
            member = Member(mid=mid, nick=nick, ip=ip, ctrl_port=addr[1],
                            seat=self._free_seat())
            with self._lock:
                self.members[mid] = member
        member.nick = nick
        member.ip = ip
        member.ctrl_port = addr[1]
        member.voice_port = int(msg.get("vp", 0) or 0)
        member.last_seen = now()
        # 3) 回执 + 广播席位表
        self._reliable({"t": WELCOME, "to": mid,
                        "members": [m.to_dict() for m in self.members.values()],
                        "seats": self.info.seats,
                        "game_id": self.info.game_id,
                        "game_title": self.info.game_title},
                       [(ip, addr[1])])
        self._emit(("system", t("net.joined", nick=nick)))
        self._push_roster()
        self._refresh_voice_peers()

    def _on_welcome(self, msg: Dict[str, Any]) -> None:

        """房主回应了我们的 hello：登记自己的席位与房间信息。"""
        if self.is_host:
            return
        with self._lock:
            self._pending.pop("join", None)
            members: Dict[str, Member] = {}
            for d in (msg.get("members") or []):
                m = Member.from_dict(d)
                if m is not None:
                    members[m.mid] = m
            if self.me.mid not in members:
                members[self.me.mid] = Member(
                    mid=self.me.mid, nick=self.me.nick, ip=self.me.ip,
                    ctrl_port=self.me.ctrl_port, seat=-1)
            self.members = members
            mine = self.members.get(self.me.mid)
            if mine is None:
                mine = Member(mid=self.me.mid, nick=self.me.nick,
                              ip=self.me.ip, ctrl_port=self.me.ctrl_port)
                self.members[self.me.mid] = mine
            self.me.seat = mine.seat
            self.me.voice_port = self.voice.bound_port
        self.info.seats = int(msg.get("seats", self.info.seats) or
                              self.info.seats)
        gid = msg.get("game_id")
        gtitle = msg.get("game_title")
        if gid:
            self.info.game_id = str(gid)
        if gtitle:
            self.info.game_title = str(gtitle)
        self.joined.set()
        self._emit(("joined", True))
        self._refresh_voice_peers()

    def _on_reject(self, msg: Dict[str, Any]) -> None:

        """房主拒绝了（房间码不对 / 房间满了 / 已被踢）。"""
        reason = str(msg.get("reason", "被拒绝"))
        with self._lock:
            self._pending.pop("join", None)
        self.join_error = reason
        self._emit(("join_failed", reason))

    # ---------- 席位表与心跳 ----------
    def _on_roster(self, msg: Dict[str, Any]) -> None:

        """房主广播的席位表：更新所有人的昵称、状态与「谁在说话」。"""
        if self.is_host:
            return
        members: Dict[str, Member] = {}
        for d in (msg.get("members") or []):
            m = Member.from_dict(d)
            if m is not None:
                members[m.mid] = m
        if not members:
            return
        self.members = members
        gid = msg.get("game_id")
        gtitle = msg.get("game_title")
        if gid:
            self.info.game_id = str(gid)
        if gtitle:
            self.info.game_title = str(gtitle)
        mine = members.get(self.me.mid)
        if mine is None:                      # 席位表里没我 = 被踢了
            self._emit(("kicked", None))
            return
        self.me.seat = mine.seat
        self.me.nick = mine.nick
        self._emit(("roster", self.roster()))
        self._refresh_voice_peers()

    def _on_ping(self, msg: Dict[str, Any], addr: Tuple[str, int]) -> None:

        """心跳包：顺手回一个 pong，让房主知道我还活着。"""
        if not self.is_host:
            return
        mid = str(msg.get("mid", ""))
        member = self.members.get(mid)
        if member is None:
            return                            # 没走 hello 的陌生心跳，忽略
        member.last_seen = now()
        member.ip = addr[0]
        member.ctrl_port = addr[1]
        vp = int(msg.get("vp", 0) or 0)
        if vp:
            member.voice_port = vp
        want = msg.get("want_seat")
        changed = False
        if isinstance(want, int) and 0 <= want < self.info.seats:
            changed = self._assign(mid, want)
        nick = str(msg.get("nick", "") or "")
        if nick and nick != member.nick:
            member.nick = nick[:16]
            changed = True
        if msg.get("mic") is not None:
            member.mic_on = bool(msg.get("mic"))
            changed = True
        if changed:
            self._push_roster()
            self._refresh_voice_peers()

    def _on_bye(self, msg: Dict[str, Any]) -> None:

        """有人离开房间（房主通知所有人）。"""
        mid = str(msg.get("mid", ""))
        nick = str(msg.get("nick", "") or "有人")
        with self._lock:
            member = self.members.pop(mid, None)
        if member is None:
            return
        self._emit(("system", t("net.left", nick=member.nick or nick)))
        if self.is_host:
            self._push_roster()
        self._emit(("roster", self.roster()))
        self._refresh_voice_peers()

    # ---------- 聊天 / 开始 / 玩法消息 ----------
    def _on_chat(self, msg: Dict[str, Any]) -> None:

        """聊天消息：原样转发给界面层。"""
        text = str(msg.get("text", ""))
        nick = str(msg.get("from", "?"))
        item = {"nick": nick, "text": text, "own": False,
                "ts": float(msg.get("ts", now()) or now())}
        if self.is_host:
            # 房主转发给其他人，保证所有人看到一样的聊天内容
            for m in list(self.members.values()):
                if m.mid != self.me.mid and m.mid != str(msg.get("mid", "")):
                    self._send(msg, (m.ip, m.ctrl_port))
        self._emit(("chat", item))

    def _on_start(self, msg: Dict[str, Any]) -> None:

        """房主说「开始」：切到对局路由，所有人一起进。"""
        self.started = True
        self._emit(("start", {"game": msg.get("game", self.info.game_id),
                              "room": msg.get("room", self.info.name)}))

    def _on_game(self, msg: Dict[str, Any]) -> None:
        """把玩法消息直接交给当前在房间里跑的游戏处理。"""
        fn = self._game_handler
        if fn is None:
            # 视图还没建好（开始游戏瞬间常有）→ 暂存，等 set_game_handler 补发
            with self._lock:
                if len(self._game_backlog) < GAME_BACKLOG:
                    self._game_backlog.append(msg)
            return
        try:
            fn(msg)
        except Exception:                     # noqa: BLE001
            # 玩法层崩了不该拖垮网络线程
            pass

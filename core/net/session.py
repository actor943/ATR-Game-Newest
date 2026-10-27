# -*- coding: utf-8 -*-
"""房间会话：席位 / 聊天 / 心跳 / 语音的运行时。

一个进程里可能有三种角色需要的房间，本模块把它们合成一个 :class:`RoomSession`：

* **房主**（``create``）：UDP 控制端口 + beacon 广播 + 席位权威；
* **客人**（``join``）：输入房间码 → ``hello`` → 拿到席位与成员表。

房间状态只有**房主是权威**：谁来谁走、坐哪个位子都由房主说了算，客人只发请求、
收房主广播下来的席位表（``roster``）。这样不需要选主也不需要共识，
丢包了客人最多是显示晚一点，房主下一次广播自然会对齐。

事件怎么给界面
--------------
网络线程只往 ``events`` 队列里丢元组 ``(kind, payload)``，**不碰 flet**。
界面层起一个轮询任务每隔一小会儿把队列抽干净再 ``update`` ——
线程安全，也不会因为异步回调顺序把界面搞乱。
"""

from __future__ import annotations

import queue
import socket
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

from ..i18n import t
from . import (
    ACK, BYE, CHAT, GAME, HELLO, PING, REJECT, RELIABLE,     ROSTER, START,
    WELCOME,
    check_code, code_hash, decode, encode, make_salt, new_mid, now, same_code,
    short_id,
)
from .discovery import BeaconBroadcaster, RoomInfo, beacon_socket, lan_ip
from .voice import VoiceBus

TICK = 0.5                 # 心跳 / 重传 / 超时检查的节奏
HEARTBEAT_TIMEOUT = 5.0    # 这么久没心跳就当人走了
ROSTER_INTERVAL = 2.0      # 房主周期性广播席位表（自愈丢包）
MAX_RETRY = 6              # 可靠消息最多重发几次
RETRY_INTERVAL = 0.5
JOIN_TIMEOUT = 4.0         # 等房主回话的最长时间
GAME_BACKLOG = 32          #  handler 未挂上时最多暂存几条玩法消息


@dataclass
class Member:
    """房间里的一个人。"""

    mid: str                 # 成员 id
    nick: str
    ip: str
    ctrl_port: int = 0
    voice_port: int = 0      # 语音端口（开了麦才有值）
    seat: int = -1           # -1 = 站着没座位
    host: bool = False
    mic_on: bool = True
    last_seen: float = field(default_factory=now)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("last_seen", None)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Optional["Member"]:
        try:
            return cls(
                mid=str(d["mid"]), nick=str(d.get("nick", "?")),
                ip=str(d.get("ip", "")), ctrl_port=int(d.get("ctrl_port", 0)),
                voice_port=int(d.get("voice_port", 0)),
                seat=int(d.get("seat", -1)), host=bool(d.get("host", False)),
                mic_on=bool(d.get("mic_on", True)),
            )
        except (KeyError, TypeError, ValueError):
            return None


class RoomSession:
    """一个房间的一次会话（房主或客人共用一套代码）。"""

    def __init__(
        self,
        info: RoomInfo,
        me: Member,
        sock: socket.socket,
        *,
        host: bool = False,
        code: str = "",
    ):
        self.info = info
        self.me = me
        self.sock = sock
        self.is_host = host
        self.code = code                      # 只有房主需要留着（校验外来人）

        self.members: Dict[str, Member] = {}
        self.events: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        self.voice = VoiceBus(port=0, on_error=self._emit_voice_error)
        self.joined = threading.Event()
        self.join_error = ""
        self.started = False

        self._beacon: Optional[BeaconBroadcaster] = None
        self._rx: Optional[threading.Thread] = None
        self._tick: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pending: Dict[str, Dict[str, Any]] = {}   # mid -> 待确认消息
        self._seen_seq: set = set()   # 已处理过的可靠消息序号（去重）
        self._last_roster = 0.0
        self._last_ping = 0.0
        self._lock = threading.RLock()
        self._game_handler = None     # 当前在房间内运行的游戏（如象棋）注册的网络回调
        # 玩法消息到达时还没有回调（视图还在路上）→ 先暂存，挂上回调立刻补发，
        # 否则「开始游戏」瞬间的头几条消息（req_state / 首发牌）会被悄悄吞掉
        self._game_backlog: List[Dict[str, Any]] = []

        if self.is_host:
            self.members[me.mid] = me
            self.joined.set()

    # ================================================================
    # 建立 / 加入
    # ================================================================

    @classmethod
    def create(
        cls,
        name: str,
        game_id: str,
        game_title: str,
        code: str,
        nick: str,
        seats: int = 4,
    ) -> Optional["RoomSession"]:
        """房主：开一个房间。失败返回 None（端口开不了）。"""
        try:
            sock = beacon_socket()
            sock.bind(("", 0))
            sock.settimeout(0.3)
        except OSError:
            return None
        ip = lan_ip()
        salt = make_salt()
        me = Member(mid=short_id(), nick=nick, ip=ip,
                    ctrl_port=sock.getsockname()[1], seat=0, host=True)
        info = RoomInfo(
            room_id=short_id(), name=name, game_id=game_id,
            game_title=game_title, host=nick, ip=ip, port=me.ctrl_port,
            seats=max(2, min(int(seats), 8)), taken=1, salt=salt,
            code_hash=code_hash(code, salt),
        )
        session = cls(info, me, sock, host=True, code=code)
        session.start()
        return session

    @classmethod
    def join(cls, room: RoomInfo, code: str, nick: str) -> Optional["RoomSession"]:
        """客人：带着房间码申请加入。

        **不阻塞**：后台发 ``hello`` 并等待房主回话。界面层用 :meth:`wait_join`
        或者在轮询里收到 ``joined`` / ``join_failed`` 事件后再决定进不进房间页。
        """
        try:
            sock = beacon_socket()
            sock.bind(("", 0))
            sock.settimeout(0.3)
        except OSError:
            return None
        me = Member(mid=short_id(), nick=nick, ip=lan_ip(),
                    ctrl_port=sock.getsockname()[1], seat=-1)
        session = cls(room, me, sock, host=False, code=code)
        # 本地预校验：广播里带了盐和散列，输错的人立刻就能知道，不用干等超时
        if not check_code(code, room.salt, room.code_hash):
            session.join_error = t("net.wrong_code")
            session._emit(("join_failed", session.join_error))
            session.close()
            return session
        session.start()
        session._say_hello()
        return session

    # ================================================================
    # 生命周期
    # ================================================================

    def start(self) -> None:
        if self._rx is not None:
            return
        self._stop.clear()
        if self.is_host:
            self._beacon = BeaconBroadcaster(self.info)
            self._beacon.start()
        self._rx = threading.Thread(target=self._rx_loop, daemon=True,
                                    name="room-rx")
        self._rx.start()
        self._tick = threading.Thread(target=self._tick_loop, daemon=True,
                                      name="room-tick")
        self._tick.start()
        self.start_voice()

    def close(self) -> None:
        """退房并收掉所有线程（离开房间页一定要调用）。"""
        if self._stop.is_set():
            return
        self._goodbye()
        self._stop.set()
        self.voice.close()
        if self._beacon is not None:
            self._beacon.stop()
            self._beacon = None
        try:
            self.sock.close()
        except OSError:
            pass
        self._rx = None
        self._tick = None

    # ---------------- 加入结果 ----------------

    def wait_join(self, timeout: float = JOIN_TIMEOUT) -> bool:
        """阻塞等待加入结果（也可以忽略它，靠事件驱动界面）。"""
        self.joined.wait(timeout)
        return self.joined.is_set()

    # ================================================================
    # 查询
    # ================================================================

    def roster(self) -> List[Member]:
        """当前席位表（按座位号排，没座位的排最后）。"""
        with self._lock:
            return sorted(self.members.values(),
                          key=lambda m: (m.seat < 0, m.seat, m.nick))

    def seat_of(self, member_id: str) -> int:
        m = self.members.get(member_id)
        return m.seat if m else -1

    def taken(self) -> int:
        return len(self.members)

    def is_host_member(self, member_id: Optional[str] = None) -> bool:
        mid = member_id or self.me.mid
        m = self.members.get(mid)
        return bool(m and m.host)

    # ================================================================
    # 动作（界面调）
    # ================================================================

    def send_chat(self, text: str) -> None:
        """发一句聊天。房主直接广播，客人先发给房主由他转发。"""
        text = (text or "").strip()
        if not text:
            return
        msg = {"t": CHAT, "from": self.me.nick, "mid": self.me.mid,
               "text": text[:200], "ts": now()}
        if self.is_host:
            self._emit(("chat", {"nick": self.me.nick, "text": text,
                                 "own": True, "ts": msg["ts"]}))
            for m in list(self.members.values()):
                if m.mid != self.me.mid:
                    self._send(msg, (m.ip, m.ctrl_port))
        else:
            self._send(msg, (self.info.ip, self.info.port))

    def take_seat(self, seat: int) -> None:
        """申请坐到某个位子（客人发请求，房主自己直接坐）。"""
        if seat < 0 or seat >= self.info.seats:
            return
        if self.is_host:
            self._assign(self.me.mid, seat)
            self._push_roster()
        else:
            self._send({"t": PING, "mid": self.me.mid, "nick": self.me.nick,
                        "want_seat": seat, "vp": self.voice.bound_port},
                       (self.info.ip, self.info.port))

    def set_mic(self, on: bool) -> bool:
        """开/关自己的麦克风，返回是否真的可用。

        第一次开麦时会把音频输入设备拉起来 —— 进房间不主动录音，
        一定要用户自己点头，这点既是礼貌也是隐私。
        """
        self.me.mic_on = bool(on)
        port_ok = self.start_voice()          # 先把语音端口准备好
        ok = self.voice.set_mic(bool(on)) and port_ok
        self._announce_voice()
        return ok

    def set_speaker(self, on: bool) -> None:
        self.voice.set_speaker(bool(on))

    def start_voice(self) -> bool:
        """准备好语音通道（只是 UDP 端口，不碰音频设备）。幂等。"""
        if self.voice.running:
            self.me.voice_port = self.voice.bound_port
            self._refresh_voice_peers()
            return True
        ok = self.voice.open_port()
        if ok:
            self.me.voice_port = self.voice.bound_port
            self._refresh_voice_peers()
        return ok

    def begin_game(self) -> None:
        """房主宣布开始：所有人收到 ``start`` 事件。

        这一步只做「联动」——各游戏自己决定接下去打开哪个路由。
        """
        if not self.is_host:
            return
        self.started = True
        self.info.started = True
        self._reliable({"t": START, "game": self.info.game_id,
                        "room": self.info.name},
                       targets=self._others())
        self._emit(("start", {"game": self.info.game_id,
                              "room": self.info.name}))

    def set_game(self, game_id: str, game_title: str) -> None:
        """房主在房间内切换游戏；客人只通过 roster 广播得知。"""
        self.info.game_id = game_id
        self.info.game_title = game_title
        if self.is_host:
            self._push_roster()

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

    # ================================================================
    # 内部：事件与通知
    # ================================================================

    def _emit(self, item: Tuple[str, Any]) -> None:
        self.events.put(item)

    def _emit_voice_error(self, text: str) -> None:
        self._emit(("voice_error", text))

    def system(self, text: str) -> None:
        """本地提示（例如「XXX 加入了房间」），只进本机的聊天窗口。"""
        self._emit(("system", text))

    def drain(self) -> List[Tuple[str, Any]]:
        """界面层调用：把攒下的事件一次取走。"""
        out: List[Tuple[str, Any]] = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                break
        return out

    # ================================================================
    # 内部：收发
    # ================================================================

    def _others(self) -> List[Tuple[str, int]]:
        return [(m.ip, m.ctrl_port) for m in self.members.values()
                if m.mid != self.me.mid and m.ctrl_port]

    def _send(self, msg: Dict[str, Any], addr: Tuple[str, int]) -> None:
        try:
            self.sock.sendto(encode(msg), addr)
        except OSError:
            pass

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
        self._send({"t": ACK, "ack": seq}, addr)

    def _say_hello(self) -> None:
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
        msg = {"t": BYE, "mid": self.me.mid, "nick": self.me.nick}
        targets = self._others()
        if not self.is_host and self.info.port:
            targets = [(self.info.ip, self.info.port)]
        for addr in targets:
            self._send(msg, addr)

    # ---------------- 接收循环 ----------------

    def _rx_loop(self) -> None:
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

    # ---------------- 各类消息的处理 ----------------

    def _on_hello(self, msg: Dict[str, Any], addr: Tuple[str, int]) -> None:
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
        reason = str(msg.get("reason", "被拒绝"))
        with self._lock:
            self._pending.pop("join", None)
        self.join_error = reason
        self._emit(("join_failed", reason))

    def _on_roster(self, msg: Dict[str, Any]) -> None:
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

    def _on_chat(self, msg: Dict[str, Any]) -> None:
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

    # ---------------- 心跳 / 重传 / 席位表 ----------------

    def _tick_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick_once()
            except Exception:                 # noqa: BLE001 — 后台线程不能死
                pass
            self._stop.wait(TICK)

    def _tick_once(self) -> None:
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

    # ---------------- 席位与语音 ----------------

    def _free_seat(self) -> int:
        busy = {m.seat for m in self.members.values() if m.seat >= 0}
        for i in range(self.info.seats):
            if i not in busy:
                return i
        return -1

    def _assign(self, mid: str, seat: int) -> bool:
        member = self.members.get(mid)
        if member is None or seat < 0 or seat >= self.info.seats:
            return False
        busy = {m.mid: m.seat for m in self.members.values() if m.seat >= 0}
        owner = next((k for k, v in busy.items() if v == seat and k != mid), None)
        if owner is not None:
            return False                       # 位子有人站着
        member.seat = seat
        return True

    def _announce_voice(self) -> None:
        if self.is_host:
            self._push_roster()
            self._refresh_voice_peers()
        else:
            self._send({"t": PING, "mid": self.me.mid, "nick": self.me.nick,
                        "vp": self.voice.bound_port, "mic": self.me.mic_on},
                       (self.info.ip, self.info.port))

    def _refresh_voice_peers(self) -> None:
        with self._lock:
            peers = [(m.ip, m.voice_port) for m in self.members.values()
                     if m.mid != self.me.mid and m.voice_port and m.mic_on]
        self.voice.set_peers(peers)

    # ---------------- 小工具 ----------------

    def describe(self) -> str:
        return f"{self.info.name}（{self.info.game_title}）· " \
               f"{self.taken()}/{self.info.seats} 人"


# ================================================================
# 当前会话（跨路由共享：多人游戏页建好房间 → 房间页接着用）
# ================================================================

_CURRENT: Optional[RoomSession] = None


def set_current(session: Optional[RoomSession]) -> None:
    """登记当前房间（进入/离开房间页时用）。"""
    global _CURRENT
    if _CURRENT is not None and _CURRENT is not session:
        _CURRENT.close()
    _CURRENT = session


def current() -> Optional[RoomSession]:
    return _CURRENT


def leave_current() -> None:
    """离开房间：收线程、停语音、清全局引用。"""
    global _CURRENT
    if _CURRENT is not None:
        _CURRENT.close()
        _CURRENT = None

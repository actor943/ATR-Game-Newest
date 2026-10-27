# -*- coding: utf-8 -*-
"""房间会话：席位 / 聊天 / 心跳 / 语音的运行时。

一个进程里可能有三种角色需要的房间，本模块把它们合成一个 :class:`RoomSession`：

* **房主**（``create``）：UDP 控制端口 + beacon 广播 + 席位权威；
* **客人**（``join``）：输入房间码 -> ``hello`` -> 拿到席位与成员表。

房间状态只有**房主是权威**：谁来谁走、坐哪个位子都由房主说了算，客人只发请求、
收房主广播下来的席位表（``roster``）。这样不需要选主也不需要共识，
丢包了客人最多是显示晚一点，房主下一次广播自然会对齐。

事件怎么给界面
--------------
网络线程只往 ``events`` 队列里丢元组 ``(kind, payload)``，**不碰 flet**。
界面层起一个轮询任务每隔一小会儿把队列抽干净再 ``update`` ——
线程安全，也不会因为异步回调顺序把界面搞乱。

模块划分
--------
原文件 800 多行，现在按职责拆开（``RoomSession`` 用 mixin 组合起来）：

============================== ========================================= ==========
模块                         负责什么                                 行数量级
============================== ========================================= ==========
``member.py``                房间里「一个人」的数据结构                 约 60
``session_const.py``         心跳 / 重传 / 超时的时间参数              约 20
``session_reliable.py``       收发包、ACK、重传、心跳、席位表广播      约 230
``session_messaging.py``      收到各类包之后的处理                    约 220
``session_game.py``          玩法消息的透传（象棋走子等）             约 70
``session.py``（本文件）      会话主体 + 全局「当前房间」             约 380
============================== ========================================= ==========
"""

from __future__ import annotations

import queue
import socket
import threading
from typing import Any, Dict, List, Optional, Tuple

from ..i18n import t
from . import (
    CHAT,
    PING,
    START,
    check_code,
    code_hash,
    make_salt,
    now,
    short_id,
)
from .discovery import BeaconBroadcaster, RoomInfo, beacon_socket, lan_ip
from .member import Member
from .session_const import JOIN_TIMEOUT
from .session_game import SessionGameMixin
from .session_messaging import SessionMessagingMixin
from .session_reliable import SessionReliableMixin
from .voice import VoiceBus

class RoomSession(SessionReliableMixin, SessionMessagingMixin,
                   SessionGameMixin):
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
# 当前会话（跨路由共享：多人游戏页建好房间 -> 房间页接着用）
# ================================================================

_CURRENT: Optional[RoomSession] = None


def set_current(session: Optional[RoomSession]) -> None:
    """登记当前房间（进入/离开房间页时用）。"""
    global _CURRENT
    if _CURRENT is not None and _CURRENT is not session:
        _CURRENT.close()
    _CURRENT = session


def current() -> Optional[RoomSession]:
    """当前正在用的房间会话；没有就是 None。"""
    return _CURRENT


def leave_current() -> None:
    """离开房间：收线程、停语音、清全局引用。"""
    global _CURRENT
    if _CURRENT is not None:
        _CURRENT.close()
        _CURRENT = None

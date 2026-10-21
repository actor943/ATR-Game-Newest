# -*- coding: utf-8 -*-
"""局域网房间发现：主机 UDP 广播，客人监听收集。

用法（主机）::

    info = RoomInfo(...)
    with beacon(info):            # 也可以手动 start/stop
        ...

用法（客人）::

    scanner = RoomScanner()
    scanner.start()
    rooms = scanner.rooms()       # 当前能看到的房间（3.5s 没刷新就当消失）
    scanner.stop()

两个类都只做「发现和保持在线」，不碰房间内部事务（那是 session.py 的事）。
"""

from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional

from . import BROADCAST_ADDR, DISCOVERY_PORT, decode, encode, now

BEACON_INTERVAL = 1.0      # 主机多久广播一次
ROOM_TTL = 3.5             # 超过这个时间没再收到 beacon 就认为房间没了
_RECV_BUFSIZE = 4096


@dataclass
class RoomInfo:
    """广播里的一条房间信息（不含任何私密内容）。"""

    room_id: str
    name: str                # 房间名
    game_id: str             # 玩哪个游戏（"guandan"）
    game_title: str          # 游戏显示名（"掼蛋"）
    host: str                # 房主昵称
    ip: str                  # 主机 LAN IP
    port: int                # 房间控制端口（UDP）
    seats: int = 4           # 总席位
    taken: int = 1           # 已坐下的席位
    locked: bool = False     # 房间码错的房不让进（显示时给个标记）
    salt: str = ""           # 房间码加盐（只用于本地校验，不离开本机）
    code_hash: str = ""      # 房间码散列：报告的改不了，输了才知道对不对
    started: bool = False    # 是否已经开始（开始后不再收人）
    ts: float = field(default_factory=now)

    # ---------- 序列化 ----------

    def to_packet(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["t"] = "beacon"
        return payload

    @classmethod
    def from_packet(cls, pkt: Dict[str, object],
                    src_ip: str) -> Optional["RoomInfo"]:
        try:
            info = cls(
                room_id=str(pkt["room_id"]),
                name=str(pkt.get("name", "")),
                game_id=str(pkt.get("game_id", "")),
                game_title=str(pkt.get("game_title", "")),
                host=str(pkt.get("host", "")),
                ip=src_ip,                      # 以包来源为准，别信包里填的
                port=int(pkt["port"]),
                seats=int(pkt.get("seats", 4)),
                taken=int(pkt.get("taken", 1)),
                locked=bool(pkt.get("locked", False)),
                salt=str(pkt.get("salt", "")),
                code_hash=str(pkt.get("code_hash", "")),
                started=bool(pkt.get("started", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None
        return info

    # ---------- 展示 ----------

    @property
    def label(self) -> str:
        if not self.started and self.taken < self.seats:
            return f"{self.taken}/{self.seats}"
        return "进行中" if self.started else "满员"


def beacon_socket() -> socket.socket:
    """能发广播也能收包的 UDP socket（复用同一端口省事）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except OSError:            # 某些平台不支持复用，忽略即可
        pass
    return s


def _local_ip() -> str:
    """本机在局域网里的 IP（拿不到就用 127.0.0.1）。

    用 connect 到一个外部地址的技巧拿到本机出口网卡 IP，不需要真的发包。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class BeaconBroadcaster:
    """主机：每隔 ``BEACON_INTERVAL`` 秒在局域网里喊一声「房间在这儿」。"""

    def __init__(self, info: RoomInfo, interval: float = BEACON_INTERVAL):
        self.info = info
        self.interval = interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    # ---------------- 控制 ----------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._sock = beacon_socket()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="room-beacon")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._thread = None

    def __enter__(self) -> "BeaconBroadcaster":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # ---------------- 内部 ----------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                data = encode(self.info.to_packet())
                if self._sock is not None:
                    self._sock.sendto(
                        data, (BROADCAST_ADDR, DISCOVERY_PORT))
            except OSError:
                pass
            self._stop.wait(self.interval)


class RoomScanner:
    """客人：监听广播，收集当前局域网里有哪些房间。"""

    def __init__(self, ttl: float = ROOM_TTL,
                 on_change: Optional[Callable[[], None]] = None):
        self.ttl = ttl
        self.on_change = on_change     # 房间集合变了就通知（UI 用）
        self._rooms: Dict[str, RoomInfo] = {}
        self._seen: Dict[str, float] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()

    # ---------------- 控制 ----------------

    def start(self) -> bool:
        """开始扫描；打不开端口返回 False（例如已经有一个扫描在跑）。"""
        if self._thread is not None:
            return True
        try:
            sock = beacon_socket()
            sock.bind(("", DISCOVERY_PORT))
            sock.settimeout(0.4)
        except OSError:
            return False
        self._sock = sock
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="room-scanner")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._thread = None
        with self._lock:
            self._rooms.clear()
            self._seen.clear()

    @property
    def running(self) -> bool:
        return self._thread is not None

    # ---------------- 查询 ----------------

    def rooms(self) -> List[RoomInfo]:
        """当前还在线的房间（按房间名排序，超时的丢掉）。"""
        now_ts = now()
        with self._lock:
            alive = {
                rid: info for rid, info in self._rooms.items()
                if now_ts - self._seen.get(rid, 0) <= self.ttl
            }
            # 顺手清掉过期的
            for rid in list(self._rooms):
                if rid not in alive:
                    self._rooms.pop(rid, None)
                    self._seen.pop(rid, None)
            return sorted(alive.values(), key=lambda r: (r.started, r.name))

    # ---------------- 内部 ----------------

    def _loop(self) -> None:
        sock = self._sock
        while sock is not None and not self._stop.is_set():
            try:
                raw, addr = sock.recvfrom(_RECV_BUFSIZE)
            except socket.timeout:
                continue
            except OSError:
                break
            pkt = decode(raw)
            if not pkt or pkt.get("t") != "beacon":
                continue
            info = RoomInfo.from_packet(pkt, addr[0])
            if info is None:
                continue
            with self._lock:
                known = info.room_id in self._rooms
                self._rooms[info.room_id] = info
                self._seen[info.room_id] = now()
                changed = not known or bool(
                    json.dumps(pkt, sort_keys=True) != json.dumps(
                        self._rooms[info.room_id].to_packet(), sort_keys=True))
            if changed and self.on_change is not None:
                try:
                    self.on_change()
                except Exception:      # noqa: BLE001 — UI 回调出错不该杀线程
                    pass

    def touch(self) -> None:
        """外部（UI 定时器）调用：清理过期房间时用。"""
        self.rooms()


def lan_ip() -> str:
    return _local_ip()


def _unused_port(sock_hint: Optional[socket.socket] = None) -> int:
    """提示用：取一个空闲 UDP 端口（给临时 sockets 用）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def room_summary(info: RoomInfo) -> str:
    """列表上显示的一行。"""
    return f"{info.name} · {info.game_title} · {info.host} · {info.label}"

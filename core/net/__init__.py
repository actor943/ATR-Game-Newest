# -*- coding: utf-8 -*-
"""联机协议：消息类型、编解码、房间码校验。

为什么是 JSON over UDP
----------------------
局域网里人数最多 4～8 个，包都很小（几百字节），可读的 JSON 让排查问题时
抓包就能看懂；真要用 Qt/Flutter 客户端重写也能直接对接。

可靠性
------
UDP 会丢包，但房间里只有三类消息丢不得：

* ``hello``（请求加入）
* ``welcome`` / ``reject``（加入结果）
* ``roster``（席位表变化）

所以给它们做了一层很轻的 **重传 + ACK**：带 ``mid`` 的消息没被 ACK 就重发
（0.5s 一次，最多 6 次），其余消息（心跳、聊天、语音）丢了就算了 ——
聊天丢一句顶多重发，语音丢了更是直接跳过。
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Dict, Optional, Tuple

# ------------------------------------------------------------------
# 端口
# ------------------------------------------------------------------

# 发现端口：全局域网广播房间存在的这一个端口，**固定**，大家才能互相听见
DISCOVERY_PORT = 45663
BROADCAST_ADDR = "255.255.255.255"

# ------------------------------------------------------------------
# 消息类型
# ------------------------------------------------------------------

BEACON = "beacon"        # 主机周期性广播：房间还在
HELLO = "hello"          # 客人 → 主机：我要进（带房间码）
WELCOME = "welcome"      # 主机 → 客人：进来了（带席位与成员表）
REJECT = "reject"        # 主机 → 客人：房间码不对 / 满员
ROSTER = "roster"        # 主机 → 全体：席位表（可靠）
ACK = "ack"              # 收到可靠消息的回执
PING = "ping"            # 客人 → 主机：心跳
BYE = "bye"              # 任一方：我要走了
CHAT = "chat"            # 聊天消息（主机转发）
START = "start"          # 房主：开始游戏
GAME = "game"            # 游戏数据透传（各游戏自定义的玩法消息，例如象棋的走子）

# 需要 ACK 的消息类型（不可靠就丢了会影响房间状态）
RELIABLE = (HELLO, WELCOME, REJECT, ROSTER, START, GAME)

# ------------------------------------------------------------------
# 编解码
# ------------------------------------------------------------------


def encode(msg: Dict[str, Any]) -> bytes:
    """消息 dict → 线上字节。"""
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8")


def decode(raw: bytes) -> Optional[Dict[str, Any]]:
    """线上字节 → 消息 dict；坏包返回 None（网络层直接忽略）。"""
    try:
        msg = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return msg if isinstance(msg, dict) else None


def new_mid() -> str:
    """一条需要 ACK 的消息的唯一编号。"""
    return uuid.uuid4().hex[:12]


def now() -> float:
    return time.time()


def short_id() -> str:
    """短 id（成员 / 房间）：8 位够用，日志里好认。"""
    return uuid.uuid4().hex[:8]


# ------------------------------------------------------------------
# 房间码
# ------------------------------------------------------------------

def make_salt() -> str:
    return uuid.uuid4().hex[:12]


def code_hash(code: str, salt: str) -> str:
    """房间码的散列。

    广播里**不发明文房间码**（局域网里随便一个抓包工具都能看到广播），
    只发加盐散列。想进来的人必须手输正确房间码，本地算出同样的散列才能通过，
    这样既没泄露口令，又把「知道口令才能进」这件事落实了。
    """
    raw = f"{salt}:{(code or '').upper()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def check_code(code: str, salt: str, expect: str) -> bool:
    """用广播里的盐本地**预校验**一下房间码，让输错的人立刻得到反馈。"""
    return bool(code) and code_hash(code, salt) == expect


def same_code(given: Any, expect: str) -> bool:
    """最终校验：把来访者报上来的房间码与本机的比对（不分大小写）。

    房间码只在**单播**里发这一次给房主本人（不进局域网广播），
    房主拿着明文比一遍，比散列表少了「盐泄漏」的顾虑，也不会因为
    两端哈希实现不同步而把正确的人挡在门外。
    """
    if expect is None:
        return False
    a = "".join(ch for ch in str(given or "").upper() if ch.isalnum())
    b = "".join(ch for ch in str(expect or "").upper() if ch.isalnum())
    return bool(a) and a == b


def addr_key(addr: Tuple[str, int]) -> str:
    return f"{addr[0]}:{addr[1]}"

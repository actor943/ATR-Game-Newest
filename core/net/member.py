# -*- coding: utf-8 -*-
"""房间里「一个人」的数据结构。

单独拆出来是因为 core.net.session_messaging 也要用它，
而那个模块又会被 core.net.session 引用 —— 拆开后就没有循环依赖了。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from . import now

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

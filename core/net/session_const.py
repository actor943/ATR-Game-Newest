# -*- coding: utf-8 -*-
"""房间会话的时间参数（心跳 / 重传 / 超时）。

集中放在一个文件里，方便调节频率时只改这一处。
"""

from __future__ import annotations

TICK = 0.5                 # 心跳 / 重传 / 超时检查的节奏
HEARTBEAT_TIMEOUT = 5.0    # 这么久没心跳就当人走了
ROSTER_INTERVAL = 2.0      # 房主周期性广播席位表（自愈丢包）
MAX_RETRY = 6              # 可靠消息最多重发几次
RETRY_INTERVAL = 0.5
JOIN_TIMEOUT = 4.0         # 等房主回话的最长时间
GAME_BACKLOG = 32          #  handler 未挂上时最多暂存几条玩法消息

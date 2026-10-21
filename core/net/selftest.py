# -*- coding: utf-8 -*-
"""局域网联机自检：在自己这一台机器上把整套流程跑一遍。

用法::

    ./venv/bin/python3 -m core.net.selftest

跑的东西（**不需要真的两台电脑**）
-----------------------------------
一个进程里同时开一个「房主」和一个「客人」两个会话，靠本机 UDP 端口互相通讯：

1. 建房间 → 局域网广播 → 能被扫描到；
2. 房间码输错进不去、输对才进得去；
3. 席位表两边一致；换座同步；
4. 聊天能到对面；
5. 语音：灌一段合成音频过去，对面抖动缓冲接得住、1 秒内被播放消费干净；
   没装音频库（sounddevice / numpy）就跳过这一步并说明原因；
6. 开始信号能广播到全员；退房之后房主这边人数正确回落；
7. 档案：房间码会被记住，下次自动带上。
"""

from __future__ import annotations

import time

import numpy as np

from core.profile import Profile, random_code
from core.net.discovery import RoomScanner
from core.net.session import RoomSession, leave_current, set_current
from core.net.voice import AUDIO_OK, FRAME_SAMPLES


def _frame(gain: float = 0.4) -> bytes:
    """合成一帧 440Hz 正弦（肯定过静音门限），用来假装有人在说话。"""
    if not AUDIO_OK:
        return b""
    t = np.arange(FRAME_SAMPLES, dtype=np.float32) / 16000.0
    return (np.sin(2 * np.pi * 440 * t) * gain * 32767).astype(np.int16).tobytes()


def test_discovery_and_join():
    """建房间 → 广播 → 扫描 → 房间码 → 席位 → 聊天 → 退房。"""
    host = RoomSession.create("自检大厅", "guandan", "掼蛋", "SELF77",
                              "房主甲", seats=4)
    assert host is not None, "建房间失败（本机 UDP 端口不给开？）"
    set_current(host)
    host.drain()

    scanner = RoomScanner()
    assert scanner.start(), "扫描端口打不开（已有一个搜索在跑？）"
    try:
        waited = 0.0
        rooms = []
        while waited < 3.0 and not rooms:
            time.sleep(0.4)
            waited += 0.4
            rooms = scanner.rooms()
        assert rooms, "扫不到自己建的房间（广播被系统拦了？）"
        assert rooms[0].name == "自检大厅", rooms[0]
        assert rooms[0].port == host.info.port, "广播里的端口不对"
    finally:
        scanner.stop()

    # 房间码错 → 进不去
    bad = RoomSession.join(host.info, "WRONG1", "路人乙")
    assert bad is not None
    assert bad.join_error == "房间码不对", bad.join_error
    assert not bad.wait_join(1.0), "房间码错了竟然放行了"

    # 房间码对（不分大小写）→ 进得去
    guest = RoomSession.join(host.info, "self77", "客人乙")
    assert guest is not None
    assert guest.wait_join(5.0), f"加入失败：{guest.join_error}"
    time.sleep(0.8)

    assert host.taken() == 2, f"房主这边人数不对：{host.roster()}"
    assert guest.taken() == 2, f"客人这边人数不对：{guest.roster()}"
    host.drain()                           # 丢掉加入阶段攒下的事件

    # 换座同步
    guest.take_seat(3)
    time.sleep(1.0)
    assert guest.me.seat == 3, guest.roster()
    host_seat = next(m.seat for m in host.roster() if m.nick == "客人乙")
    assert host_seat == 3, host.roster()

    # 聊天
    guest.send_chat("你好，我是客人")
    time.sleep(0.6)
    chats = [p for k, p in host.drain() if k == "chat"]
    assert chats and chats[0]["text"] == "你好，我是客人", chats

    # 开始信号
    host.begin_game()
    time.sleep(0.4)
    kinds = [k for k, _ in guest.drain()]
    assert "start" in kinds, kinds

    # 退房 → 房主这边人数回落
    guest.close()
    time.sleep(1.2)
    assert host.taken() == 1, host.roster()
    host.close()
    leave_current()


def test_voice_pipeline():
    """语音：发送 → 抖动缓冲 → 播放消费 → 静音不再攒。"""
    if not AUDIO_OK:
        print("  跳过语音：这台机器没有 sounddevice / numpy")
        return
    host = RoomSession.create("语音自检", "guandan", "掼蛋", "VOICE1",
                              "房主", seats=4)
    set_current(host)
    guest = RoomSession.join(host.info, "voice1", "客人")
    assert guest.wait_join(5.0), guest.join_error
    time.sleep(0.6)
    try:
        assert host.voice._peers, "房主没学到客人的语音端口"
        assert guest.voice._peers, "客人没学到房主的语音端口"
        host.set_mic(False)          # 关掉真麦克风：环境噪声会干扰计数
        guest.set_mic(False)
        time.sleep(0.2)

        target = (guest.me.ip, guest.voice.bound_port)
        for _ in range(30):
            host.voice._sock.sendto(_frame(), target)
        time.sleep(0.05)
        buffers = guest.voice._buffers
        assert any(len(v) > 0 for v in buffers.values()), "客人没收到语音包"
        peer = list(buffers)[0]
        assert guest.voice.is_talking(peer), "说话状态没点亮"

        time.sleep(1.2)
        assert guest.voice._out_stream is not None, "按需播放流没拉起来"
        assert all(len(v) == 0 for v in guest.voice._buffers.values()), \
            "语音帧没被播放消费掉"

        guest.set_speaker(False)
        time.sleep(0.1)
        for _ in range(5):
            host.voice._sock.sendto(_frame(), target)
            time.sleep(0.01)
        time.sleep(0.3)
        assert not any(len(v) > 0 for v in guest.voice._buffers.values()), \
            "扬声器关了还在攒缓冲"
    finally:
        guest.close()
        time.sleep(0.3)
        host.close()
        leave_current()


def test_profile_remember_code():
    """房间码会被本地记住，下次建房间自动带上。"""
    profile = Profile.load()
    code = random_code()
    profile.remember_room("记住我", code)
    again = Profile.load()
    assert again.last_room_code == code, again.last_room_code
    assert again.last_room_name == "记住我", again.last_room_name
    nick = again.ensure_nick()
    assert nick, "没名字时应该随机一个"
    assert Profile.load().nick == nick, "随机名字应该写回本地"


def main() -> None:
    for test in (test_profile_remember_code, test_discovery_and_join,
                 test_voice_pipeline):
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            print(f"FAIL {test.__name__}: {exc}")
            raise
    print("ALL OK")


if __name__ == "__main__":
    main()

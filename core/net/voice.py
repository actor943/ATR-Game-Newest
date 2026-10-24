# -*- coding: utf-8 -*-
"""房间语音：麦克风采集 + 局域网 UDP 单播 + 混音播放。

能不用就不用硬依赖
------------------
桌面端用 ``sounddevice``（内部是 PortAudio）做采集/播放，但它是**可选依赖**：

* 装了 → 房间里有真的语音；
* 没装（手机端打包、或者用户的 Python 没有对应 wheel）→ :data:`AUDIO_OK`
  为 ``False``，界面上把麦克风/扬声器按钮标成「未安装音频库」，其余功能照常。

这样即便在没有 PortAudio 的平台上，应用也不会因为 import 失败而崩在启动阶段。

语音怎么走
----------
.Controls (``session.py``) 走的是 UDP 文本 JSON；语音用它自己的 UDP 端口，
20ms 一帧、16kHz 单声道 int16（640 字节/帧 ≈ 32KB/s/人），点对点发给房间里
其他每个人 —— 局域网带宽完全够，也不用服务器转发。

* **静音门限**（``GATE``）：低于阈值的帧直接不发，安静时几乎零流量；
* **抖动缓冲**：每个远端一个 ~400ms 的队列，网络抖一下不会听起来断断续续；
* **混音**：只有一个播放流，多路远端在回调里相加并 clip，避免 PortAudio
  多实例互相抢设备。
"""

from __future__ import annotations

import socket
import threading
import time
from collections import deque
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from ..i18n import t

try:                                  # 可选依赖：没有就降级，不阻断启动
    import numpy as np
    import sounddevice as sd
    AUDIO_OK = True
    AUDIO_ERROR = ""
except Exception as _exc:             # noqa: BLE001 — ImportError / OSError 都要兜住
    np = None                         # type: ignore[assignment]
    sd = None                         # type: ignore[assignment]
    AUDIO_OK = False
    AUDIO_ERROR = f"{type(_exc).__name__}: {_exc}"

SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000        # 320 samples
FRAME_BYTES = FRAME_SAMPLES * 2                       # int16 单声道
GATE = 0.006                                          # 静音门限（ RMS，归一化 ）
JITTER_FRAMES = 20                                     # 抖动缓冲：400ms
_RECV_BUFSIZE = FRAME_BYTES * 4

Peer = Tuple[str, int]


class VoiceBus:
    """一条语音总线：采集本机麦克风 → 发给 peers；收 peers 的 → 混音播放。"""

    def __init__(
        self,
        port: int = 0,
        on_level: Optional[Callable[[float], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.port = port
        self.on_level = on_level
        self.on_error = on_error

        self.mic_on = False
        self.speaker_on = True
        self.ptt = False                    # True 时按住才说话
        self._ptt_down = False
        self.level = 0.0                    # 最近一帧音量（0~1），UI 画电平条

        self._peers: List[Peer] = []
        self._buffers: Dict[Peer, deque] = {}
        self._buf_lock = threading.Lock()
        self._talking: Dict[Peer, float] = {}

        self._sock: Optional[socket.socket] = None
        self._rx: Optional[threading.Thread] = None
        self._in_stream = None
        self._out_stream = None
        self._stop = threading.Event()
        self._started = False

    # ---------------- 属性 ----------------

    @property
    def available(self) -> bool:
        """这台机器上语音能不能用。"""
        return AUDIO_OK

    @property
    def reason(self) -> str:
        return "" if AUDIO_OK else AUDIO_ERROR

    @property
    def running(self) -> bool:
        return self._started

    @property
    def bound_port(self) -> int:
        try:
            return self._sock.getsockname()[1] if self._sock else 0
        except OSError:
            return 0

    # ---------------- 生命周期 ----------------

    def open_port(self) -> bool:
        """只把 UDP 语音端口准备好（**不碰任何音频设备**）。

        进房间就先做这一步：端口有了才能在席位表里告诉别人「我在这儿」。
        麦克风/扬声器这类**真设备**要等到用户点头才拉开，进房间就偷偷
        录音不合适，也容易把别人的音乐打断。
        """
        if self._started:
            return True
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.bind(("", self.port or 0))
            self._sock.settimeout(0.3)
        except OSError as exc:
            self._notify(t("voice.port_error", exc=exc))
            return False
        self._stop.clear()
        self._rx = threading.Thread(target=self._recv_loop, daemon=True,
                                    name="voice-rx")
        self._rx.start()
        self._started = True
        return True

    def start(self) -> bool:
        """兼容旧调用：等同于 :meth:`open_port`。"""
        return self.open_port()

    # ---------------- 真正碰设备的部分 ----------------

    def ensure_input(self) -> bool:
        """按需打开麦克风采集流（用户点了「开麦克风」才走到这里）。"""
        if not AUDIO_OK or not self._started:
            return False
        if self._in_stream is not None:
            return True
        try:
            self._in_stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16",
                blocksize=FRAME_SAMPLES, callback=self._mic_cb)
            self._in_stream.start()
        except Exception as exc:            # noqa: BLE001 — 没权限 / 设备被占
            self._notify(t("voice.mic_error", kind=type(exc).__name__,
                           exc=exc))
            self._in_stream = None
            return False
        return True

    def ensure_output(self) -> bool:
        """按需打开播放流（收到别人的语音时才拉起来）。"""
        if not AUDIO_OK or not self._started or not self.speaker_on:
            return False
        if self._out_stream is not None:
            return True
        try:
            self._out_stream = sd.OutputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16",
                blocksize=FRAME_SAMPLES, callback=self._play_cb)
            self._out_stream.start()
        except Exception as exc:            # noqa: BLE001
            self._notify(t("voice.speaker_error", kind=type(exc).__name__,
                           exc=exc))
            self._out_stream = None
            return False
        return True

    def stop(self) -> None:
        self._started = False
        self._stop.set()
        for stream in (self._in_stream, self._out_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:           # noqa: BLE001
                    pass
        self._in_stream = None
        self._out_stream = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._rx = None
        with self._buf_lock:
            self._buffers.clear()
            self._talking.clear()

    def close(self) -> None:
        self.stop()

    # ---------------- 对端与开关 ----------------

    def set_peers(self, peers: Iterable[Peer]) -> None:
        """更新要发给谁（席位表变了就调用）。"""
        peers = [tuple(p) for p in peers if p and p[0]]      # type: ignore[misc]
        key = set(peers)
        if set(self._peers) == key:
            return
        self._peers = list(key)
        with self._buf_lock:
            for p in list(self._buffers):
                if p not in self._peers:
                    self._buffers.pop(p, None)
                    self._talking.pop(p, None)

    def set_mic(self, on: bool) -> bool:
        """开/关麦克风，返回麦克风是否真的可用（界面据此提示）。"""
        self.mic_on = bool(on)
        if not self.mic_on:
            return True
        return self.ensure_input()

    def set_speaker(self, on: bool) -> bool:
        """开/关扬声器；关掉时把播放流也收了，别占着设备。"""
        self.speaker_on = bool(on)
        if not self.speaker_on:
            stream, self._out_stream = self._out_stream, None
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:               # noqa: BLE001
                    pass
            with self._buf_lock:
                for buf in self._buffers.values():
                    buf.clear()
            return True
        return True                             # 播放流等人真来了再开

    def set_ptt(self, enabled: bool, down: bool = False) -> None:
        """按住说话模式：``enabled`` 开关atégie，``down`` 当前是否按住。"""
        self.ptt = bool(enabled)
        self._ptt_down = bool(down)

    def press(self, down: bool) -> None:
        self._ptt_down = bool(down)

    def is_talking(self, peer: Peer) -> bool:
        """某个远端最近 300ms 内有没有出声（界面上点亮他的头像用）。"""
        return time.time() - self._talking.get(tuple(peer), 0.0) < 0.3

    # ---------------- 内部：采集发送 ----------------

    def _mic_cb(self, indata, _frames, _time_info, _status) -> None:
        sock = self._sock
        if sock is None:
            return
        data = np.frombuffer(indata, dtype=np.int16)
        rms = float(np.sqrt(np.mean((data.astype(np.float32) / 32768.0) ** 2)))
        self.level = min(1.0, rms * 6.0)         # 放大到肉眼好看的区间
        if not self.mic_on:
            self.level = 0.0
            return
        if self.ptt and not self._ptt_down:
            self.level = 0.0
            return
        if rms < GATE:                            # 静音帧不发，省带宽
            return
        if self.on_level is not None:
            try:
                self.on_level(self.level)
            except Exception:                     # noqa: BLE001
                pass
        payload = data.tobytes()
        for peer in list(self._peers):
            try:
                sock.sendto(payload, peer)
            except OSError:
                pass

    # ---------------- 内部：接收 ----------------

    def _recv_loop(self) -> None:
        sock = self._sock
        while sock is not None and not self._stop.is_set():
            try:
                raw, addr = sock.recvfrom(_RECV_BUFSIZE)
            except socket.timeout:
                continue
            except OSError:
                break
            if len(raw) != FRAME_BYTES:
                continue
            peer = (addr[0], addr[1])
            with self._buf_lock:
                buf = self._buffers.get(peer)
                if buf is None:
                    if len(self._buffers) >= 8:     # 防御：别让陌生包吃掉内存
                        continue
                    buf = deque(maxlen=JITTER_FRAMES)
                    self._buffers[peer] = buf
                if not self.speaker_on:
                    continue                    # 静音期间不攒 buffer
                buf.append(raw)
                self._talking[peer] = time.time()
            # 真有人说话了才把播放设备拉起来（平时不占着别人的音乐）
            if self.speaker_on:
                self.ensure_output()

    # ---------------- 内部：混音播放 ----------------

    def _play_cb(self, outdata, frames, _time_info, _status) -> None:
        if not self.speaker_on or np is None:
            outdata[:] = 0
            return
        mixed = np.zeros(frames, dtype=np.int32)
        with self._buf_lock:
            for buf in list(self._buffers.values()):
                if not buf:
                    continue
                try:
                    chunk = np.frombuffer(buf.popleft(), dtype=np.int16)
                except ValueError:
                    continue
                if chunk.shape[0] != frames:        # 长度不对就丢掉这一帧
                    continue
                mixed += chunk.astype(np.int32)
        np.clip(mixed, -32768, 32767, out=mixed)
        outdata[:, 0] = mixed.astype(np.int16)

    # ---------------- 内部：提示 ----------------

    def _notify(self, text: str) -> None:
        if self.on_error is not None:
            try:
                self.on_error(text)
            except Exception:                       # noqa: BLE001
                pass


def mic_sample_once(seconds: float = 0.1) -> float:
    """自检用：录一小段，返回音量（0~1）；没库或非交互环境返回 -1。"""
    if not AUDIO_OK:
        return -1.0
    try:
        rec = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                     channels=CHANNELS, dtype="int16")
        sd.wait()
        data = rec.astype(np.float32) / 32768.0
        return float(np.sqrt(np.mean(data ** 2)))
    except Exception:                               # noqa: BLE001
        return -1.0


def list_devices() -> List[str]:
    """自检用：可用的输入输出设备名。"""
    if not AUDIO_OK:
        return []
    try:
        devs = sd.query_devices()
        return [f"{d['name']}（in{d['max_input_channels']}"
                f"/out{d['max_output_channels']}）" for d in devs]
    except Exception:                               # noqa: BLE001
        return []

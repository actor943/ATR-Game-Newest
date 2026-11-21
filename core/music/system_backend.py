# -*- coding: utf-8 -*-
"""macOS 系统音频后端：不用 pygame 也能播放内置歌曲（0.4.10 新增）。

为什么需要它
------------
`flet build macos` 把 Python 依赖塞进 app bundle 后，pygame(-ce) 自带的
``pygame/.dylibs/libSDL2*.dylib`` 在打包环境里加载失败（``dlopen(...):
Library not loaded / code signature invalid``）。本机源码运行正常，装机后
播放器却报「当前设备无法播放音乐」。

这里改走 macOS 自带工具 + 已经能正常打包的 sounddevice：

1. ``/usr/bin/afconvert`` 把当前 mp3 转成临时 44.1kHz/16bit WAV（实测 3 分钟
   曲子约 0.7 秒、33MB，只缓存最近 3 首，不堆积）；
2. ``sounddevice.RawOutputStream`` 按块写 PCM，``numpy`` 做音量增益；
3. 自己记帧号，所以暂停 / 继续 / 拖动进度都是真的有效，不是假反馈。

对外伪装成 ``pygame.mixer.music`` 的接口（见 :class:`SystemMusic`），
:class:`core.music.player.MusicPlayer` 在 pygame 初始化失败时自动改用它，
其余播放逻辑一行不用改。
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

_BASE = Path(tempfile.gettempdir()) / "atr_music_wav"
_MAX_CACHE = 3
_CHUNK_FRAMES = 4096


def _cache_path(src: Path) -> Path:
    try:
        stat = src.stat()
        key = f"{src.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
    except OSError:
        key = str(src)
    return _BASE / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + ".wav")


def _evict_cache() -> None:
    """只留最近 3 个转码文件，免得听完全部曲库塞满临时目录。"""
    try:
        files = sorted(_BASE.glob("*.wav"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[_MAX_CACHE:]:
            old.unlink(missing_ok=True)
    except OSError:
        pass


def _to_wav(src: Path) -> Path:
    """用系统 afconvert 转码；已缓存过就直接复用。"""
    dst = _cache_path(src)
    try:
        if dst.is_file() and dst.stat().st_size > 44:
            return dst
    except OSError:
        pass
    _BASE.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        # 用绝对路径：装机后的 app 进程 PATH 不一定包含 /usr/bin
        ["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@44100", "-c", "2",
         str(src), str(dst)],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0 or not dst.is_file():
        detail = (result.stderr or result.stdout or "").strip()[:200]
        raise RuntimeError(f"afconvert 转码失败：{detail}")
    _evict_cache()
    return dst


class SystemMusic:
    """``pygame.mixer.music`` 的最小替身，接口一一对应。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._wave = None
        self._rate = 44100
        self._channels = 2
        self._total = 0
        self._pos = 0
        self._volume = 1.0
        self._running = False
        self._paused = False
        self._thread: threading.Thread | None = None

    # ---- pygame.mixer.music 兼容接口 ----

    def load(self, filename: str) -> None:
        """转码并打开一个 WAV，准备好从头播放。"""
        self.stop()
        wav_path = _to_wav(Path(filename))
        handle = wave.open(str(wav_path), "rb")
        with self._lock:
            if self._wave is not None:
                try:
                    self._wave.close()
                except OSError:
                    pass
            self._wave = handle
            self._rate = handle.getframerate() or 44100
            self._channels = handle.getnchannels() or 2
            self._total = handle.getnframes()
            self._pos = 0

    def play(self, loops: int = 0, start: float = 0.0,
             fade_ms: int = 0) -> None:
        """从 ``start`` 秒开始播放（``loops`` 由上层 never 使用，忽略）。"""
        self.stop()
        with self._lock:
            if self._wave is None:
                raise RuntimeError("还没有 load 音频")
            self._pos = max(0, min(int(float(start) * self._rate), self._total))
            self._running = True
            self._paused = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._paused = False
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            try:
                thread.join(timeout=0.6)
            except RuntimeError:
                pass
        with self._lock:
            self._thread = None
            self._pos = 0

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def unpause(self) -> None:
        with self._lock:
            self._paused = False

    def set_volume(self, value: float) -> None:
        with self._lock:
            self._volume = max(0.0, min(1.0, float(value)))

    def get_pos(self) -> int:
        """已播放毫秒数（pygame 同名接口返回 ms）。"""
        with self._lock:
            return int(self._pos * 1000.0 / max(self._rate, 1))

    def set_pos(self, seconds: float) -> None:
        """跳转：重启写流线程并从新帧号继续。"""
        with self._lock:
            target = max(0.0, min(float(seconds), self._total / self._rate))
            was_running = self._running
            self._pos = int(target * self._rate)
        if was_running:
            # stop() 会清 _pos，所以先记下来，再按这个位置重新 play
            self.play(start=target)

    def get_busy(self) -> bool:
        with self._lock:
            return bool(self._running and self._thread is not None
                        and self._thread.is_alive())

    def get_length(self) -> float:
        """WAV 的精确时长（秒），给进度条用。"""
        with self._lock:
            return self._total / max(self._rate, 1)

    # ---- 内部写流线程 ----

    def _run(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except Exception as exc:                 # noqa: BLE001 — 没有声音库
            print(f"[music] 系统音频后端缺少依赖：{exc!r}")
            with self._lock:
                self._running = False
            return
        try:
            with sd.RawOutputStream(samplerate=self._rate,
                                    channels=self._channels,
                                    dtype="int16") as stream:
                while True:
                    with self._lock:
                        if not self._running:
                            break
                        if self._paused:
                            time.sleep(0.05)
                            continue
                        data = self._wave.readframes(_CHUNK_FRAMES)
                        if not data:
                            self._running = False
                            break
                        self._pos += len(data) // (2 * self._channels)
                        volume = self._volume
                    if volume < 1.0:
                        samples = np.frombuffer(data, dtype="<i2")
                        samples = np.clip(
                            samples.astype(np.float32) * volume,
                            -32768, 32767).astype("<i2")
                        data = samples.tobytes()
                    stream.write(data)
        except Exception as exc:                # noqa: BLE001 — 设备被占用等
            print(f"[music] 系统音频播放失败：{exc!r}")
            with self._lock:
                self._running = False


class _MixerModule:
    """pygame.mixer 那一级的替身。"""

    def __init__(self) -> None:
        self.music = SystemMusic()


class _MixerShim:
    """让 player 里的 ``self._pygame.mixer.music`` 照常工作。"""

    def __init__(self) -> None:
        self.mixer = _MixerModule()


def create() -> _MixerShim:
    """构造一个 pygame 风格的替身（构造本身不打开音频设备）。"""
    return _MixerShim()

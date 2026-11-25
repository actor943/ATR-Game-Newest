# -*- coding: utf-8 -*-
"""跨平台音频后端：基于官方 flet-audio 扩展（0.4.10 新增）。

``flet-audio`` 是 Flet 1.0 的官方扩展包，底层是 Flutter 的 audioplayers，
Windows / macOS / Linux / iOS / Android / Web 全支持。把它作为**首选后端**
后，手机端不再需要 pygame（Android 上没有 pygame 的 wheel），打包后的
macOS 也不再依赖会被 serious_python 弄坏的 SDL 动态库。

本模块把它伪装成 ``pygame.mixer.music`` 的接口，:class:`MusicPlayer` 的
播放逻辑不用改。flet-audio 的方法是协程，这里统一用 ``page.run_task``
派发；播放位置 / 时长 / 状态由事件回调写回 shim，UI 读到的是实时值。
"""

from __future__ import annotations

import time
from pathlib import Path

import flet as ft

from .library import SONGS_DIR_NAME


def _duration(ms: float) -> ft.Duration:
    return ft.Duration(milliseconds=max(0, int(ms)))


class _MixerProxy:
    """给 player 的 ``self._pygame.mixer.music`` 路径补一层。"""

    def __init__(self, music: "FletAudioMusic") -> None:
        self.music = music


class FletAudioMusic:
    """``pygame.mixer.music`` 风格的 flet-audio 替身。"""

    def __init__(self, page: ft.Page, audio, owner) -> None:
        self._page = page
        self._audio = audio
        self._owner = owner            # MusicPlayer，用来通知 UI 刷新
        self._position_ms = 0
        self._duration_ms = 0
        self._playing = False
        self._clock_started = 0.0
        self._clock_base_ms = 0
        self._src_ready = False
        self._pending_start_ms: int | None = None

    def _start_clock(self, position_ms: int) -> None:
        self._clock_base_ms = int(position_ms)
        self._clock_started = time.monotonic()

    @property
    def audio(self):
        """Page.services 里挂着的就是它，必须保持强引用。"""
        return self._audio

    @property
    def mixer(self) -> _MixerProxy:
        """兼容 ``player._pygame.mixer.music`` 的访问路径。"""
        return _MixerProxy(self)

    def _dispatch(self, method, *args) -> None:
        """把协程方法交给 Flet 的事件循环执行，不阻塞 UI 线程。"""
        async def _call():
            await method(*args)

        try:
            self._page.run_task(_call)
        except Exception as exc:        # noqa: BLE001 — 页面已关闭等
            print(f"[music] flet-audio 调用失败：{exc!r}")

    # ---- pygame.mixer.music 兼容接口 ----

    def _local_position_ms(self) -> int:
        """本地时钟估算的位置：Flutter 事件迟到时进度条也能走。"""
        if not self._playing:
            return self._position_ms
        return self._clock_base_ms + int(
            (time.monotonic() - self._clock_started) * 1000)

    def load(self, filename: str) -> None:
        """换歌：src 用相对 assets 根的路径，桌面 / 手机都认。"""
        self._position_ms = 0
        self._duration_ms = 0
        self._playing = False
        self._clock_started = 0.0
        self._pending_start_ms = None
        self._src_ready = False
        self._audio.src = f"{SONGS_DIR_NAME}/{Path(filename).name}"
        try:
            self._audio.update()
            # 必须先把 src 刷到 Flutter，再让 play 协程跑；否则 audioplayers
            # 可能拿到旧 src（空串），表现为「点了没声音、进度不动」。
            self._page.update()
        except RuntimeError:            # 页面还没真正 attach（如命令行自检）
            pass

    def play(self, loops: int = 0, start: float = 0.0,
             fade_ms: int = 0) -> None:
        self._position_ms = max(0, int(float(start) * 1000))
        self._playing = True
        self._start_clock(self._position_ms)
        if not self._src_ready:
            # Dart 侧 play() 不会自己 setSource，只 rely on update() 完成。
            # 此时直接 play 会拿到旧 source（甚至空 source），完全没声音。
            self._pending_start_ms = self._position_ms
            return
        self._dispatch(self._audio.play, _duration(self._position_ms))

    def pause(self) -> None:
        self._position_ms = self._local_position_ms()
        self._playing = False
        self._dispatch(self._audio.pause)

    def unpause(self) -> None:
        self._playing = True
        self._start_clock(self._position_ms)
        self._dispatch(self._audio.resume)

    def stop(self) -> None:
        self._playing = False
        self._position_ms = 0
        self._start_clock(0)
        self._dispatch(self._audio.release)

    def set_volume(self, value: float) -> None:
        self._audio.volume = max(0.0, min(1.0, float(value)))
        try:
            self._audio.update()
        except RuntimeError:            # 页面还没真正 attach（如命令行自检）
            pass

    def get_pos(self) -> int:
        return max(self._position_ms, self._local_position_ms())

    def set_pos(self, seconds: float) -> None:
        self._position_ms = max(0, int(float(seconds) * 1000))
        self._start_clock(self._position_ms)
        self._dispatch(self._audio.seek, _duration(self._position_ms))

    def get_busy(self) -> bool:
        return bool(self._playing)

    def get_length(self) -> float:
        return self._duration_ms / 1000.0 if self._duration_ms > 0 else 0.0

    # ---- flet-audio 事件 ----

    def on_loaded(self, _e=None) -> None:
        """Flutter 已 setSource 完毕：这时才能安全调用 play()。"""
        self._src_ready = True
        pending = self._pending_start_ms
        self._pending_start_ms = None
        if pending is not None:
            self._dispatch(self._audio.play, _duration(pending))
        self._owner.notify()

    def on_position(self, e) -> None:
        self._position_ms = max(0, int(getattr(e, "position", 0) or 0))
        self._owner.notify()

    def on_duration(self, e) -> None:
        duration = getattr(e, "duration", None)
        if duration is not None and hasattr(duration, "in_milliseconds"):
            self._duration_ms = max(0, int(duration.in_milliseconds))
        self._owner.notify()

    def on_state(self, e) -> None:
        from flet_audio.types import AudioState
        state = getattr(e, "state", None)
        if state == AudioState.PLAYING:
            if not self._playing:
                self._start_clock(self._local_position_ms())
            self._playing = True
        elif state in (AudioState.PAUSED, AudioState.COMPLETED,
                       AudioState.STOPPED, AudioState.DISPOSED):
            self._position_ms = self._local_position_ms()
            self._playing = False
            if state == AudioState.COMPLETED:
                self._position_ms = 0
                self._start_clock(0)
        self._owner.notify()


def create(page: ft.Page, owner) -> FletAudioMusic:
    """创建 Audio service 并返回 shim（调用方负责 ``page.services.append``）。"""
    import flet_audio as fta

    # 事件回调必须在构造 Audio 时就传进去：Flet 在构造时把事件处理器注册
    # 到控件上，构造完再赋值，Flutter 侧收不到订阅 —— 表现就是「歌在放但
    # 进度条永远 0」。用 holder 把稍后创建的 shim 间接接进来。
    holder: dict[str, FletAudioMusic] = {}

    def on_position(e):
        holder["shim"].on_position(e)

    def on_duration(e):
        holder["shim"].on_duration(e)

    def on_state(e):
        holder["shim"].on_state(e)

    def on_loaded(e):
        holder["shim"].on_loaded(e)

    # AudioService.init() 会立刻 update()，Dart 侧对空 src 直接抛
    # "Audio must have \"src\" specified."，服务初始化就废了 —— 之后
    # play() 全都无声。所以创建时必须给它一个真实存在的曲目地址。
    current = owner.current
    initial_src = (
        f"{SONGS_DIR_NAME}/{current.filename}" if current is not None
        else f"{SONGS_DIR_NAME}/.placeholder"
    )
    audio = fta.Audio(
        src=initial_src,
        autoplay=False,
        volume=max(0.0, min(1.0, float(owner.volume))),
        release_mode=fta.ReleaseMode.STOP,
        on_position_change=on_position,
        on_duration_change=on_duration,
        on_state_change=on_state,
        on_loaded=on_loaded,
    )
    shim = FletAudioMusic(page, audio, owner)
    holder["shim"] = shim
    return shim

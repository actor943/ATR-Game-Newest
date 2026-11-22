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

from pathlib import Path

import flet as ft

from .library import SONGS_DIR_NAME


def _duration(ms: float) -> ft.Duration:
    return ft.Duration(milliseconds=max(0, int(ms)))


class FletAudioMusic:
    """``pygame.mixer.music`` 风格的 flet-audio 替身。"""

    def __init__(self, page: ft.Page, audio, owner) -> None:
        self._page = page
        self._audio = audio
        self._owner = owner            # MusicPlayer，用来通知 UI 刷新
        self._position_ms = 0
        self._duration_ms = 0
        self._playing = False

    @property
    def audio(self):
        """Page.services 里挂着的就是它，必须保持强引用。"""
        return self._audio

    def _dispatch(self, method, *args) -> None:
        """把协程方法交给 Flet 的事件循环执行，不阻塞 UI 线程。"""
        async def _call():
            await method(*args)

        try:
            self._page.run_task(_call)
        except Exception as exc:        # noqa: BLE001 — 页面已关闭等
            print(f"[music] flet-audio 调用失败：{exc!r}")

    # ---- pygame.mixer.music 兼容接口 ----

    def load(self, filename: str) -> None:
        """换歌：src 用相对 assets 根的路径，桌面 / 手机都认。"""
        self._position_ms = 0
        self._duration_ms = 0
        self._playing = False
        self._audio.src = f"{SONGS_DIR_NAME}/{Path(filename).name}"
        try:
            self._audio.update()
        except RuntimeError:            # 页面还没真正 attach（如命令行自检）
            pass

    def play(self, loops: int = 0, start: float = 0.0,
             fade_ms: int = 0) -> None:
        self._position_ms = max(0, int(float(start) * 1000))
        self._playing = True
        self._dispatch(self._audio.play, _duration(self._position_ms))

    def pause(self) -> None:
        self._playing = False
        self._dispatch(self._audio.pause)

    def unpause(self) -> None:
        self._playing = True
        self._dispatch(self._audio.resume)

    def stop(self) -> None:
        self._playing = False
        self._position_ms = 0
        self._dispatch(self._audio.release)

    def set_volume(self, value: float) -> None:
        self._audio.volume = max(0.0, min(1.0, float(value)))
        try:
            self._audio.update()
        except RuntimeError:            # 页面还没真正 attach（如命令行自检）
            pass

    def get_pos(self) -> int:
        return self._position_ms

    def set_pos(self, seconds: float) -> None:
        self._position_ms = max(0, int(float(seconds) * 1000))
        self._dispatch(self._audio.seek, _duration(self._position_ms))

    def get_busy(self) -> bool:
        return bool(self._playing)

    def get_length(self) -> float:
        return self._duration_ms / 1000.0 if self._duration_ms > 0 else 0.0

    # ---- flet-audio 事件 ----

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
            self._playing = True
        elif state in (AudioState.PAUSED, AudioState.COMPLETED,
                       AudioState.STOPPED, AudioState.DISPOSED):
            self._playing = False
            if state == AudioState.COMPLETED:
                self._position_ms = 0
        self._owner.notify()


def create(page: ft.Page, owner) -> FletAudioMusic:
    """创建 Audio service 并返回 shim（调用方负责 ``page.services.append``）。"""
    import flet_audio as fta

    audio = fta.Audio(
        src="",
        autoplay=False,
        volume=max(0.0, min(1.0, float(owner.volume))),
        release_mode=fta.ReleaseMode.STOP,
    )
    shim = FletAudioMusic(page, audio, owner)
    audio.on_position_change = shim.on_position
    audio.on_duration_change = shim.on_duration
    audio.on_state_change = shim.on_state
    try:
        audio.update()
    except RuntimeError:                # 还没 add 到 page（自检桩）
        pass
    return shim

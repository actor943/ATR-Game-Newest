# -*- coding: utf-8 -*-
"""内置音乐播放器：播放控制、音量、曲库与状态通知（0.4.10 新增）。

为什么不用 ``ft.Audio``
-----------------------
本项目锁定的 flet 1.0.4 **没有** Audio / Video 控件（0.25 时代有，1.0 移除了），
所以音频在 Python 侧用 ``pygame.mixer`` 播放，Flet 侧只负责悬浮窗界面。
pygame 是可选依赖：没装或声卡打不开时全部操作安全降级，界面显示原因，
不会影响游戏本身。

本模块不依赖 flet；:class:`MusicPlayer` 通过 ``subscribe`` 把状态变化广播给
悬浮窗和设置页，UI 层再决定何时 ``page.update()``。
"""

from __future__ import annotations

import os
import time
from typing import Callable, Optional

from . import library
from .library import Track

Listener = Callable[[], None]


class MusicPlayer:
    """进程内唯一的音乐播放器（状态 + 控制）。"""

    def __init__(self) -> None:
        self._tracks: list[Track] = library.discover()
        self._index = 0
        self._volume = 0.65
        self._playing = False
        self._paused = False
        self._loop = False
        self._reason = ""
        self._backend_checked = False
        self._backend_ok = False
        self._seekable: Optional[bool] = None
        self._pygame = None
        self._started_at = 0.0
        self._listeners: set[Listener] = set()
        self._restore_preferences()

    # ---------- 曲目与状态 ----------

    def refresh_tracks(self) -> list[Track]:
        """重新扫描 assets/songs（用户往目录里加歌后可调）。"""
        self._tracks = library.discover()
        self._index = min(self._index, max(len(self._tracks) - 1, 0))
        if not self._tracks:
            self._playing = False
            self._paused = False
        self.notify()
        return list(self._tracks)

    @property
    def tracks(self) -> list[Track]:
        return list(self._tracks)

    @property
    def current(self) -> Optional[Track]:
        if not self._tracks:
            return None
        return self._tracks[self._index]

    @property
    def index(self) -> int:
        return self._index

    @property
    def playing(self) -> bool:
        """是否处于「已开始播放」（暂停时也返回 True）。"""
        return self._playing

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def loop(self) -> bool:
        return self._loop

    @property
    def available(self) -> bool:
        """音频后端是否可用（第一次真正播放时才会探测）。"""
        self._ensure_backend()
        return self._backend_ok

    @property
    def reason(self) -> str:
        """后端不可用的原因（展示在界面上）。"""
        self._ensure_backend()
        return self._reason

    def position(self) -> float:
        """当前播放位置（秒）。"""
        music = self._music()
        if music is None:
            return 0.0
        try:
            return max(0.0, music.get_pos() / 1000.0)
        except Exception:                   # noqa: BLE001
            return 0.0

    def duration(self) -> float:
        """当前曲目的近似时长（秒）。"""
        track = self.current
        return track.duration if track else 0.0

    @property
    def seekable(self) -> bool:
        """解码器是否支持拖动进度（首次尝试后确定，未知时按支持处理）。"""
        return self._seekable is not False

    # ---------- 状态订阅 ----------

    def subscribe(self, listener: Listener) -> None:
        """登记状态变化回调（幂等）。"""
        self._listeners.add(listener)

    def unsubscribe(self, listener: Listener) -> None:
        """移除状态变化回调。"""
        self._listeners.discard(listener)

    def notify(self) -> None:
        """把当前状态广播给所有订阅者；单个订阅者出错不影响其他。"""
        for listener in list(self._listeners):
            try:
                listener()
            except Exception as exc:        # noqa: BLE001
                print(f"[music] 状态订阅者出错：{exc!r}")

    # ---------- 播放控制 ----------

    def play(self, index: Optional[int] = None, start: float = 0.0) -> bool:
        """播放指定曲目（默认当前曲）；成功返回 True。"""
        if not self._tracks:
            self._reason = "assets/songs 里没有找到 mp3"
            self.notify()
            return False
        if index is not None:
            self._index = index % len(self._tracks)
        music = self._music()
        if music is None:
            self.notify()
            return False
        track = self.current
        assert track is not None
        try:
            music.load(str(track.path))
            music.set_volume(self._volume)
            music.play(start=max(0.0, float(start)))
            self._playing = True
            self._paused = False
            self._started_at = time.monotonic()
            self._reason = ""
            self.persist()
            self.notify()
            return True
        except Exception as exc:            # noqa: BLE001 — 坏文件 / 设备被占用
            self._reason = str(exc) or type(exc).__name__
            self._playing = False
            self._paused = False
            self.notify()
            return False

    def pause(self) -> None:
        """暂停（保留当前进度）。"""
        music = self._music()
        if self._playing and not self._paused and music is not None:
            try:
                music.pause()
            except Exception:               # noqa: BLE001
                pass
        if self._playing:
            self._paused = True
            self.notify()

    def resume(self) -> None:
        """从暂停处继续。"""
        music = self._music()
        if self._playing and self._paused and music is not None:
            try:
                music.unpause()
                self._paused = False
            except Exception as exc:        # noqa: BLE001
                self._reason = str(exc)
        self.notify()

    def toggle(self) -> bool:
        """播放 / 暂停 / 继续三合一。"""
        if self._playing:
            if self._paused:
                self.resume()
            else:
                self.pause()
        else:
            return self.play()
        return self._playing

    def stop(self) -> None:
        """停止播放（不清除当前曲目）。"""
        music = self._music()
        if music is not None:
            try:
                music.stop()
            except Exception:               # noqa: BLE001
                pass
        self._playing = False
        self._paused = False
        self.notify()

    def next(self) -> bool:
        """下一首；正在播放时直接切歌，否则只切换选中项。"""
        return self._step(1)

    def previous(self) -> bool:
        """上一首；播放开头 3 秒时先回到本曲开头（常见播放器习惯）。"""
        if self._playing and self.position() > 3.0:
            return self.seek(0.0)
        return self._step(-1)

    def _step(self, delta: int) -> bool:
        if not self._tracks:
            self.notify()
            return False
        index = (self._index + delta) % len(self._tracks)
        if self._playing:
            return self.play(index)
        self._index = index
        self.persist()
        self.notify()
        return True

    def select(self, index: int, *, autoplay: bool = False) -> bool:
        """选中曲目；``autoplay=True`` 时立即播放。"""
        if not self._tracks:
            return False
        index %= len(self._tracks)
        if self._playing:
            return self.play(index)
        self._index = index
        self.persist()
        self.notify()
        if autoplay:
            return self.play(index)
        return True

    def seek(self, seconds: float) -> bool:
        """跳到指定秒数。

        SDL_mixer 的 MP3 解码器在很多平台上**接受** ``set_pos`` 却不真正
        跳转（调用后 get_pos 仍在原处）。探测一次：真的动了才认为可拖动，
        否则记下「不支持」，界面把进度条改成只读，免得给用户假反馈。
        """
        music = self._music()
        if music is None or not self._playing or self._seekable is False:
            return False
        target_ms = max(0.0, float(seconds)) * 1000.0
        try:
            music.set_pos(target_ms / 1000.0)
        except Exception:                   # noqa: BLE001 — 部分解码器不支持
            try:
                music.play(start=target_ms / 1000.0)
            except Exception:               # noqa: BLE001
                self._seekable = False
                return False
        if target_ms < 500:
            return True
        time.sleep(0.12)                    # 给解码器一点时间真正定位
        try:
            after = music.get_pos()
        except Exception:                   # noqa: BLE001
            after = -1.0
        if after < target_ms * 0.5:
            self._seekable = False
            return False
        self._seekable = True
        return True

    def set_volume(self, value: float) -> None:
        """设置音量（0~1），会通知界面但不写盘（写盘交给 persist）。"""
        self._volume = max(0.0, min(1.0, float(value)))
        music = self._music()
        if music is not None:
            try:
                music.set_volume(self._volume)
            except Exception:               # noqa: BLE001
                pass
        self.notify()

    def set_loop(self, value: bool) -> None:
        """单曲循环开关。"""
        self._loop = bool(value)
        self.persist()
        self.notify()

    def tick(self) -> bool:
        """由 UI 定时器每 0.5 秒调一次：检测播完并自动下一首。

        Returns:
            是否发生了自动切歌（界面需要重新取曲名）。
        """
        if not self._playing or self._paused or not self._tracks:
            return False
        # 刚点下播放时解码器还没真正开始，别急着判「已结束」
        if time.monotonic() - self._started_at < 0.8:
            return False
        music = self._music()
        if music is None:
            return False
        try:
            if music.get_busy():
                return False
        except Exception:                   # noqa: BLE001
            return False
        if self._loop:
            self.play(self._index)
            return False
        self.next()
        return True

    # ---------- 后端与偏好 ----------

    def _ensure_backend(self) -> bool:
        """懒加载 pygame.mixer；失败时记录原因供界面提示。"""
        if self._backend_checked:
            return self._backend_ok
        self._backend_checked = True
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16,
                                  channels=2, buffer=1024)
            self._pygame = pygame
            self._backend_ok = True
            self._reason = ""
        except Exception as exc:            # noqa: BLE001 — 没装 / 无音频设备
            self._backend_ok = False
            self._reason = str(exc) or type(exc).__name__
        return self._backend_ok

    def _music(self):
        """拿到 pygame.mixer.music；后端不可用时返回 None。"""
        if not self._ensure_backend():
            return None
        return self._pygame.mixer.music

    def _restore_preferences(self) -> None:
        """从 settings.json 恢复上次音量 / 选中曲目。"""
        try:
            from core.settings import Settings
            settings = Settings.load()
            self._volume = max(0.0, min(1.0, float(settings.music_volume)))
            self._loop = bool(settings.music_loop)
            if self._tracks:
                names = {t.filename: i for i, t in enumerate(self._tracks)}
                self._index = names.get(settings.music_track, 0)
        except Exception:                   # noqa: BLE001 — 设置坏了也要能听歌
            pass

    def persist(self) -> None:
        """把音量 / 当前曲目 / 循环状态写回 settings.json（失败不影响播放）。"""
        try:
            from core.settings import Settings
            settings = Settings.load()
            settings.music_volume = self._volume
            settings.music_loop = self._loop
            settings.music_track = (
                self.current.filename if self.current else "")
            settings.save()
        except Exception:                   # noqa: BLE001
            pass


# 进程内单例：悬浮窗、设置页、主菜单共用同一份播放状态。
player = MusicPlayer()

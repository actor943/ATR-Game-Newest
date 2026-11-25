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
import platform
import random
import time
from enum import IntEnum
from typing import Callable, Optional

from . import library
from .library import Track

Listener = Callable[[], None]


class PlayMode(IntEnum):
    """循环按钮依次切换的三种模式。"""

    SEQUENCE = 0     # 播完按顺序下一首，播到末尾回到开头
    REPEAT_ONE = 1   # 单曲循环
    SHUFFLE = 2      # 随机循环：每首播完后随机挑一首（不重复当前曲）


class MusicPlayer:
    """进程内唯一的音乐播放器（状态 + 控制）。"""

    def __init__(self) -> None:
        self._tracks: list[Track] = library.discover()
        self._index = 0
        self._volume = 0.65
        self._playing = False
        self._paused = False
        self._mode = PlayMode.SEQUENCE
        self._history: list[int] = []
        self._reason = ""
        self._backend_checked = False
        self._backend_ok = False
        self._backend_name = ""
        self._page_attached = False
        self._attached_page = None
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
    def mode(self) -> PlayMode:
        return self._mode

    @property
    def loop(self) -> bool:
        """兼容旧接口：只有「单曲循环」算 loop。"""
        return self._mode == PlayMode.REPEAT_ONE

    @property
    def shuffle(self) -> bool:
        return self._mode == PlayMode.SHUFFLE

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

    @property
    def backend_name(self) -> str:
        """当前实际使用的后端：``pygame`` / ``system`` / ``""``。"""
        self._ensure_backend()
        return self._backend_name

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
        """当前曲目时长（秒）：系统后端用 WAV 精确值，否则用 mp3 估算。"""
        music = self._music()
        if music is not None and hasattr(music, "get_length"):
            try:
                exact = float(music.get_length())
                if exact > 0:
                    return exact
            except Exception:                 # noqa: BLE001
                pass
        track = self.current
        return track.duration if track else 0.0

    @property
    def seekable(self) -> bool:
        """解码器是否支持拖动进度（首次尝试后确定，未知时按支持处理）。"""
        return self._seekable is not False

    def attach_page(self, page) -> None:
        """优先挂上官方 flet-audio 服务（全平台，含 Android / iOS）。

        必须在 Flet 页面可用后调用（:func:`core.music.install` 会做）。
        失败也不致命：桌面端继续走 pygame / 系统音频兜底，手机端会在界面
        上显示原因。
        """
        if self._page_attached and self._attached_page is page:
            return
        self._page_attached = True
        self._attached_page = page
        try:
            from .flet_backend import create
            shim = create(page, self)
            services = page.services
            if shim.audio not in services:
                services.append(shim.audio)
            try:
                page.update()           # 让 Audio service 真正注册到 Flutter
            except Exception:           # noqa: BLE001 — 页面还没就绪
                pass
            self._pygame = shim
            self._backend_name = "flet"
            self._backend_ok = True
            self._backend_checked = True
            self._seekable = None
            self._reason = ""
            self.notify()
        except Exception as exc:            # noqa: BLE001 — 没装 flet-audio
            print(f"[music] flet-audio 不可用，改用本地后端：{exc!r}")

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

    def play(self, index: Optional[int] = None, start: float = 0.0,
             *, _retried: bool = False) -> bool:
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
        except Exception as exc:            # noqa: BLE001 — 坏文件 / dlopen 失败
            self._reason = str(exc) or type(exc).__name__
            # 有些打包环境里 pygame.mixer.init() 能过，真正 load 时才 dlopen
            # 失败。这时再兜一次系统音频后端，别让用户对着错误提示干瞪眼。
            if (not _retried and self._backend_name == "pygame"
                    and self._use_system_backend(self._reason)):
                return self.play(index, start, _retried=True)
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
        if self._mode == PlayMode.SHUFFLE:
            if delta < 0 and self._history:
                # 随机模式下「上一首」回到真正听过的上一首
                index = self._history.pop()
            else:
                if delta > 0:
                    self._history.append(self._index)
                    self._history = self._history[-len(self._tracks):]
                index = random.randrange(len(self._tracks))
                if len(self._tracks) > 1 and index == self._index:
                    index = (index + 1) % len(self._tracks)
        else:
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

    def set_mode(self, mode: PlayMode | int) -> None:
        """设置播放模式（0 顺序 / 1 单曲循环 / 2 随机循环）。"""
        self._mode = PlayMode(int(mode))
        self._history.clear()
        self.persist()
        self.notify()

    def cycle_mode(self) -> PlayMode:
        """点循环按钮：顺序 → 单曲循环 → 随机循环 → 顺序。"""
        self.set_mode((int(self._mode) + 1) % len(PlayMode))
        return self._mode

    def set_loop(self, value: bool) -> None:
        """兼容旧调用：True=单曲循环，False=顺序。"""
        self.set_mode(PlayMode.REPEAT_ONE if value else PlayMode.SEQUENCE)

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
        if self._mode == PlayMode.REPEAT_ONE:
            self.play(self._index)
            return False
        self.next()
        return True

    # ---------- 后端与偏好 ----------

    def _ensure_backend(self) -> bool:
        """懒加载音频后端：先试 pygame，macOS 失败再走系统音频。

        打包后的 macOS app 里 pygame(-ce) 自带的 ``libSDL2*.dylib`` 可能
        被 serious_python 搬进 bundle 后加载失败（dlopen 报错）。这时改用
        :mod:`core.music.system_backend`：afconvert + sounddevice 都是系统
        自带的 / 已确认能正常打包的依赖，播放控制接口完全兼容。
        """
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
            self._backend_name = "pygame"
            self._backend_ok = True
            self._reason = ""
            return True
        except Exception as exc:            # noqa: BLE001 — 没装 / dlopen 失败
            pygame_error = str(exc) or type(exc).__name__
        if self._use_system_backend():
            return True
        self._backend_ok = False
        self._reason = pygame_error
        return False

    def _use_system_backend(self, detail: str = "") -> bool:
        """切到 macOS 系统音频后端；不是 macOS 或切失败就返回 False。"""
        if platform.system() != "Darwin":
            return False
        try:
            from . import system_backend
            self._pygame = system_backend.create()
            self._backend_name = "system"
            self._backend_ok = True
            self._backend_checked = True
            self._seekable = None
            self._reason = detail
            return True
        except Exception:                   # noqa: BLE001
            return False

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
            self._mode = PlayMode(settings.music_mode)
            if self._tracks:
                names = {t.filename: i for i, t in enumerate(self._tracks)}
                self._index = names.get(settings.music_track, 0)
        except Exception:                   # noqa: BLE001 — 设置坏了也要能听歌
            pass

    def persist(self) -> None:
        """把音量 / 当前曲目 / 播放模式写回 settings.json（失败不影响播放）。"""
        try:
            from core.settings import Settings
            settings = Settings.load()
            settings.music_volume = self._volume
            settings.music_mode = int(self._mode)
            # 旧字段同步一下，方便旧版本 / 外部工具读取
            settings.music_loop = self._mode == PlayMode.REPEAT_ONE
            settings.music_track = (
                self.current.filename if self.current else "")
            settings.save()
        except Exception:                   # noqa: BLE001
            pass


# 进程内单例：悬浮窗、设置页、主菜单共用同一份播放状态。
player = MusicPlayer()

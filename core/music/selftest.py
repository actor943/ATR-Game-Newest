# -*- coding: utf-8 -*-
"""内置音乐播放器自检：曲库 / 时长 / 播放状态机 / 悬浮窗控件构建。

跑法：``python -m core.music.selftest``。不播放真实音频、不写用户设置。
"""

from __future__ import annotations

import builtins
import inspect
import platform

import flet as ft

from core import settings as settings_mod

from . import library
from .floating import FloatingPlayer
from .player import MusicPlayer


class _FakePage:
    """够 FloatingPlayer 构建用的 Page 桩（不起事件循环）。"""

    def __init__(self) -> None:
        self.controls: list[ft.Control] = []
        self.services: list[ft.Control] = []
        self._overlay: list[ft.Control] = []
        self.width = 1200.0
        self.height = 800.0
        self.tasks: list[object] = []

    @property
    def overlay(self) -> list[ft.Control]:
        # 和 flet 1.0 的 Page.overlay 一致：只读，只能原地 append/remove。
        # 这样「给 overlay 赋新列表」的写法会在自检里直接暴露出来。
        return self._overlay

    def update(self) -> None:
        pass

    def run_task(self, handler, *_args, **_kwargs):
        if not inspect.iscoroutinefunction(handler):
            raise TypeError("handler must be a coroutine function")
        task = object()
        self.tasks.append(task)
        return task


def _walk(control):
    """遍历一棵 Flet 控件树（内容 + 子控件列表）。"""
    yield control
    for attr in ("content", "controls"):
        value = getattr(control, attr, None)
        if isinstance(value, ft.Control):
            yield from _walk(value)
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, ft.Control):
                    yield from _walk(child)


def _no_write(self, path=None) -> None:
    """自检期间禁止把测试状态写进用户 settings.json。"""
    return None


def _case_library() -> None:
    directory = library.songs_dir()
    assert directory is not None and directory.is_dir(), "找不到 assets/songs"
    tracks = library.discover()
    assert len(tracks) == 23, f"歌曲数不对：{len(tracks)}"
    assert all(t.path.is_file() for t in tracks), "有歌曲路径指向不存在的文件"
    assert library.display_name("07 Liminal x Desert.mp3") == \
        "Liminal x Desert"
    assert library.display_name(
        "Marshmello - Alone (Official Music Video).mp3") == \
        "Marshmello - Alone"
    duration = library.mp3_duration(tracks[0].path)
    assert duration > 1.0, f"时长估算失败：{tracks[0].filename} → {duration}"


def _case_player() -> None:
    original = settings_mod.Settings.save
    settings_mod.Settings.save = _no_write        # type: ignore[method-assign]
    try:
        p = MusicPlayer()
        assert len(p.tracks) == 23
        assert p.current is not None and not p.playing

        assert p.next()
        first = p.index
        assert p.next() and p.index == (first + 1) % 23
        assert p.previous() and p.index == first

        p.set_volume(2.0)
        assert p.volume == 1.0
        p.set_volume(-3.0)
        assert p.volume == 0.0
        p.set_volume(0.4)
        assert abs(p.volume - 0.4) < 1e-9

        assert p.select(7)
        assert p.index == 7
        assert p.tick() is False, "没播放时 tick 不该自动切歌"
        assert isinstance(p.available, bool)
        if not p.available:
            assert p.reason, "后端不可用时必须给出原因"
    finally:
        settings_mod.Settings.save = original      # type: ignore[method-assign]


def _case_flet_backend() -> None:
    """全平台首选后端：flet-audio 服务挂进 page.services。"""
    page = _FakePage()
    p = MusicPlayer()
    p.attach_page(page)
    assert p.backend_name == "flet", f"后端没切到 flet-audio：{p.reason}"
    assert len(page.services) == 1, "Audio 服务必须挂进 page.services"
    audio = page.services[0]
    shim = p._pygame
    shim.load("On My Way.mp3")
    assert audio.src == "songs/On My Way.mp3", audio.src
    shim.set_volume(0.3)
    assert abs(audio.volume - 0.3) < 1e-9


def _case_system_backend() -> None:
    """模拟打包后 pygame 加载失败，验证自动回退到系统音频后端。"""
    if platform.system() != "Darwin":
        return
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pygame":
            raise ImportError("模拟打包环境的 dlopen 失败")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        p = MusicPlayer()
        assert p.available, f"系统音频回退失败：{p.reason}"
        assert p.backend_name == "system", p.backend_name
    finally:
        builtins.__import__ = real_import


def _case_overlay() -> None:
    page = _FakePage()
    p = MusicPlayer()
    overlay = FloatingPlayer(page, p, visible=True)
    overlay.attach()
    assert page.overlay and overlay.root in page.overlay
    assert overlay.handle in page.overlay
    assert len(page.tasks) == 1, "悬浮窗应启动一个心跳任务"
    assert overlay.compact.visible and not overlay.expanded_view.visible

    # flet 控件只能有一个父节点：迷你条 / 展开面板不得复用同一个实例，
    # 否则其中一边不会渲染 —— 这正是「点了音乐图标没反应」的成因之一。
    controls = list(_walk(overlay.root))
    assert len(controls) == len({id(c) for c in controls}), \
        "悬浮窗里有被两个父节点复用的控件"

    overlay.show(expanded=True)
    assert overlay.expanded and overlay.expanded_view.visible
    assert len(overlay.track_list.controls) == len(p.tracks)

    overlay.hide()
    assert not overlay.root.visible and overlay.handle.visible, \
        "收起后必须留下全游戏可用的音乐小入口"
    overlay._on_handle_click()
    assert overlay.root.visible and not overlay.handle.visible \
        and overlay.expanded, "点右上角音符应重新展开播放器"

    overlay.detach()
    assert overlay.root not in page.overlay
    assert overlay.handle not in page.overlay


def main() -> int:
    cases = [
        ("曲库扫描与时长", _case_library),
        ("播放状态机", _case_player),
        ("flet-audio 首选后端", _case_flet_backend),
        ("系统音频回退", _case_system_backend),
        ("悬浮窗控件", _case_overlay),
    ]
    failed = 0
    for label, case in cases:
        try:
            case()
        except Exception as exc:                   # noqa: BLE001
            failed += 1
            print(f"  [FAIL] {label}: {exc!r}")
        else:
            print(f"  [OK] {label}")
    print(f"音乐播放器自检：{len(cases) - failed}/{len(cases)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

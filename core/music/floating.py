# -*- coding: utf-8 -*-
"""悬浮音乐窗：跨页面常驻的迷你播放器（0.4.10 新增）。

控件挂在 ``page.overlay`` 而不是路由视图里 —— Router 换页时只清空
``page.controls``，overlay 不会被带走，所以玩小游戏 / 进房间时音乐窗仍在。
支持拖动、收起 / 展开、播放 / 暂停、上一首 / 下一首、进度、音量、循环与
曲库点歌；颜色与文案每次刷新都从 ``theme.T`` / ``i18n.t`` 重新取，主题或
语言切换后不用重建也能跟着变。
"""

from __future__ import annotations

import asyncio
from typing import Optional

import flet as ft

from core import responsive
from core.i18n import t
from core.theme import T

from .player import MusicPlayer, PlayMode


def _time(seconds: float) -> str:
    """秒 → m:ss（时长读不出来时显示 --:--）。"""
    if seconds <= 0:
        return "--:--"
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def _offset(value, *names: str) -> float:
    """兼容不同 flet 版本里 Offset 的字段名（x/y 或 dx/dy）。"""
    for name in names:
        if hasattr(value, name):
            try:
                return float(getattr(value, name))
            except (TypeError, ValueError):
                return 0.0
    return 0.0


class FloatingPlayer:
    """一个 Page 对应一个悬浮窗实例。"""

    COMPACT_W = 356
    EXPANDED_W = 396
    COMPACT_H = 68
    EXPANDED_H = 460

    def __init__(self, page: ft.Page, player: MusicPlayer,
                 *, visible: bool = True) -> None:
        self.page = page
        self.player = player
        self.visible = bool(visible)
        self.expanded = False
        self.x = 24.0
        self.y = 92.0
        self._dirty = False
        self._scrubbing = False
        self._task: Optional[asyncio.Task] = None
        self._rows: list[ft.Container] = []
        self._build()
        self.player.subscribe(self._on_player_change)
        responsive.subscribe(page, "music.overlay", self._on_resize)

    # ---------------- 构建 ----------------

    def _icon_btn(self, icon, handler, tip: str, *, size: int = 19) -> ft.IconButton:
        return ft.IconButton(
            icon=icon, icon_size=size, tooltip=tip,
            width=34, height=34, on_click=handler,
        )

    def _text_pair(self):
        """每个视图各要一套 Text —— 同一个控件不能挂两个父节点。"""
        return (
            ft.Text(size=12, weight=ft.FontWeight.BOLD, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS, expand=True),
            ft.Text(size=10, max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS, expand=True),
        )

    def _build(self) -> None:
        # 展开面板用的一套控件
        self.title, self.subtitle = self._text_pair()
        self.play_btn = self._icon_btn(ft.Icons.PLAY_ARROW,
                                       self._on_toggle_play, "")
        self.next_btn = self._icon_btn(ft.Icons.SKIP_NEXT,
                                       self._on_next, "")
        self.expand_btn = self._icon_btn(ft.Icons.EXPAND_MORE,
                                         self._on_expand, "")
        self.close_btn = self._icon_btn(ft.Icons.CLOSE,
                                        self._on_hide, "")

        # 迷你条另建一套：flet 控件是单父节点的，复用会让其中一边不渲染。
        self.c_title, self.c_subtitle = self._text_pair()
        self.c_play_btn = self._icon_btn(ft.Icons.PLAY_ARROW,
                                         self._on_toggle_play, "")
        self.c_next_btn = self._icon_btn(ft.Icons.SKIP_NEXT,
                                         self._on_next, "")
        self.c_expand_btn = self._icon_btn(ft.Icons.EXPAND_MORE,
                                           self._on_expand, "")

        # 迷你条：拖动区只包标题，按钮留给手势自己处理，避免拖窗误触
        compact_drag = ft.GestureDetector(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.MUSIC_NOTE, size=19),
                    ft.Container(width=8),
                    ft.Column([self.c_title, self.c_subtitle], spacing=1,
                              expand=True),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
            on_pan_start=self._on_pan_start,
            on_pan_update=self._on_pan_update,
            on_tap=self._on_expand,
        )
        self.compact = ft.Row(
            [
                compact_drag,
                self.c_play_btn,
                self.c_next_btn,
                self.c_expand_btn,
            ],
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # 展开面板
        header_drag = ft.GestureDetector(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.DRAG_INDICATOR, size=16),
                    ft.Container(width=4),
                    ft.Text(t("music.title"), size=13,
                            weight=ft.FontWeight.BOLD, expand=True),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
            on_pan_start=self._on_pan_start,
            on_pan_update=self._on_pan_update,
            on_tap=self._on_expand,
        )
        self.seek = ft.Slider(min=0, max=1, value=0, divisions=200,
                              on_change=self._on_seek_change,
                              on_change_start=self._on_seek_start,
                              on_change_end=self._on_seek_end)
        self.seek_label = ft.Text("--:-- / --:--", size=10)
        self.volume = ft.Slider(min=0, max=100, value=65, divisions=20,
                                on_change=self._on_volume_change,
                                on_change_end=self._on_volume_end)
        self.volume_btn = self._icon_btn(ft.Icons.VOLUME_UP,
                                         self._on_mute, "")
        self.prev_btn = self._icon_btn(ft.Icons.SKIP_PREVIOUS,
                                       self._on_prev, "")
        self.loop_btn = self._icon_btn(ft.Icons.REPEAT,
                                       self._on_loop, "")
        self.hint = ft.Text(size=10, max_lines=2,
                            overflow=ft.TextOverflow.ELLIPSIS)

        self.track_list = ft.Column([], scroll=ft.ScrollMode.AUTO, height=170)
        self._build_track_rows()

        self.expanded_view = ft.Column(
            [
                header_drag,
                ft.Container(height=4),
                ft.Row([self.title, self.expand_btn, self.close_btn],
                       spacing=0,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.subtitle,
                ft.Container(height=6),
                self.seek,
                self.seek_label,
                ft.Row(
                    [
                        self.prev_btn, self.play_btn, self.next_btn,
                        self.loop_btn, ft.Container(expand=True),
                        self.volume_btn, self.volume,
                    ],
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.hint,
                ft.Container(height=4),
                ft.Text(size=11, weight=ft.FontWeight.BOLD),
                self.track_list,
            ],
            spacing=2,
        )
        self._tracks_label = self.expanded_view.controls[-2]

        self.root = ft.Container(
            left=self.x, top=self.y,
            padding=ft.Padding.all(10),
            border_radius=12,
            content=ft.Column([self.compact, self.expanded_view],
                              spacing=0),
            visible=self.visible,
        )
        # 播放器被收起时留一个全局小入口：它同样挂在 page.overlay 上，
        # 所以在任何游戏页都能点开音乐，不用退回主菜单。
        self.handle = ft.Container(
            width=42, height=42,
            border_radius=21,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("🎵", size=19),
            ink=True,
            on_click=self._on_handle_click,
            visible=not self.visible,
        )
        self._refresh()

    def _build_track_rows(self) -> None:
        """曲库行只建一次，切歌时只改高亮，不重建整列控件。"""
        self._rows = []
        for index, track in enumerate(self.player.tracks):
            label = ft.Text(track.name, size=11, max_lines=1,
                            overflow=ft.TextOverflow.ELLIPSIS, expand=True)
            row = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.MUSIC_NOTE, size=13),
                        ft.Container(width=6),
                        label,
                        ft.Text(_time(track.duration), size=9),
                    ],
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                border_radius=6,
                ink=True,
                on_click=self._pick_track(index),
            )
            self._rows.append(row)
        self.track_list.controls = self._rows

    # ---------------- 公共接口 ----------------

    def attach(self) -> None:
        """把悬浮窗挂到 page.overlay 并启动状态定时器。

        ⚠ flet 1.0 的 ``Page.overlay`` 是**只读属性**（返回内部列表），
        必须用 ``append`` 原地修改。赋值一个新列表会抛 AttributeError，
        一旦被 except 吞掉，界面上就完全看不到悬浮窗 —— 表现正是「点音乐
        图标没反应」。这里不再整体赋值。
        """
        try:
            overlay = self.page.overlay
            for control in (self.root, self.handle):
                if control not in overlay:
                    overlay.append(control)
            self.page.update()
        except Exception as exc:            # noqa: BLE001 — 测试桩可能没 overlay
            print(f"[music] 悬浮窗挂载失败：{exc!r}")
        if self._task is None:
            self._task = self.page.run_task(self._tick)

    def detach(self) -> None:
        """从页面摘掉悬浮窗（应用退出 / 测试清理）。"""
        self.player.unsubscribe(self._on_player_change)
        responsive.unsubscribe(self.page, "music.overlay")
        if self._task is not None:
            try:
                self._task.cancel()
            except Exception:               # noqa: BLE001
                pass
            self._task = None
        try:
            overlay = self.page.overlay
            for control in (self.root, self.handle):
                if control in overlay:
                    overlay.remove(control)
            self.page.update()
        except Exception:                   # noqa: BLE001
            pass

    def show(self, *, expanded: bool = True) -> None:
        """显示悬浮窗（可选展开曲库）。"""
        self.visible = True
        if expanded:
            self.expanded = True
        self._dirty = True
        self._persist_visible()
        self._refresh()
        self._update()

    def hide(self) -> None:
        """隐藏悬浮窗（不停止播放）。"""
        self.visible = False
        self._persist_visible()
        self._refresh()
        self._update()

    def toggle(self) -> None:
        """显示 / 隐藏切换。"""
        if self.visible:
            self.hide()
        else:
            self.show()

    def set_visible(self, value: bool) -> None:
        if bool(value):
            self.show()
        else:
            self.hide()

    def refresh_now(self) -> None:
        """主题 / 语言切换后外部调用：下一帧重取颜色与文案。"""
        self._dirty = True

    # ---------------- 状态刷新 ----------------

    def _on_player_change(self) -> None:
        self._dirty = True
        self._refresh()
        self._update()

    def _on_resize(self, _w: float, _h: float) -> None:
        self._dirty = True
        self._clamp_position()

    async def _tick(self) -> None:
        """后台心跳：自动下一首 + 进度刷新（0.5 秒一次）。"""
        while True:
            try:
                self.player.tick()
                if self.visible and (self.player.playing or self._dirty):
                    self._clamp_position()
                    self._refresh()
                    self._update()
            except asyncio.CancelledError:
                raise
            except Exception as exc:        # noqa: BLE001 — 定时器绝不能死掉
                print(f"[music] 悬浮窗刷新失败：{exc!r}")
            await asyncio.sleep(0.5)

    def _refresh(self) -> None:
        player = self.player
        track = player.current
        title_value = track.name if track else t("music.no_track")
        subtitle_value = (
            t("music.track_of", count=len(player.tracks),
              filename=track.filename) if track else t("music.empty_hint")
        )
        for control in (self.title, self.c_title):
            control.value = title_value
        for control in (self.subtitle, self.c_subtitle):
            control.value = subtitle_value

        play_icon = (
            ft.Icons.PAUSE if player.playing and not player.paused
            else ft.Icons.PLAY_ARROW
        )
        expand_icon = (
            ft.Icons.EXPAND_LESS if self.expanded else ft.Icons.EXPAND_MORE
        )
        for button in (self.play_btn, self.c_play_btn):
            button.icon = play_icon
            button.disabled = not player.tracks
        for button in (self.next_btn, self.c_next_btn):
            button.disabled = not player.tracks
        for button in (self.expand_btn, self.c_expand_btn):
            button.icon = expand_icon
        self.prev_btn.disabled = not player.tracks
        self.loop_btn.icon = {
            PlayMode.SEQUENCE: ft.Icons.REPEAT,
            PlayMode.REPEAT_ONE: ft.Icons.REPEAT_ON,
            PlayMode.SHUFFLE: ft.Icons.SHUFFLE,
        }[player.mode]

        duration = player.duration()
        position = player.position()
        self.seek.max = max(duration, 1.0)
        if not self._scrubbing:
            self.seek.value = min(position, max(duration, 1.0))
        self.seek.disabled = duration <= 0 or not player.seekable
        self.seek_label.value = f"{_time(position)} / {_time(duration)}"

        percent = int(round(player.volume * 100))
        if not self._scrubbing:
            self.volume.value = percent
        self.volume_btn.icon = (
            ft.Icons.VOLUME_OFF if percent == 0 else ft.Icons.VOLUME_UP
        )
        self._tracks_label.value = t("music.library", count=len(player.tracks))

        if not player.available:
            hint = t("music.unavailable", reason=player.reason)
        elif player.playing and player.paused:
            hint = t("music.paused")
        elif duration > 0 and not player.seekable:
            hint = t("music.seek_unsupported")
        elif player.playing:
            hint = t("music.playing_hint")
        else:
            hint = t("music.drag_hint")
        if player.backend_name == "system":
            hint = t("music.system_backend") + " · " + hint
        self.hint.value = hint

        # 主题 / 语言变化后重新取色与文案（不重建控件树）
        self._apply_style()
        self._highlight_rows()
        self._dirty = False

    def _apply_style(self) -> None:
        self.root.bgcolor = T.SURFACE
        self.root.border = ft.Border.all(1, T.BORDER)
        for control in (self.title, self.c_title):
            control.color = T.TEXT_PRIMARY
        for control in (self.subtitle, self.c_subtitle):
            control.color = T.TEXT_SECONDARY
        self.seek_label.color = T.TEXT_MUTED
        self.hint.color = T.TEXT_MUTED
        self._tracks_label.color = T.TEXT_SECONDARY
        self.compact.visible = not self.expanded
        self.expanded_view.visible = self.expanded
        self.root.visible = self.visible
        self.root.width = min(self.EXPANDED_W if self.expanded
                              else self.COMPACT_W,
                              max(200, responsive.page_width(self.page) - 24))
        # 收起状态：右上角留一个音符按钮，任何页面（含全屏对局）都能点开
        self.handle.visible = not self.visible
        self.handle.bgcolor = T.SURFACE
        self.handle.border = ft.Border.all(1, T.PRIMARY)
        self.handle.left = max(0.0, responsive.page_width(self.page) - 58)
        self.handle.top = 16.0
        play_tip = t("music.play" if not (
            self.player.playing and not self.player.paused) else "music.pause")
        expand_tip = t("music.expand" if not self.expanded
                       else "music.collapse")
        for button in (self.play_btn, self.c_play_btn):
            button.tooltip = play_tip
        for button in (self.next_btn, self.c_next_btn):
            button.tooltip = t("music.next")
        for button in (self.expand_btn, self.c_expand_btn):
            button.tooltip = expand_tip
        self.prev_btn.tooltip = t("music.prev")
        self.loop_btn.tooltip = {
            PlayMode.SEQUENCE: t("music.mode_sequence"),
            PlayMode.REPEAT_ONE: t("music.mode_repeat"),
            PlayMode.SHUFFLE: t("music.mode_shuffle"),
        }[self.player.mode]
        self.close_btn.tooltip = t("music.hide")
        self.volume_btn.tooltip = t("music.volume")
        self._tracks_label.value = t("music.library",
                                     count=len(self.player.tracks))

    def _highlight_rows(self) -> None:
        for index, row in enumerate(self._rows):
            active = index == self.player.index
            row.bgcolor = T.SURFACE_ALT if active else None
            row.border = (ft.Border.all(1, T.PRIMARY) if active
                          else ft.Border.all(1, T.DIVIDER))

    def _clamp_position(self) -> None:
        width = float(self.root.width or self.COMPACT_W)
        height = self.EXPANDED_H if self.expanded else self.COMPACT_H
        pw, ph = responsive.size(self.page)
        self.x = min(max(0.0, self.x), max(0.0, pw - width - 8))
        self.y = min(max(0.0, self.y), max(0.0, ph - height - 8))
        self.root.left, self.root.top = self.x, self.y

    def _update(self) -> None:
        try:
            self.page.update()
        except Exception:                   # noqa: BLE001 — 测试桩没事件循环
            pass

    def _persist_visible(self) -> None:
        try:
            from core.settings import Settings
            settings = Settings.load()
            settings.music_visible = self.visible
            settings.save()
        except Exception:                   # noqa: BLE001
            pass

    # ---------------- 事件 ----------------

    def _on_toggle_play(self, _e=None) -> None:
        self.player.toggle()
        self._refresh()
        self._update()

    def _on_next(self, _e=None) -> None:
        self.player.next()

    def _on_prev(self, _e=None) -> None:
        self.player.previous()

    def _on_loop(self, _e=None) -> None:
        self.player.cycle_mode()

    def _on_mute(self, _e=None) -> None:
        if self.player.volume > 0:
            self._muted_volume = self.player.volume
            self.player.set_volume(0.0)
        else:
            self.player.set_volume(getattr(self, "_muted_volume", 0.6) or 0.6)
        self.player.persist()

    def _on_expand(self, _e=None) -> None:
        self.expanded = not self.expanded
        self._dirty = True
        self._refresh()
        self._clamp_position()
        self._update()

    def _on_hide(self, _e=None) -> None:
        self.hide()

    def _on_handle_click(self, _e=None) -> None:
        """点右上角音符：在任何游戏页都能重新展开播放器。"""
        self.show(expanded=True)

    def _on_seek_start(self, _e=None) -> None:
        self._scrubbing = True

    def _on_seek_change(self, e) -> None:
        self._scrubbing = True
        try:
            self.seek_label.value = (
                f"{_time(float(e.control.value))} / "
                f"{_time(self.player.duration())}")
            self._update()
        except (TypeError, ValueError):
            pass

    def _on_seek_end(self, e) -> None:
        self._scrubbing = False
        try:
            self.player.seek(float(e.control.value))
        except (TypeError, ValueError):
            pass
        self._refresh()
        self._update()

    def _on_volume_change(self, e) -> None:
        try:
            self.player.set_volume(float(e.control.value) / 100.0)
        except (TypeError, ValueError):
            pass

    def _on_volume_end(self, _e=None) -> None:
        self.player.persist()

    def _pick_track(self, index: int):
        """生成某一行的点击回调（闭包装行号）。"""
        def _handler(_e=None) -> None:
            self.player.select(index, autoplay=True)
            self._refresh()
            self._update()
        return _handler

    # ---------------- 拖动 ----------------

    def _on_pan_start(self, _e=None) -> None:
        self._clamp_position()

    def _on_pan_update(self, e) -> None:
        delta = getattr(e, "local_delta", None) or getattr(
            e, "global_delta", None)
        dx = _offset(delta, "x", "dx")
        dy = _offset(delta, "y", "dy")
        width = float(self.root.width or self.COMPACT_W)
        height = self.EXPANDED_H if self.expanded else self.COMPACT_H
        pw, ph = responsive.size(self.page)
        self.x = min(max(0.0, self.x + dx), max(0.0, pw - width - 8))
        self.y = min(max(0.0, self.y + dy), max(0.0, ph - height - 8))
        self.root.left, self.root.top = self.x, self.y
        self._update()

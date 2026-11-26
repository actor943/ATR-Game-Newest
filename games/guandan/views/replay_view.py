# -*- coding: utf-8 -*-
"""掼蛋对局回放：选一局 -> 逐帧复盘（四家手牌全部明着）。

回放页刻意复用实时对局的 :class:`~games.guandan.views.play_table.PlayTableMixin`
与 :func:`~games.guandan.views.play_table.build_table_screen`，所以看到的牌桌
和真打时完全一致；区别只在：

* 对手席位上的牌背换成真实手牌（明牌视角）；
* 底部操作按钮换成 上一帧 / 播放 / 下一帧 / 倍速 / 进度条；
* 手牌与事件区都按当前帧截断，不能改牌、不能出牌。

只有带 ``.replay.json`` 的对局会出现在列表里；旧版纯文字记录仍可在
「历史记录」里看全文，只是无法逐帧复盘。
"""

from __future__ import annotations

import asyncio
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import flet as ft

from core.registry import NavigateFn
from core.theme import T
from core.ui_common import app_bar
from games.guandan import config as cfgmod
from games.guandan import replay as replay_mod
from games.guandan.views.play_const import (
    FG,
    HAND_ROW_GAP,
    MUTED,
    NAMES,
    table_metrics,
)
from games.guandan.views.play_table import PlayTableMixin, build_table_screen

REPLAY_LIST_PATH = "/g/guandan/replay"
REPLAY_PLAY_PATH = "/g/guandan/replay/play"
_PENDING_PATH = ""


def _summary(path: Path, doc: Dict[str, Any]) -> str:
    """列表里的一行摘要：时间 + 状态 + 胜方 + 局数 + 帧数。"""
    meta = doc.get("meta") or {}
    parts = [meta.get("生成时间") or path.stem]
    for key in ("状态", "胜方"):
        value = meta.get(key, "")
        if value:
            parts.append(value)
    if meta.get("局数"):
        parts.append(f"{meta['局数']} 局")
    parts.append(f"{len(doc.get('frames') or [])} 帧")
    return " · ".join(parts)


class ReplayListPage:
    """回放选局页（有选中状态，所以用类）。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self.items: List[tuple[Path, Dict[str, Any]]] = []
        self.index = -1
        self.list_col = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO,
                                  height=260)
        self.detail_text = ft.Text(
            "", size=12, selectable=True, font_family="monospace",
            color=T.TEXT_PRIMARY)
        self.enter_btn = ft.Button(
            content=ft.Text("进入回放（明牌）"),
            bgcolor=T.PRIMARY, color=T.TEXT_INVERT,
            disabled=True, on_click=self._on_enter,
        )

    def build(self) -> ft.Control:
        self._reload()
        body = ft.Column(
            [
                ft.Text("选择一局已保存的对局进入回放；回放使用与对局相同的牌桌视角，"
                        "其他三家的手牌会全部摊开。",
                        size=13, color=T.TEXT_SECONDARY),
                ft.Text("旧版纯文字记录没有帧数据，不会出现在这里，请到「历史记录」查看。",
                        size=11, color=MUTED),
                ft.Container(height=10),
                ft.Container(
                    bgcolor=T.SURFACE,
                    border=ft.Border.all(1, T.BORDER),
                    border_radius=8,
                    padding=ft.Padding.all(8),
                    content=self.list_col,
                ),
                ft.Container(height=10),
                ft.Text("── 记录详情 ──", size=11, color=MUTED),
                ft.Container(height=4),
                ft.Container(
                    bgcolor=T.SURFACE,
                    border=ft.Border.all(1, T.BORDER),
                    border_radius=8,
                    padding=ft.Padding.all(10),
                    expand=True,
                    content=ft.Column([self.detail_text], spacing=0,
                                      expand=True, scroll=ft.ScrollMode.AUTO),
                ),
                ft.Container(height=10),
                ft.Row(
                    [self.enter_btn,
                     ft.Button(content=ft.Text("刷新列表"),
                               on_click=lambda _e: self._reload()),
                     ft.Button(content=ft.Text("返回掼蛋菜单"),
                               on_click=lambda _e: self.navigate("/g/guandan"))],
                    spacing=10, wrap=True,
                ),
            ],
            spacing=0, expand=True,
        )
        return ft.Column(
            [
                app_bar(
                    "对局回放 · 选择对局",
                    on_back=lambda _e: self.navigate("/g/guandan"),
                    actions=[
                        ft.TextButton(
                            content=ft.Row(
                                [ft.Icon(ft.Icons.REFRESH, size=16,
                                         color=T.TEXT_PRIMARY),
                                 ft.Text("刷新", size=12,
                                         color=T.TEXT_PRIMARY)],
                                spacing=4, tight=True,
                            ),
                            on_click=lambda _e: self._reload(),
                        ),
                    ],
                ),
                ft.Container(padding=ft.Padding.all(T.PADDING),
                             content=body, expand=True),
            ],
            expand=True,
        )

    def _reload(self) -> None:
        self.items = replay_mod.list_replays()
        self.index = -1
        self.list_col.controls = [
            self._item(i, path, doc)
            for i, (path, doc) in enumerate(self.items)
        ] or [ft.Text("还没有可回放的对局。先打一场，结束后会自动保存回放。",
                      size=12, color=MUTED)]
        if self.items:
            self._select(0)
        else:
            self.detail_text.value = (
                "没有找到回放文件。回放会在对局结束（或中途离开）时，"
                "与文字记录一起自动保存到应用数据目录。"
            )
            self.enter_btn.disabled = True
        self.page.update()

    def _item(self, i: int, path: Path, doc: Dict[str, Any]) -> ft.Control:
        selected = i == self.index
        return ft.Container(
            bgcolor=T.SURFACE_ALT if selected else T.SURFACE,
            border=ft.Border.all(2 if selected else 1,
                                 T.PRIMARY if selected else T.BORDER),
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            ink=True,
            on_click=lambda _e: self._select(i),
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.PLAY_CIRCLE, size=16,
                            color=T.PRIMARY if selected else T.TEXT_MUTED),
                    ft.Container(width=6),
                    ft.Text(_summary(path, doc), size=12,
                            color=T.TEXT_PRIMARY, expand=True),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
        )

    def _select(self, i: int) -> None:
        if not (0 <= i < len(self.items)):
            return
        self.index = i
        path, doc = self.items[i]
        meta = doc.get("meta") or {}
        controllers = list(doc.get("controllers") or [])
        lines = [f"文件：{path.name}"]
        lines += [f"{k}：{v}" for k, v in meta.items()]
        if controllers:
            lines.append("座位：" + "  ".join(
                f"{NAMES[p]}·{controllers[p]}" for p in range(min(4, len(controllers)))))
        lines.append(f"可回放帧数：{len(doc.get('frames') or [])}")
        lines.append("── 出牌摘录（前 12 行）──")
        lines += list(doc.get("logs") or [])[:12]
        self.detail_text.value = "\n".join(lines)
        self.enter_btn.disabled = False
        self.list_col.controls = [
            self._item(n, p, d) for n, (p, d) in enumerate(self.items)
        ]
        self.page.update()

    def _on_enter(self, _e) -> None:
        if 0 <= self.index < len(self.items):
            open_replay(self.navigate, str(self.items[self.index][0]))


class _Replay(PlayTableMixin):
    """一帧一帧看的牌桌：复用实时对局的全部渲染逻辑。"""

    def __init__(self, page: ft.Page, navigate: NavigateFn, path: str):
        self.page = page
        self.navigate = navigate
        self.doc = replay_mod.load_replay(Path(path)) if path else None
        self.replay_mode = True
        self.frames: List[Dict[str, Any]] = (
            list(self.doc.get("frames") or []) if self.doc else []
        )
        self.index = 0
        self.playing = False
        self.alive = True
        self.speed = 1.0

        self.m = table_metrics(page)
        seats = list(self.doc.get("seats") or []) if self.doc else []
        if len(seats) != 4:
            seats = ["human", "ai", "ai", "ai"]
        try:
            local_seat = int((self.doc or {}).get("local_seat", 0))
        except (TypeError, ValueError):
            local_seat = 0
        if not 0 <= local_seat < 4:
            local_seat = 0
        controllers = list(self.doc.get("controllers") or []) if self.doc else []
        if len(controllers) != 4:
            controllers = ["你", "电脑", "电脑", "电脑"]
        self.cfg = cfgmod.MatchConfig(
            seats=tuple(seats), local_seat=local_seat,
            preset="replay", local_nick=controllers[local_seat],
        )
        self.my_seat = local_seat
        self.controllers = controllers
        self.net = None
        self.spectator = False
        self.selected: set = set()
        self.gift_marks: set = set()
        self.last_plays: Dict[int, object] = {}

        self.match = None
        self.hand = None
        self.result = None
        self.seat_row = ft.Row()
        self.target_box = ft.Container()
        self.hand_box: Optional[ft.Container] = None  # build_table_screen 里赋值
        self.result_box = ft.Container()
        self.my_hand_col = ft.Column(
            spacing=HAND_ROW_GAP, scroll=ft.ScrollMode.AUTO,
            auto_scroll=False, expand=True,
        )
        self.score_text = ft.Text("", size=13, weight=ft.FontWeight.BOLD,
                                  color=T.TEXT_PRIMARY)
        self.level_note = ft.Text("", size=11, color=MUTED)
        self.net_text = ft.Text("回放模式 · 四家手牌全部明牌", size=11,
                                color=MUTED)
        self.turn_text = ft.Text("", size=12)
        self.events_text = ft.Text(
            value="", spans=[], selectable=True, font_family="monospace",
            size=12,
        )
        self.events_inner = ft.Column(
            [self.events_text], scroll=ft.ScrollMode.AUTO,
            auto_scroll=True, expand=True, spacing=0,
        )

        last = max(0, len(self.frames) - 1)
        self.prev_btn = ft.IconButton(
            icon=ft.Icons.SKIP_PREVIOUS, tooltip="上一帧",
            on_click=self._on_prev,
        )
        self.next_btn = ft.IconButton(
            icon=ft.Icons.SKIP_NEXT, tooltip="下一帧",
            on_click=self._on_next,
        )
        self.play_pause_btn = ft.Button(
            content=ft.Text("播放"), height=36,
            bgcolor=T.PRIMARY, color=T.TEXT_INVERT,
            on_click=self._on_play_pause,
        )
        # 项目锁 flet 1.0.4：下拉框用 dropdown.Option + on_select
        # （0.28 的 DropdownOption / on_change 在这里会直接抛异常，
        #  被 build_replay_play 兜住后看起来像「回放文件损坏」）
        self.speed_dd = ft.Dropdown(
            width=110, value="1",
            options=[
                ft.dropdown.Option("0.5", "0.5 倍速"),
                ft.dropdown.Option("1", "1 倍速"),
                ft.dropdown.Option("2", "2 倍速"),
            ],
            on_select=self._on_speed,
        )
        self.progress = ft.Slider(
            min=0, max=float(last), divisions=max(1, last), value=0,
            on_change=self._on_slider, expand=True,
        )
        self.frame_text = ft.Text("", size=11, color=MUTED)

        self._goto(0)

    # ---------- 回放页特有的小接口（牌桌 mixin 会用到） ----------
    def _controller(self, seat: int) -> str:
        return self.controllers[seat] if 0 <= seat < 4 else "电脑"

    def _is_local(self, seat: int) -> bool:
        return seat == self.cfg.local_seat

    def _is_auto(self, seat: int) -> bool:
        return seat != self.cfg.local_seat

    def _tribute_active(self) -> bool:
        return False

    def _toggle_card(self, _card) -> None:
        return

    def _on_after_hand(self, _e) -> None:
        return

    # ---------- 帧 ----------
    def _goto(self, index: int) -> None:
        last = max(0, len(self.frames) - 1)
        index = max(0, min(last, index))
        state = replay_mod.frame_state(self.doc, index)
        if state is None:
            return
        self.index = index
        self.match = state["match"]
        self.hand = state["hand"]
        self.result = state["result"]
        self.last_plays = state["plays"]
        self.frame_text.value = (
            f"第 {index + 1}/{len(self.frames)} 帧 · {state['label']}"
        )
        spans = []
        metas = state["log_meta"]
        for n, line in enumerate(state["logs"]):
            color, bold = metas[n] if n < len(metas) else (FG, False)
            spans.append(ft.TextSpan(
                line + "\n",
                style=ft.TextStyle(
                    color=color, size=12, font_family="monospace",
                    weight=(ft.FontWeight.BOLD if bold
                            else ft.FontWeight.NORMAL),
                ),
            ))
        self.events_text.spans = spans
        self._refresh()

    def _refresh(self) -> None:
        self._render_top()
        self._render_seats()
        self._render_target()
        self._render_my_hand()
        self._render_result()
        self._sync_controls()
        self.page.update()

    def _sync_controls(self) -> None:
        self.prev_btn.disabled = self.index <= 0
        self.next_btn.disabled = self.index >= len(self.frames) - 1
        self.play_pause_btn.content = ft.Text("暂停" if self.playing else "播放")
        self.progress.value = float(self.index)

    # ---------- 播放控制 ----------
    def _stop(self) -> None:
        self.playing = False

    def _on_prev(self, _e) -> None:
        self._stop()
        self._goto(self.index - 1)

    def _on_next(self, _e) -> None:
        self._stop()
        self._goto(self.index + 1)

    def _on_play_pause(self, _e) -> None:
        if self.playing:
            self._stop()
            self._sync_controls()
            self.page.update()
            return
        if self.index >= len(self.frames) - 1:
            self._goto(0)
        self.playing = True
        self._sync_controls()
        self.page.run_task(self._auto_play)

    def _on_speed(self, e) -> None:
        try:
            self.speed = float(e.control.value or 1)
        except (TypeError, ValueError):
            self.speed = 1.0

    def _on_slider(self, e) -> None:
        self._stop()
        try:
            index = int(round(float(e.control.value)))
        except (TypeError, ValueError):
            return
        self._goto(index)

    async def _auto_play(self) -> None:
        while self.alive and self.playing:
            await asyncio.sleep(0.9 / max(0.1, self.speed))
            if not self.alive or not self.playing:
                return
            if self.index >= len(self.frames) - 1:
                self.playing = False
                self._sync_controls()
                self.page.update()
                return
            self._goto(self.index + 1)

    # ---------- 页面 ----------
    def _on_back(self, _e) -> None:
        self._stop()
        self.alive = False
        open_replay_list(self.navigate)

    def build(self) -> ft.Control:
        playback = ft.Row(
            [
                self.prev_btn, self.play_pause_btn, self.next_btn,
                self.speed_dd, ft.Container(width=8), self.progress,
                self.frame_text,
            ],
            spacing=8, wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        view = build_table_screen(
            self, actions=playback, title="对局回放 · 明牌视角",
            on_back=self._on_back,
            app_actions=[
                ft.TextButton(
                    content=ft.Row(
                        [ft.Icon(ft.Icons.LIST, size=16,
                                 color=T.TEXT_PRIMARY),
                         ft.Text("选择对局", size=12,
                                 color=T.TEXT_PRIMARY)],
                        spacing=4, tight=True,
                    ),
                    on_click=self._on_back,
                ),
            ],
        )
        # build_table_screen 会重建 seat_panels，骨架好了再画一次当前帧
        self._refresh()
        return view


def _empty_page(page: ft.Page, navigate: NavigateFn, text: str) -> ft.Control:
    return ft.Column(
        [
            app_bar("对局回放", on_back=lambda _e: navigate(REPLAY_LIST_PATH)),
            ft.Container(
                padding=ft.Padding.all(T.PADDING),
                content=ft.Column(
                    [
                        ft.Text(text, size=14, color=T.TEXT_PRIMARY),
                        ft.Container(height=12),
                        ft.Button(content=ft.Text("选择对局"),
                                  on_click=lambda _e: navigate(REPLAY_LIST_PATH)),
                    ],
                    spacing=0,
                ),
            ),
        ],
        expand=True,
    )


def open_replay_list(navigate: NavigateFn) -> None:
    """跳到选局页（丢缓存，保证列表是最新的）。"""
    from core.router import Router

    if Router.current is not None:
        Router.current.invalidate(REPLAY_LIST_PATH)
    navigate(REPLAY_LIST_PATH)


def open_replay(navigate: NavigateFn, path: str) -> None:
    """选中一局后进入回放：路径经模块级暂存传给路由 builder。"""
    from core.router import Router

    global _PENDING_PATH
    _PENDING_PATH = str(path)
    if Router.current is not None:
        Router.current.invalidate(REPLAY_PLAY_PATH)
    navigate(REPLAY_PLAY_PATH)


def build_replay(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """路由 builder：回放选局页。"""
    return ReplayListPage(page, navigate).build()


def build_replay_play(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """路由 builder：回放牌桌页。"""
    global _PENDING_PATH
    path = _PENDING_PATH
    if not path:
        items = replay_mod.list_replays()
        path = str(items[0][0]) if items else ""
    if not path:
        return _empty_page(page, navigate,
                           "暂无可回放的对局。普通对局结束后会自动保存回放。")
    try:
        return _Replay(page, navigate, path).build()
    except Exception as exc:                           # noqa: BLE001
        traceback.print_exc()
        return _empty_page(
            page, navigate,
            f"这局回放打不开：{type(exc).__name__}。"
            f"文件一般没坏，详情见运行日志；也可以换一局试试。",
        )

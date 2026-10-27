# -*- coding: utf-8 -*-
"""房间大厅：席位、语音、聊天都在这一屏（联机的大厅）。

一屏三件事
----------
1. **席位**：房间里几个位子一目了然。空位点一下就坐过去（换座同理）；
   有人说话时他的头像边框会亮起来 —— 这是语音的即时反馈。
2. **语音**：麦克风 / 扬声器开关 + 麦克风电平条。采集到的每一帧 20ms 音频
   直接 UDP 单点发给房间里其他人，没有服务器中转（见 ``core/net/voice.py``）。
3. **聊天**：打字也行 —— 房主负责把消息转发给所有人，保证大家看到的顺序一致。

房主点「开始」会广播一声开始，然后所有人一起进到具体游戏的房间里。

刷新机制
--------
网络线程只往队列里丢事件，这里用一个 asyncio 循环每 0.25 秒抽一次队列、
顺手刷新席位与电平条 —— **不在网络线程里碰任何控件**，避免多线程把界面搞崩。

界面风格
--------
所有零件走 :mod:`core.ui_theme`：默认材料风 / 暗黑2 石砖风 / 以后的社区包，
设置页切换后这一屏跟着换皮。
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import flet as ft

from core import ui_theme as ui
from core.i18n import t
from core.net import session as _sess
from core.net.session import RoomSession
from core.net.voice import AUDIO_OK
from core import registry
from core.registry import NavigateFn, game_players
from core.router import Router

POLL = 0.25                 # 界面刷新间隔（电平条需要一点点流畅度）
MAX_CHAT = 200              # 聊天记录最多留多少条

# 房间里「开始」把大家送去哪儿：每个已接好的游戏在这里登记它的对局路由。
# 0.4.7-fix2：直接进牌桌，不再走中间的「房间设置」页（那页已取消）。
GAME_ROOM_ROUTE = {
    "guandan": "/g/guandan/play",
    "chess": "/g/chess/play",
}

# 一个房间同一时刻只允许一个轮询协程在跑（key = id(会话)）。
# 房间视图会被路由器缓存复用；从对局页退回房间时 build() 不再执行，
# 旧实例的轮询若还活着，新旧两个轮询就会抢同一个事件队列 ——
# 谁抢到「开始」谁就跳转，可见的那个房间就收不到响应。
_POLL_OWNER: dict = {}


def _enter_game_route(navigate: NavigateFn, route: str) -> None:
    """进对局页前先丢掉路由缓存。

    0.4.8-fix：开始游戏后有人停在旧对局 / 各玩各的，根因之一就是牌桌视图被
    路由器缓存复用——上一局（甚至上一款游戏）的实例连网回调都没换。象棋早就
    这么处理了，现在**所有游戏一视同仁**：每次进对局都重建视图，重新判断
    本地 / 联网并接管网络回调。
    """
    if Router.current is not None:
        Router.current.invalidate(route)
    navigate(route)


class _Lobby:
    def __init__(self, page: ft.Page, navigate: NavigateFn):
        self.page = page
        self.navigate = navigate
        self.session: Optional[RoomSession] = _sess.current()
        self.chat_lines: List[ft.Control] = []
        self.mic_on = False
        self.speaker_on = True
        self._polling = False
        self._voice_row: Optional[ft.Row] = None

        self.seat_row = ft.Row(wrap=True, spacing=10, run_spacing=10)
        self.chat_col = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO,
                                  auto_scroll=True, expand=True)
        self.input_ref = ft.Ref[ft.TextField]()
        self.tip = ui.hint("")
        self.head_info = ui.hint("")
        self.level = ft.Container(content=ui.level_bar(0.0))
        self.game_panel = ui.panel(ft.Column([ui.hint("")], spacing=0))

    # ================================================================
    # 构建
    # ================================================================

    def build(self) -> ft.Control:
        session = self.session
        if session is None:                     # 兜底：没房间就别硬待在这儿
            return ui.page(
                t("room.title"),
                ui.panel(ft.Column([
                    ui.text(t("room.empty"), 14, ""),
                    ft.Container(height=10),
                    ui.button(t("room.back_mp"), "🧭",
                              lambda _e: self.navigate("/multiplayer")),
                ], spacing=0)),
                on_back=lambda _e: self.navigate("/multiplayer"),
            )

        if not self._polling:
            self._polling = True
            # 认领这个房间的轮询权（旧的房间视图若还在跑，让它自己收摊）
            _POLL_OWNER[id(session)] = self
            self.page.run_task(self._poll)

        body = ft.Column(
            [
                self._head(session),
                ft.Container(height=12),
                self._game_selector_area(session),
                ft.Container(height=12),
                self._seats_area(session),
                ft.Container(height=12),
                self._voice_area(session),
                ft.Container(height=12),
                self._chat_area(session),
                ft.Container(height=10),
                self.tip,
            ],
            spacing=0, scroll=ft.ScrollMode.AUTO, expand=True,
        )
        self.system(t("room.entered", name=session.info.name,
                      game=session.info.game_title))
        self._render_seats()
        return ui.page(t("room.title"), body, on_back=self._on_leave)

    # ---------------- 各区块 ----------------

    def _head(self, session: RoomSession) -> ft.Control:
        self.head_info.value = t("room.head_info", host=session.info.host,
                                 game=session.info.game_title,
                                 addr=f"{session.info.ip}:"
                                      f"{session.info.port}")
        return ui.panel(
            ft.Column(
                [
                    # 注意：wrap=True 的 Row 里**不能**放 expand 占位 ——
                    # flet 会把剩余空间当成独立一行撑成一块灰色巨墙
                    # （0.4.7「没有底的诡异窗口」的另一半原因）。
                    # 想左右分开就用 SPACE_BETWEEN。
                    ft.Row(
                        [
                            ui.text(session.info.name or t("room.room"), 17,
                                    "gold", ft.FontWeight.BOLD),
                            ui.pill(t("room.code",
                                      code=session.code or "——")),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        wrap=True,
                    ),
                    ft.Container(height=6),
                    self.head_info,
                    ft.Container(height=4),
                    ui.hint(t("room.head_hint")),
                ],
                spacing=0,
            )
        )

    def _seats_area(self, session: RoomSession) -> ft.Control:
        return ui.panel(
            ft.Column(
                [
                    ui.text(t("room.seats"), 13, "gold", ft.FontWeight.BOLD),
                    ft.Container(height=10),
                    self.seat_row,
                    ft.Container(height=8),
                    ui.hint(t("room.seats_hint")),
                ],
                spacing=0,
            )
        )

    # ---------------- 选游戏（房主可在房间内切换） ----------------

    def _game_selector_area(self, session: RoomSession) -> ft.Control:
        players = game_players(session.info.game_id)
        note = (t("room.players_note_extra", n=players)
                if session.info.seats > players
                else t("room.players_note", n=players))
        if session.is_host:
            chips = [
                ui.chip(it.label, active=(it.id == session.info.game_id),
                        on_click=(lambda _e, gid=it.id,
                                  gt=it.label: self._set_room_game(gid, gt)))
                for it in registry.menu_items() if it.available
            ]
            inner = ft.Column(
                [
                    ui.text(t("room.select_game"), 13, "gold",
                            ft.FontWeight.BOLD),
                    ft.Container(height=6),
                    ft.Row(chips, wrap=True, spacing=6,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(height=6),
                    ui.hint(note),
                ],
                spacing=0,
            )
        else:
            inner = ft.Column(
                [
                    ui.text(t("room.current_game"), 13, "gold",
                            ft.FontWeight.BOLD),
                    ft.Container(height=6),
                    ui.text(session.info.game_title, 15, "", ft.FontWeight.BOLD),
                    ft.Container(height=6),
                    ui.hint(note),
                ],
                spacing=0,
            )
        self.game_panel.content = inner
        return self.game_panel

    def _set_room_game(self, game_id: str, game_title: str) -> None:
        if self.session is None or not self.session.is_host:
            return
        self.session.set_game(game_id, game_title)
        self.system(t("room.game_changed", game=game_title))
        # 重画选游戏区（让 chip 高亮跟上）与席位区（观战席数量变了）
        self._game_selector_area(self.session)
        self._render_seats()
        self.head_info.value = t(
            "room.head_info", host=self.session.info.host,
            game=self.session.info.game_title,
            addr=f"{self.session.info.ip}:{self.session.info.port}")
        self.page.update()

    def _voice_area(self, session: RoomSession) -> ft.Control:
        tip_text = t("room.voice_tip") if AUDIO_OK else t("room.voice_unavailable")
        if not AUDIO_OK and session.voice.reason:
            # 把真实原因带上（模块缺失 / PortAudio 加载失败 / 设备打不开）：
            # 0.4.8 实测「分发版没有语音库」就是靠这一行区分出来的 ——
            # 只有笼统文案时，打包漏依赖和本机缺 PortAudio 看起来一模一样。
            tip_text = f"{tip_text}（{session.voice.reason}）"
        self._voice_row = ft.Row(
            [
                ui.button(t("room.mic_on"), "🎤", self._toggle_mic, height=40),
                ft.Container(width=10),
                ui.button(t("room.speaker_off"), "🔊", self._toggle_speaker,
                          height=40),
                ft.Container(width=14),
                ft.Column([ui.text(t("room.level"), 10, "dim"), self.level],
                          spacing=2),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True,
        )
        return ui.panel(
            ft.Column(
                [
                    ui.text(t("room.voice"), 13, "gold", ft.FontWeight.BOLD),
                    ft.Container(height=10),
                    self._voice_row,
                    ft.Container(height=8),
                    ui.hint(tip_text),
                ],
                spacing=0,
            )
        )

    def _chat_area(self, session: RoomSession) -> ft.Control:
        return ui.panel(
            ft.Column(
                [
                    ui.text(t("room.chat"), 13, "gold", ft.FontWeight.BOLD),
                    ft.Container(height=8),
                    ui.scroll_box(self.chat_col, height=180),
                    ft.Container(height=8),
                    # 输入行 + 按钮行分开：wrap 的 Row 里放 expand 输入框
                    # 会被撑成一块灰墙（见 _head 的注释）
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.TextField(
                                    ref=self.input_ref,
                                    hint_text=t("room.chat_placeholder"),
                                    border=ft.InputBorder.OUTLINE, text_size=14,
                                    color=ui.colors().text,
                                    bgcolor=ui.colors().ink,
                                    on_submit=self._send,
                                    hint_style=ft.TextStyle(
                                        color=ui.colors().text_muted,
                                        size=13),
                                ),
                                border=ft.Border.all(1, ui.colors().border),
                                border_radius=8, expand=True,
                                padding=ft.Padding.symmetric(horizontal=8),
                            ),
                            ft.Container(width=8),
                            ui.button(t("room.send"), "✉", self._send,
                                      height=44),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=8),
                    ft.Row(
                        [
                            ui.button(t("room.start") if session.is_host
                                      else t("room.wait_start"),
                                      "⚔", self._begin,
                                      primary=session.is_host,
                                      enabled=session.is_host, height=44),
                        ],
                    ),
                ],
                spacing=0,
            )
        )

    # ================================================================
    # 动作
    # ================================================================

    def _toggle_mic(self, _e=None) -> None:
        if self.session is None:
            return
        self.mic_on = not self.mic_on
        ok = self.session.set_mic(self.mic_on)
        self.tip.value = ("" if ok else t("room.mic_error"))
        self.tip.color = ui.tone("danger")
        self.system(t("room.mic_enabled") if self.mic_on
                    else t("room.mic_disabled"))
        self._render_voice_buttons()
        self.page.update()

    def _toggle_speaker(self, _e=None) -> None:
        if self.session is None:
            return
        self.speaker_on = not self.speaker_on
        self.session.set_speaker(self.speaker_on)
        self.system(t("room.speaker_enabled") if self.speaker_on
                    else t("room.speaker_muted"))
        self._render_voice_buttons()
        self.page.update()

    def _send(self, _e=None) -> None:
        if self.session is None or self.input_ref.current is None:
            return
        text = (self.input_ref.current.value or "").strip()
        if not text:
            return
        self.input_ref.current.value = ""
        self.session.send_chat(text)
        self._append_chat(self.session.me.nick, text, own=True)
        self.page.update()

    def _begin(self, _e=None) -> None:
        session = self.session
        if session is None or not session.is_host:
            return
        session.begin_game()
        route = GAME_ROOM_ROUTE.get(session.info.game_id)
        if route:
            # 对局页构建失败不能让这个点击处理抛出去：手机上未捕获异常
            # 会直接变成 "Error running app" 红屏，整个应用都得重开。
            try:
                _enter_game_route(self.navigate, route)
            except Exception as exc:              # noqa: BLE001
                print(f"[room] 进入对局失败：{exc!r}")
                self.tip.value = t("room.game_failed")
                self.tip.color = ui.tone("danger")
                self.page.update()
        else:
            self.tip.value = t("room.game_not_ready",
                               game=session.info.game_title)
            self.tip.color = ui.tone("danger")
            self.page.update()

    def _take_seat(self, seat: int):
        def _handler(_e=None):
            if self.session is not None:
                self.session.take_seat(seat)
        return _handler

    def _on_leave(self, _e=None) -> None:
        """离开房间：广播一声 bye，停掉语音与所有线程。"""
        self.system(t("room.leave"))
        if self.session is not None:
            _POLL_OWNER.pop(id(self.session), None)
        _sess.leave_current()
        self.session = None
        self._polling = False
        self.navigate("/multiplayer")

    # ================================================================
    # 渲染
    # ================================================================

    def _render_seats(self) -> None:
        session = self.session
        if session is None:
            return
        members = session.roster()
        by_seat = {m.seat: m for m in members if m.seat >= 0}
        players = game_players(session.info.game_id)
        cells: List[ft.Control] = []
        for i in range(session.info.seats):
            spectator = i >= players          # 超出游戏人数的席位是观战席
            member = by_seat.get(i)
            if member is None:
                label = (t("room.empty_seat", n=i + 1)
                         + (t("room.spectator") if spectator else ""))
                cells.append(ui.slot(label, on_click=self._take_seat(i)))
                continue
            peer = (member.ip, member.voice_port)
            talking = bool(member.voice_port) and session.voice.is_talking(peer)
            suffix = t("room.spectator") if spectator else ""
            cells.append(ui.taken_slot(
                member.nick + suffix, host=member.host, talking=talking,
                muted=not member.mic_on))
        # 还没坐下的人（席位满了 / 刚进来）一律算观战
        for member in members:
            if member.seat >= 0:
                continue
            cells.append(ui.taken_slot(member.nick + t("room.spectator_paren"),
                                       host=member.host, muted=True))
        self.seat_row.controls = cells

    def _render_voice_buttons(self) -> None:
        """把麦克风 / 扬声器按钮换成当前状态对应的文案。"""
        if self.session is None or self._voice_row is None:
            return
        self._voice_row.controls = [
            ui.button(t("room.mic_off") if self.mic_on else t("room.mic_on"),
                      "🎤" if self.mic_on else "🔇",
                      self._toggle_mic, height=40),
            ft.Container(width=10),
            ui.button(t("room.speaker_on") if not self.speaker_on
                      else t("room.speaker_off"),
                      "🔊" if self.speaker_on else "🔈",
                      self._toggle_speaker, height=40),
            ft.Container(width=14),
            ft.Column([ui.text(t("room.level"), 10, "dim"), self.level],
                      spacing=2),
        ]

    def system(self, text: str) -> None:
        self._append(None, text)

    def _append_chat(self, nick: str, text: str, own: bool = False) -> None:
        self._append({"nick": nick, "text": text}, None, own)

    def _append(self, item, system_text: Optional[str] = None,
                own: bool = False) -> None:
        if system_text is not None:
            self.chat_lines.append(ui.chat_row("", system_text, system=True))
        elif item is not None:
            self.chat_lines.append(ui.chat_row(item["nick"], item["text"],
                                               own=own))
        if len(self.chat_lines) > MAX_CHAT:
            del self.chat_lines[:len(self.chat_lines) - MAX_CHAT]
        self.chat_col.controls = self.chat_lines

    # ================================================================
    # 轮询：把网络事件搬到界面上
    # ================================================================

    async def _poll(self) -> None:
        dead_updates = 0
        while True:
            session = self.session
            # 房间被换掉 / 已经离开，旧协程自动收摊（别拽着上一个房间不放）
            if (session is None or not self._polling
                    or session is not _sess.current()):
                self._release_poll(session)
                return
            # 同一个房间同一时刻只允许一个轮询在跑：房间视图会被路由器缓存
            # 复用，新旧实例若都活着就会互相抢事件（「开始」被旧实例吃掉，
            # 可见的那个房间就收不到响应）。
            if _POLL_OWNER.get(id(session)) is not self:
                return
            try:
                for kind, payload in session.drain():
                    if kind == "chat":
                        if not payload.get("own"):   # 自己发的已经本地加过了
                            self._append_chat(payload.get("nick", "?"),
                                              payload.get("text", ""))
                    elif kind == "system":
                        self.system(str(payload))
                    elif kind == "start":
                        self.system(t("room.start_broadcast"))
                        route = GAME_ROOM_ROUTE.get(str(payload.get("game", "")))
                        if route and not session.is_host:
                            # 同上：每次重建视图以接管网络回调。
                            # 对局页建不起来时不能把轮询带走（否则这端从此
                            # 收不到任何房间事件）：提示一句，继续等。
                            try:
                                _enter_game_route(self.navigate, route)
                                # 关键：**这里不能 return**。以前一跳进对局页
                                # 轮询协程就结束了，等玩家从对局页退回房间，
                                # 房间视图是缓存复用的、build() 不会再跑，
                                # 于是这端再也没有轮询 —— 房主第二次点开始，
                                # 访客就再也收不到「开始」的响应（症状之二）。
                                # 继续轮询：事件照收，界面刷新只在房间页可见时做。
                            except Exception as exc:      # noqa: BLE001
                                print(f"[room] 进入对局失败：{exc!r}")
                                self.tip.value = t("room.game_failed")
                                self.tip.color = ui.tone("danger")
                    elif kind == "kicked":
                        self.system(t("room.kicked"))
                        self._polling = False
                        _POLL_OWNER.pop(id(session), None)
                        _sess.leave_current()
                        self.navigate("/multiplayer")
                        return
                    elif kind == "voice_error":
                        self.tip.value = str(payload)
                        self.tip.color = ui.tone("danger")
                # 只有房间页当前可见时才刷新界面：对局页盖住时去刷新
                # page 会把整页重绘，既浪费又会打断对局页的渲染。
                if self._room_visible():
                    self._render_seats()
                    if self.level.content is not None and session.voice.running:
                        self.level.content = ui.level_bar(session.voice.level)
                    self.page.update()
                dead_updates = 0
            except Exception as exc:             # noqa: BLE001
                # 席位表 / 渲染 / 刷新任何一环出错，都不能带走整个轮询
                # （轮询一死，这端从此收不到任何房间事件，对局也就废了）；
                # 打印后继续下一轮，连续出错太多次才收摊。
                print(f"[room] 刷新出错，继续轮询：{exc!r}")
                dead_updates += 1
                if dead_updates >= 20:
                    return
            await asyncio.sleep(POLL)

    def _room_visible(self) -> bool:
        """房间页是不是当前显示的那一页（对局页盖住时返回 False）。"""
        r = Router.current
        return r is not None and r.current_path() == "/room"

    def _release_poll(self, session) -> None:
        """交还轮询权（房间没了 / 换人了，别让旧条目一直占着位置）。"""
        if session is not None and _POLL_OWNER.get(id(session)) is self:
            _POLL_OWNER.pop(id(session), None)


def build(page: ft.Page, navigate: NavigateFn) -> ft.Control:
    """路由入口：一间房间一屏，进来时从全局会话里取当前房间。"""
    # 回到房间时，摘掉任何残留的玩法网络回调（避免旧的对局实例继续收消息）
    s = _sess.current()
    if s is not None:
        s.set_game_handler(None)
    return _Lobby(page, navigate).build()
